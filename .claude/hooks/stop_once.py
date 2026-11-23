# -*- coding: utf-8 -*-
"""Shared limiter for every Stop hook: at most ONE block per hook per human instruction,
and no block at all while the model is only waiting for its own background work.

WHY (2026-11-22, user: 「なんで、こんなに細切れに合計で大量の報告してくるんだ？読みにくすぎだし、
ユーザーに不要だろが大半が。最終報告以外は、ほぼゼロか一行程度ってルールはどうなった？」)
----------------------------------------------------------------------------------------
Measured on the interactive sessions 2026-11-15..22 (127 human instructions, 16 sessions):
  * 46.5% of instructions got 4+ separate assistant messages (median 3, max 77).
  * The biggest source of messages after the 2nd: Stop-hook pushbacks (185), then
    subagent wakes (205 = peer 138 + notify 67), scheduled wakes (43).
  * A hook's 「1回のみ」 was per TURN, and one instruction has many turns (every subagent
    completion wakes the model). review_gate re-fired 276 times inside the same instruction,
    existence gate 27, report_render 31, completion check 26 (all repeats, 2026-11-15..22 window
    of all sessions). Every pushback forces one more visible message.
  * On wakes with background work still pending, 83 of 157 still wrote text.
    A pushback on such an interim line makes a second interim line.

CONTRACT
--------
    import stop_once; stop_once.install("review_gate")     # first lines of main(), before stdin is read

install() reads stdin once and puts it back (sys.stdin stays readable, text or .buffer).
For a Stop event it captures stdout; at exit, a {"decision": "block"} output is passed through
only if (a) this hook has not blocked yet for the current human instruction and (b) the turn was
not started by a background wake while background tasks are still pending. Everything else
(non-Stop events, non-block output, parse failures) passes through unchanged.

State: ~/.claude/state/stop_once/<session>/<hook>.json = {"key": <instruction id>}; one file per
hook so concurrently running Stop hooks never race. Suppressions are appended to
~/.claude/state/stop_once/suppressed.jsonl (counts only) for calibration.

FAIL-OPEN: any error inside this module passes the hook's output through untouched.
Deployed from claude-governance/templates/hooks/ -- edit there.
"""
import atexit
import hashlib
import io
import json
import os
import re
import sys
import time

STATE_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "state", "stop_once")


def _is_block(data):
    try:
        obj = json.loads(data.decode("utf-8", "replace").strip() or "{}")
    except Exception:
        return False
    return isinstance(obj, dict) and obj.get("decision") == "block"


QUEUED_WAKE = ("<task-notification>", "<agent-message", "<cross-session", "Another Claude session")


def _queued_human(r):
    """A prompt the human typed while the model was working: recorded only as a queued_command
    attachment (Fable 2026-11-22 S2). Notifications use the same row type with a wake prefix."""
    if r.get("type") != "attachment":
        return False
    a = r.get("attachment") or {}
    p = a.get("prompt")
    return (a.get("type") == "queued_command" and isinstance(p, str) and p.strip() != ""
            and not p.lstrip().startswith(QUEUED_WAKE))


def instruction_state(tp):
    """-> (instruction key, pending background task ids) for the transcript tail."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import response_length_guard as g
    rows = g.read_rows(tp, need_boundary=True)
    start = None
    for i in range(len(rows) - 1, -1, -1):
        if g._is_boundary(rows[i]) or _queued_human(rows[i]):
            start = i
            break
    if start is None:
        # No human prompt in the readable tail (resumed file, a turn over the read limit):
        # one key for the whole tail, so the hook still blocks at most once (Fable S4).
        return "tail", frozenset()
    b = rows[start]
    # No uuid (old or hand-made transcripts): the prompt, its time and the row before it, so the same
    # words typed again later are a new instruction.
    prev = json.dumps(rows[start - 1], ensure_ascii=False, sort_keys=True)[:2000] if start else ""
    key = b.get("uuid") or hashlib.sha1(
        (g._user_text(b) + str((b.get("attachment") or {}).get("prompt")) + str(b.get("timestamp")) + prev
         ).encode("utf-8", "replace")).hexdigest()[:16]
    # Pending = launched in this instruction and not yet reported done, whatever started the
    # current turn (Fable S1a: a 「待ちます」 stop inside the human turn itself must not use up the block).
    launched, done = g.pending_tasks(rows[start:])
    return key, frozenset(launched - done)


def decide(hook, ev):
    """True = let the block through (and remember it)."""
    tp = ev.get("transcript_path")
    if not tp or not os.path.exists(tp):
        return True
    key, pending = instruction_state(tp)
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(ev.get("session_id") or "nosession"))[:60]
    # The transcript file is part of the identity: a session id reused with another transcript
    # (tests, a resumed copy) is another conversation.
    sid += "_" + hashlib.sha1(os.path.normcase(os.path.abspath(tp)).encode("utf-8", "replace")).hexdigest()[:8]
    d = os.path.join(STATE_ROOT, sid)
    p = os.path.join(d, hook + ".json")
    st = {}
    try:
        with io.open(p, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    if st.get("key") == key and st.get("blocked"):
        _log(hook, sid, "already_blocked")
        return False
    if pending:
        # Interim stop while own background work runs: hold the block, do not use it up. The same
        # pending set is held only once (Fable S1b: a task that never notifies must not mute the hook).
        ps = ",".join(sorted(pending))
        if not (st.get("key") == key and st.get("held") == ps):
            _save(d, p, {"key": key, "held": ps, "t": int(time.time())})
            _log(hook, sid, "pending")
            return False
    _save(d, p, {"key": key, "blocked": 1, "t": int(time.time())})
    return True


def _save(d, p, obj):
    try:
        os.makedirs(d, exist_ok=True)
        with io.open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    except Exception:
        pass


def _log(hook, sid, why):
    try:
        os.makedirs(STATE_ROOT, exist_ok=True)
        with io.open(os.path.join(STATE_ROOT, "suppressed.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "hook": hook, "sid": sid[:8], "why": why}) + "\n")
    except Exception:
        pass


class _Sink(io.BytesIO):
    """Capture buffer that survives a hook re-wrapping or closing sys.stdout (Fable S5)."""
    def close(self):
        pass


# Remote Control (2026-11-23, user: 「スマホの画面で見ると、あなたの回答が一部しか載っていません」):
# the phone shows only the last answer of an instruction, so every pushback -- from any hook --
# must be answered with the complete answer, not an add-on or 「以上」 (Fable S2: one place).
REMOTE_NOTE = (u"\n【Remote Control】このセッションはスマホにつながっており、スマホには最後の回答しか表示されない。"
               u"この差し戻しへの回答は、追記や「以上」ではなく、前の回答を置き換える完全版"
               u"（結論・表・成果物表・留保・Next Action）にする。前の回答を参照しない。")
BRIDGE_MARK = b'"type":"bridge-session"'
BRIDGE_TAIL = 2 * 1024 * 1024


def _remote_note(data, ev):
    try:
        if not _is_block(data):
            return data
        with io.open(ev.get("transcript_path") or "", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - BRIDGE_TAIL))
            if BRIDGE_MARK not in f.read():
                return data
        obj = json.loads(data.decode("utf-8", "replace").strip())
        reason = obj.get("reason") or ""
        if "Remote Control" in reason:
            return data
        obj["reason"] = reason + REMOTE_NOTE
        return json.dumps(obj, ensure_ascii=True).encode("ascii")
    except Exception:
        return data


def install(hook=None):
    if os.environ.get("ANSWER_PRECHECK") == "1":
        return   # answer_precheck shows every pushback on the draft; its HOME is a copy (Fable S6)
    hook = hook or os.path.splitext(os.path.basename(sys.argv[0] or "hook"))[0]
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return
    sys.stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="replace")
    try:
        ev = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return
    if not isinstance(ev, dict) or ev.get("hook_event_name") != "Stop":
        return
    real = sys.stdout
    cap = _Sink()
    wrapper = io.TextIOWrapper(cap, encoding="utf-8", errors="replace", write_through=True)
    sys.stdout = wrapper

    def _finish():
        try:
            try:
                wrapper.flush()
                if sys.stdout is not wrapper:
                    sys.stdout.flush()
            except Exception:
                pass
            data = cap.getvalue()
            if not data:
                return
            try:
                ok = (not _is_block(data)) or decide(hook, ev)
            except Exception:
                ok = True
            if ok:
                data = _remote_note(data, ev)
                real.buffer.write(data)
                real.buffer.flush()
        except Exception:
            pass

    atexit.register(_finish)
    return True
