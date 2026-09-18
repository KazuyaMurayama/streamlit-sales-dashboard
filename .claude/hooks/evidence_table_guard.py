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
  R8 coverage     主張表が **別表** として存在する場合のみ: その C-番号がすべて
                  エビデンス表に現れること。                                FAIL
                  標準書式は主張・判定・論文・信頼度・効果量・URL を 1 表に
                  統合したもの（2026-09-15 ユーザー指示: 2 表だと上にスクロール
                  して戻る往復が起きる）。統合表では各行が主張そのものなので
                  R8 は対象外。行順は有望順（判定→信頼度→効果量）で、
                  C 番号は本文参照用の ID として残す。

SCOPE: 書き込まれた .md に、①「信頼度」＋「効果量」（科学系）または
       ②「判定」＋「独自性」（製品・実務系。2026-09-18 追加）をヘッダに持つ表がある場合。
       パスは問わない（全リポ配布しても、表が無ければ何もしない）。

NETWORK: PubMed E-utilities と Crossref。識別子ごとに1回、結果は
       ~/.claude/state/evidence_table_guard/cache.json に永続キャッシュ。
       ネットワーク不通で解決できない識別子は「未確認」＝ FAIL（cite_gate と同じ
       思想: 合格記録が無いものは通さない）。内部例外は FAIL-OPEN。

CALIBRATION (実測 2026-09-15): 本物の表（decks/CREATOR_BRAIN_40S_20260915-v2.md、
       主張 18 行・エビデンス 19 行・識別子 23 件）に対し、初版は FAIL 8（うち本物 0、
       偽陽性 8: URL/DOI 内の数字と「20代」「2019年」を検証キーにしていた）、
       2 版は FAIL 9（偽陽性: 補助 PMID を要点セルに書くと代表論文の取り違え）、
       3 版は FAIL 2（偽陽性: 「PMID 1923」を著者年と誤読、コロン無し DOI 未抽出）、
       4 版は FAIL 1（偽陽性: 全角括弧まで DOI に含めて 404）、5 版で FAIL 0 / REVIEW 0。
       偽陽性を 4 回潰して初めて本番で使える。欠陥版フィクスチャ（Bowlby DOI・404 DOI・
       要旨に無い d=0.26・主張の欠落・語彙外・年ずれ）で FAIL することを
       tests/test_evidence_table_guard.py が確認する（8/8）。直した版で PASS しても
       何も証明しない（CLAUDE.md 絶対ルール 8）。

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
    from codex_adapter import normalize as _codex_normalize
except Exception:
    def _codex_normalize(d):
        return d
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
# 2026-09-18 追加: 二軸化（判定＋独自性）。独自性は「効く」ことを含意せず、証拠の代わりにならない。
# 未検証 = 検証可能だが当たる研究が無い（自己申告・逸話のみ）。検証対象外 = 原理的に実証不能。
VERDICT_VOCAB = {"支持", "部分支持", "反証", "未検証", "検証対象外"}
NOVELTY_VOCAB = {"通説", "再構成", "独自"}
VERDICT_RANK = {"支持": 0, "部分支持": 1, "反証": 2, "未検証": 3, "検証対象外": 4}
VERDICT_RANK_NAME = dict((v, k) for k, v in VERDICT_RANK.items())
EFFECT_VOCAB = {"大", "中", "小", "ほぼゼロ", "不明", "不適用"}
EXEMPT_RE = re.compile(r"該当なし|検証対象外|に同じ")
PMID_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)|\bPMID\s*[:：]?\s*(\d{6,9})", re.I)
# 「DOI: 10.…」だけでなく「DOI 10.…」（コロン無し）も識別子として拾う。
# 実測 2026-09-15: コロン無しで書いた Haber 1979 の DOI が抽出されず、
# 「識別子なし」の偽 FAIL になった。
# 終端は半角だけでなく全角の括弧・読点でも止める（実測 2026-09-15: 「DOI 10.…）も成人での」
# まで DOI として拾い、Crossref 404 の偽 FAIL になった）。
DOI_RE = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s\)\]\|>）」』、。]+)|\bDOI\s*[:：]?\s*(10\.\d{4,9}/[^\s\)\]\|>）」』、。]+)", re.I)
CLAIM_ID_RE = re.compile(r"^\s*(C\d+'?)\s*$")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# 第一著者姓 + 年 の並び（「Zell 2020」「von der Embse 2018」「Bangert-Drowns 2004」）
# 年の後ろに数字が続くもの（PMID 19231028 → 「PMID 1923」）は年ではない。
# 実測 2026-09-15: この取り違えで偽 FAIL 1 件。識別子ラベルは著者名から除外する。
AUTHOR_YEAR_RE = re.compile(r"(?<![A-Za-z])(?!(?:PMID|PMC|PMCID|DOI|ISBN)\b)"
                            r"([A-Z][A-Za-z'\-]+(?:\s+(?:von|van|de|der|den|la|le)\s+[A-Z][A-Za-z'\-]+)?"
                            r"|(?:von|van|de)\s+(?:der\s+)?[A-Z][A-Za-z'\-]+)\s+((?:19|20)\d{2})(?!\d)")
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
        # 科学系（信頼度＋効果量）に加え、2026-09-18 から製品系（判定＋独自性）も対象にする。
        # 理由: 製品系の表は 信頼度／効果量 を持たないため従来は完全に不可視で、
        # R9（判定・独自性の語彙）が一度も走らなかった（実測: R9 追加直後に 0 件発火）。
        # 論文照合系（R1〜R4・R6・R7）は識別子を持つ行だけが対象なので、
        # 製品系の表を通しても偽 FAIL は増えない（R1 は「検証対象外」等で免除される）。
        is_science = "信頼度" in h and "効果量" in h
        is_product = "判定" in h and "独自性" in h
        if (is_science or is_product) and evidence is None:
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
    i_verdict, i_novel = _col(header, "判定"), _col(header, "独自性")
    # 科学系＝信頼度／効果量を持つ表。論文照合（R1 識別子必須・R5 語彙）はここだけに課す。
    # 製品・実務系の表は突き合わせ先が公式ドキュメントであり PMID/DOI を持たないため、
    # R1 を課すと全行が偽 FAIL になる（2026-09-18 実測で確認したうえでこの分岐を入れた）。
    is_science_table = i_conf is not None and i_eff is not None

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
    verdict_seq = []          # R9b（バンド順）用: 行の並び順に判定を控える
    for row in body:
        if len(row) <= max(i_conf or 0, i_eff or 0):
            continue
        cid = row[i_id].strip("* ")
        seen_ids.add(cid)
        rowtext = " | ".join(row)
        exempt = bool(EXEMPT_RE.search(rowtext))
        # R9 二軸の語彙（2026-09-18 追加）。判定列を持つ表すべてが対象＝製品系も含む。
        if i_verdict is not None:
            # 括弧の注記を先に落としてから強調記号を剥がす。逆順だと
            # 「**支持**（条件付き）」→「支持**」が残り偽 FAIL になる
            # （2026-09-18 実測: 実デッキ1本で 10 件の偽陽性）。
            vd = row[i_verdict] if i_verdict < len(row) else ""
            vd = re.sub(r"（.*?）|\(.*?\)", "", vd).replace("*", "").strip()
            if vd and vd not in VERDICT_VOCAB:
                fails.append("%s R9 判定が語彙外: 「%s」（支持/部分支持/反証/未検証/検証対象外）"
                             % (cid, vd))
            elif vd:
                verdict_seq.append((cid, vd))
        if i_novel is not None:
            nv = row[i_novel] if i_novel < len(row) else ""
            nv = re.sub(r"（.*?）|\(.*?\)", "", nv).replace("*", "").strip()
            if nv and nv not in ("—", "-") and nv not in NOVELTY_VOCAB:
                fails.append("%s R9 独自性が語彙外: 「%s」（通説/再構成/独自）" % (cid, nv))
        ids = extract_ids(rowtext)
        if not ids:
            # R1 は科学系の表だけに課す。製品・実務系は一次資料が公式ドキュメントであり
            # PMID/DOI を持たない（課すと全行が偽 FAIL になる）。R9 の語彙検査は上で済んでいる。
            if not exempt and is_science_table:
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

    # R9b バンド順（2026-09-18 追加）。二軸設計の中核の不変条件:
    # 独自性で判定バンドを越えさせない＝未証拠の行が証明済みの行より上に来てはならない。
    # VERDICT_RANK は定義だけされて一度も使われておらず、逆転した表が exit 0 で通っていた
    # （独立QC Fable が実証, 2026-09-18）。規則文書には「逆転は FAIL」と書いてあったため、
    # 散文が実装していない保証を約束している状態だった。
    # 独自性列を持つ表＝二軸レポート（book/deck）のみが並び順の規約を持つ。
    # 判定列だけの表（既存の科学系フィクスチャ等）に課すと正当な表が FAIL する
    # （2026-09-18 実測: selftest 9/9 → 7/9）。
    worst = -1
    worst_cid = None
    for cid, vd in (verdict_seq if i_novel is not None else []):
        r = VERDICT_RANK.get(vd)
        if r is None:
            continue
        if r < worst:
            fails.append(
                "%s R9b バンド順の逆転: 「%s」が「%s」(%s) より下にある。"
                "未証拠の行を証明済みの行より上に置かない"
                % (cid, vd, VERDICT_RANK_NAME.get(worst, "?"), worst_cid))
            break
        if r > worst:
            worst, worst_cid = r, cid

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
        ("green: 統合 1 表（主張列＋信頼度＋効果量）は R8 を要求しない",
         "| # | 主張・推奨 | 位置 | 判定 | 代表論文 | 信頼度 | 効果量 | 要点 | URL |\n|---|---|---|---|---|---|---|---|---|\n"
         "| C14 | 自分を頭がいいと思う | [00:22:00] | 支持 | Zell 2020 Psychol Bull（メタ分析） | 高 | 大 | dz=0.78 | [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n"
         "| C5 | 迷いは設計 | [00:08:00] | 検証対象外 | 該当なし | — | — | 比喩 | — |\n", 0, None),
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


def _read_payload():
    """stdin を UTF-8 バイトとして読む（cp932 既定で日本語ペイロードが落ちるのを防ぐ。
    実測 2026-09-15: asr_term_guard で content に日本語を含む payload が json.load で
    落ち、exit 0 で素通りした。同じ構造なのでここも同じ読み方にする）。"""
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8", "replace")
    return _codex_normalize(json.loads(raw.decode("utf-8", "replace")))


def main():
    try:
        payload = _read_payload()
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
