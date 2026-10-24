# -*- coding: utf-8 -*-
"""Stop hook: block once when a Playwright MCP tab is left open at the end of a turn.

WHY (2026-10-24, user request for every repo)
---------------------------------------------
「Playwright の MCP で Web 操作を任せた後、新しいタブを開きっぱなしにして作業を完了させているので、
そのタブを閉じていいのかわからなくなっています。一通りタスクが終わり報告が終わったら閉じるように
してもらうことはできますか？すべてのリポジトリに対しての要望です。」

The agent cannot act after its final message, so "after the report" means:
close the tab as the last browser step of the turn, then report.

MEASURED 2026-10-24 (playwright-ext = the user's own Chrome via the Playwright Extension,
@playwright/mcp 0.0.80, tabs counted through Windows UI Automation):
  - browser_close          -> "No open tabs" is reported, but the Chrome tab STAYS
                              (reproduced twice). The connection is dropped, so the tab
                              is orphaned and can no longer be closed through MCP.
  - browser_tabs action=close -> the Chrome tab is really closed (tab count 18 -> 17).
So for playwright-ext only `browser_tabs` close counts. For the isolated `playwright`
server (its own browser profile) browser_close closes that browser, so either counts.

WHAT IT DOES
------------
For each Playwright server used by the MAIN agent in this turn (calls since the last
human prompt): after the last call that leaves a tab open (navigate, click, snapshot,
tabs new/select, ...), at least as many closing calls must follow as tabs were opened
in the turn (1 + number of `browser_tabs new`). Otherwise block once per instruction.
Passes when the user asked to keep the tab (開いたまま / 閉じないで / keep open) or the
final message says why it is deliberately left open (タブ…開いたまま / 残して / 閉じずに),
e.g. the user must log in or look at the page.
Not covered: tool calls made by subagents (their transcripts are separate).

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

NAME = "browser_tab_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

EXT = "mcp__playwright-ext__"
ISO = "mcp__playwright__"
KEEP_PROMPT = re.compile(r"開いたまま|開きっぱなし(?:に|で)(?:して|いい|よい|OK)|閉じないで|閉じなくて|残しておいて|keep (?:it |the tab )?open", re.I)
KEEP_FINAL = re.compile(r"タブ[^。\n]{0,30}(?:開いたまま|残して|残した|閉じず|閉じていません|閉じない)")


def _action(inp):
    return str((inp or {}).get("action") or "")


def open_tabs_left(calls):
    """calls: [(tool_name, input)] in order. Returns [(server, opened, closed, used_browser_close)]
    for each server whose tab is still open at the end of the turn."""
    out = []
    for srv in (EXT, ISO):
        mine = [(n[len(srv):], i) for n, i in calls if n.startswith(srv)]
        if not mine:
            continue

        def closer(t, i):
            if t == "browser_tabs" and _action(i) == "close":
                return True
            return srv == ISO and t == "browser_close"

        def neutral(t, i):
            return closer(t, i) or t == "browser_close" or (t == "browser_tabs" and _action(i) == "list")

        last_open = max((k for k, (t, i) in enumerate(mine) if not neutral(t, i)), default=-1)
        if last_open < 0:
            continue
        opened = 1 + sum(1 for t, i in mine if t == "browser_tabs" and _action(i) == "new")
        after = mine[last_open + 1:]
        closed = sum(1 for t, i in after if closer(t, i))
        if closed < opened:
            out.append((srv, opened, closed, any(t == "browser_close" for t, _ in after)))
    return out


def decide(calls, prompt="", final=""):
    if KEEP_PROMPT.search(prompt or "") or KEEP_FINAL.search(final or ""):
        return None
    return open_tabs_left(calls) or None


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
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def turns(lines):
    """Yield (prompt, timestamp, calls, last assistant text) for each turn in the transcript lines."""
    prompt, pts, calls, final = None, "", [], ""
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            if prompt is not None:
                yield prompt, pts, calls, final
            prompt, pts, calls, final = _text(d.get("message")).strip(), d.get("timestamp", ""), [], ""
        elif d.get("type") == "assistant":
            t = _text(d.get("message")).strip()
            if t:
                final = t
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                calls.extend((b.get("name", ""), b.get("input") or {}) for b in c
                             if isinstance(b, dict) and b.get("type") == "tool_use")
    if prompt is not None:
        yield prompt, pts, calls, final


def read_turn(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    last = None
    for t in turns(data):
        last = t
    return last


REASON = ("【ブラウザのタブ閉じ忘れ（1回のみ）】このターンで Playwright（%s）を使ったが、最後の操作の後に"
          "タブを閉じていない（開いた %d 枚に対して閉じた %d 枚）。ユーザー指示（2026-10-24・全リポ）:"
          "「一通りタスクが終わり報告が終わったら閉じるようにしてもらうことはできますか？」。"
          "報告の前に、自分が開いたタブを閉じること。playwright-ext（本人の Chrome）は "
          "browser_tabs で action=\"list\" → 自分が開いたタブを action=\"close\"（index 指定）で閉じる。"
          "browser_close は本人の Chrome ではタブを閉じず、接続だけ切れて閉じられなくなる（2026-10-24 実測）。"
          "隔離の playwright は browser_close でよい。%s"
          "ユーザーがログインやページの確認をする必要があって残す場合は、閉じずに「タブを開いたままにした理由」を最終回答に1文で書く。")
ORPHAN = ("このターンは browser_close を使ったので、そのタブは Chrome に残ったまま MCP から閉じられない。"
          "最終回答に、残ったタブの名前と「閉じてよい」ことを書く。")


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
    t = read_turn(tp)
    if not t:
        return
    prompt, pts, calls, final = t
    hit = decide(calls, prompt, final)
    if not hit:
        return
    srv, opened, closed, used_close = hit[0]
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
    reason = REASON % (srv.strip("_").replace("mcp__", ""), opened, closed, ORPHAN if (used_close and srv == EXT) else "")
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
