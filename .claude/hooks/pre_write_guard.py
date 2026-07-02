"""PreToolUse hook (Write|Edit): deny file creation outside repos on Desktop (rule 3).

Allows Desktop\\repos\\* and Desktop\\投資・不動産\\* (existing local clones).
Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import sys


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        data = json.load(sys.stdin)
        fp = (data.get("tool_input") or {}).get("file_path") or ""
        p = fp.replace("/", "\\").lower()
        if "\\desktop\\" in p:
            allowed = ("\\desktop\\repos\\", "\\desktop\\投資・不動産\\")
            if not any(a in p for a in allowed):
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
