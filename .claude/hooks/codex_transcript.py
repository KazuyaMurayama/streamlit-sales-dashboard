#!/usr/bin/env python3
"""Codex の transcript を Claude Code 形式の行に変換する。

なぜ必要か（F10e）:
  Stop 系フックのうち4本（`review_gate` / `notfound_guard` /
  `unverified_identifier_guard` / `countermeasure_gate`）は `tool_input` を見ない。
  `transcript_path` の JSONL を自前で走査し、「このターンで何を書いたか」「どのツールを
  呼んだか」「ユーザーは何を頼んだか」を再構成する。`codex_adapter.normalize()` は
  `tool_input` を直すものなので、**これらに対しては何もしない**（QC 2026-09-18 実測）。

  そして Codex の transcript は Claude Code と**スキーマが根本的に違う**。実測:

    Claude Code : {"type":"assistant","message":{"content":[
                     {"type":"tool_use","name":"Write","input":{"file_path":...}}]}}
                  {"type":"user","message":{"content":[{"type":"text","text":...}]}}

    Codex       : {"type":"response_item","payload":{"type":"message","role":"user",
                     "content":[{"type":"input_text","text":...}]}}
                  {"type":"response_item","payload":{"type":"custom_tool_call",
                     "name":"exec","input":"<JavaScript source>"}}

  行の種類も、入れ子も、ツールの表し方も一致しない。したがって matcher の置換では
  1行も読めず、フックは「ツール呼び出し0件・発言なし」と解釈して**静かに素通りする**。

  さらに厄介な点（実測で判明）:
  **Codex はファイル編集を独立したツールとして呼ばない。** `name="exec"` の JavaScript の
  中で `tools.apply_patch("*** Begin Patch ...")` を呼ぶ。つまりツール名だけを見ても
  「ファイルを書いた」ことは分からず、`input` の JavaScript を読む必要がある。

使い方:
    from codex_transcript import to_claude_rows
    rows = to_claude_rows(path)   # Claude Code 形式の dict のリスト
    # 以降は既存の走査ロジックがそのまま使える

限界:
  JavaScript の解析は正規表現による**近似**である。`tools.apply_patch(...)` の呼び出しを
  文字列として拾うため、動的に組み立てられたパッチ（変数経由・テンプレート結合）は
  取りこぼす。取りこぼしは「検出漏れ」＝ガードが緩む方向に出るので、
  **ここで拾えたものは信用してよいが、拾えなかったことを不在の証拠にしてはいけない**。
"""
from __future__ import annotations

import io
import json
import os
import re

__all__ = ["to_claude_rows", "is_codex_transcript", "iter_rows"]

# tools.apply_patch("....") / tools.apply_patch('....') / backtick template.
# Non-greedy up to the closing quote of the same kind; escapes are handled by
# json-style unescaping below.
_APPLY_RE = re.compile(
    r"""tools\.apply_patch\s*\(\s*(["'`])(?P<body>(?:\\.|(?!\1).)*)\1""",
    re.S)

# Shell commands run through the exec tool.
#
# MEASURED 2026-09-18: every real shell call uses the OBJECT form --
#     tools.exec_command({"cmd": "Get-Content -LiteralPath a.md", "workdir": ...})
# -- never a bare string. Matching only the string form returned ZERO shell
# evidence from real sessions. That is not a harmless miss: guards that ask
# "did this turn verify anything?" conclude no command ran and block a turn
# that did check itself. An over-block is worse than silence here, because it
# punishes exactly the behaviour the guard exists to encourage.
_SHELL_RE = re.compile(
    r"""tools\.(?:shell|bash|exec_command|run)\s*\(\s*(["'`])(?P<body>(?:\\.|(?!\1).)*)\1""",
    re.S)

# Object form. Accepts "cmd" or "command", quoted or bare, anywhere in the
# object literal -- the key order is not guaranteed.
_SHELL_OBJ_RE = re.compile(
    r"""tools\.(?:shell|bash|exec_command|run)\s*\(\s*\{"""
    r"""(?:[^{}]*?)["']?(?:cmd|command)["']?\s*:\s*"""
    r"""(["'`])(?P<body>(?:\\.|(?!\1).)*)\1""",
    re.S)


def _unescape(s):
    """Turn a JS string literal body into its actual text."""
    try:
        return json.loads('"%s"' % s.replace('"', '\\"'))
    except Exception:
        return (s.replace("\\n", "\n").replace("\\t", "\t")
                 .replace("\\\"", "\"").replace("\\'", "'")
                 .replace("\\\\", "\\"))


def iter_rows(path, tail=4000):
    """Yield parsed JSONL rows from `path` (last `tail` lines only)."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-tail:]
    except Exception:
        return
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            yield json.loads(ln)
        except Exception:
            continue


def is_codex_transcript(path):
    """True when `path` looks like a Codex rollout rather than a Claude one."""
    for r in iter_rows(path, tail=80):
        t = r.get("type")
        if t in ("response_item", "event_msg", "session_meta", "turn_context"):
            return True
        if t in ("assistant", "user", "system"):
            return False
    return False


def _text_of(payload):
    """Concatenate the text of a Codex message payload."""
    out = []
    for c in (payload.get("content") or []):
        if isinstance(c, dict):
            # input_text (user/developer) and output_text (assistant)
            v = c.get("text")
            if isinstance(v, str):
                out.append(v)
    return "\n".join(out)


def _tool_uses_from_exec(src):
    """Extract Claude-shaped tool_use blocks from an exec payload's JS source.

    Codex runs file edits as `tools.apply_patch("*** Begin Patch ...")` INSIDE a
    JavaScript program passed to the `exec` tool, so the tool name alone never
    says a file was written. This reads the patch text back out and reports it
    the way Claude Code would have: one Write/Edit per file touched.
    """
    blocks = []
    try:
        from codex_adapter import parse_apply_patch
    except Exception:
        parse_apply_patch = None

    for m in _APPLY_RE.finditer(src or ""):
        patch = _unescape(m.group("body"))
        ops = parse_apply_patch(patch) if parse_apply_patch else []
        if not ops:
            continue
        for op in ops:
            blocks.append({
                "type": "tool_use",
                "name": "Write" if op["op"] == "add" else "Edit",
                "input": {"file_path": op["file_path"],
                          "content": op["content"],
                          "old_string": op["old_string"],
                          "new_string": op["new_string"]},
            })

    seen = set()
    for rx in (_SHELL_RE, _SHELL_OBJ_RE):
        for m in rx.finditer(src or ""):
            cmd = _unescape(m.group("body"))
            if cmd and cmd not in seen:
                seen.add(cmd)
                blocks.append({"type": "tool_use", "name": "Bash",
                               "input": {"command": cmd}})
    return blocks


def to_claude_rows(path, tail=4000):
    """Return Codex transcript rows rewritten in Claude Code's shape.

    Produces the two row kinds the Stop hooks walk:
        {"type": "user",      "message": {"content": [{"type":"text","text":...}]}}
        {"type": "assistant", "message": {"content": [ ...text / tool_use... ]}}

    `developer` role messages become "system" so that harness preamble is not
    mistaken for something the user asked for -- anchoring a review to the
    skills preamble would review the answer against boilerplate.
    """
    rows = []
    for r in iter_rows(path, tail=tail):
        if r.get("type") != "response_item":
            continue
        p = r.get("payload") or {}
        kind = p.get("type")

        if kind == "message":
            role = p.get("role")
            text = _text_of(p)
            if not text:
                continue
            if role == "user":
                rows.append({"type": "user", "message": {
                    "content": [{"type": "text", "text": text}]}})
            elif role == "assistant":
                rows.append({"type": "assistant", "message": {
                    "content": [{"type": "text", "text": text}]}})
            else:
                # developer / system preamble
                rows.append({"type": "system", "message": {
                    "content": [{"type": "text", "text": text}]}})

        elif kind in ("custom_tool_call", "function_call", "local_shell_call"):
            name = p.get("name") or ""
            src = p.get("input") or p.get("arguments") or ""
            if not isinstance(src, str):
                try:
                    src = json.dumps(src, ensure_ascii=False)
                except Exception:
                    src = str(src)
            blocks = _tool_uses_from_exec(src)
            if not blocks:
                # Keep the raw call so "did it call any tool" stays answerable.
                blocks = [{"type": "tool_use", "name": name or "exec",
                           "input": {"command": src}}]
            rows.append({"type": "assistant", "message": {"content": blocks}})
    return rows


def materialize(path, out_path, tail=4000):
    """Write a Claude-shaped copy of `path` to `out_path`; return out_path.

    Lets a hook that insists on reading a file keep doing so: convert first,
    then point the existing logic at the converted copy.
    """
    rows = to_claude_rows(path, tail=tail)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out_path


def resolve(path, tmp_dir=None, tail=4000):
    """Return a transcript path in Claude Code shape.

    Claude transcripts are returned unchanged; Codex transcripts are converted
    into a temporary file whose path is returned. Safe to call unconditionally.
    """
    if not path or not os.path.exists(path):
        return path
    if not is_codex_transcript(path):
        return path
    import tempfile
    d = tmp_dir or tempfile.gettempdir()
    out = os.path.join(d, "codex_as_claude_%d.jsonl" % abs(hash(path)))
    try:
        return materialize(path, out, tail=tail)
    except Exception:
        return path
