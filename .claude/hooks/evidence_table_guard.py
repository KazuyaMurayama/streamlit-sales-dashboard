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
                  「検証対象外」を含む行と、探索記録「探索: <検索語> → N件」を持つ行のみ免除
                  （2026-09-26: 「該当なし」単独の免除を廃止。探さずに済ませる抜け道のため）。
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
  R9b band order  独自性列を持つ表で、判定バンドの逆転（未証拠の行が証明済みの
                  行より上）を FAIL。ただし文書に「並び順: 本書の中心命題に近い順」
                  と宣言した表は対象外（book_summary 2026-09-28 ユーザー指示:
                  中心命題が検証対象外だと表の下に沈み、何の本か最初の数行で分からない）。

SCOPE: 書き込まれた .md に、①「信頼度」＋「効果量」（科学系）または
       ②「判定」＋「独自性」（製品・実務系。2026-09-18 追加）をヘッダに持つ表がある場合。
       パスは問わない（全リポ配布しても、表が無ければ何もしない）。

NETWORK: PubMed E-utilities と Crossref。識別子ごとに1回、結果は
       ~/.claude/state/evidence_table_guard/cache.json に永続キャッシュ。
       ネットワーク不通で解決できない識別子は「未確認」＝ FAIL（cite_gate と同じ
       思想: 合格記録が無いものは通さない）。内部例外は FAIL-OPEN。
       2026-09-29 改修（book_summary 段階4・28冊で実害3件）:
         ① R6 の照合先に OpenAlex と PubMed の要旨を追加。Crossref は DOI の約53%
            （キャッシュ実測 232/438）で要旨を持たず、正しい数値（Walter 2019 の
            d=0.29・k=30・N=20,963 等）を FAIL にして執筆者に削らせていた。
            Crossref にある値で足りないときだけ遅延取得する（通信を増やさない）。
            要旨が増えると旧版の REVIEW が FAIL に変わるため、実コーパス42本で較正して
            偽陽性の型を4つ潰した: 主張列の数値（本の主張であって論文の値ではない）、
            「19世紀」、「30.9万人」（要旨は 308,849）、丸め（13.2 と 13.21）、
            綴りの数（Seventy articles）。
            独立QC（Fable 2026-09-29）で差し戻された2点も直した:
            ・「要旨の無い論文を行に足すと FAIL が REVIEW に化ける」抜け道 → FAIL のまま、
              その論文名を示して「本文値」の明記を促す（値を削らせない）。
            ・429 の再送が1回の書き込みで数十回・数百秒に膨らみ、フックの60秒で殺されて
              キャッシュも保存されない → 1プロセスの通信予算 NET_BUDGET 秒、未確認は
              RETRY_AFTER_S 秒は再問い合わせしない。
            丸めは「小数2桁以上 または 有効数字3桁以上」、万は「有効数字2桁以上」に限る
            （0.3 が p = .254 に、1万 が 5,001〜14,999 に一致していた）。主張列は
            統計記号（d= r= N= k= OR %）付きの数値だけ照合し、無ければ REVIEW。
         ② HTTP 429（過負荷）・5xx は「無い論文」ではなく「未確認」。旧版は 429 を
            ok=False で永続キャッシュし、実在論文を恒久的に R2 FAIL にしていた。
            未確認（ok=None）はキャッシュから再試行し、_get は 429/5xx を短く再送する。
         ③ タイトルの U+2010 等のハイフン（Meta‐analysis）を R7 で認識し、著者名の
            ø・ö・é 等を「Surname YYYY」として拾い、Søgaard / Sogaard / Soegaard を同一視する。

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
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from codex_adapter import normalize as _codex_normalize
except Exception:  # adapter missing: say so, do not fail silently
    def _codex_normalize(d):
        # A hook that cannot convert Codex payloads reads empty values and
        # returns early -- silence indistinguishable from "no violation".
        # One line on stderr keeps a broken deployment visible (QC
        # 2026-09-18). stderr does not affect the hook's decision.
        if isinstance(d, dict) and d.get("tool_name") == "apply_patch":
            sys.stderr.write(
                "[%s] codex_adapter.py not found next to this hook; "
                "Codex apply_patch payloads are NOT being checked."
                % os.path.basename(__file__) + chr(10))
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
CENTRAL_ORDER_RE = re.compile(r"並び順\s*[:：]\s*(?:本書の)?中心命題")
EFFECT_VOCAB = {"大", "中", "小", "ほぼゼロ", "不明", "不適用"}
EXEMPT_RE = re.compile(r"検証対象外|に同じ")
# 2026-09-26 追加: 識別子の代わりに「探して見つからなかった記録」を認める。
# 書式「探索: <検索語> → N件」。検索語と件数の両方が要る（「該当なし」とだけ書いて
# 探さずに済ませる抜け道を塞ぐため、「該当なし」単独は免除しない）。
# 較正（2026-09-26・全リポの科学系の表 18ファイル 269行）: 識別子なし 235行、
# 「該当なし」だけで免除されていた行 0、探索記録のある行 0 → 既存ファイルの判定は変わらない。
SEARCH_LOG_RE = re.compile(r"探索\s*[:：][^|]*?[→>]\s*\d+\s*件")
PMID_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)|\bPMID\s*[:：]?\s*(\d{6,9})", re.I)
# 「DOI: 10.…」だけでなく「DOI 10.…」（コロン無し）も識別子として拾う。
# 実測 2026-09-15: コロン無しで書いた Haber 1979 の DOI が抽出されず、
# 「識別子なし」の偽 FAIL になった。
# 終端は半角だけでなく全角の括弧・読点でも止める（実測 2026-09-15: 「DOI 10.…）も成人での」
# まで DOI として拾い、Crossref 404 の偽 FAIL になった）。
# DOI の境界（2026-09-27 に2回直した。tests/test_doi_extraction_invariant.py が全抽出器を同じ実DOI集で検査する）:
#   - 本体は ASCII の非空白文字。括弧 ( ) と < > ; : を含みうる
#     （Elsevier: 10.1016/0148-2963(91)90050-8、Wiley SICI: 10.1002/(SICI)1097-4679(199910)55:10<1243::AID-JCLP6>3.0.CO;2-N）
#   - 全角文字（（）」、。等）・| ] " で終わる
#   - 末尾の記号と、対応の取れない ) > は _trim_doi で剥がす（verify_citations.py の trim_url と同じ方針）
# 旧版は ) と > で止めていたため括弧入り DOI を途中で切り、実在論文を「無い論文」と誤判定していた
# （実レポート95本で壊れた DOI 69件）。
_DOI_BODY = r'10\.\d{4,9}/[^\s"|\u3000-\uffff]+'   # ] も本体に入れ、対応の無い ] は _clean_doi で切る
# 接頭辞（DOI: / doi.org/）を要求しない。**DOI**: や `…` や ＤＯＩ： で接頭辞の照合が外れ、実在の DOI を
# 「識別子なし」と誤判定していた（2026-09-27 Fable 第3回）。前が英数字・. - の位置からは始めない
DOI_RE = re.compile(r"(?<![\w.\-])(" + _DOI_BODY + r")")


def _prep_text(t):
    """DOI を探す前の下ごしらえ。3つの抽出器で一字一句同じ（2026-09-27 Fable 再攻撃で破れた形）。
      - 表セルの HTML（<br> <sup> 等）と &nbsp; 等の実体参照を空白にする。SICI の <1243::AID-...> は残す
      - Markdown のエスケープ \\( \\) \\[ \\] \\_ \\* を外す
      - %2F 等の符号化を戻す（/ まで符号化された DOI は、戻さないと正規表現に一致しない）
    """
    t = re.sub(r"</?(?:br|sup|sub|span|b|i|em|strong|code|td|th|tr|p|div|li)\b[^>]*>", " ", t, flags=re.I)
    t = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", t)
    t = re.sub(r"\\([()\[\]_*])", r"\1", t)
    t = re.sub(r"\[\^[^\]]*\]", " ", t)                        # 脚注 [^1]
    t = urllib.parse.unquote(t)
    t = re.sub(r"([,;])(?=\s*(?:https?://\S*?)?10\.\d{4,9}/)", r"\1 ", t)   # 「A,B」「A;B」を2つに分ける
    return t


def _clean_doi(d):
    """取り出した DOI 候補の後始末。3つの抽出器（evidence_table_guard / verify_citations /
    check_citation_titles）で同一の本文を持ち、claude-governance/tests/test_doi_extraction_invariant.py が
    同じ実在 DOI 集で検査する（2026-09-27 に Fable の攻撃的検証で6形が破れたため追加）。
      - %3C 等の符号化を戻す（ブラウザから複写した SICI DOI）
      - ?utm_source=... のクエリと #abstract のページ内リンクを落とす。
        ただし Wiley SICI の検査文字 '#' 単独（...;2-#）は DOI の一部なので残す
      - 対応の無い ) で切り、対応の無い ( の手前で切る（「DOI:10.x/y(注)」「...8(2026-09-27閲覧)」）
      - 末尾の記号と、対応の取れない ) > を剥がす（<https://doi.org/...> の自動リンク）
    """
    d = urllib.parse.unquote(d)
    d = re.split(r"[^!-~]", d, maxsplit=1)[0]   # 非ASCII（「閲覧」等の本文）の手前で切る。DOI は実用上 ASCII
    d = re.sub(r"\?[A-Za-z_][\w.-]*=.*$", "", d)
    d = re.sub(r"#[A-Za-z][^#]*$", "", d)   # #page=3・#abstract 等。SICI の検査文字 #（英字が続かない）は残す
    for op, cl in (("(", ")"), ("[", "]")):   # 角括弧入りの実DOI: 10.1175/1520-0493(1900)28[24:twotm]2.0.co;2
        opens = []
        for i, ch in enumerate(d):
            if ch == op:
                opens.append(i)
            elif ch == cl:
                if not opens:
                    d = d[:i]
                    break
                opens.pop()
        else:
            if opens:
                d = d[:opens[0]]
    prev = None
    while prev != d:
        prev = d
        d = d.rstrip(".,;:*_`'?!~")
        if d.endswith(")") and d.count(")") > d.count("("):
            d = d[:-1]
        if d.endswith(">") and d.count(">") > d.count("<"):
            d = d[:-1]
    return d


def _doi_prefixes(d):
    """照会で見つからなかった DOI 候補から、短い候補を長い順に返す（3つの抽出器で一字一句同じ）。
    文章側の記号まで取り込んだ候補（…(2009)・…#・…?ref・….PMID:1 等）でも、本当の DOI は必ず先頭部分にある。
    区切りになりうる記号の手前で切り、後始末してから試す。最大6件。見つかった DOI は元の候補と違うので、
    呼び出し側は著者・年・題名の照合で別論文への取り違えを検出すること。
    """
    out = []
    head = d.index("/") + 1
    for i in range(len(d) - 1, head, -1):
        if d[i] in "()[]<>,;.#?!~*_`'&:":
            c = _clean_doi(d[:i])
            if len(c) > head and c != d and c not in out:
                out.append(c)
        if len(out) >= 6:
            break
    return out


CLAIM_ID_RE = re.compile(r"^\s*(C\d+'?)\s*$")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# 第一著者姓 + 年 の並び（「Zell 2020」「von der Embse 2018」「Bangert-Drowns 2004」）
# 年の後ろに数字が続くもの（PMID 19231028 → 「PMID 1923」）は年ではない。
# 実測 2026-09-15: この取り違えで偽 FAIL 1 件。識別子ラベルは著者名から除外する。
# 2026-09-29: ø・ö・é・ł 等のラテン文字を姓に含める（旧版は「Søgaard 2019」を拾えず R3 REVIEW）。
# CJK は含めない（「研究 2019」を姓と誤読しないため）。
_LU = "A-Z\u00c0-\u00d6\u00d8-\u00de\u0100-\u017f"
_LL = "A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff\u0100-\u017f'\u2019\\-"
AUTHOR_YEAR_RE = re.compile(r"(?<![" + _LL + r"])(?!(?:PMID|PMC|PMCID|DOI|ISBN)\b)"
                            r"([" + _LU + r"][" + _LL + r"]+(?:\s+(?:von|van|de|der|den|la|le)\s+[" + _LU + r"][" + _LL + r"]+)?"
                            r"|(?:von|van|de)\s+(?:der\s+)?[" + _LU + r"][" + _LL + r"]+)\s+((?:19|20)\d{2})(?!\d)")
_FOLD = {"\u2019": "'", "\u00f8": "o", "\u00e6": "ae", "\u0153": "oe", "\u00df": "ss", "\u0142": "l",
         "\u0111": "d", "\u00f0": "d", "\u00fe": "th", "\u0131": "i"}
_TRANSLIT = {"\u00f6": "oe", "\u00f8": "oe", "\u00fc": "ue", "\u00e4": "ae", "\u00e5": "aa"}


def _surname_variants(s):
    """Søgaard → {søgaard, sogaard, soegaard}。転写・記号落ちの表記ゆれで R3 を偽 FAIL にしない。"""
    s = s.lower()
    out = {s}
    for table in (_TRANSLIT, {}):
        t = "".join(table.get(c, c) for c in s)
        t = "".join(_FOLD.get(c, c) for c in t)
        t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
        out.add(t)
        out.add(t.replace("'", ""))           # O'Brien / OBrien
    return out
# 主張列のうち統計記号の付いた数値（d=0.44・N=99,999・OR 1.5・30%）
CLAIM_STAT_RE = re.compile(r"(?<![A-Za-z])(?:[dgrkNnβ]\s*[=＝]|(?:OR|RR|HR|SMD)\s*[=＝:]?)\s*[−\-]?(\d[\d,]*(?:\.\d+)?|\.\d+)"
                           r"|(\d+(?:\.\d+)?)\s*[%％]")
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


TRANSIENT = (429, 500, 502, 503, 504)
# フックは既定60秒で殺され、殺されるとキャッシュも保存されない。通信は1プロセス合計でこの秒数まで。
NET_BUDGET = 25.0
RETRY_AFTER_S = 600          # 未確認（429・通信失敗）の再問い合わせまでの間隔
_T0 = time.time()
_THROTTLED = set()


class NetBudgetExceeded(Exception):
    pass


def _remaining():
    return NET_BUDGET - (time.time() - _T0)


def _get(url, timeout=40, retries=2):
    """429/5xx は短く再送する（2026-09-29: 一括照合で Crossref が 429 を返し、
    その 429 が「無い論文」として永続キャッシュされていた）。待ちは Retry-After（上限5秒）。
    通信予算を超えそうなら待たずに NetBudgetExceeded（呼び出し側で「未確認」になる）。"""
    host = urllib.parse.urlsplit(url).netloc
    for attempt in range(retries + 1):
        if _remaining() <= 1.0:
            raise NetBudgetExceeded("network budget %.0fs exhausted" % NET_BUDGET)
        if host in _THROTTLED:
            # このプロセスで一度 429/5xx を諦めたホストには以後問い合わせない（1件ずつ叩き続ける嵐を防ぐ）
            raise NetBudgetExceeded("%s throttled earlier in this run" % host)
        req = urllib.request.Request(url, headers=UA)
        try:
            return urllib.request.urlopen(req, timeout=min(timeout, max(1.0, _remaining()))).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in TRANSIENT:
                raise
            if attempt == retries:
                _THROTTLED.add(host)
                raise
            try:
                wait = float(e.headers.get("Retry-After") or 0)
            except Exception:
                wait = 0
            wait = min(max(wait, 1.0 + attempt), 5.0)
            if wait >= _remaining() - 1.0:
                _THROTTLED.add(host)
                raise
            time.sleep(wait)


def _unconfirmed(err):
    return {"ok": None, "err": err, "retry_at": time.time() + RETRY_AFTER_S}


def _due(rec):
    """キャッシュを使わず問い合わせるべきか: 未取得、または未確認で再試行時刻を過ぎたもの。"""
    return rec is None or (rec.get("ok") is None and rec.get("retry_at", 0) <= time.time())


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
    for m in DOI_RE.finditer(_prep_text(cell_text)):
        d = _clean_doi(m.group(1))
        ids.append(("doi", d))
    return ids


# ----------------------------------------------------------------- resolvers
def resolve_pmids(pmids, cache):
    # 未確認（ok=None: 通信失敗・429）は次回に再試行する。確定した結果だけを使い回す。
    need = [p for p in pmids if _due(cache.get("pmid:" + p))]
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
                if (cache.get("pmid:" + p) or {}).get("ok") is None:
                    cache["pmid:" + p] = _unconfirmed(str(e)[:80])
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
    if not _due(cache.get(k)):
        return
    try:
        try:
            m = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))["message"]
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            m = None
            for cand in _doi_prefixes(doi):      # 文章側の記号の取り込み過ぎ（2026-09-27）
                try:
                    m = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(cand)))["message"]
                    break
                except urllib.error.HTTPError as e2:
                    if e2.code != 404:
                        raise
                    continue
            if m is None:
                # Crossref 未登録の DOI（DataCite 等。実測 10.5281/zenodo.3233986）は OpenAlex で引く
                oa = _openalex_work(doi)
                if oa is None:
                    raise
                cache[k] = oa
                return
        cache[k] = {
            "doi_resolved": m.get("DOI", doi),
            "ok": True,
            "title": " ".join(m.get("title", [])),
            "year": str((m.get("issued", {}).get("date-parts", [[None]])[0][0]) or ""),
            "authors": [(a.get("family", "") + " " + a.get("given", "")).strip() for a in m.get("author", [])],
            "pubtype": [m.get("type", "")],
            "journal": (m.get("container-title") or [""])[0],
            "abstract": " ".join(re.sub(r"<[^>]+>", "", m.get("abstract", "")).split()),
        }
    except urllib.error.HTTPError as e:
        # 「無い」と言えるのは 404/410 だけ。429・5xx は過負荷であって不在ではない
        cache[k] = {"ok": False, "err": "HTTP %s" % e.code} if e.code in (404, 410) else _unconfirmed("HTTP %s" % e.code)
    except Exception as e:
        cache[k] = _unconfirmed(str(e)[:80])


def _openalex_abstract(j):
    inv = (j or {}).get("abstract_inverted_index") or {}
    pos = [(i, w) for w, idx in inv.items() for i in idx]
    return " ".join(w for _, w in sorted(pos))


def _pubmed_xml_abstract(x):
    """efetch XML から AbstractText だけを取り出す（書誌行の巻号・頁・PMID を照合に混ぜない）。"""
    body = " ".join(re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", x or "", re.S))
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def _openalex_work(doi):
    """Crossref が 404 の DOI を OpenAlex で解決する。無ければ None（404 以外の失敗は例外のまま上げる）。"""
    try:
        j = json.loads(_get("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi), 20, 1))
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return None
        raise
    return {
        "doi_resolved": doi, "ok": True, "source": "openalex",
        "title": j.get("title") or j.get("display_name") or "",
        "year": str(j.get("publication_year") or ""),
        # display_name は「Given Family」。姓照合は部分一致なので順序は問わない
        "authors": [((a.get("author") or {}).get("display_name") or "") for a in j.get("authorships", [])],
        "pubtype": [j.get("type") or ""],
        "journal": (((j.get("primary_location") or {}).get("source") or {}).get("display_name") or ""),
        "abstract": _openalex_abstract(j),
        "alt_checked": 0,
    }


def resolve_alt_abstracts(kind, v, cache):
    """Crossref／esummary の要旨で足りないときの補助要旨（OpenAlex＋PubMed）。
    両方とも応答が得られた時だけ alt_checked を立てる（通信失敗は次回に再試行）。"""
    k = ("pmid:" + v) if kind == "pmid" else ("doi:" + v.lower())
    rec = cache.get(k)
    if not rec or not rec.get("ok") or rec.get("alt_checked") == 2 or rec.get("alt_retry_at", 0) > time.time():
        return
    texts, answered = [], 0
    doi = rec.get("doi_resolved") or v
    try:
        key = ("pmid:" + v) if kind == "pmid" else ("doi:" + urllib.parse.quote(doi))
        texts.append(_openalex_abstract(json.loads(_get("https://api.openalex.org/works/" + key, 20, 1))))
        answered += 1
    except urllib.error.HTTPError as e:
        answered += e.code == 404
    except Exception:
        pass
    try:
        pmid = v if kind == "pmid" else None
        if pmid is None:
            j = json.loads(_get(EUTILS + "esearch.fcgi?db=pubmed&retmode=json&term="
                                + urllib.parse.quote(doi + "[doi]"), 20, 1))
            ids = j.get("esearchresult", {}).get("idlist", [])
            pmid = ids[0] if len(ids) == 1 else None
        if pmid:
            # XML の AbstractText だけを使う（text 形式は書誌行の巻号・頁・PMID を含み、偶然一致で通してしまう）
            texts.append(_pubmed_xml_abstract(_get(EUTILS + "efetch.fcgi?db=pubmed&retmode=xml&id=" + pmid, 30, 1)))
        answered += 1
    except Exception:
        pass
    rec["abstract_alt"] = " ".join(t for t in texts if t)
    if answered == 2:
        rec["alt_checked"] = 2  # 2 = XML の AbstractText 版
    else:
        rec["alt_retry_at"] = time.time() + RETRY_AFTER_S


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
    t = re.sub(r"\d+\s*(代|歳|年|か月|ヶ月|番目|位|点|つ|回|巡|周|本|章|節|時間|分|秒|世紀)(?![\d])", " ", t)
    nums = set()
    for m in NUM_RE.finditer(t):
        v = _norm_num(m.group(1))
        rest = t[m.end():m.end() + 6].lstrip()
        unit = rest[:1]
        if unit in ("万", "億"):
            # 「30.9万人」は要旨では 308,849。_abstract_has が丸めて照合する。
            # 「3万人超」「3万以上」は下限の主張なので +（30,625 は 3万人超として正しい）
            over = re.match(r"[万億][人件名例本社]?(超|以上|余)", rest)
            nums.add(v + unit + ("+" if over else ""))
            continue
        if v in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"):
            continue           # 単独の一桁・10 は列挙語（2本・3件）が多く検証キーにならない
        nums.add(v)
    return nums


_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORDNUM_RE = re.compile(r"\b(" + "|".join(_TENS) + r")(?:[\s\-\u2010\u2011]+(" + "|".join(k for k in _ONES if _ONES[k] < 10) + r"))?\b"
                         r"|\b(" + "|".join(k for k in _ONES if _ONES[k] >= 11) + r")\b", re.I)


def _digitize_words(a):
    """要旨の文頭では数を綴る（APA: "Seventy articles containing 147 tests"）。11〜99 を数字に直す。"""
    def f(m):
        if m.group(3):
            return str(_ONES[m.group(3).lower()])
        return str(_TENS[m.group(1).lower()] + (_ONES[m.group(2).lower()] if m.group(2) else 0))
    return _WORDNUM_RE.sub(f, a)


def _abstract_has(num, abstract):
    a = _digitize_words(abstract.replace(",", ""))
    if num.endswith(("万+", "億+")):
        # 下限の主張（3万人超）: 書いた値以上・次の桁未満（3万人超 ← 30,625、31,000 は可、45,000 は不可）
        digits = num[:-2]
        base = 1e4 if num[-2] == "万" else 1e8
        dec = len(digits.split(".")[1]) if "." in digits else 0
        lo, hi = float(digits) * base, (float(digits) + 10 ** -dec) * base
        return any(lo <= float(x) < hi for x in re.findall(r"(?<![\d.])\d{4,}(?:\.\d+)?(?![\d])", a))
    if num[-1:] in ("万", "億"):
        # 30.9万 ← 308849（書いた桁で丸めて一致）。有効数字1桁（1万・2万）は丸めを許さず完全一致のみ
        # （1万 が 5,001〜14,999 に一致していた。Fable 2026-09-29）
        base = 1e4 if num[-1] == "万" else 1e8
        digits = num[:-1]
        v = float(digits)
        dec = len(digits.split(".")[1]) if "." in digits else 0
        sig = len(digits.replace(".", "").lstrip("0"))
        for x in re.findall(r"(?<![\d.])\d{4,}(?:\.\d+)?(?![\d])", a):
            if (sig >= 2 and round(float(x) / base, dec) == v) or float(x) == v * base:
                return True
        return False
    if re.fullmatch(r"\d+\.\d+", num) and (len(num.split(".")[1]) >= 2 or len(num.replace(".", "").lstrip("0")) >= 3):
        # 丸め: 13.2 ← -13.21。書いた桁より細かい要旨の値が、書いた桁に丸まれば一致。
        # 小数2桁以上か有効数字3桁以上に限る（0.3 が p = .254 に一致していた。Fable 2026-09-29）
        dec = len(num.split(".")[1])
        for x in re.findall(r"(?<![\d])\d*\.\d+(?![\d])", a):
            xd = len(x.split(".")[1])
            if xd > dec and abs(round(float(x), dec) - float(num)) < 10 ** -(dec + 3):
                return True
    cands = {num}
    if re.fullmatch(r"0\.\d+", num):
        cands.add(num[1:])                      # .78
    if re.fullmatch(r"\d+\.\d+", num):
        cands.add(num.rstrip("0").rstrip("."))  # 0.780 -> 0.78
    return any(re.search(r"(?<![\d.])" + re.escape(c) + r"(?![\d])", a) for c in cands)


def analyze(text, cache, resolver_pm=resolve_pmids, resolver_doi=resolve_doi, resolver_alt=resolve_alt_abstracts):
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
        exempt = bool(EXEMPT_RE.search(rowtext) or SEARCH_LOG_RE.search(rowtext))
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
                fails.append("%s R1 識別子なし（PubMed/DOI の URL か PMID/DOI を書く。見つからない場合は scripts/evidence_search.py で探し「探索: <検索語> → N件」を書く。免除は「検証対象外」明記時のみ）" % cid)
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
                auth = " ".join(_surname_variants(" ".join(r.get("authors", []))))
                try:
                    ry = int(r.get("year") or 0)
                except Exception:
                    ry = 0
                return any(sv in auth for sv in _surname_variants(surname)) and ry and abs(ry - yr) <= 1
            if not any(_match(r) for r in resolved):
                near = [r for r in resolved
                        if any(sv in " ".join(_surname_variants(" ".join(r.get("authors", []))))
                               for sv in _surname_variants(surname))]
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
        # 行番号のセル（| 13 |）は数値照合の対象外（2026-09-27: 10行目以降だけが偽 FAIL になっていた）
        # 主張列の数値（「20%ルール」「摂氏37度」）は本の主張であって論文の値ではない（2026-09-29 較正）
        i_claim = _col(header, "主張")
        nums = _row_numbers(" | ".join(c for j, c in enumerate(row) if j != i_id and j != i_claim))
        # ただし主張列でも統計記号付きの数値（d=0.44・N=99,999・30%）は照合する（無検査の通り道にしない）
        claim_nums = set()
        if i_claim is not None and i_claim < len(row) and i_claim != i_id:
            for m in CLAIM_STAT_RE.finditer(row[i_claim]):
                v = _norm_num(next(g for g in m.groups() if g))
                if v not in nums:
                    claim_nums.add(v)
        abstracts = [r.get("abstract", "") or "" for r in row_recs]
        if nums and any(not any(_abstract_has(n, a) for a in abstracts if a) for n in nums):
            # Crossref/esummary で足りないときだけ OpenAlex・PubMed の要旨を足す（①）
            for kind2, v2 in ids:
                try:
                    resolver_alt(kind2, v2, cache)
                except Exception:
                    pass
            abstracts = [" ".join(x for x in ((r.get("abstract") or ""), (r.get("abstract_alt") or "")) if x)
                         for r in row_recs]
        if nums:
            if not any(abstracts):
                reviews.append("%s R6 要旨が取得できず数値 %s を照合できない" % (cid, sorted(nums)))
            else:
                missing = sorted(n for n in nums if not any(_abstract_has(n, a) for a in abstracts if a))
                blind = [r.get("title", "")[:40] for r, a in zip(row_recs, abstracts) if not a]
                if missing:
                    # 要旨の無い論文を足しても FAIL のまま（REVIEW に逃がす抜け道にしない。Fable 2026-09-29）。
                    # その論文の値なら、値を削らず「本文値」と明記するよう促す（正しい値を削らせた実害への対処）
                    hint = ("。要旨を API で取得できない論文（%s）から取った値なら、値は削らず「本文値」と明記する"
                            % " / ".join(blind)) if blind else ""
                    msg = "%s R6 原著要旨に無い数値: %s（要旨に無い数値は書かない。本文から取ったなら「本文値」と明記。別論文の値なら、その論文の PMID/DOI を同じ行に書く%s）" % (cid, missing, hint)
                    (reviews if "本文値" in rowtext else fails).append(msg)
        if claim_nums and any(abstracts):
            cmiss = sorted(n for n in claim_nums if not any(_abstract_has(n, a) for a in abstracts if a))
            if cmiss:
                reviews.append("%s R6 主張列の統計値 %s が行内の論文の要旨に無い（本の主張の値なら問題ない。論文の値として書いたなら確認する）"
                               % (cid, cmiss))
        # R7 design label: 行内のどれか1本が meta-analysis なら整合とみなす
        if "メタ分析" in rowtext or "メタアナリシス" in rowtext:
            def _is_meta(r):
                pt = " ".join(r.get("pubtype", [])).lower() + " " + r.get("title", "").lower()
                # U+2010 等のハイフン（Meta‐analysis）・「meta analysis」を同一視（③）
                pt = re.sub("[\u2010-\u2015\u2212\u00ad]", "-", pt).replace("meta analy", "meta-analy")
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
    # 「並び順: 本書の中心命題に近い順」を宣言した文書は、判定ではなく本書での重みで並べる
    # 規約なのでバンド順を課さない（book_summary 2026-09-28 ユーザー指示）。
    worst = -1
    worst_cid = None
    band_rows = verdict_seq if (i_novel is not None and not CENTRAL_ORDER_RE.search(text)) else []
    for cid, vd in band_rows:
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
    T = ("| # | 主張 | 独自性 | 判定 | 信頼度 | 効果量 | 根拠の要点 | 出典 |\n|---|---|---|---|---|---|---|---|\n"
         "| 1 | 中心命題 | 独自 | 検証対象外 | 低 | 不適用 | 規範 | 著者の主張のみ |\n"
         "| 2 | 平均以上効果 | 通説 | 支持 | 高 | 大 | dz=0.78 | Zell 2020 [PM](https://pubmed.ncbi.nlm.nih.gov/31789535/) |\n")
    cases += [
        ("red R9b: 宣言なしで検証対象外が支持より上", T, 1, "R9b"),
        ("green R9b: 「並び順: 本書の中心命題に近い順」宣言ありは対象外", "並び順: 本書の中心命題に近い順\n\n" + T, 0, None),
    ]
    bad = 0
    for name, text, want_fail, tag in cases:
        fails, reviews, st = analyze(text, {}, pm, do, lambda *a: None)
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
