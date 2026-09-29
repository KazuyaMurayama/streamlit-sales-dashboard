# -*- coding: utf-8 -*-
"""Stop hook: block an answer that hands the user work Claude could do itself.

WHY (2026-09-29, loop action C03 -- reports/CORRECTION_DIGEST_20260929.md)
-------------------------------------------------------------------------
Defect class C03「ユーザーへの丸投げ・不要な確認」: 20 corrections in 30 days
(「Claude Code側でできるのでは？」「言われなくてもやって」「明らかなミスは
ユーザーに聞くな」), and the most expensive class: answering them cost 2.65億
context tokens. In 18 of the 20 cases the answer before the correction put
the hand-off in its closing lines -- usually the Next Action -- as「〜を実行
して結果を教えてください」「ご指示いただければ実施します」「お決めください」.

The rule already exists in prose (CLAUDE.md §11.2: ask the user only for
①権限がない ②本人しか知らない情報 ③本人の意思決定). Prose did not stop it,
because the Next Action format itself pulls toward handing something over.

WHAT IT DOES
------------
If the closing part of the final answer asks the user to operate, report
back, or approve, the stop is blocked ONCE with the §11.2 test. Claude then
either does the work itself, or keeps the request and labels it with the
reason, e.g. 「（本人の判断）」「（権限）」「（本人のみ）」. A labelled request
passes, so a legitimate question costs one short rewrite, not a loop.

CALIBRATION (measured 2026-09-29, tests/calibrate_delegation_guard.py, 418
real instructions over 30 days, the hook's own decide() imported):
    fires on 11.7% of answers; catches 9 of the 20 answers the user corrected
    as C03. Rejected wider sets: every 「〜してください」+decision requests
    42.5% (15/20); adding 「〜してください」 alone 15.8% (10/20); decision
    requests without a recommendation 21.1% (9/20, no gain).
The 11 misses are decision requests (「お決めください」「ご判断ください」),
which look the same as legitimate ③本人の意思決定 questions.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
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

NAME = "delegation_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

# Two shapes only. Broader patterns (any 「〜してください」 or any request for a
# decision) fired on 42.5% of real answers -- a guard that fires on half
# of all answers is noise (calibration 2026-09-29, see WHY above).
DELEGATE = re.compile(
    # 1. a conditional offer addressed to the user: "tell me and I will do it".
    #    Bare 「〜があれば修正する」 is NOT here: that is Claude's own plan.
    r"(?:いただければ|いただけたら|頂ければ|もらえれば|もらえたら|くだされば|ご指示あれば|指示があれば"
    r"|ご希望(?:が)?あれば|お申し付け)[^。]{0,20}(?:実施|実行|着手|進め|対応|作成|修正|反映|直し)"
    r"|(?:着手|実施|実行|進め|修正|対応)(?:して)?(?:も)?(?:よければ|よろしければ|いいなら)"
    r"|よければ一言|進めてよいか|進めてよろしいですか|実施してよいか"
    # 2. run-and-report: the user operates, Claude waits for the output
    #    (may span a line break: 「1. 実行 / 2. 結果を貼ってください」)
    r"|(?:実行|試し|確認|開い|押し|起動|入れ|操作)[^。]{0,60}(?:結果|出力|表示|最終行|RESULT|エラー|届いたか|出たか|あるか|できたか)"
    r"[^。]{0,30}(?:教えて|貼って|送って|返して|返信して|お知らせ|ご共有|共有して)")
LABEL = re.compile(r"（(?:権限|本人のみ|本人の判断|本人の意思決定|本人しか知らない)）"
                   r"|本人しか(?:知らない|できない)|権限が(?:ない|無い)|本人の意思決定")


def closing(answer):
    """The part of the answer that hands something over: from the last
    「Next Action:」 label (at a line start) if there is one, otherwise the last
    300 characters. Code blocks and 「quoted」 text are removed first -- an
    answer that quotes a hand-off phrase is not making one."""
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    a = re.sub(r"「[^」]{0,200}」", "「」", a)
    m = list(re.finditer(r"(?m)^\W{0,4}Next Action\W{0,4}[:：]", a))
    return a[m[-1].start():] if m else a[-300:]


def decide(answer):
    """Return the matched hand-off phrase, or None. A run-and-report may span
    a line break, so the whole closing is searched; a label excuses only the
    sentence it sits in."""
    tail = closing(answer)
    for hit in DELEGATE.finditer(tail):
        s = tail.rfind("。", 0, hit.start()) + 1
        e = tail.find("。", hit.end())
        if not LABEL.search(tail[s:e if e >= 0 else len(tail)]):
            return hit.group(0)
    return None


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    """A prompt the user typed -- not a tool result or harness notification."""
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":     # subagent hand-backs, task notifications
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def read_turn(tp):
    """(last human prompt, its timestamp, final assistant text of this turn)."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, answer = None, "", ""
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            prompt, pts, answer = _text(d.get("message")).strip(), d.get("timestamp", ""), ""
        elif d.get("type") == "assistant":
            t = _text(d.get("message")).strip()
            if t:
                answer = t
    return prompt, pts, answer


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return
    prompt, pts, answer = read_turn(tp)
    hit = decide(answer) if prompt else None
    if not hit:
        return
    # keyed on the prompt's timestamp too: the same words sent again later
    # (「再開して」) are a new instruction and must be checked again
    key = hashlib.sha1((pts + (prompt or "")).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_") + "_" + key)
    if os.path.exists(mark):
        return          # already blocked once for this instruction
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    reason = ("【丸投げ検査（1回のみ）】回答の締めがユーザーへの作業・承認の依頼になっている（「%s」）。"
              "ユーザーに頼んでよいのは ①権限がない ②本人しか知らない情報 ③本人の意思決定 だけ（CLAUDE.md §11.2）。"
              "該当しないなら、今このターンで自分で実行し、結果を報告し直せ（確認・操作・結果取得・明らかなミスの修正・"
              "推奨が明確な次の手順は自分でやる）。該当するなら依頼は残してよいが、その行に理由を"
              "「（権限）」「（本人のみ）」「（本人の判断）」のいずれかで明記せよ。" % hit)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
