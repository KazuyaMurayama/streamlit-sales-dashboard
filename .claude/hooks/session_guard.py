"""Stop hook: session-end guard (rule 1 & 7 enforcement).

Blocks the FIRST attempt to end the turn when the working repo is in a
rule-violating state (non-main branch / unpushed commits), feeding the exact
remediation back to Claude. Second attempt is allowed (stop_hook_active),
so this can never loop.

Fail-open by design: any error -> exit 0 (never breaks a session).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import subprocess
import sys


def main():
    # If a same-named repo-local copy exists and we are the global copy, defer to it.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        return  # already nudged once; never loop

    def git(*args):
        return subprocess.run(["git"] + list(args), capture_output=True, text=True, timeout=15)

    try:
        r = git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            return  # not a git repo
        branch = r.stdout.strip()
        problems = []
        if branch and branch not in ("main", "master", "HEAD"):
            problems.append(
                f"現在ブランチが '{branch}'。ルール1: 完了 = main へマージ → ブランチ削除 → push。"
                "ブランチに成果物を残したまま終了しない。"
            )
        r2 = git("rev-list", "--count", "@{u}..HEAD")
        if r2.returncode == 0 and r2.stdout.strip().isdigit() and int(r2.stdout.strip()) > 0:
            problems.append(f"未 push コミットが {r2.stdout.strip()} 件。push を完了させ、成果物URLを検証すること。")
        if problems:
            print(json.dumps({
                "decision": "block",
                "reason": "【完了前チェック（自動ガード・1回のみ）】 " + " / ".join(problems)
                          + " 対応して終了するか、対応不要ならその理由を最終回答でユーザーに明示すること。",
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
