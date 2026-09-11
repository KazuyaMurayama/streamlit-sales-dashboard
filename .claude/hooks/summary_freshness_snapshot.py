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
#
# ⛔ The character class matters more than it looks (adversarial QC, 2026-09-11).
# The first version stopped at ァ-ヶ, so it did not include 「・」(U+30FB) or
# 「ー」(U+30FC). The user's main working tree is
#     C:\Users\user\Desktop\投資・不動産\nasdaq_backtest\
# so every Bash write under it was truncated to a relative fragment, resolved
# to a nonexistent file, and skipped -- 100% blind on that repo.
PATH_RE = re.compile(r"[\w./\\\-~$（）()、。ぁ-んァ-ヶー・ｰ－一-龥]+"
                     r"\.(?:md|markdown|mdx)\b", re.I)
# Quoted paths win: they may contain spaces, which no bare-word class can.
QUOTED_RE = re.compile(r"""(['"])(.+?\.(?:md|markdown|mdx))\1""", re.I)
# A leading `cd <dir> &&` / `cd <dir>;` rebases every relative path after it.
CD_RE = re.compile(r"""(?:^|[;&|]|\bthen\b)\s*cd\s+(?:-P\s+)?"""
                   r"""(?:(['"])(.+?)\1|([^\s;&|]+))""")


def _turn_key(ev):
    raw = str(ev.get("prompt_id") or ev.get("session_id") or "")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:80]


def _msys_to_win(p):
    """/c/Users/... -> C:/Users/...  (Git Bash writes paths this way.)

    Without this, abspath() turns "/c/Users/x/r.md" into "C:\\c\\Users\\x\\r.md",
    which never exists, so the file is silently skipped. 6% of real Bash .md
    writes use this form (adversarial QC, 2026-09-11).
    """
    m = re.match(r"^/([A-Za-z])/(.*)$", p)
    return "%s:/%s" % (m.group(1).upper(), m.group(2)) if m else p


def _bases(ev):
    """Directories a relative path in this command could be relative to.

    The hook process's own cwd is NOT the session's cwd, and a command may
    start with `cd <dir> &&`. Measured: 63% of real Bash .md writes are
    relative-after-cd and 19% are bare relative -- together 82% of the cases
    the first version could not see at all.
    """
    out = []
    cwd = ev.get("cwd")
    if isinstance(cwd, str) and cwd:
        out.append(cwd)
    cmd = (ev.get("tool_input") or {}).get("command")
    if isinstance(cmd, str):
        for m in CD_RE.finditer(cmd):
            d = _msys_to_win((m.group(2) or m.group(3) or "").strip())
            if not d or d.startswith("-"):
                continue
            d = os.path.expanduser(d)
            out.append(d if os.path.isabs(d)
                       else os.path.join(out[0] if out else os.getcwd(), d))
    out.append(os.getcwd())
    return out


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
        # Quoted first -- a quoted path may contain spaces.
        out.extend(m.group(2) for m in QUOTED_RE.finditer(cmd))
        out.extend(PATH_RE.findall(cmd))
    return out


def _resolve(cand, bases):
    """Every plausible absolute path for one candidate, best guess first."""
    cand = _msys_to_win(os.path.expanduser(cand.strip().strip("'\"")))
    if os.path.isabs(cand) or re.match(r"^[A-Za-z]:", cand):
        return [os.path.abspath(cand)]
    seen, out = set(), []
    for b in bases:
        try:
            p = os.path.abspath(os.path.join(b, cand))
        except Exception:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
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
    bases = _bases(ev)
    for cand in _candidates(ev):
        try:
            resolved = _resolve(cand, bases)
        except Exception:
            continue
        for full in resolved:
            if full in snap:
                break                     # first touch already recorded
            if not SFC.in_scope(full):
                continue
            if not os.path.isfile(full):
                continue                  # wrong base, or a new file
            try:
                if os.path.getsize(full) > 2 * 1024 * 1024:
                    break
            except Exception:
                break
            snap[full] = SFC.read_text(full)
            changed = True
            break                         # first base that exists wins
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
