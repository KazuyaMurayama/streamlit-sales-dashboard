# -*- coding: utf-8 -*-
"""UserPromptSubmit hook: require requirements-definition before high-stakes work.

THE PROBLEM
-----------
The user's rules already mandate invoking planning skills ("必須・スキップ禁止")
before creative work. They report that up-front requirements work is still
inadequate — which is evidence, not opinion, that mandatory-by-prose does not
bind. The reason is the same one recorded for the stale-date defect: a model
that believes it understands the request will not stop to define requirements,
because nothing feels wrong. Prose cannot fire when the author has already
(mistakenly) concluded it is unnecessary.

WHAT THIS DOES
--------------
On every prompt, injects a short instruction via `additionalContext` telling the
model to state a REQSPEC — goal, explicit requirements, DERIVED requirements,
assumptions, out-of-scope — before starting high-stakes work.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not classify the prompt by keywords or length, and it does not block.

Measured (1,270 real turns, 2026-08-24): 56% of this user's prompts carry
>=2,000 chars of bare pasted prose — quoted rules, prior answers, tables. Every
keyword scan of the prompt therefore reads pasted text as intent ("repo delete"
fired 272x, all quoted rules). Prompt-length thresholds are equally useless:
typed-prompt length is bimodal (p25=277, median=8,055) and measures "did they
paste something", not complexity. So at UserPromptSubmit time — before any tool
has run — there is NO reliable signal for how consequential the turn will be.

The honest consequence: the real gate is at Stop (review_gate.py), where the
outcome IS observable (files written, report produced, judgement asserted). This
hook is the cheap front half — it plants the requirement to think first, at a
cost of ~60 tokens, and lets the back half enforce coverage against the answer.
Claiming more than that would be the same over-confidence this system exists to
catch.

BLOCKING IS NOT USED, on purpose. `deny` here would reject the user's prompt
outright — a terrible failure mode for a heuristic that cannot see the outcome.

FAIL-OPEN: any exception -> exit 0.
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

# Kept deliberately short — this is paid on every non-trivial prompt.
REQSPEC = (
    "【要件定義ゲート】着手前に、ファイル変更や成果物作成を伴うなら "
    "REQSPEC を数行で述べてから始めること:\n"
    "・ゴール: 達成状態を1文で（作業内容ではなく「何がどうなれば完了か」）\n"
    "・明示要件: ユーザーが実際に書いた依頼（逐語）\n"
    "・派生要件: 明示されていないが当然含まれるもの。"
    "ゼロ件なら要件定義できていないと考えること\n"
    "・前提: 確認せず仮定した事項。「前提: 〜と解釈した。違えば言ってくれ」と"
    "宣言する（質問して止まらない＝ルール6）\n"
    "・対象外: 今回やらないと決めたこと\n"
    "重要な判断を含む場合は、着手前に Fable でこの REQSPEC を反証させること"
    "（自分の計画を自分でQCしない）。"
    "軽微な質問・調査のみのターンでは省略してよい。"
)


def _has_imperative(text):
    """True if a short prompt asks for an ACTION rather than an answer.

    Only consulted for prompts <=60 chars, so pasted material never reaches it.
    Deliberately generous: when in doubt this returns True and the (cheap,
    self-limiting) instruction is injected. A missed injection costs a turn of
    unstated assumptions; a false one costs ~200 tokens.
    """
    import re
    return bool(re.search(
        r"して|してくれ|しろ|せよ|たい$|ほしい|作|直|書|実装|修正|追加|削除|"
        r"変更|展開|調査|検討|設計|作成|確認|整備|移行|対応|"
        r"make|create|fix|add|write|implement|update|change|build|refactor",
        text or ""))


# ---------------------------------------------------------------------------
# COUNTERMEASURE REQSPEC (added 2026-09-11)
#
# WHY A SECOND, SPECIFIC BLOCK
# countermeasure_gate.py enforces the 5-defect rule -- but it fires at STOP,
# after the plan has been written and shown to the user. On 2026-09-11 the user
# asked for a countermeasure and the plan that came back had NO adversarial
# verification and NO independent QC, both of which the user's own rule
# requires. Nothing stated those requirements AT THE MOMENT THE PLAN WAS BEING
# FORMED. Enforcement at the end cannot prevent a bad plan; it can only reject
# one. This block is the front half.
#
# IS A PROMPT KEYWORD SCAN SAFE HERE?
# This module's own docstring warns that prompt scans misfire because 56% of
# prompts are pasted prose -- and the countermeasure RULE TEXT itself contains
# 再発防止, so a pasted CLAUDE.md would match a naive scan. Measured on 2,857
# real prompts:
#     naive 「再発防止」 anywhere        40  (1.40%)
#     ask + FIX VERB, typed-only       36  (1.26%)
#     naive fires, typed-only does not  4   <- pasted rule text, skipped
# 21 distinct; all but two are genuine requests. Requiring a FIX VERB next to
# the topic, evaluated on the TYPED body with pasted blocks stripped, is what
# makes it safe. Do not loosen to the topic word alone.
CM_ASK_RE = re.compile(
    u"(?:再発防止|恒久対策|再発を?防|二度と(?:起こ|同じ|繰り返)"
    u"|同じ(?:ミス|問題|失敗)を?(?:繰り返|起こ)さな"
    u"|同様の(?:問題|ミス|失敗)[^。\n]{0,10}(?:防|起こ)"
    u"|(?:何回|何度|複数回|繰り返し)[^。\n]{0,16}(?:ミス|失敗|発生|起こ)"
    u"|毎回必ず[^。\n]{0,16}(?:防|起動))",
    re.IGNORECASE)

CM_FIX_RE = re.compile(
    # ⚠️ Built from REAL phrasings, not invented ones. The first draft
    # required 「更新して」 and therefore missed the user's actual words
    # 「更新をかけてください」 (2026-09-11) -- the very message this block
    # exists for. Accept a particle between the noun and the verb, and
    # accept かけて/くわえて which this user uses often.
    u"(?:立てて|計画して|実行して|対策して|考えて|作って|やって|防いで|直して"
    u"|修正|改善|反映|更新|検討|対応)(?:を?(?:かけて|くわえて|加えて|して))?"
    u"(?:ください|下さい|ほしい|欲しい)"
    u"|(?:修正|改善|反映|更新|検討|対応|変更)(?:を)?(?:かけて|くわえて|加えて|して)"
    u"|防ぐように|防止して"
    u"|お願いし|してください|して下さい|してほしい|して欲しい"
    u"|せよ|しろ|してくれ|できますか|ないでください"
    u"|(?:不十分|甘い|できていない|意味が(?:ほぼ)?無|意味がない|応えな"
    u"|終わったこと|限定すぎ|ほとんど発火|繰り返して)")

# Kept deliberately short: this is injected on ~1.3% of prompts, and a wall of
# text at prompt time is how an injection gets skimmed instead of read.
CM_BLOCK = u"""【再発防止 REQSPEC — 着手前に必須。ルール文章の追記だけで終えてはならない】
これは再発防止の依頼である。対策そのものを成果物とみなし、下記を計画に含めてから着手すること:
・クラス化: 指摘された1件でなく「不変条件」を1文で定義する（固有文字列で塞がない＝類似問題も防ぐ）
・機械化: 散文でなくフック/スクリプトで強制する。全リポ＋グローバルへ配布する
・攻撃的検証: 自作テストの合格は証拠にならない。回避文面を別モデル(Fable)に生成させ逐語でケース化する
・赤緑: 当時の欠陥版に当てて FAIL することを確認する（直した版で PASS しても何も証明しない）
・較正: 実データで発火率を実測する（高すぎれば形骸化、0%なら死んでいる）
・独立QC: 自分の計画を自分でQCしない。最終チェックは Fable に反証させる
・完了条件: python scripts/countermeasure_ledger.py と scripts/audit_countermeasures.py を実行し実出力を貼る
正典: ~/.claude/CLAUDE.md の「再発防止策の実効性」ブロック"""


def main():
    # Defer to a registered repo-local copy (existing convention).
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        raw = sys.stdin.buffer.read()
        ev = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return

    prompt = ev.get("prompt") or ev.get("user_prompt") or ""
    if not prompt:
        return

    try:
        import turn_classify as tc
    except Exception:
        return

    # Only two prompt-derived facts are trustworthy here (see docstring):
    # an explicit override, and whether this is a bare continuation.
    if tc.is_continuation(prompt):
        return
    # A short interrogative with no imperative is a question, not a task.
    # This is the one prompt-shape judgement that survives the pasting problem,
    # because it keys on the prompt being SHORT — a pasted prompt never is.
    # Without it the gate injected 326 chars onto 「このファイル何？」, which is
    # precisely the crying-wolf behaviour that gets a guard switched off.
    body = tc.strip_pasted(tc.strip_wrappers(prompt)).strip()

    # A countermeasure request gets the specific block INSTEAD of the generic
    # one, and is exempt from the short-question early return: 「どのようにして
    # 再発防止し、二度と起こらないようにできますか？」 is a question in form and
    # a commission in substance.
    is_cm = bool(CM_ASK_RE.search(body) and CM_FIX_RE.search(body))

    if not is_cm and len(body) <= 60 and not _has_imperative(body):
        return

    # ensure_ascii + binary write: several kanji end in byte 0x5C under CP932
    # (「表」= 0x95 0x5C), which corrupts JSON emitted through a text stream.
    payload = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (CM_BLOCK if is_cm else REQSPEC),
        }
    }, ensure_ascii=True)
    # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
    _record_firing("reqspec_gate", ev)
    sys.stdout.buffer.write(payload.encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
