"""PostToolUse hook (Bash|PowerShell): after `git push`, remind the
deliverables-report rules (rule 2) at exactly the moment they become due.

Fail-open: any error -> exit 0.
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import re
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
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if re.search(r"git\s+push\b", cmd) and "--delete" not in cmd:
            print(json.dumps({
                "decision": "block",
                "reason": (
                    "【自動リマインド】git push を検出。"
                    "最終回答に (1) 成果物3列表（成果物/説明/リンク） "
                    "(2) 各URLの存在確認（Contents API 200） "
                    "(3) ブランチが main のみであること を含めること。"
                    "既に対応済みならこのリマインドは無視してよい。"
                ),
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
