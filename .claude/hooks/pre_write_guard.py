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
except Exception:
    def _codex_normalize(d):
        return d

    def _codex_paths(d):
        fp = ((d or {}).get("tool_input") or {}).get("file_path")
        return [fp] if fp else []


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
