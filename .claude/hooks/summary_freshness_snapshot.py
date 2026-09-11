# -*- coding: utf-8 -*-
"""PreToolUse: record a report file's content the FIRST time a turn touches it.

Pairs with summary_freshness_guard.py (Stop), which compares this baseline
against the disk at end of turn to answer one question: did the update change
the late body while leaving the opening block byte-identical?

WHY SNAPSHOT AT PreToolUse RATHER THAN JUST DIFFING GIT AT Stop
----------------------------------------------------------------
git only knows the last COMMIT. A turn that edits a file which was already
dirty would be measured against the wrong baseline, and a turn that edits and
commits mid-way would look like it changed nothing. The baseline has to be
"what the file looked like when this turn first touched it", which only a
PreToolUse observation can supply.

WHY IT WATCHES Bash AND PowerShell TOO
---------------------------------------
Because the write frequently does not go through Write|Edit at all. Measured in
one real session: 0 of 3 report writes used those tools; all were Bash
heredocs. For a shell command this hook cannot know which file will be written,
so it snapshots every in-scope report file named ANYWHERE in the command
string. Cheap (reports are small, and the snapshot is per-turn), and it fails
open on anything it cannot parse.

The snapshot is keyed by prompt_id -- one baseline per turn, written once and
never overwritten, so a file edited five times in a turn is still compared
against its state before edit #1.

FAIL-OPEN, ALWAYS: this hook must never deny anything. It only observes.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import summary_freshness_check as SFC
except Exception:
    SFC = None

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "summary_freshness")

# Any .md-ish path appearing in a shell command. Quoted or bare.
PATH_RE = re.compile(r"[\w./\\\-~$（）()、。ぁ-んァ-ヶ一-龥]+"
                     r"\.(?:md|markdown|mdx)\b", re.I)


def _turn_key(ev):
    raw = str(ev.get("prompt_id") or ev.get("session_id") or "")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:80]


def _candidates(ev):
    ti = ev.get("tool_input") or {}
    out = []
    for k in ("file_path", "filePath", "path", "notebook_path"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            out.append(v)
    for e in (ti.get("edits") or []):
        if isinstance(e, dict):
            v = e.get("file_path") or e.get("filePath")
            if isinstance(v, str) and v:
                out.append(v)
    cmd = ti.get("command")
    if isinstance(cmd, str) and cmd:
        out.extend(PATH_RE.findall(cmd))
    return out


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        return
    if SFC is None:
        return

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return

    key = _turn_key(ev)
    if not key:
        return

    path = os.path.join(STATE_DIR, key + ".json")
    try:
        with io.open(path, encoding="utf-8") as f:
            snap = json.load(f)
        if not isinstance(snap, dict):
            snap = {}
    except Exception:
        snap = {}

    changed = False
    for cand in _candidates(ev):
        try:
            full = os.path.abspath(cand)
        except Exception:
            continue
        if full in snap:
            continue                      # first touch already recorded
        if not SFC.in_scope(full):
            continue
        if not os.path.isfile(full):
            continue                      # new file: no "before" to compare
        try:
            if os.path.getsize(full) > 2 * 1024 * 1024:
                continue                  # absurd for a report; skip
        except Exception:
            continue
        snap[full] = SFC.read_text(full)
        changed = True

    if not changed:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
