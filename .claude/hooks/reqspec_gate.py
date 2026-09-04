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
    if len(body) <= 60 and not _has_imperative(body):
        return

    # ensure_ascii + binary write: several kanji end in byte 0x5C under CP932
    # (「表」= 0x95 0x5C), which corrupts JSON emitted through a text stream.
    payload = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": REQSPEC,
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
