"""PreToolUse hook (Write|Edit): deny file creation outside repos on Desktop (rule 3).

Allows Desktop\\repos\\* and Desktop\\投資・不動産\\* (existing local clones).
Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Fired on 12 of 600 real Write/Edit calls replayed from 27 production
transcripts = 2.00%. A low rate is expected here: most Write/Edit calls
already target an existing repo clone under Desktop\repos or
Desktop\投資・不動産, so the guard should only trip on genuine outliers
(e.g. a stray file heading for Desktop itself), not on routine work.
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

try:
    from codex_adapter import normalize as _codex_normalize
    from codex_adapter import codex_paths as _codex_paths
except Exception:  # adapter missing: say so, do not fail silently
    def _codex_normalize(d):
        # A hook that cannot convert Codex payloads reads empty values and
        # returns early -- silence indistinguishable from "no violation".
        # One line on stderr keeps a broken deployment visible (QC
        # 2026-09-18). stderr does not affect the hook's decision.
        if isinstance(d, dict) and d.get("tool_name") == "apply_patch":
            sys.stderr.write(
                "[%s] codex_adapter.py not found next to this hook; "
                "Codex apply_patch payloads are NOT being checked."
                % os.path.basename(__file__) + chr(10))
        return d

    def _codex_paths(d):
        fp = ((d or {}).get("tool_input") or {}).get("file_path")
        return [fp] if fp else []


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
            return
    except Exception:
        pass

    try:
        raw = sys.stdin.buffer.read()
        data = _codex_normalize(json.loads(raw.decode("utf-8", "replace")))
        # A single Codex apply_patch can touch several files. Reading file_path
        # alone would check only the first and let a Desktop write in the 2nd..nth
        # through, so every path in the patch is checked (QC 2026-09-18).
        allowed = ("\\desktop\\repos\\", "\\desktop\\投資・不動産\\")
        bad = ""
        for fp in _codex_paths(data):
            p = (fp or "").replace("/", "\\").lower()
            if "\\desktop\\" in p and not any(a in p for a in allowed):
                bad = fp
                break
        if bad:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("pre_write_guard", data)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "ルール3: Desktop へのファイル生成は禁止。"
                        "成果物はリポ内、使い捨ては OS temp へ。"
                        "ユーザーが明示的に Desktop 保存を指示した場合のみ例外。"
                    ),
                }
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
