# -*- coding: utf-8 -*-
"""PostToolUse (Write|Edit|MultiEdit): recompute every star rating from the numbers written next to it,
using the repo's own canonical threshold table, and block when the written star disagrees.

WHY (C07「論理・判断の誤り」, CORRECTION_DIGEST_20261026, adopted by the user「採用してすすめて」)
-----------------------------------------------------------------------------------------------
2026-10-22 23:53 JST the user asked「それだと星5のレベルってほとんどないんじゃないですか？ r = 0.5 以上って
非常に珍しい」and on 2026-10-23「効果量が星5になっているものを20個チャットで抜粋して … 違和感がある」.
The extract showed 19 of 20 values that the canon put at ★5 written as ★4 (e.g. d 0.66 / r 0.42 as ★4),
i.e. stars had been set by feel, not by looking the value up in the table.
INVARIANT: a written star equals the star recomputed from the value / study size written in its own
parenthesis with the canonical table; where the parenthesis does not decide it, the hook stays silent.

WHAT IT DOES (only in a repo that has _meta/prompts/evidence-stars.md -- elsewhere it does nothing)
-------------------------------------------------------------------------------------------------
Thresholds are NOT copied here: the §1 table (d・g / r / オッズ比 columns, 以上・を超え・未満・以下) and the
numbers in the §2 table cells (5本・3,000人・200人・1,000人・100人・3施設・300人) are parsed from the canon on
every run. If the canon cannot be parsed the corresponding check is skipped (fail-open).
  E  効果の大きさ: a star followed by （d = x）/（r = .41〜.43）/「★3/5、OR 1.50」. |x| decides; ranges use the
     midpoint; OR/RR/HR below 1 use 1/x; η² -> d = 2*sqrt(η²/(1-η²)); Fisher z (ESz) -> r = tanh z; ρ -> r;
     δ・g・SMD・ES・d̄ -> d. With two indicators the canon order d・g -> r -> OR decides (first of that family).
     RR/HR read on the OR column (canon: base rate unknown -> OR column); a HIGHER written star is accepted
     only when a % (base rate, needed for the RR->OR conversion) is on the same line.
     ★1 conditions (meta-analysis / 1,000+ / CI upper < 0.2) cannot be checked: ★1 on a ≤0.05 value passes.
  N  β・R²・重相関 with a star and no convertible indicator -> block (canon: no star, say it in words).
  S  根拠の強さ (label within 12 chars before the star, or a table column so named): the parenthesis gives
     an UPPER bound only (study type, number of studies, participants). Lower stars pass, because the canon
     lowers stars for failed replications. 本書の主張のみ・論考・専門家の意見 alone -> exactly ★1.
  D  Editing evidence-stars.md or scripts/star_rules.py: the copy of the table in star_rules.py (_TH/_ONE)
     must equal the canon (the copy drifted risk: 2026-10-23 the canon was re-cut and 361 stars disagreed).
Edit/MultiEdit: only lines touched by new_string are checked. Write: the whole file.
Not covered: wording next to the star (「大きい部類」), the sign wording 逆効果, values outside parentheses,
whether the parenthesis itself is true (that is evidence_table_guard / cite_gate).

OVERLAP with Soulful-Content: article_quality_gate (Stop) runs K11-K13 (scripts/star_rules.py) on
deliverables/note/*.md only, at the end of the turn, with a hard-coded copy of the table. This hook adds:
the §2 upper bound (K7 only checks ★5 vs 3,000人; K12 only 本書の主張のみ), the d->r->OR priority, every
other .md in the repo, immediate feedback, and the drift check D. E duplicates K11 on articles by design
(independent second implementation reading the canon, so a stale copy cannot hide a wrong star).

Scope: every .md of the repo except _meta/ (records of past states). The drift check D still runs on the canon.

FABLE REVIEW 2026-10-26 (fable_c04_c07_review.md, C07) -- fixed:
  A2 people are counted per clause (。・「と、」), never summed across kinds of study (canon §2 足し算しない);
  P2/P3 among several values of the deciding family, one after 出版バイアス・追試・事前登録 is the one to rate,
        otherwise any written value may carry the star (plain 「補正後 ρ」 = reliability correction, not preferred);
  A1 「効果の大きさ ★4/5・根拠の強さ ★4/5（…）」 share the parenthesis; A3 table cell 「★4/5 d = 0.66」;
  A4 「d が 0.66」「g 0.31」 (decimal only; 「r は 0.1 未満」 is a bound and skipped); A5 value on the next line
  (also for Edit); P5 kanji people (三千人); P1 the canon file itself is never star-checked.
  Calibration after the fixes added 2 rules: unlabeled experiments give an upper bound (1本<100人 ★2, <1,000人 ★3,
  else ★4) instead of silence, and 「126の現場実験」 counts as 126 studies.

CALIBRATED 2026-10-26 on Soulful-Content deliverables/note (260 .md, 3,375 stars; after the Fable fixes 1,495 read
as effect stars, 1,649 as evidence stars with a decidable upper bound; first version 1,502 / 1,497):
  - first draft 42 disagreements, 30 false (6万926人 read as 926; 社・組 as people; 「くじで…割り振った」;
    「くじで分けた実験ではない」; 「理論モデルによる試算」 as 理論; 「研究を整理した論考」) -> fixed;
  - now 12 disagreements, all true by the canon: 11 legacy ★2/★3 on 本書の主張のみ・論考・理論・逸話 (canon §2 says
    read them as ★1) + 1 ★5 meta-analysis without participants (nt-135). 0 effect-star disagreements
    (star_rules.py --fix ran 2026-10-23).
  - history: the versions before commit 24a7747 give 83 effect disagreements (the commit changed 82 stars);
    after it 2 remain, one a real ★3 for ρ = −.23 that star_rules.py missed (nt-140, fixed later by hand).

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import ast
import io
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False
try:
    from codex_adapter import normalize as _codex_normalize
except Exception:
    def _codex_normalize(d):
        return d

NAME = "rating_recompute_guard"
CANON_REL = os.path.join("_meta", "prompts", "evidence-stars.md")
STAR_RULES_REL = os.path.join("scripts", "star_rules.py")
MAX_LIST = 8

# ---------------------------------------------------------------- canon parsing


def _num(s):
    return float(s.replace(",", "").replace("−", "-").replace("–", "-").replace(" ", ""))


def _section(text, n):
    m = re.search(r"^##\s*%d\.[^\n]*\n(.*?)(?=^##\s|\Z)" % n, text, re.S | re.M)
    return m.group(1) if m else ""


def _cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


_BOUND = re.compile(r"(\d+(?:\.\d+)?)\s*(以上|を超え|超|未満|以下)")


def _interval(cell):
    lo = hi = None
    lo_inc = hi_inc = False
    for v, w in _BOUND.findall(cell):
        v = float(v)
        if w == "以上":
            lo, lo_inc = v, True
        elif w in ("を超え", "超"):
            lo, lo_inc = v, False
        elif w == "未満":
            hi, hi_inc = v, False
        else:
            hi, hi_inc = v, True
    if lo is None and hi is None:
        return None
    return (lo, lo_inc, hi, hi_inc)


def parse_effect_table(canon):
    """{'d': {5: (lo, lo_inc, hi, hi_inc), ...}, 'r': ..., 'or': ...} or None."""
    sec = _section(canon, 1)
    lines = sec.split("\n")
    cols = None
    out = {"d": {}, "r": {}, "or": {}}
    for ln in lines:
        c = _cells(ln)
        if not c:
            continue
        if cols is None:
            if any("オッズ比" in x for x in c):
                cols = {}
                for i, x in enumerate(c):
                    if "オッズ比" in x:
                        cols["or"] = i
                    elif re.search(r"(?<![A-Za-z])r(?![A-Za-z])", x):
                        cols["r"] = i
                    elif re.search(r"(?<![A-Za-z])d(?![A-Za-z])", x):
                        cols["d"] = i
            continue
        m = re.match(r"★\s*([1-5])\s*/\s*5", c[0])
        if not m:
            continue
        star = int(m.group(1))
        for k, i in cols.items():
            if i < len(c):
                iv = _interval(c[i])
                if iv:
                    out[k][star] = iv
    if any(len(v) != 5 for v in out.values()):
        return None
    return out


def parse_evidence_rules(canon):
    """Numbers from the §2 table cells, or None when any is missing."""
    sec = _section(canon, 2)
    rows = {}
    for ln in sec.split("\n"):
        c = _cells(ln)
        if c and re.match(r"★\s*[1-5]\s*/\s*5", c[0]) and len(c) >= 2:
            rows[int(re.match(r"★\s*([1-5])", c[0]).group(1))] = c[1]
    try:
        r5, r4, r3 = rows[5], rows[4], rows[3]
        g = {}
        g["meta_n"] = int(re.search(r"(\d+)\s*本以上の研究", r5).group(1))
        g["meta_m"] = _num(re.search(r"参加者\s*([\d,]+)\s*人以上", r5).group(1))
        m = re.search(r"(\d+)\s*本以上・合わせて\s*([\d,]+)\s*人以上", r4)
        g["rct_multi_n"], g["rct_multi_m"] = int(m.group(1)), _num(m.group(2))
        g["rct_big"] = _num(re.search(r"1本でも\s*([\d,]+)\s*人以上", r4).group(1))
        m = re.search(r"(\d+)\s*施設以上で合わせて\s*([\d,]+)\s*人以上", r4)
        g["sites"], g["sites_m"] = int(m.group(1)), _num(m.group(2))
        g["rct_one"] = _num(re.search(r"実験が1本（\s*([\d,]+)\s*人以上）", r3).group(1))
        g["survey"] = _num(re.search(r"([\d,]+)\s*人以上の調査", r3).group(1))
        return g
    except Exception:
        return None


def star_for(table, kind, v):
    for star in (5, 4, 3, 2, 1):
        lo, lo_inc, hi, hi_inc = table[kind][star]
        if lo is not None and (v < lo - 1e-12 or (not lo_inc and v <= lo + 1e-12)):
            continue
        if hi is not None and (v > hi + 1e-12 or (not hi_inc and v >= hi - 1e-12)):
            continue
        return star
    return None

# ---------------------------------------------------------------- effect stars

_NUMRE = r"[+\-−–]?\s*(?:\d+(?:\.\d+)?|\.\d+)"
_SYMS = [  # (regex, family, conversion)
    (r"Hedges'?\s*g|Cohen'?s\s*d|Glass'?\s*Δ|SMD|標準化平均差|ESz|ES|δ|d̄|d|g", "d", None),
    (r"偏\s*η\s*[²2]|η\s*p\s*[²2]|η\s*[²2]", "d", "eta"),
    (r"ρ|r", "r", None),
    (r"調整オッズ比|オッズ比|相対リスク|リスク比|ハザード比|AOR|aOR|OR|RR|HR|IRR", "or", None),
]
_IND = re.compile(
    r"(?<![A-Za-z])(?P<sym>" + "|".join("(?:%s)" % s for s, _f, _c in _SYMS) + r")\*?(?![A-Za-zΔ])"
    r"\s*(?:[=＝≈:：]\s*|(?<=[RH]R|OR)\s+|(?<=比)\s*|(?<=スク)\s*"
    r"|(?<=[dgrρδDSz])\s*(?:が|は|の値は)?\s*(?=[+\-−–]?\s*\d*\.\d))"
    r"(?P<v1>" + _NUMRE + r")(?:\s*[〜~～]\s*(?P<v2>" + _NUMRE + r"))?(?![\d.]|\s*(?:未満|以下|以上|を超|超|より))")
_NONCONV = re.compile(r"(?<![A-Za-z])(?:β|ベータ|R\s*²|R2|R\s*[=＝]|重相関|偏相関|標準化(?:回帰)?係数)")
_STAR = re.compile(r"[★⭐]\s*([1-5])\s*/\s*5")
_EVID_LABEL = re.compile(r"根拠の強さ[^★⭐\n]{0,12}$")
_EFF_LABEL = re.compile(r"効果の大きさ[^★⭐\n]{0,12}$")


def _family(sym):
    s = sym.replace(" ", "")
    if s == "ESz":
        return "r", "z"
    for rx, fam, conv in _SYMS:
        if re.fullmatch(rx, s):
            if fam == "or" and s in ("RR", "HR", "IRR", "相対リスク", "リスク比", "ハザード比"):
                return "or", "rr"
            return fam, conv
    return "d", None


def _paren_after(text, end):
    """Text that belongs to the star at `end`: （...） right after it, or「、 d = x」up to the sentence end."""
    m = re.match(r"\s*[（(]", text[end:])
    if m:
        i = end + m.end()
        depth = 1
        j = i
        while j < len(text) and j - i < 200:
            ch = text[j]
            if ch in "（(":
                depth += 1
            elif ch in "）)":
                depth -= 1
                if depth == 0:
                    break
            elif ch == "\n":
                break
            j += 1
        return text[i:j]
    # 「（根拠の強さ ★5/5。くじで分けた実験ではなく、139か国・1,120推計を集めたもの）」: the star sits inside an
    # open parenthesis and its description follows after 。/：  -> take the rest of that parenthesis
    depth = sum(1 for ch in text[:end] if ch in "（(") - sum(1 for ch in text[:end] if ch in "）)")
    m = re.match(r"\s*[。:：]\s*", text[end:])
    if m and depth > 0:
        i = end + m.end()
        j = i
        while j < len(text) and j - i < 200 and text[j] not in "）)\n★⭐":
            j += 1
        return text[i:j]
    m = re.match(r"\s*[、,]\s*([^。\n★⭐]{0,60})", text[end:])
    if m:
        return m.group(1)
    if text.lstrip().startswith("|"):
        m = re.match(r"\s*[:：]?\s*([^|\n★⭐]{0,80})", text[end:])      # rest of the table cell
        return m.group(1).strip() if m else ""
    m = re.match(r"\s*[:：]\s*([^。\n★⭐]{0,60})", text[end:])
    return m.group(1) if m else ""


_PREFER = re.compile(r"(?:出版バイアス|バイアスを?補正|追試|再現研究|再現試験|事前登録)[^。]{0,14}$")
_ORIG = re.compile(r"(?:もとの|元の|当初の|補正前|最初の|原典の|もともと)[^。、]{0,14}$")


def _value(m, fam, conv):
    v = _num(m.group("v1")) if not m.group("v2") else (_num(m.group("v1")) + _num(m.group("v2"))) / 2.0
    if conv == "eta":
        v = abs(v)
        if v >= 1:
            return None
        v = 2 * math.sqrt(v / (1 - v))
    elif conv == "z":
        v = math.tanh(abs(v))
    if fam == "or":
        if v <= 0:
            return None
        return 1.0 / v if v < 1 else v
    return abs(v)


def effect_expected(table, seg):
    """(expected_star, family, conv, value, symbol, allowed_stars) for the deciding family, or None.

    canon §1: the family is chosen d・g -> r -> OR. Within it, a value introduced by 補正後・追試・事前登録 is the
    one to rate (the original is to be mentioned in words, 「もとの研究では d = 0.62 とされた」): when such a value
    exists only its star is allowed; otherwise any of the written values may carry the star (Fable P2/P3)."""
    found = {}
    for m in _IND.finditer(seg):
        fam, conv = _family(m.group("sym"))
        found.setdefault(fam, []).append((m, conv))
    for fam in ("d", "r", "or"):
        if fam not in found:
            continue
        cands = []
        for idx, (m, conv) in enumerate(found[fam]):
            v = _value(m, fam, conv)
            if v is None:
                continue
            st = star_for(table, fam, v)
            if st is None:
                continue
            pre = seg[max(0, m.start() - 24):m.start()]
            pri = 2 if _PREFER.search(pre) else 0 if _ORIG.search(pre) else 1
            cands.append((pri, -idx, st, conv, v, m.group("sym")))
        if not cands:
            return None
        best = max(cands)
        allowed = {c[2] for c in cands if c[0] == 2} if best[0] == 2 else {c[2] for c in cands}
        return best[2], fam, best[3], best[4], best[5], allowed
    return None


# ---------------------------------------------------------------- evidence stars

_META = re.compile(r"メタ分析|まとめ(?!ていない|ずに)|集めた|統合|束ね|再分析")
_RCT = re.compile(r"くじ(?!を使わない)|割り振|割り付け|ランダム|無作為|RCT")
_OBS = re.compile(r"追跡|観察|調査|コホート|自然実験|双子|くじを使わない|総説|レビュー|縦断|横断|比較研究|疫学|まとめていない")
_LOW = re.compile(r"事例|症例|質的|聞き取り|インタビュー|モデル計算|試算|シミュレーション|動物")
# negated randomisation (「くじで分けた実験ではない」「くじを使わない」) is removed before the RCT test
_NOT_RCT = re.compile(r"(?:くじ|ランダム|無作為)[^。、）)]{0,8}?(?:ではな|でない|ではありません|ていない|を使わない|なし)")
_EXP = re.compile(r"実験|試験")
_NONE = re.compile(r"本書の主張のみ|著者の主張のみ|論考|専門家の意見|理論|逸話")
# 「6万926人」「6万1千人」「11.5万人」「2万698名」「11,046社」「14,558,903組」。「3人集団」「5人組」は人数ではない
_PEOPLE = re.compile(r"(1群|各群)?\s*約?\s*(\d[\d,]*(?:\.\d+)?)\s*(万)?\s*(\d[\d,]*)?\s*(千)?\s*(?:人|名|社|組|世帯)"
                     r"(?!集団|組|ずつ|1組|一組|の班|のチーム|グループ)")
_STUDIES = re.compile(r"(\d[\d,]*)\s*の?\s*[^\d、。・人名組社（）()]{0,4}?(?:本の研究|本|研究|件の研究|試験|検証|標本|コホート|実験|レビュー|件)(?!人|名)"
                      r"|(?:研究|実験|試験)\s*(\d+)\s*本")
# research is present (not 「研究は無い」「研究なし」「実証研究ではない」)
_HAS_RESEARCH = re.compile(r"(?:研究|調査|実験|分析|データ|資料)(?!は無|は見つから|なし|が無|がない|は無い|はない|ではない|は見当たら)")
_SITES = re.compile(r"(\d+)\s*(?:施設|か所|カ所|拠点)")


_KD = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KU = {"十": 10, "百": 100, "千": 1000}


def _kanji_int(k):
    total, sect, digit = 0, 0, 0
    for ch in k:
        if ch in _KD:
            digit = _KD[ch]
        elif ch in _KU:
            sect += (digit or 1) * _KU[ch]
            digit = 0
        elif ch == "万":
            total += (sect + digit) * 10000
            sect = digit = 0
    return total + sect + digit


def _kanji_people(seg):
    """「三千人」「一万二千人」 -> 「3000人」 (canon wants Arabic numerals; read them anyway, Fable P5)."""
    return re.sub(r"(?<![\d,.万])[一二三四五六七八九十百千][一二三四五六七八九十百千万]*(?=\s*(?:人|名))", lambda m: str(_kanji_int(m.group(0))), seg)


def _people_all(seg):
    """[(size, is_person)]: 社・組・世帯 are sample units, used only for the meta-analysis ★5 size."""
    out = []
    for m in _PEOPLE.finditer(seg):
        grp, n, man, n2, sen = m.groups()
        v = _num(n) * (10000 if man else 1)
        if n2:
            v += _num(n2) * (1000 if sen else 1)
        elif sen:
            v = _num(n) * 1000
        unit = seg[m.end() - 1:m.end()]
        out.append((v * (2 if grp else 1), unit in "人名"))
    return out


def _studies(seg):
    vals = [int((a or b).replace(",", "")) for a, b in _STUDIES.findall(seg) if (a or b)]
    return max(vals) if vals else None


_CLAUSE = re.compile(r"。|と、|；|;|\s/\s")


def evidence_upper(g, seg):
    """(upper_star, exact, why) or None when the parenthesis does not decide.

    canon §2「研究の種類が混ざるときは、いちばん強い種類1つで決める。足し算しない」: the parenthesis is split into
    clauses (。・「と、」) and each clause is rated with its own people; the highest clause wins (Fable A2:
    「くじで分けた実験1本・30人。追跡研究は 5,000人」 must not count 5,030 people for the RCT)."""
    seg = _kanji_people(seg)
    whole = _upper_clause(g, seg)
    if whole and whole[1]:
        return whole
    best = None
    for c in _CLAUSE.split(seg):
        if not c.strip():
            continue
        u = _upper_clause(g, c)
        if u and not u[1] and (best is None or u[0] > best[0]):
            best = u
    return best


def _upper_clause(g, seg):
    if _NONE.search(seg) and not (_META.search(seg) or _RCT.search(seg) or _OBS.search(seg)
                                  or _LOW.search(seg) or _HAS_RESEARCH.search(seg)):
        return 1, True, "研究が無い（本書の主張のみ・論考・専門家の意見）"
    allp, n_st = _people_all(seg), _studies(seg)
    pp = [v for v, person in allp if person]
    m_people = max(v for v, _p in allp) if allp else None   # one pooled sample (meta-analysis), any unit
    m_sum = sum(pp) if pp else None                          # persons in all experiments together
    m_one = pp[0] if len(pp) == 1 else None                  # exactly one person count
    pooled = n_st is not None and n_st >= 2
    rct = bool(_RCT.search(_NOT_RCT.sub("", seg)))
    sites = max([int(x) for x in _SITES.findall(seg)] or [0])
    cand = []
    if _META.search(seg) or pooled:
        if m_people is not None and m_people >= g["meta_m"] and (n_st is None or n_st >= g["meta_n"]):
            cand.append((5, "まとめ（%s人）" % _fmt(m_people)))
        else:
            why = ("参加者の人数が書かれていない" if m_people is None else
                   "参加者 %s人 < %s人" % (_fmt(m_people), _fmt(g["meta_m"])) if m_people < g["meta_m"] else
                   "研究 %d本 < %d本" % (n_st, g["meta_n"]))
            cand.append((4, "まとめだが★5 の条件を満たさない（%s）" % why))
    if rct:
        m_people = m_sum
        if m_people is None:
            cand.append((4, "くじで分けた実験（人数なし）"))
        elif m_people >= g["rct_big"]:
            cand.append((4, "くじで分けた実験 %s人" % _fmt(m_people)))
        elif (n_st is None or n_st >= g["rct_multi_n"]) and m_people >= g["rct_multi_m"]:
            cand.append((4, "くじで分けた実験 計%s人" % _fmt(m_people)))
        elif sites >= g["sites"] and m_people >= g["sites_m"]:
            cand.append((4, "くじで分けた実験 %d施設・%s人" % (sites, _fmt(m_people))))
        elif n_st == 1 and m_people < g["rct_one"]:
            cand.append((2, "くじで分けた実験1本・%s人（%s人未満）" % (_fmt(m_people), _fmt(g["rct_one"]))))
        else:
            cand.append((3, "くじで分けた実験 計%s人（★4 の人数に届かない）" % _fmt(m_people)))
    if _OBS.search(seg):
        only_survey = re.search(r"調査", seg) and not re.search(r"追跡|追う|追った|コホート|縦断|実験|試験|データ", seg)
        if only_survey and m_one is not None and m_one < g["survey"] and len(allp) == 1:
            cand.append((2, "%s人の調査（%s人未満）" % (_fmt(m_one), _fmt(g["survey"]))))
        else:
            cand.append((3, "観察研究・調査・総説などくじを使わない研究"))
    if _LOW.search(seg):
        cand.append((2, "事例研究・質的研究・モデル計算・動物実験"))
    if _EXP.search(seg) and not (rct or _META.search(seg) or _OBS.search(seg) or pooled):
        # only 「M人の実験1本」 with M < 100 is decidable (★2 whether or not it was randomised)
        if n_st == 1 and m_sum is not None and m_sum < g["rct_one"]:
            cand.append((2, "%s人の実験1本（%s人未満）" % (_fmt(m_sum), _fmt(g["rct_one"]))))
        elif n_st == 1 and m_sum is not None and m_sum < g["rct_big"]:
            cand.append((3, "実験1本・%s人（%s人未満）" % (_fmt(m_sum), _fmt(g["rct_big"]))))
        else:
            cand.append((4, "実験（くじで分けたかは書かれていない）"))
    if not cand:
        return None
    top = max(cand)
    return top[0], False, top[1]


def _fmt(v):
    return "{:,}".format(int(v)) if float(v).is_integer() else str(v)

# ---------------------------------------------------------------- scanning


def _table_label(lines, li, col_text_before):
    """Header text of the table column holding the star on line li, or ''."""
    ln = lines[li]
    if not ln.strip().startswith("|"):
        return ""
    col = col_text_before.count("|") - 1
    k = li - 1
    while k >= 0 and lines[k].strip().startswith("|"):
        k -= 1
    k += 1
    if k + 1 <= li and re.match(r"^\s*\|?\s*:?-{2,}", lines[k + 1] if k + 1 < len(lines) else ""):
        hdr = _cells(lines[k]) or []
        return hdr[col] if 0 <= col < len(hdr) else ""
    return ""


def scan(text, table, g, line_filter=None):
    """[(line_no, code, written, expected, excerpt, why)]"""
    hits = []
    lines = text.split("\n")
    pos = 0
    for li, ln in enumerate(lines):
        if line_filter is not None and (li + 1) not in line_filter:
            pos += len(ln) + 1
            continue
        for m in _STAR.finditer(ln):
            written = int(m.group(1))
            before = ln[:m.start()]
            seg = _paren_after(ln, m.end())
            if not seg:
                # A1「効果の大きさ ★4/5・根拠の強さ ★4/5（d = 0.66、…）」: both stars share the next parenthesis
                m2 = re.match(r"\s*[・／/]\s*[^★⭐（(\n]{0,12}[★⭐]\s*[1-5]\s*/\s*5", ln[m.end():])
                if m2:
                    seg = _paren_after(ln, m.end() + m2.end())
            if not seg and not ln[m.end():].strip() and li + 1 < len(lines) and re.match(r"\s*[（(]", lines[li + 1]):
                seg = _paren_after(lines[li + 1], 0)        # A5: the value sits on the next line
            label = "evid" if _EVID_LABEL.search(before) else "eff" if _EFF_LABEL.search(before) else ""
            if not label:
                h = _table_label(lines, li, before)
                label = "evid" if "根拠の強さ" in h else "eff" if "効果の大きさ" in h else ""
            excerpt = (ln[m.start():m.end()] + ("（" + seg + "）" if seg else ""))[:70]
            if label != "evid" and table:
                e = effect_expected(table, seg)
                if e:
                    exp, fam, conv, v, sym, allowed = e
                    if written not in allowed:
                        if conv == "rr" and written > exp and re.search(r"\d\s*[%％]", ln):
                            continue  # base rate on the line: RR->OR conversion can raise it (canon §1)
                        col = {"d": "d・g", "r": "r", "or": "オッズ比"}[fam]
                        hits.append((li + 1, "E", written, exp, excerpt,
                                     "%s → %s 列で %.3g は★%d（evidence-stars.md §1）" % (sym, col, v, exp)))
                    continue
                if _NONCONV.search(seg) and label != "evid":
                    hits.append((li + 1, "N", written, 0, excerpt,
                                 "β・R²・重相関は d・r・オッズ比に直せない。星を外し向きと大きさを言葉で書く（§1）"))
                    continue
            if label == "evid" and g:
                u = evidence_upper(g, seg)
                if u:
                    up, exact, why = u
                    if written > up or (exact and written != up):
                        hits.append((li + 1, "S", written, up, excerpt, "%s → 上限★%d（evidence-stars.md §2。人数は算用数字で書く）" % (why, up)))
        pos += len(ln) + 1
    return hits


def drift(root, table):
    """Differences between scripts/star_rules.py _TH/_ONE and the canon §1 table."""
    p = os.path.join(root, STAR_RULES_REL)
    if not (table and os.path.isfile(p)):
        return []
    try:
        tree = ast.parse(io.open(p, encoding="utf-8").read())
        vals = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in ("_TH", "_ONE"):
                    vals[node.targets[0].id] = ast.literal_eval(node.value)
        th, one = vals["_TH"], vals["_ONE"]
    except Exception:
        return []
    out = []
    for k in ("d", "r", "or"):
        canon_lo = {s: table[k][s][0] for s in (5, 4, 3)}
        copy_lo = {s: lo for lo, s in th.get(k, ())}
        if canon_lo != copy_lo:
            out.append("%s: 正典 %s / star_rules %s" % (k, canon_lo, copy_lo))
        if abs(table[k][1][2] - one.get(k, -1)) > 1e-12:
            out.append("%s ★1: 正典 %s 以下 / star_rules %s" % (k, table[k][1][2], one.get(k)))
    return out

# ---------------------------------------------------------------- hook plumbing


def find_root(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(d, CANON_REL)):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd


def load_rules(root):
    try:
        canon = io.open(os.path.join(root, CANON_REL), encoding="utf-8").read().replace("\r\n", "\n")
    except Exception:
        return None, None
    return parse_effect_table(canon), parse_evidence_rules(canon)


def _touched_lines(text, news):
    out = set()
    for ns in news:
        ns = (ns or "").replace("\r\n", "\n")
        if not ns.strip():
            continue
        start = 0
        while True:
            i = text.find(ns, start)
            if i < 0:
                break
            a = text.count("\n", 0, i) + 1
            b = a + ns.count("\n")
            out.update(range(a, b + 1))
            start = i + max(1, len(ns))
    return out


def check(path, tool="Write", news=None):
    """Returns (hits, drift_list, root)."""
    root = find_root(path)
    if not root:
        return [], [], None
    table, g = load_rules(root)
    ap = os.path.normcase(os.path.abspath(path))
    if ap in (os.path.normcase(os.path.join(root, CANON_REL)), os.path.normcase(os.path.join(root, STAR_RULES_REL))):
        return [], drift(root, table), root
    if not re.search(r"\.(md|markdown)$", path, re.I):
        return [], [], root
    # _meta/ holds records of past states (caveat_triage, pickup_scores quote the stars as they were before the
    # 2026-10-23 re-cut: 5 hits on 2026-10-26, all historical quotes) -- recomputing them would rewrite history
    rel = os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    if rel.startswith("_meta/"):
        return [], [], root
    try:
        text = io.open(path, encoding="utf-8").read().replace("\r\n", "\n")
    except Exception:
        return [], [], root
    lf = None
    if tool in ("Edit", "MultiEdit") and news is not None:
        lf = _touched_lines(text, news)
        if not lf:
            return [], [], root
        tl = text.split("\n")
        lf |= {n - 1 for n in lf if n >= 2 and n - 1 <= len(tl) and re.match(r"\s*[（(]", tl[n - 1])}
    return scan(text, table, g, lf), [], root


def _targets(ev):
    ti = ev.get("tool_input") or {}
    tool = ev.get("tool_name") or ""
    files = list(ti.get("_codex_files") or [])
    if not files and ti.get("file_path"):
        files = [ti.get("file_path")]
    news = None
    if tool == "Edit":
        news = [ti.get("new_string") or ""]
    elif tool == "MultiEdit":
        news = [e.get("new_string") or "" for e in (ti.get("edits") or [])]
    if ti.get("_codex_files"):
        tool, news = "Write", None
    return tool, files, news


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass
    try:
        ev = _codex_normalize(json.loads(sys.stdin.buffer.read().decode("utf-8", "replace")))
    except Exception:
        return
    tool, files, news = _targets(ev)
    msgs = []
    for f in files:
        if not (f and os.path.isfile(f)):
            continue
        hits, dr, _root = check(f, tool, news)
        if dr:
            msgs.append("%s: scripts/star_rules.py の表の写しが正典 evidence-stars.md §1 と違う: %s。"
                        "写しを正典に合わせる（逆に写しが正しいなら正典を直す）" % (os.path.basename(f), "; ".join(dr)))
        if hits:
            lst = ["  %s:%d ★%d/5 → %s ｜ %s ｜ %s" % (os.path.basename(f), ln, w, ("★%d/5" % e) if e else "星なし", ex, why)
                   for ln, _c, w, e, ex, why in hits[:MAX_LIST]]
            more = "" if len(hits) <= MAX_LIST else "\n  ほか %d か所" % (len(hits) - MAX_LIST)
            msgs.append("星の数が、カッコ内の値・研究の規模から正典の表で再計算した星と %d か所食い違う:\n%s%s"
                        % (len(hits), "\n".join(lst), more))
    if not msgs:
        return
    _record_firing(NAME, ev)
    reason = ("[rating_recompute_guard] " + "\n".join(msgs) +
              "\n星は語感で決めず、カッコ内の値を _meta/prompts/evidence-stars.md の表で引いて付ける。"
              "星を直したら近くの言い方（大きい部類・ごく小さい等）も表に合わせる。根拠の強さは上限だけを見ている"
              "（追試で再現されない等で下げるのは可）。")
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


def _cli(argv):
    """--scan <file>...: print every disagreement (calibration)."""
    total = 0
    for f in argv:
        hits, dr, root = check(f)
        for d in dr:
            print("%s DRIFT %s" % (f, d))
        for ln, c, w, e, ex, why in hits:
            total += 1
            print("%s:%d\t%s\t★%d->%s\t%s\t%s" % (f, ln, c, w, ("★%d" % e) if e else "none", ex, why))
    print("TOTAL %d" % total)


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        _cli(sys.argv[2:])
        sys.exit(0)
    try:
        main()
    except Exception:
        pass
