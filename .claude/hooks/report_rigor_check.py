# -*- coding: utf-8 -*-
"""Detect unfalsifiable / over-claimed assertions in analysis reports (検証不足対策).

Targets the pattern the user repeatedly attacked:
  「本当にまだ試してないんですか？…検証計画に穴がありそう」(2026-07-01)
  「推測ではなく事実確認して分析して対策して」(2026-06-29)

It does NOT try to judge whether an analysis is correct — that is not
mechanically decidable. Instead it flags COMPLETENESS CLAIMS made without an
adjacent scope limit, which is exactly the failure mode the user caught.

CLAIM  : 網羅的/すべて検証/全パターン/他にない/最適/確定 …
ANCHOR : 未検証/対象外/スコープ外/限界/留保/前提/除外/サンプル/条件付き …

A claim is a finding only when NO anchor appears within WINDOW lines of it.
Regression-only usage (see hook) means pre-existing debt never blocks work.
"""
import re

CLAIM = re.compile(
    r"網羅的に(調査|検証|探索|試|分析)|網羅した|すべて(の)?(を)?(検証|試|探索|カバー)"
    r"|全(パターン|ケース|条件|候補)(を)?(検証|試)"
    r"|他に(は)?(候補|選択肢|方法)は?(ない|無い)|最適(である|です)|確定(した|です|である)"
    r"|完全に[^。\n]{0,12}(解消|解決|排除|網羅|一致)|漏れ(は)?(ない|無い)|すべて洗い出"
)
# 「確定した」は日本語の平叙な過去形としても多用される。2026-08-04 の実コーパス監査
# （16件中12件が誤検知）では、以下がすべて「網羅性の主張」ではなかった:
#   ・確定した損益 / 確定した違反は5件 / 確定した事例（＝会計・事実記述の名詞句）
#   ・TOP3 候補が確定した後、再検索する（＝手順の記述）
#   ・確定した最重要事実（＝判明した、の意）
# 主張として扱うのは「◯◯と確定した」等の断定形に限り、名詞を直接修飾する連体用法と
# 「確定した後/時点で」等の時系列用法は除外する。
KAKUTEI_BENIGN = re.compile(
    r"確定した(?:[^\s。、]{0,4}?)"
    r"(?:損益|利益|申告|拠出|金額|数値|違反|事例|事実|情報|日|後|時点|時|ら|場合|"
    r"内容|結果として|もの|一覧|の(?:は|が|を|で))"
)
# 否定・反実の文脈にある主張は「主張していない」。
#   例: 「バナナを完全に排除するのは合理的でない」
NEGATED = re.compile(r"(?:ない|無い|べきでな|できな|しな)(?:い|く|かった)?[^。\n]{0,6}$|"
                     r"は合理的でな|とは言えな|わけではな|とは限らな")
# 「ほぼ完全に一致」「概ねすべて」等、程度を弱める副詞が直前に付く場合は
# 断定的な網羅主張ではない（＝それ自体が留保表現）。2026-08-04 実コーパスで
# 「公表値$8.70/日とほぼ完全に一致しており、手法の妥当性を確認済み」を誤検知。
HEDGED = re.compile(r"(?:ほぼ|概ね|おおむね|ほとんど|大部分|実質的に|事実上)\s*"
                    r"(?:完全に|すべて|全て|網羅)")
# Table rows are usually cited source material (paper titles etc.), not our own claims.
TABLE_ROW = re.compile(r"^\s*\|")
# "v26.0で確定した" / "2026-05-12に確定した" — a changelog pointer, not a completeness claim.
VERSION_LABEL = re.compile(r"v?\d+(?:\.\d+)?\s*(?:版)?\s*で確定した|\d{4}-\d{2}-\d{2}\s*(?:に)?確定した")
ANCHOR = re.compile(
    r"未検証|未実施|対象外|スコープ外|範囲外|限界|留保|前提|除外|条件付き|サンプル|一部|"
    r"のみ|に限[るり]|想定|可能性|今後|残課題|TODO|要検証|不明|推定"
)
WINDOW = 6  # lines of context on each side


def _strip_uncheckable(text):
    out = list(text)

    def blank(m):
        # Keep newlines — blanking them collapses the line count, which shifts
        # every reported line number and slides the ±WINDOW anchor context onto
        # unrelated lines. (Same bug as numeric_precision_check, 2026-08-04.)
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "

    for m in re.finditer(r"```.*?```", text, flags=re.DOTALL):
        blank(m)
    for m in re.finditer(r"<!--.*?-->", text, flags=re.DOTALL):
        blank(m)
    return "".join(out)


def analyze_text(text):
    """Return findings: completeness claims lacking a nearby scope anchor."""
    if not text:
        return []
    lines = _strip_uncheckable(text).split("\n")
    findings = []
    for i, ln in enumerate(lines):
        if TABLE_ROW.match(ln):
            continue  # cited source rows, not our own assertion
        if VERSION_LABEL.search(ln):
            # "v26.0で確定した検証" is a changelog label naming WHEN a decision was
            # taken, not a claim that the analysis is exhaustive. (2026-08-04 audit:
            # this pattern alone produced 14 of 70 findings, all in one file.)
            continue
        m = CLAIM.search(ln)
        if not m:
            continue
        if m.group(0).startswith("確定") and KAKUTEI_BENIGN.search(ln):
            continue  # 過去形の事実記述であって網羅性の主張ではない
        if NEGATED.search(ln):
            continue  # 否定文脈では主張が成立していない
        if HEDGED.search(ln):
            continue  # 「ほぼ完全に」等の緩和表現は断定的な網羅主張ではない
        lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
        context = "\n".join(lines[lo:hi])
        if ANCHOR.search(context):
            continue  # claim is scoped -> acceptable
        findings.append({
            "line": i + 1,
            "claim": m.group(0),
            "text": ln.strip()[:90],
        })
    return findings
