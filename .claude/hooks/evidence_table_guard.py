# -*- coding: utf-8 -*-
"""PostToolUse (Write|Edit|MultiEdit): エビデンス照合表の機械検証。

THE DEFECT THIS EXISTS FOR (2026-09-15)
---------------------------------------
動画・記事の主張に「代表的なメタ分析／RCT」を当てて信頼度・効果量を表にする
作業で、次の5つが同じターンの中で実際に起きた:

  1. 無い論文を挙げる      Haber 1979 の DOI を記憶で書き、解決すると Bowlby の
                           論文だった（10.1017/S0140525X00064955）。
                           JEBO 2024 の DOI は Crossref で 404 だった。
  2. 別の論文に付け替える  同じ著者・同じ年の別論文（PMID 22023565 と 22023566）
  3. 原著に無い数値を書く  d=0.26 を記憶で書きかけた（要旨には small としか無い）
  4. 主張を静かに落とす    主張表に載せた C-番号がエビデンス表に無い
  5. 語彙の逃げ            信頼度に「やや高い」等の自由記述を書いて判定を曖昧にする

いずれも「もっともらしく具体的」なので目視レビューを通過する。識別子の実在・
著者・年・数値は API で機械照合できるので、書いた瞬間に照合する。

WHAT IS MECHANICAL, WHAT IS NOT
-------------------------------
機械で判定できるのは「表に書かれた識別子が実在し、著者・年・数値が原著要旨と
一致し、語彙が定義内で、主張が全数カバーされているか」まで。
「論文の見逃し」「選択の適切さ」「反映の妥当性」は判断であり、ここでは判定しない。
それらは REVIEW として stderr に列挙し、独立した攻撃的検証（別コンテキストの
サブエージェント）へ差し戻す。閾値を下げて PASS にはしない（analysis-qa-checklist
SKILL.md「判定できないものは REVIEW にする」）。

CHECKS (per evidence row)
-------------------------
  R1 identifier   PubMed URL / doi.org URL / PMID: / DOI: のいずれかが必要。
                  「該当なし」「検証対象外」を含む行のみ免除。
  R2 resolves     PubMed esummary / Crossref works で解決できること。      FAIL
  R3 author       行に書いた第一著者姓が解決結果の著者に含まれること。     FAIL
  R4 year         行に書いた年と解決結果の出版年が ±1 年以内。             FAIL
  R5 vocabulary   信頼度 ∈ {高,中,低}、効果量 ∈ {大,中,小,ほぼゼロ,不明,不適用}
                  （「小〜中」のような範囲は可）。                            FAIL
  R6 numbers      行中の数値（N=, k件, d=, r=, %, CI）が原著要旨に存在する。
                  要旨が取得できない／数値が無い → REVIEW。
                  行に「本文値」と明記してあれば REVIEW に緩和。          FAIL/REVIEW
  R7 design       行が「メタ分析」を名乗るのに PubMed PublicationType にも
                  タイトルにも meta-analy が無い。                         REVIEW
  R8 coverage     主張表（ヘッダに「主張」を含む表）の C-番号がすべて
                  エビデンス表に現れること。                                FAIL

SCOPE: 書き込まれた .md に「信頼度」と「効果量」を両方ヘッダに持つ表がある場合のみ。
       パスは問わない（全リポ配布しても、表が無ければ何もしない）。

NETWORK: PubMed E-utilities と Crossref。識別子ごとに1回、結果は
       ~/.claude/state/evidence_table_guard/cache.json に永続キャッシュ。
       ネットワーク不通で解決できない識別子は「未確認」＝ FAIL（cite_gate と同じ
       思想: 合格記録が無いものは通さない）。内部例外は FAIL-OPEN。

CALIBRATION (実測 2026-09-15): 本物の表（decks/CREATOR_BRAIN_40S_20260915-v2.md、
       主張18行・エビデンス18行・識別子15件）で走らせ、FAIL 0 / REVIEW の内訳を
       docstring 末尾に記録。欠陥版フィクスチャ（Bowlby DOI・404 DOI・要旨に無い
       d=0.26・主張の欠落）で FAIL することを tests/test_evidence_table_guard.py
       が確認する。直した版で PASS しても何も証明しない（CLAUDE.md 絶対ルール 8）。

⚠ WIRING: `python hook.py || python3 hook.py || exit 0` は exit 2 を 0 に変える。
       deploy_all.py が生成する `P=$(command -v python3 || command -v python) ||
       exit 0; exec "$P" .claude/hooks/evidence_table_guard.py` を使うこと。

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_fired
except Exception:
    def _record_fired(name, ev):
        return False

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "evidence_table_guard")
CACHE = os.path.join(STATE_DIR, "cache.json")
UA = {"User-Agent": "evidence_table_guard/1.0 (mailto:kazuya.murayama.21@gmail.com)"}
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

CONF_VOCAB = {"高", "中", "低"}
EFFECT_VOCAB = {"大", "中", "小", "ほぼゼロ", "不明", "不適用"}
EXEMPT_RE = re.compile(r"該当なし|検証対象外|に同じ")
PMID_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)|\bPMID\s*[:：]?\s*(\d{6,9})", re.I)
DOI_RE = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s\)\]\|>]+)|\bDOI\s*[:：]\s*(10\.\d{4,9}/[^\s\)\]\|>]+)", re.I)
CLAIM_ID_RE = re.compile(r"^\s*(C\d+'?)\s*$")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# 第一著者姓 + 年 の並び（「Zell 2020」「von der Embse 2018」「Bangert-Drowns 2004」）
AUTHOR_YEAR_RE = re.compile(r"([A-Z][A-Za-z'\-]+(?:\s+(?:von|van|de|der|den|la|le)\s+[A-Z][A-Za-z'\-]+)?"
                            r"|(?:von|van|de)\s+(?:der\s+)?[A-Z][A-Za-z'\-]+)\s+((?:19|20)\d{2})")
# 行内の「原著に存在すべき数値」。年・タイムスタンプ・C番号は除外する。
NUM_RE = re.compile(r"(?<![\d.:\[])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\.\d+|\d+)(?![\d:\]])")


# ----------------------------------------------------------------- utilities
def _read_text(path):
    try:
        raw = io.open(path, "rb").read()
    except Exception:
        return ""
    for enc in ("utf-8-sig", "utf-8", "cp932", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def _load_cache():
    try:
        return json.load(io.open(CACHE, encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = CACHE + ".tmp"
        io.open(tmp, "w", encoding="utf-8").write(json.dumps(c, ensure_ascii=False))
        os.replace(tmp, CACHE)
    except Exception:
        pass


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")


# ----------------------------------------------------------------- parsing
def _tables(text):
    """Markdown 表を [(header_cells, [row_cells,...])] で返す。"""
    out, cur = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cur.append(line)
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    parsed = []
    for blk in out:
        rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in blk]
        if len(rows) < 2:
            continue
        header = rows[0]
        body = [r for r in rows[2:] if any(x for x in r)] if re.match(r"^\s*\|?\s*:?-", blk[1]) else rows[1:]
        parsed.append((header, body))
    return parsed


def find_tables(text):
    """(claims_table, evidence_table)。無ければ None。"""
    claims = evidence = None
    for header, body in _tables(text):
        h = "".join(header)
        if "信頼度" in h and "効果量" in h and evidence is None:
            evidence = (header, body)
        elif "主張" in h and header and header[0].strip() == "#" and claims is None:
            claims = (header, body)
    return claims, evidence


def _col(header, key):
    for i, h in enumerate(header):
        if key in h:
            return i
    return None


def extract_ids(cell_text):
    ids = []
    for m in PMID_RE.finditer(cell_text):
        ids.append(("pmid", m.group(1) or m.group(2)))
    for m in DOI_RE.finditer(cell_text):
        d = (m.group(1) or m.group(2)).rstrip(".,;")
        ids.append(("doi", d))
    return ids


# ----------------------------------------------------------------- resolvers
def resolve_pmids(pmids, cache):
    need = [p for p in pmids if "pmid:" + p not in cache]
    if need:
        try:
            j = json.loads(_get(EUTILS + "esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(need)))
            res = j.get("result", {})
            for p in need:
                x = res.get(p)
                if not x or "error" in x:
                    cache["pmid:" + p] = {"ok": False}
                    continue
                cache["pmid:" + p] = {
                    "ok": True,
                    "title": x.get("title", ""),
                    "year": (x.get("pubdate", "") or "")[:4],
                    "authors": [a.get("name", "") for a in x.get("authors", [])],
                    "pubtype": x.get("pubtype", []),
                    "journal": x.get("source", ""),
                }
        except Exception as e:
            for p in need:
                cache.setdefault("pmid:" + p, {"ok": None, "err": str(e)[:80]})
        # abstracts (batched)
        try:
            t = _get(EUTILS + "efetch.fcgi?db=pubmed&rettype=abstract&retmode=text&id=" + ",".join(need), 60)
            for rec in re.split(r"\n(?=\d+\. )", t):
                m = re.search(r"PMID: (\d+)", rec)
                if m and "pmid:" + m.group(1) in cache:
                    cache["pmid:" + m.group(1)]["abstract"] = " ".join(rec.split())
        except Exception:
            pass


def resolve_doi(doi, cache):
    k = "doi:" + doi.lower()
    if k in cache:
        return
    try:
        m = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))["message"]
        cache[k] = {
            "ok": True,
            "title": " ".join(m.get("title", [])),
            "year": str((m.get("issued", {}).get("date-parts", [[None]])[0][0]) or ""),
            "authors": [(a.get("family", "") + " " + a.get("given", "")).strip() for a in m.get("author", [])],
            "pubtype": [m.get("type", "")],
            "journal": (m.get("container-title") or [""])[0],
            "abstract": " ".join(re.sub(r"<[^>]+>", "", m.get("abstract", "")).split()),
        }
    except urllib.error.HTTPError as e:
        cache[k] = {"ok": False, "err": "HTTP %s" % e.code}
    except Exception as e:
        cache[k] = {"ok": None, "err": str(e)[:80]}


# ----------------------------------------------------------------- analysis
def _norm_num(s):
    s = s.replace(",", "")
    if s.startswith("."):
        s = "0" + s
    return s


def _row_numbers(text):
    """行中の検証対象数値。

    除外するもの（実測 2026-09-15、selftest 4/8 → 8/8 に直した原因）:
      - URL・PMID・DOI に含まれる数字（識別子は R2 で別途検証する）
      - 年（19xx/20xx）。`\\b` は数字と CJK の間で境界にならず「2019年」が
        素通りしたので lookaround で書く
      - タイムスタンプ [HH:MM:SS]・C番号・「95% CI」
      - 年代・年齢・順序の助数詞（20代／50歳／3番目／2点）。要旨には "30s" や
        "age 50" と書かれ、数字だけの一致にならない
    残るのは N=・k研究・d/r/OR・%・か国・名 など、要旨に**そのまま**現れるべき値。
    """
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"\b(?:PMID|PMC|DOI)\s*[:：]?\s*[\w./()\-]+", " ", t, flags=re.I)
    t = re.sub(r"\b10\.\d{4,9}/\S+", " ", t)
    t = re.sub(r"\[\d\d:\d\d:\d\d\]", " ", t)
    t = re.sub(r"(?<![A-Za-z])C\d+'?(?!\d)", " ", t)
    t = re.sub(r"(?<!\d)(19|20)\d{2}(?!\d)", " ", t)
    t = re.sub(r"95\s*[%％]\s*CI", " ", t)
    t = re.sub(r"\d+\s*[〜~～\-–]\s*\d+\s*(代|歳|年)", " ", t)
    t = re.sub(r"\d+\s*(代|歳|年|か月|ヶ月|番目|位|点|つ|回|巡|周|本|章|節|時間|分|秒)(?![\d])", " ", t)
    nums = set()
    for m in NUM_RE.finditer(t):
        v = _norm_num(m.group(1))
        if v in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"):
            continue           # 単独の一桁・10 は列挙語（2本・3件）が多く検証キーにならない
        nums.add(v)
    return nums


def _abstract_has(num, abstract):
    a = abstract.replace(",", "")
    cands = {num}
    if re.fullmatch(r"0\.\d+", num):
        cands.add(num[1:])                      # .78
    if re.fullmatch(r"\d+\.\d+", num):
        cands.add(num.rstrip("0").rstrip("."))  # 0.780 -> 0.78
    return any(re.search(r"(?<![\d.])" + re.escape(c) + r"(?![\d])", a) for c in cands)


def analyze(text, cache, resolver_pm=resolve_pmids, resolver_doi=resolve_doi):
    """戻り値: (fails, reviews, stats)。"""
    fails, reviews = [], []
    claims, evidence = find_tables(text)
    if evidence is None:
        return fails, reviews, {"scope": False}
    header, body = evidence
    i_id = 0
    i_conf, i_eff = _col(header, "信頼度"), _col(header, "効果量")

    # 全識別子を先に集めて一括解決
    all_pm, all_doi = [], []
    for row in body:
        for kind, v in extract_ids(" ".join(row)):
            (all_pm if kind == "pmid" else all_doi).append(v)
    if all_pm:
        resolver_pm(sorted(set(all_pm)), cache)
    for d in sorted(set(all_doi)):
        resolver_doi(d, cache)

    seen_ids = set()
    for row in body:
        if len(row) <= max(i_conf or 0, i_eff or 0):
            continue
        cid = row[i_id].strip("* ")
        seen_ids.add(cid)
        rowtext = " | ".join(row)
        exempt = bool(EXEMPT_RE.search(rowtext))
        ids = extract_ids(rowtext)
        if not ids:
            if not exempt:
                fails.append("%s R1 識別子なし（PubMed/DOI の URL か PMID/DOI を書く。免除は「該当なし」「検証対象外」明記時のみ）" % cid)
            continue
        # R5 vocabulary（免除行以外）
        if not exempt:
            conf = row[i_conf].strip("* ") if i_conf is not None else ""
            eff = row[i_eff].strip("* ") if i_eff is not None else ""
            if conf not in CONF_VOCAB:
                fails.append("%s R5 信頼度が語彙外: 「%s」（高/中/低 のみ）" % (cid, conf))
            eff_parts = [p for p in re.split(r"[〜~～]", re.sub(r"（.*?）|\(.*?\)", "", eff)) if p]
            if not eff_parts or any(p not in EFFECT_VOCAB for p in eff_parts):
                fails.append("%s R5 効果量が語彙外: 「%s」（大/中/小/ほぼゼロ/不明/不適用）" % (cid, eff))
        # R2: 行内の全識別子が解決できること（代表＝URL 列＝行末の識別子）。
        # 実測 2026-09-15: 補助論文の PMID を要点セルに書くと ids[0] が補助論文になり、
        # 代表論文の著者・年と突き合わせて 9 件の偽 FAIL を出した。代表は行末で取る。
        kind, v = ids[-1]
        rec = cache.get(("pmid:" + v) if kind == "pmid" else ("doi:" + v.lower()), {})
        unresolved = False
        for kind2, v2 in ids:
            r2 = cache.get(("pmid:" + v2) if kind2 == "pmid" else ("doi:" + v2.lower()), {})
            if r2.get("ok") is False:
                fails.append("%s R2 無い論文: %s %s は解決できない（%s）" % (cid, kind2.upper(), v2, r2.get("err", "not found")))
                unresolved = True
            elif r2.get("ok") is None:
                fails.append("%s R2 未確認: %s %s をネットワーク不通で解決できず（未確認は通さない）" % (cid, kind2.upper(), v2))
                unresolved = True
        if unresolved:
            continue
        resolved = [cache.get(("pmid:" + v2) if k2 == "pmid" else ("doi:" + v2.lower()), {}) for k2, v2 in ids]
        # R3/R4: 行に書かれた **すべての** 「Surname YYYY」が、行内のいずれかの
        # 解決結果（著者に姓を含み、年が ±1）に対応すること。対応の無い言及は
        # 「名前だけ書いて識別子を付けていない論文」＝照合不能なので FAIL。
        pairs = AUTHOR_YEAR_RE.findall(rowtext)
        if not pairs:
            reviews.append("%s R3 著者・年の表記が「Surname YYYY」形式でなく機械照合できない" % cid)
        for full, ystr in pairs:
            surname = full.split()[-1].lower()
            yr = int(ystr)
            def _match(r):
                auth = " ".join(r.get("authors", [])).lower()
                try:
                    ry = int(r.get("year") or 0)
                except Exception:
                    ry = 0
                return surname in auth and ry and abs(ry - yr) <= 1
            if not any(_match(r) for r in resolved):
                near = [r for r in resolved if surname in " ".join(r.get("authors", [])).lower()]
                if near:
                    fails.append("%s R4 年不一致: 「%s %d」に対し実際の出版年は %s 『%s』" %
                                 (cid, full, yr, near[0].get("year"), near[0].get("title", "")[:60]))
                else:
                    fails.append("%s R3 別論文または識別子なし: 「%s %d」に対応する PMID/DOI が行内に無い（行内の実タイトル: %s）" %
                                 (cid, full, yr, " / ".join(r.get("title", "")[:40] for r in resolved)))
        # 行内で識別された全論文（代表＋補助）の解決結果。行が複数論文の数値を
        # 引くのは正当だが、その論文も識別子付きで行に書かれていなければならない。
        # 「Mata 2011（29比較）」と名前だけ書いた数値は照合先が無い＝FAIL になる。
        row_recs = []
        for kind2, v2 in ids:
            r2 = cache.get(("pmid:" + v2) if kind2 == "pmid" else ("doi:" + v2.lower()), {})
            if r2.get("ok"):
                row_recs.append(r2)
        # R6 numbers
        nums = _row_numbers(rowtext)
        abstracts = [r.get("abstract", "") or "" for r in row_recs]
        if nums:
            if not any(abstracts):
                reviews.append("%s R6 要旨が取得できず数値 %s を照合できない" % (cid, sorted(nums)))
            else:
                missing = sorted(n for n in nums if not any(_abstract_has(n, a) for a in abstracts if a))
                if missing:
                    msg = "%s R6 原著要旨に無い数値: %s（要旨に無い数値は書かない。本文から取ったなら「本文値」と明記。別論文の値なら、その論文の PMID/DOI を同じ行に書く）" % (cid, missing)
                    (reviews if "本文値" in rowtext else fails).append(msg)
        # R7 design label: 行内のどれか1本が meta-analysis なら整合とみなす
        if "メタ分析" in rowtext or "メタアナリシス" in rowtext:
            def _is_meta(r):
                pt = " ".join(r.get("pubtype", [])).lower() + " " + r.get("title", "").lower()
                return any(k in pt for k in ("meta-analy", "metaanaly", "metasynth", "quantitative review"))
            if not any(_is_meta(r) for r in row_recs):
                reviews.append("%s R7 「メタ分析」と記載だが行内のどの論文も PublicationType/タイトルに meta-analysis が無い『%s』" %
                               (cid, rec.get("title", "")[:70]))

    # R8 coverage
    if claims is not None:
        chead, cbody = claims
        claim_ids = [r[0].strip("* ") for r in cbody if r and CLAIM_ID_RE.match(r[0].strip("* "))]
        base_seen = {s.rstrip("'") for s in seen_ids}
        for c in claim_ids:
            if c not in seen_ids and c not in base_seen:
                fails.append("%s R8 主張表にあるがエビデンス表に行が無い（「該当なし」でも行を置く）" % c)

    return fails, reviews, {"scope": True, "rows": len(body), "ids": len(set(all_pm)) + len(set(all_doi))}


def check_file(path, cache=None, quiet=False):
    cache = _load_cache() if cache is None else cache
    text = _read_text(path)
    fails, reviews, st = analyze(text, cache)
    _save_cache(cache)
    if not st.get("scope"):
        return 0, fails, reviews
    if not quiet:
        sys.stderr.write("evidence_table_guard: %s rows=%s ids=%s FAIL=%d REVIEW=%d\n" %
                         (os.path.basename(path), st.get("rows"), st.get("ids"), len(fails), len(reviews)))
        for f in fails:
            sys.stderr.write("  FAIL   " + f + "\n")
        for r in reviews:
            sys.stderr.write("  REVIEW " + r + "\n")
    return (2 if fails else 0), fails, reviews


# ----------------------------------------------------------------- selftest
def _selftest():
    """ネットワーク不要。resolver をスタブ化して 8 検査の赤/緑を確認する。"""
    stub = {
        "pmid:31789535": {"ok": True, "title": "The better-than-average effect in comparative self-evaluation: A comprehensive review and meta-analysis.",
                          "year": "2020", "authors": ["Zell E", "Strickhouser JE", "Sedikides C", "Alicke MD"],
                          "pubtype": ["Journal Article", "Meta-Analysis"],
                          "abstract": "data from 124 published articles, 291 independent samples, and more than 950,000 participants. dz = 0.78, 95% CI [0.71, 0.84]"},
        "doi:10.1017/s0140525x00064955": {"ok": True, "title": "The Bowlby-Ainsworth attachment theory", "year": "1979",
                                          "authors": ["Bowlby John"], "pubtype": ["journal-article"], "abstract": ""},
        "doi:10.1016/j.jebo.2024.106631": {"ok": False, "err": "HTTP 404"},
        "doi:10.3102/00346543074001029": {"ok": True, "title": "The Effects of School-Based Writing-to-Learn Interventions on Academic Achievement: A Meta-Analysis",
                                          "year": "2004", "authors": ["Bangert-Drowns Robert L.", "Hurley Marlene M.", "Wilkinson Barbara"],
                                          "pubtype": ["journal-article"], "abstract": "This meta-analysis of 48 school-based writing-to-learn programs shows that writing can have a small, positive impact"},
    }
    def pm(ids, cache):
        for p in ids:
            cache["pmid:" + p] = stub.get("pmid:" + p, {"ok": False, "err": "not found"})
    def do(d, cache):
        cache["doi:" + d.lower()] = stub.get("doi:" + d.lower(), {"ok": False, "err": "HTTP 404"})

    H = ("| # | 主張 | 種別 |\n|---|---|---|\n| C1 | 平均以上効果 | 主張 |\n| C2 | 映像記憶 | 主張 |\n| C3 | 書く学習 | 推奨 |\n\n"
         "| # | 判定 | 代表論文 | 設計 | 信頼度 | 効果量 | 要点 | URL |\n|---|---|---|---|---|---|---|---|\n")
    good = H + ("| C1 | 支持 | Zell 2020 Psychol Bull | メタ分析・291サンプル | 高 | 大 | dz=0.78 | [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n"
                "| C2 | 検証対象外 | 該当なし | — | — | — | 体験談 | — |\n"
                "| C3 | 支持 | Bangert-Drowns 2004 Rev Educ Res | メタ分析・48プログラム | 中 | 小 | small positive | [DOI](https://doi.org/10.3102/00346543074001029) |\n")
    cases = [
        ("green: 正しい表は FAIL 0", good, 0, None),
        ("red R2: 404 DOI（本物の欠陥）", H + "| C1 | 支持 | Blanchflower 2024 JEBO | 横断 | 中 | 大 | 44か国 | [DOI](https://doi.org/10.1016/j.jebo.2024.106631) |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C3 | 検証対象外 | 該当なし | — | — | — | — | — |\n", 1, "R2"),
        ("red R3: Haber と書いて Bowlby に解決（本物の欠陥）", H + "| C1 | 部分支持 | Haber 1979 BBS | 総説 | 低 | 不適用 | 消失 | [DOI](https://doi.org/10.1017/S0140525X00064955) |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C3 | 検証対象外 | 該当なし | — | — | — | — | — |\n", 1, "R3"),
        ("red R6: 要旨に無い d=0.26（本物の欠陥）", H + "| C1 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C3 | 支持 | Bangert-Drowns 2004 Rev Educ Res | メタ分析・48プログラム | 中 | 小 | d=0.26 | [DOI](https://doi.org/10.3102/00346543074001029) |\n", 1, "R6"),
        ("red R8: 主張 C3 がエビデンス表に無い", H + "| C1 | 支持 | Zell 2020 Psychol Bull | メタ分析 | 高 | 大 | dz=0.78 | [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n", 1, "R8"),
        ("red R5: 信頼度の自由記述", H + "| C1 | 支持 | Zell 2020 Psychol Bull | メタ分析 | やや高い | 大きめ | dz=0.78 | [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C3 | 検証対象外 | 該当なし | — | — | — | — | — |\n", 2, "R5"),
        ("red R4: 年ずれ（Zell 2013 と書く）", H + "| C1 | 支持 | Zell 2013 Psychol Bull | メタ分析 | 高 | 大 | dz=0.78 | [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n| C2 | 検証対象外 | 該当なし | — | — | — | — | — |\n| C3 | 検証対象外 | 該当なし | — | — | — | — | — |\n", 1, "R4"),
        ("scope: 表が無い .md は対象外", "# x\n\n本文のみ\n", 0, None),
    ]
    bad = 0
    for name, text, want_fail, tag in cases:
        fails, reviews, st = analyze(text, {}, pm, do)
        ok = (len(fails) == want_fail) and (tag is None or any(tag in f for f in fails))
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %s" % fails))
        bad += 0 if ok else 1
    print("selftest: %d/%d ok" % (len(cases) - bad, len(cases)))
    return 1 if bad else 0


# ----------------------------------------------------------------- hook main
def _targets(ti):
    out = []
    for k in ("file_path", "filePath", "path"):
        v = ti.get(k)
        if isinstance(v, str):
            out.append(v)
    for e in ti.get("edits") or []:
        v = e.get("file_path") if isinstance(e, dict) else None
        if isinstance(v, str):
            out.append(v)
    return out


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    ti = payload.get("tool_input") or {}
    targets = [t for t in _targets(ti) if re.search(r"\.(md|markdown)$", t, re.I) and os.path.isfile(t)]
    if not targets:
        return 0
    worst = 0
    for t in targets:
        code, fails, reviews = check_file(t)
        if code == 2:
            _record_fired("evidence_table_guard", payload)
            sys.stderr.write(
                u"⛔【evidence_table】エビデンス表の機械照合で FAIL %d件。無い論文・別論文・年ずれ・"
                u"要旨に無い数値・語彙外・主張の欠落は、もっともらしいほど目視を通過する。上の行を直すこと。\n"
                % len(fails))
        elif reviews:
            sys.stderr.write(
                u"⚠【evidence_table・REVIEW %d件】機械では判定できない項目。見逃し・選択の適切さ・反映の妥当性は"
                u"独立した攻撃的検証（別コンテキスト）へ差し戻すこと。\n" % len(reviews))
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--file" in sys.argv:
        p = sys.argv[sys.argv.index("--file") + 1]
        code, _, _ = check_file(p)
        sys.exit(code)
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
