"""PostToolUse hook (Bash|PowerShell): after `git push`, remind the
deliverables-report rules (rule 2) at exactly the moment they become due.

Fail-open: any error -> exit 0.
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Fired on 89 of 600 real Bash/PowerShell calls replayed from 27 production
transcripts = 14.83%. This rate is high and carries a warning-fatigue
risk: firing roughly 1 in 7 Bash/PowerShell calls means the reminder
appears often enough that it risks becoming background noise the user
tunes out. This is a side effect of the trigger's breadth rather than a
sizing choice -- `git push` itself is a frequent operation (901 of 14394
Bash calls across all transcripts contain `git push`), so any hook keyed
to "after a push" inherits that frequency. There is room to narrow this:
firing only when the push actually succeeds (rather than on any push
attempt) would likely cut the rate without weakening the rule-2 reminder
where it matters.
"""
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
        data = json.loads(raw.decode("utf-8", "replace"))
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if re.search(r"git\s+push\b", cmd) and "--delete" not in cmd:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("post_bash_guard", data)
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
