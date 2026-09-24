# -*- coding: utf-8 -*-
"""PreToolUse hook (all tools): warn when ONE user instruction has run too many
main-agent turns, or when every turn is re-sending a very large context.

WHY THIS EXISTS (2026-09-21, measured -- not chosen)
----------------------------------------------------
Over 48h (2026-09-18/19) Claude Code consumed 981M tokens. 95.9% of them were
cache READS -- the same context re-sent on every turn. Output was 0.4%. The
tool results actually read in that window totalled ~0.46M tokens, i.e. each
piece of data was re-sent ~2,100 times on average.

The cost is a product: (turns per instruction) x (context per turn). Single
short instructions ("進めて", "1から3、どれも。") ran 177-519 turns at
19-27万 tokens per turn. The user's verdict: 4-5 research reports reviewed
once or twice should never cost this much.

Nothing in the harness shows the model either factor. Context grows silently
and turns accumulate silently, so the model cannot notice that it is in the
expensive regime. This hook makes both numbers visible at the moment of the
next tool call, and says what to do about them.

WHAT IT DOES NOT DO
-------------------
It never blocks. Denying a tool call mid-edit leaves files half-written,
which costs more turns to repair than it saves. It does not see subagent
turns (they live in separate transcript files).

INCREMENTAL READ
----------------
Transcripts reach 100MB. State under ~/.claude/state/context_budget_guard_offsets/
<session>.json keeps the byte offset already processed, so each call reads
only what was appended since the last tool call. On first sight of a session
only the last TAIL_BYTES are scanned (the turn count is then a lower bound).

CALIBRATION: tests/calibrate_context_budget_guard.py replays real transcripts
through step() -- numbers are recorded in docs/TOKEN_EFFICIENCY_20260924.md.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

NAME = "context_budget_guard"
TURN_WARN = int(os.environ.get("CBG_TURN_WARN", "120"))   # main turns since last human instruction
TURN_STEP = int(os.environ.get("CBG_TURN_STEP", "80"))    # re-warn every N turns after that
CTX_WARN = int(os.environ.get("CBG_CTX_WARN", "300000"))  # tokens re-sent per turn (re-armed after compaction)
CUM_WARN = int(os.environ.get("CBG_CUM_WARN", "20000000"))  # tokens consumed by one instruction
TAIL_BYTES = 4 * 1024 * 1024
# NOT state/<NAME>/: firing_log writes state/<NAME>/<sid>.json, and sharing that
# path let each firing record overwrite the byte offset (test 7c).
STATE_DIR = os.environ.get("CBG_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state", NAME + "_offsets")

AUTO_PREFIXES = ("<task-notification", "<local-command", "<command-name>",
                 "Caveat:", "[Request interrupted")


def new_state():
    return {"offset": 0, "turns": 0, "last_id": None, "ctx": 0, "cum": 0,
            "next_turn_warn": TURN_WARN, "next_cum_warn": CUM_WARN,
            "ctx_warned": False, "prompt": ""}


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_human_prompt(d):
    """A real instruction typed by the user -- not a tool result, hook feedback,
    background-task notification, slash command or compaction summary.
    Only typed prompts carry promptSource/permissionMode (checked 2026-09-24
    against 48 record variants in a real transcript)."""
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return False
    if d.get("isCompactSummary"):
        return False
    if "promptSource" not in d and "permissionMode" not in d:
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result"
                                   for b in c):
        return False                      # a tool result is never an instruction
    t = _text(d.get("message")).lstrip()
    return bool(t) and not t.startswith(AUTO_PREFIXES)


def step(st, d):
    """Feed one transcript record. Returns the list of warning kinds it fired."""
    fired = []
    if is_human_prompt(d):
        # ctx_warned is deliberately NOT reset: context is a property of the
        # session, and re-warning on every new instruction fired on 53.8% of
        # real instructions (calibration 2026-09-24) -- pure noise.
        st.update(turns=0, cum=0, next_turn_warn=TURN_WARN, next_cum_warn=CUM_WARN,
                  prompt=" ".join(_text(d.get("message")).split())[:40])
        return fired
    if d.get("type") != "assistant" or d.get("isSidechain"):
        return fired
    m = d.get("message") or {}
    u = m.get("usage")
    if not isinstance(u, dict):
        return fired
    mid = m.get("id")
    if mid and mid == st.get("last_id"):      # streamed duplicate of the same turn
        return fired
    st["last_id"] = mid
    st["turns"] += 1
    st["ctx"] = ((u.get("cache_read_input_tokens") or 0)
                 + (u.get("cache_creation_input_tokens") or 0)
                 + (u.get("input_tokens") or 0))
    st["cum"] += st["ctx"] + (u.get("output_tokens") or 0)
    if st["cum"] >= st["next_cum_warn"]:
        fired.append("cum")
        st["next_cum_warn"] = st["cum"] + CUM_WARN
    if st["turns"] >= st["next_turn_warn"]:
        fired.append("turns")
        st["next_turn_warn"] = st["turns"] + TURN_STEP
    if st["ctx"] < CTX_WARN * 0.6:               # compacted / cleared: re-arm
        st["ctx_warned"] = False
    if st["ctx"] >= CTX_WARN and not st["ctx_warned"]:
        fired.append("ctx")
        st["ctx_warned"] = True
    return fired


def message(st, kinds):
    head = []
    if "cum" in kinds:
        head.append("この1指示の消費が約 %d万トークンに到達" % (st["cum"] // 10000))
    if "turns" in kinds:
        head.append("この1指示で既に %d ターン" % st["turns"])
    if "ctx" in kinds or st["ctx"] >= CTX_WARN:
        head.append("毎ターン約 %d万トークンの文脈を再送中" % (st["ctx"] // 10000))
    return (
        "⚠ トークン予算（warn・ブロックしない）: " + "、".join(head) + "。"
        "消費はターン数×文脈サイズの積で増える（2026-09-18 実測: 1タスクが"
        "177〜519ターン×19〜27万トークンで48時間消費の約3割）。今この時点で適用せよ:\n"
        "・指摘への対応なら、全件の再点検ではなく指摘箇所の差分修正に絞る\n"
        "・残りの編集・検証は1本のスクリプトにまとめ、ツール呼び出し回数を減らす\n"
        "・大きな出力は画面に出さずファイルに受け、件数と要点だけ読む\n"
        "・区切りのよい所で成果を報告して止め、ユーザーに /compact を勧める"
        "（状態は tasks.md 等に書き出してから）")


def _state_path(sid):
    safe = "".join(ch for ch in (sid or "nosession") if ch.isalnum() or ch in "-_")
    return os.path.join(STATE_DIR, safe + ".json")


def _load(sid):
    try:
        with open(_state_path(sid), encoding="utf-8") as f:
            st = json.load(f)
        base = new_state()
        base.update(st)
        return base, True
    except Exception:
        return new_state(), False


def _save(sid, st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path(sid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, _state_path(sid))
    except Exception:
        pass


class _Lock:
    """Parallel tool calls in one assistant message start several hook
    processes at once; without a lock each loads the same offset and every
    one of them warns (adversarial review 2026-09-24: 9/15 trials double-fired).
    The loser simply skips -- the winner reports for everyone."""
    STALE = 30

    def __init__(self, sid):
        self.path = _state_path(sid) + ".lock"
        self.held = False

    def __enter__(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            try:
                if time.time() - os.path.getmtime(self.path) > self.STALE:
                    os.remove(self.path)          # left behind by a killed process
            except OSError:
                pass
            os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            self.held = True
        except OSError:
            self.held = False
        return self

    def __exit__(self, *_):
        if self.held:
            try:
                os.remove(self.path)
            except OSError:
                pass


def process(tp, st, known):
    """Consume transcript bytes appended since st['offset']; return fired kinds."""
    size = os.path.getsize(tp)
    if known and size < st["offset"]:             # file rewritten / truncated
        st.update(new_state())
        known = False
    fired = []
    with open(tp, "rb") as f:
        if known:
            f.seek(st["offset"])
        else:
            start = max(0, size - TAIL_BYTES)
            f.seek(start)
            if start:
                f.readline()                       # drop the partial first line
        pos = f.tell()
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return fired
    for line in data[:end].split(b"\n"):
        try:
            d = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            continue
        if is_human_prompt(d):
            # Warnings about an instruction that has since ended are stale
            # (found 2026-09-24: a first-sight tail scan of a real transcript
            # warned "17 turns" because 100+ turns of the PREVIOUS instruction
            # preceded the prompt). ctx is session-level, so it survives.
            fired = [k for k in fired if k == "ctx"]
        for k in step(st, d):
            if k not in fired:
                fired.append(k)
    if st["ctx"] < CTX_WARN:                     # it was big earlier, not any more
        fired = [k for k in fired if k != "ctx"]
    st["offset"] = pos + end + 1                  # keep the unterminated tail for next time
    return fired


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks",
                                             os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return  # repo copy takes over; avoid double-firing with the global copy
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tp = ev.get("transcript_path") or ""
        if not tp or not os.path.isfile(tp):
            return
        sid = ev.get("session_id") or os.path.splitext(os.path.basename(tp))[0]
        with _Lock(sid) as lk:
            if not lk.held:
                return
            st, known = _load(sid)
            fired = process(tp, st, known)
            _save(sid, st)
        if not fired:
            return
        _record_firing(NAME, ev)
        out = json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": message(st, fired)}}, ensure_ascii=False)
        sys.stdout.buffer.write(out.encode("utf-8"))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
