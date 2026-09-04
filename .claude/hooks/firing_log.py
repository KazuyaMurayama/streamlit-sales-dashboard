# -*- coding: utf-8 -*-
"""Shared firing recorder for every guard hook.

WHY THIS MODULE EXISTS (2026-09-04)
-----------------------------------
CLAUDE.md §14 F2 says: 「無反応＝正常と解釈しない。無反応は故障と区別がつか
ない」. That rule was in force while 18 of 19 guards kept no record of ever
having fired. Nobody could tell a guard that was quietly protecting the repo
from one that had been dead since the day it shipped -- and one HAD been dead
(a payload-shape mismatch made it early-return every time, discovered
2026-08-04 only because someone forced a firing by hand).

WHY SHARED, NOT COPIED INTO EACH HOOK
-------------------------------------
Because copying is how the last failure happened. `scripts/` accumulated ten
deploy_*.py, each hardcoding its own hook list; none was ever re-run, and five
hooks silently sat at 0/44 repos. By the time this module was written there
were already TWO divergent firing-log implementations (notfound_guard.py's
{"key": ...} dedupe state and countermeasure_gate.py's {"last_fired","count"}).
Thirteen more hand-written copies would drift the same way. One writer, many
callers.

CONTRACT
--------
    from firing_log import record
    record("md_date_guard", ev)      # ev = the hook's parsed stdin payload

Writes ~/.claude/state/<hook>/<session_id>.json:
    {"last_fired": "<ISO8601 UTC>", "count": <cumulative>}

`countermeasure_ledger.py` reads only the DIRECTORY's existence, so any single
successful call flips has_firing_log to True. The count and timestamp are for
humans deciding whether a guard is over- or under-firing.

FAIL-SILENT BY DESIGN: every path is wrapped. A hook must never break because
its bookkeeping failed -- a guard that crashes is worse than one that forgets
to write a log line. Callers therefore do not check the return value, though
one is provided (True on success) for tests.

CALL IT ONLY WHEN THE GUARD ACTUALLY ACTS -- on the block/warn path, not on
every invocation. A log that records "ran and stayed silent" cannot answer the
question this exists for ("has this guard ever caught anything?").

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
A firing rate does not apply to this module itself: it performs no checks
and makes no block/warn decisions, so there is nothing here to measure a
rate against. The calibration target is always the calling guard, not this
recorder. What is measured here instead is correctness of the bookkeeping:
`test_firing_log.py` passes 16/16, verified against real disk operations
(actual writes under STATE_ROOT, counts that accumulate across repeated
calls, and recovery from a corrupted state file) rather than a stub that
merely returns True.
"""
import io
import json
import os
import re

from datetime import datetime

STATE_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "state")


def _sid(ev):
    """Filesystem-safe session id. Mirrors notfound_guard.py's sanitiser.

    Path separators, '..' and stray punctuation are stripped rather than
    escaped: this value becomes a filename, and a session_id is attacker-
    influenced in principle. Truncated to 64 chars for Windows path limits.
    """
    try:
        s = (ev or {}).get("session_id") or "default"
    except Exception:
        s = "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64] or "default"


def _utc_now():
    """ISO8601 UTC. datetime.now(timezone.utc) needs Python 3.2+; the
    fallback keeps this importable under an ancient interpreter rather than
    taking the whole hook down with an ImportError."""
    try:
        from datetime import timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def record(hook_name, ev=None):
    """Record one firing of `hook_name`. Never raises. True if written."""
    try:
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(hook_name))
        if name.endswith(".py"):
            name = name[:-3]
        if not name:
            return False
        d = os.path.join(STATE_ROOT, name)
        path = os.path.join(d, _sid(ev) + ".json")

        prev = {}
        try:
            with io.open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
        count = prev.get("count", 0)
        if not isinstance(count, int) or count < 0:
            count = 0

        os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_fired": _utc_now(), "count": count + 1}, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False
