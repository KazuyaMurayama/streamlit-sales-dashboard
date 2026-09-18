"""PreToolUse hook (Read): deny full reads of files >50KB without limit/offset (context-hygiene C2).

Prevents auto-compact churn from loading huge files into context.
Allows: partial reads (limit/offset/pages), files <=50KB, images/PDF/notebooks.
Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Fired on 12 of 600 real Read calls replayed from 27 production transcripts
= 2.00%. A low, occasional-deny rate is consistent with the 50KB threshold
being sized for genuinely large files rather than routine reads; of the
2356 real Read calls across all transcripts, 1092 lacked limit/offset,
so most large-file reads elsewhere were presumably already under 50KB or
already used partial reads.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

MAX_BYTES = 50_000
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb"}


# --- Codex blocking contract (F10g, 2026-09-18) -----------------------------
# Claude Code blocks on stdout JSON + exit 0. Codex blocks ONLY on exit code 2
# with the reason on stderr; its binary carries the string "PreToolUse hook
# exited with code 2 but did not write a blocking reason to stderr", and its
# TUI shows "Hook failed" (not "Blocked by hook") for anything else.
#
# Measured: these guards fired 28 times against a future-dated file under Codex
# and the file was written anyway. The guard was right; the decision was
# discarded. So "the hook fired" was never evidence of enforcement.
#
# Rather than edit each deny site (several sit inside `try/except: pass`, which
# would swallow a SystemExit), capture stdout and translate at process exit.
_CODEX_EXIT2_INSTALLED = True
if True:
    import atexit as _atexit
    import io as _io
    import json as _json
    import os as _os
    import sys as _sys

    class _TeeOut(_io.TextIOBase):
        """Pass stdout through while keeping a copy for the exit translator."""

        def __init__(self, real):
            self._real = real
            self.buf = []

        def write(self, s):
            self.buf.append(s)
            return self._real.write(s)

        def flush(self):
            self._real.flush()

    def _under_codex():
        if _os.environ.get("CLAUDE_HOOK_RUNTIME") == "claude":
            return False
        if _os.environ.get("CODEX_HOOK_RUNTIME") == "codex":
            return True
        return bool(_os.environ.get("CODEX_HOME"))

    _tee = _TeeOut(_sys.stdout)
    _sys.stdout = _tee

    def _codex_exit2():
        _sys.stdout = _tee._real
        if not _under_codex():
            return
        text = "".join(_tee.buf)
        reason = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = _json.loads(line)
            except Exception:
                continue
            hso = d.get("hookSpecificOutput") or {}
            if hso.get("permissionDecision") == "deny":
                reason = hso.get("permissionDecisionReason") or "blocked"
                break
        if reason is None:
            return
        try:
            _sys.stderr.write(reason + _os.linesep)
            _sys.stderr.flush()
        except Exception:
            pass
        _os._exit(2)   # bypass further atexit handlers and any except: pass

    _atexit.register(_codex_exit2)
# --- end Codex blocking contract -------------------------------------------


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return  # repo copy takes over; avoid double-firing with the global copy
    except Exception:
        pass

    try:
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
        ti = data.get("tool_input") or {}
        if ti.get("limit") or ti.get("offset") or ti.get("pages"):
            return
        fp = ti.get("file_path") or ""
        if not fp or not os.path.isfile(fp):
            return
        if os.path.splitext(fp)[1].lower() in SKIP_EXT:
            return
        size = os.path.getsize(fp)
        if size > MAX_BYTES:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("pre_read_guard", data)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "context-hygiene C2: このファイルは {:,} bytes（50KB超）。"
                        "全文Readはコンテキスト肥大の主因のため禁止。代替: "
                        "(1) Grep で必要行だけ抽出 (2) Read に offset+limit を付けて必要範囲だけ読む "
                        "(3) スクリプトで処理し件数・検証結果のみ受け取る"
                        "（CLAUDE.md コンテキスト管理節 C1〜C3 参照）。".format(size)
                    ),
                }
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
