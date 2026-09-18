#!/usr/bin/env python3
"""Codex のフックペイロードを Claude Code 形式に正規化する。

なぜ必要か（F10）:
  Claude Code と Codex はイベント名もペイロードのキーもほぼ同じだが、
  **ファイル編集ツールの `tool_input` の中身が全く違う**。

    Claude Code : tool_name="Write"       tool_input={"file_path":..., "content":...}
                  tool_name="Edit"        tool_input={"file_path":..., "old_string":..., "new_string":...}
    Codex       : tool_name="apply_patch" tool_input={"command": "*** Begin Patch\\n*** Add File: C:/x.md\\n+hello\\n*** End Patch"}

  実測では、移植対象フックのうち 16 本が `file_path` / `content` / `new_string` を
  直接読んでいた。matcher を `Write|Edit` → `apply_patch` に置換するだけでは、
  これらは **空の値を読んで素通りする**。ブロックしないので失敗が見えず、
  「移植済みなのに一度も発火しない」という F5 と同じ沈黙の故障になる。

  そこで各フックの先頭でこのアダプタを通し、`tool_input` を Claude 形式へ
  変換してから既存のロジックに渡す。フック本体を二重メンテしないための1枚。

使い方:
    from codex_adapter import normalize
    data = normalize(json.load(sys.stdin))
    # 以降は data["tool_input"]["file_path"] などが Claude と同じように読める

変換できないもの:
  patch に含まれない情報は復元できない。`Update File` の場合、Claude の Edit が持つ
  `old_string` は patch の `-` 行から、`new_string` は `+` 行から再構成するが、
  文脈行（先頭が空白の行）は両方に含める。完全な等価ではないので、
  厳密な一致判定をするフックは個別に確認すること。
"""
from __future__ import annotations

import re

__all__ = ["normalize", "parse_apply_patch", "is_codex_payload", "codex_paths",
           "emit_deny", "running_under_codex"]


# --------------------------------------------------------------------------
# Deny emission: the two runtimes do NOT share a blocking contract.
#
# Claude Code blocks on stdout JSON with exit 0:
#     {"hookSpecificOutput": {"permissionDecision": "deny", ...}}
#
# Codex blocks ONLY on **exit code 2 with the reason on stderr**. Its own
# binary carries the string:
#     "PreToolUse hook exited with code 2 but did not write a blocking
#      reason to stderr"
# and its TUI distinguishes "Blocked by hook" from "Hook failed". A hook that
# prints the JSON above and exits 0 renders as **Hook failed** and the tool
# call **proceeds anyway**.
#
# Measured 2026-09-18 (F10g): all 8 blocking guards used the JSON form with
# exit 0, and zero used exit 2. They fired 28 times against a future-dated
# file under Codex and the file was still written. The guards were correct;
# the decision was discarded. This is why "the hook fired" was never evidence
# that anything was enforced.
#
# emit_deny() satisfies BOTH runtimes in one call: it prints the JSON (which
# Codex ignores and Claude Code honours) and, under Codex, additionally exits
# 2 with the reason on stderr.
# --------------------------------------------------------------------------

def running_under_codex():
    """True when this hook was invoked by Codex rather than Claude Code.

    CODEX_HOME is exported by the Codex CLI and the desktop app for every
    hook process. Checked at call time, not import time, so a test can set
    it per case.
    """
    import os
    if os.environ.get("CLAUDE_HOOK_RUNTIME") == "claude":
        return False      # explicit override wins, for tests
    if os.environ.get("CODEX_HOOK_RUNTIME") == "codex":
        return True
    return bool(os.environ.get("CODEX_HOME"))


def emit_deny(reason, event="PreToolUse", _exit=True):
    """Block the tool call in whichever runtime is executing this hook.

    Always prints the Claude Code JSON decision. Under Codex, also writes the
    reason to stderr and exits 2, which is the only form Codex honours.

    Returns the exit code it used when _exit is False (for tests).
    """
    import json as _json
    import os
    import sys as _sys

    _sys.stdout.write(_json.dumps({"hookSpecificOutput": {
        "hookEventName": event,
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False) + os.linesep)
    _sys.stdout.flush()

    code = 0
    if running_under_codex():
        # Codex reads the reason from stderr; without it the block is dropped
        # with "did not write a blocking reason to stderr".
        _sys.stderr.write((reason or "blocked by governance hook") + os.linesep)
        _sys.stderr.flush()
        code = 2
    if _exit:
        _sys.exit(code)
    return code


_BEGIN = "*** Begin Patch"
_END = "*** End Patch"
# Anchored at line start: a patch that ADDS a line reading "+*** End Patch"
# (this repo's own ledger does) would otherwise truncate the whole patch and
# silently drop every later file. Verified by QC 2026-09-18.
_END_RE = re.compile(r"^\*\*\* End Patch\s*$", re.M)
_FILE_RE = re.compile(
    r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$", re.M)


def is_codex_payload(data):
    """True when this payload came from Codex rather than Claude Code."""
    if not isinstance(data, dict):
        return False
    # The tool NAME is the only safe signal. Sniffing for the patch marker
    # inside `command` misfires on Claude Code's own Bash: a heredoc that
    # merely CONTAINS patch text was rewritten to tool_name="Write" with a
    # file_path lifted out of the quoted body, and pre_write_guard then denied
    # a legitimate shell command (QC 2026-09-18).
    return data.get("tool_name") == "apply_patch"


def parse_apply_patch(command):
    """Parse an apply_patch command string into a list of file operations.

    Returns a list of dicts:
        {"op": "add"|"update"|"delete"|"move",
         "file_path": str,
         "content": str,      # full new content for add; "+" lines for update
         "old_string": str,   # "-" and context lines (update only)
         "new_string": str}   # "+" and context lines (update only)
    """
    if not command or _BEGIN not in command:
        return []

    body = command.split(_BEGIN, 1)[1]
    m_end = _END_RE.search(body)
    if m_end:
        body = body[:m_end.start()]

    marks = list(_FILE_RE.finditer(body))
    ops = []
    for i, m in enumerate(marks):
        kind = m.group(1)
        path = m.group(2).strip()
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        chunk = body[start:end]

        added, removed, new_ctx, old_ctx = [], [], [], []
        for line in chunk.splitlines():
            if not line:
                # A bare empty line carries no +/-/space marker, so which side
                # of the diff it belongs to cannot be known. Properly encoded
                # blank lines ARE preserved: an added blank is "+" and a blank
                # context line is " ", both handled below. Whether real Codex
                # ever emits a bare empty line inside a hunk is UNVERIFIED
                # (no sample captured as of 2026-09-18).
                continue
            head, rest = line[0], line[1:]
            if head == "+":
                added.append(rest)
                new_ctx.append(rest)
            elif head == "-":
                removed.append(rest)
                old_ctx.append(rest)
            elif head == " ":
                new_ctx.append(rest)
                old_ctx.append(rest)
            # "@@" hunk headers and anything else are ignored on purpose.

        op = {"Add File": "add", "Update File": "update",
              "Delete File": "delete", "Move to": "move"}[kind]
        ops.append({
            "op": op,
            "file_path": path,
            "content": "\n".join(added),
            "old_string": "\n".join(old_ctx),
            "new_string": "\n".join(new_ctx),
        })
    return ops


def normalize(data):
    """Return a copy of `data` whose tool_input looks like Claude Code's.

    Non-Codex payloads and non-patch tools are returned unchanged, so this is
    safe to call unconditionally at the top of every hook.
    """
    if not is_codex_payload(data):
        return data

    out = dict(data)
    ti = dict(out.get("tool_input") or {})
    ops = parse_apply_patch(str(ti.get("command", "")))
    if not ops:
        return data

    first = ops[0]
    # NOTE: file_path carries the FIRST path only, because that is the shape
    # Claude Code hooks expect. A multi-file patch therefore hides files 2..n
    # from any guard that reads file_path alone. `_codex_files` below holds all
    # of them; path-scoped guards must consult it (see codex_paths()).
    ti.setdefault("file_path", first["file_path"])
    ti.setdefault("content", first["content"])
    ti.setdefault("old_string", first["old_string"])
    ti.setdefault("new_string", first["new_string"])
    # Every touched path, so guards that check more than one file can see them.
    ti["_codex_files"] = [o["file_path"] for o in ops]
    ti["_codex_ops"] = ops

    out["tool_input"] = ti
    # Map the tool name onto the closest Claude Code equivalent so that
    # name-based branching inside existing hooks keeps working.
    out.setdefault("_codex_tool_name", out.get("tool_name"))
    out["tool_name"] = "Write" if first["op"] == "add" else "Edit"
    return out


def codex_paths(data):
    """Every file path this payload touches, for guards that check paths.

    Claude Code's Write/Edit touch exactly one file, so guards read `file_path`.
    A single Codex `apply_patch` can touch many. Reading `file_path` alone lets
    violations in the 2nd..nth file through, so path-scoped guards should use
    this instead. Works for both harnesses.
    """
    ti = (data or {}).get("tool_input") or {}
    files = ti.get("_codex_files")
    if files:
        return list(files)
    fp = ti.get("file_path")
    return [fp] if fp else []
