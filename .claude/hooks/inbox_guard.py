# -*- coding: utf-8 -*-
"""Inbox guard (UserPromptSubmit + Stop): an unattended job's output must reach
the user in a chat answer, not only exist as a file.

WHY (2026-10-06)
----------------
The weekly correction digest (scripts/correction_digest.py, scheduled task
ClaudeCorrectionDigest) ran on 2026-10-05, wrote
reports/CORRECTION_DIGEST_20261005.md and pushed it. The report asks the user
for a decision (「採用 C02」). Nothing told the user it existed. They found it
only because they happened to ask 「今週分の起動が行われていないのでは？」 a day
later, and then had to point out the omission themselves.

The job's design (docs/HERMES_GAP_PLAN_20260927.md P1) assumed "the user reads
the report". A pipeline whose last step is a person must have a delivery step;
writing the file is not delivery. Prose could not fix this: the job runs
headless, at 09:00 on a Sunday, with no conversation to put prose into.

Class (not this one job): **an output produced without the user present that
needs the user's attention is undelivered until a chat answer has shown it.**

WHAT IT DOES
------------
Producers (any scheduled job) call ``add_item()`` -- or
``python inbox_guard.py add --id ... --title ... --url ... [--path ...]`` --
to append to ~/.claude/state/inbox.jsonl.

UserPromptSubmit: if undelivered items exist, inject them into context with
the instruction to report them at the top of this answer, with the link.

Stop: the FINAL answer text (after the turn's last tool call, code blocks
removed) must link each injected item: its URL, or a markdown link whose
target contains the file name. A bare file name in passing, a mention in an
intermediate message, or one inside a code block does not count (Fable attack
2026-10-06, F1/F2). Missing -> block ONCE per prompt.

Delivered = shown AND the user wrote again in that session. Showing alone is
not delivery: a `claude -p` run started by some other tool also gets the
injection and would "show" it into a JSON result nobody reads (reproduced by
the Fable attack, HIGH #1). A -p run has one prompt, so it never confirms.
Until confirmed, other sessions keep showing the item -- a duplicate report is
cheap; a lost one is the defect.

Skipped entirely when CLAUDE_HEADLESS_JOB=1 (the producing jobs) or when
CLAUDE_CODE_ENTRYPOINT starts with "sdk" (a standalone `claude -p`), so their
output is not polluted. A -p nested inside an interactive session inherits
that session's entrypoint and still gets the injection; the confirmation rule
above keeps it from stealing the delivery.

CALIBRATION
-----------
Firing is deterministic on the inbox, not a text heuristic: it fires only while
an undelivered item exists. With one weekly producer that is 1 item per week.
tests/test_inbox_guard.py runs this file as a subprocess, including the Fable
attack cases (link only in an intermediate message / in a code block, bare
name, -p session never confirming, concurrent adds).

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import argparse
import datetime
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

NAME = "inbox_guard"
STATE_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "state")
INBOX = os.path.join(STATE_ROOT, "inbox.jsonl")
# NOT STATE_ROOT/<NAME>: firing_log owns that directory and writes
# <session_id>.json there, which overwrote this hook's per-session state
# (found by tests/test_inbox_guard.py on the first run).
SESS_DIR = os.path.join(STATE_ROOT, NAME + "_sessions")
MAX_AGE_DAYS = 30          # an item nobody saw for a month is stale, not urgent
TAIL_BYTES = 4 * 1024 * 1024


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _inbox_path():
    return os.environ.get("CLAUDE_INBOX_PATH") or INBOX


def _load():
    try:
        with io.open(_inbox_path(), encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception:
        return []


def _save(items):
    """Unique temp name + retried replace: two jobs adding at once used to
    collide on one fixed .tmp and drop items (Fable attack, MED #6)."""
    p = _inbox_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = "%s.%d.%d.tmp" % (p, os.getpid(), int(time.time() * 1e6))
    with io.open(tmp, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    for _ in range(20):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, p)


def _update(fn):
    """Read-modify-write under a crude lock file, so concurrent writers do
    not overwrite each other's items."""
    lock = _inbox_path() + ".lock"
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    fd = None
    for _ in range(100):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 30:
                    os.remove(lock)          # stale lock from a killed process
                    continue
            except Exception:
                pass
            time.sleep(0.05)
    try:
        items = _load()
        fn(items)
        _save(items)
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(lock)
            except Exception:
                pass


def add_item(item_id, title, summary="", url="", path="", match=None):
    """Register an output for delivery. Same id = replace (a re-run of the
    same job updates its item and makes it undelivered again). An item needs
    a URL or a path: with neither, nothing could ever prove it was shown."""
    if not (url or path):
        raise ValueError("inbox item needs a url or a path")
    match = [m for m in (match or []) if m] or [os.path.basename(url or path)]
    new = {"id": item_id, "created": _now(), "title": title, "summary": summary,
           "url": url, "path": path, "match": match, "shown": None, "delivered": None}

    def fn(items):
        items[:] = [it for it in items if it.get("id") != item_id] + [new]
    _update(fn)


def _created(it):
    s = it.get("created", "")
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def pending():
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=MAX_AGE_DAYS)
    return [it for it in _load() if not it.get("delivered") and (_created(it) or cut) >= cut]


def _mark(ids, key, session):
    if not ids:
        return

    def fn(items):
        for it in items:
            if it.get("id") in ids and not it.get("delivered"):
                it[key] = {"ts": _now(), "session": session}
    _update(fn)


def shown(item, answer):
    """The final answer links the item: its URL, or a markdown link whose
    target names the file. Code blocks do not count."""
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    a = re.sub(r"`[^`\n]*`", " ", a)
    if item.get("url") and item["url"] in a:
        return True
    targets = re.findall(r"\]\(([^)\s]+)\)", a)
    names = [m for m in item.get("match") or [] if m] + [os.path.basename(item.get("path") or "")]
    return any(n and n in t for t in targets for n in names)


def _sid(ev):
    return "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")[:64]


def _sess_path(ev):
    return os.path.join(SESS_DIR, _sid(ev) + ".json")


def _sess_load(ev):
    try:
        with io.open(_sess_path(ev), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _sess_save(ev, d):
    os.makedirs(SESS_DIR, exist_ok=True)
    with io.open(_sess_path(ev), "w", encoding="utf-8") as f:
        json.dump(d, f)


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def final_answer(tp):
    """Assistant text after the turn's last tool call -- what the user reads
    as the answer. Intermediate messages are excluded."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    parts = []
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            parts = []
        elif d.get("type") == "assistant":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_use" for b in c):
                parts = []
                continue
            t = _text(d.get("message")).strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _line(it):
    return "- %s: %s %s" % (it.get("title", ""), it.get("summary", ""), it.get("url") or it.get("path", ""))


def on_prompt(ev):
    sid = _sid(ev)
    # the user wrote again in a session that showed an item: that is delivery
    _mark([it["id"] for it in pending() if (it.get("shown") or {}).get("session") == sid],
          "delivered", sid)
    items = pending()
    if not items:
        _sess_save(ev, {"ids": [], "blocked": False})
        return None
    _sess_save(ev, {"ids": [it["id"] for it in items], "blocked": False})
    return ("【未報告の自動成果物 %d件（inbox_guard）】ユーザー不在の定期ジョブが作った成果物で、"
            "まだユーザーに届いていない。今回の回答の冒頭で、依頼への回答とは別に各1〜2行で報告し、"
            "Markdown リンク [名前](URL) を必ず付けること（最終回答にリンクが無いと終了時に止まる）:\n"
            % len(items)) + "\n".join(_line(it) for it in items)


def on_stop(ev):
    st = _sess_load(ev)
    ids = st.get("ids") or []
    if not ids:
        return None
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return None
    answer = final_answer(tp)
    live = {it["id"]: it for it in pending()}
    todo = [live[i] for i in ids if i in live]       # someone else may have delivered it
    done = [it["id"] for it in todo if shown(it, answer)]
    _mark(done, "shown", _sid(ev))
    missing = [it for it in todo if it["id"] not in done]
    if not missing:
        return None
    if ev.get("stop_hook_active") or st.get("blocked"):
        return None                                   # never block twice for one prompt
    st["blocked"] = True
    _sess_save(ev, st)
    _record_firing(NAME, ev)
    return ("【報告漏れ（1回のみ）】ユーザー不在の定期ジョブの成果物が、この回答で報告されていない。"
            "ファイルを作っただけでは届いたことにならない（2026-10-05 の訂正ダイジェストを誰も報告せず、"
            "ユーザーが自分で気づいた実害）。最終回答の冒頭に各1〜2行で追記し、Markdown リンクを付けて"
            "回答し直せ:\n" + "\n".join(_line(it) for it in missing))


def _skip():
    if os.environ.get("CLAUDE_HEADLESS_JOB") == "1":
        return True
    return (os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "").startswith("sdk")


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                                             ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass
    if _skip():
        return
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    name = ev.get("hook_event_name") or ""
    if name == "UserPromptSubmit":
        text = on_prompt(ev)
        if text:
            sys.stdout.buffer.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": text}},
                ensure_ascii=True).encode("ascii"))
    elif name == "Stop":
        reason = on_stop(ev)
        if reason:
            sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason},
                                               ensure_ascii=True).encode("ascii"))


def cli(argv):
    ap = argparse.ArgumentParser(prog="inbox_guard.py")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--summary", default="")
    a.add_argument("--url", default="")
    a.add_argument("--path", default="")
    a.add_argument("--match", action="append")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        add_item(args.id, args.title, args.summary, args.url, args.path, args.match)
    elif args.cmd == "list":
        for it in _load():
            print(json.dumps(it, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli(sys.argv[1:])
    else:
        try:
            main()
        except Exception:
            pass
