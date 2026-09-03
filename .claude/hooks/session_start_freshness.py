"""SessionStart hook: fetch origin/main and surface how stale this checkout is.

Why this exists (incident 2026-07-30):
    A web session opened on a pre-existing branch whose base was 11 days old.
    Nothing said so, so every file read in that session — the cross-repo report
    index, CHANGELOG, rules — silently served 11-day-old content. The agent then
    diagnosed the staleness as "the daily CI job stopped running", which was
    false (it had succeeded every day); it had simply never fetched.

Mechanism: one `git fetch origin main` per session, then report the gap as
injected context. Root-cause layer: makes staleness visible at turn 0 instead
of never. Cost: a single fetch per session.

Fail-open: any error -> exit 0 (never breaks a session).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import subprocess
import sys


def git(*args, timeout=30):
    return subprocess.run(["git"] + list(args), capture_output=True,
                          text=True, timeout=timeout)


def main():
    # If a same-named repo-local copy exists and we are the global copy, defer to it.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks",
                                            os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        if git("rev-parse", "--git-dir").returncode != 0:
            return  # not a git repo

        base = "main"
        if git("rev-parse", "--verify", "origin/main").returncode != 0:
            if git("rev-parse", "--verify", "origin/master").returncode != 0:
                return
            base = "master"

        git("fetch", "origin", base)  # best effort; offline -> stale ref, handled below

        r = git("rev-list", "--count", f"HEAD..origin/{base}")
        if r.returncode != 0 or not r.stdout.strip().isdigit():
            return
        behind = int(r.stdout.strip())
        if behind == 0:
            return

        d = git("log", "-1", "--format=%cr", f"origin/{base}")
        age = d.stdout.strip() if d.returncode == 0 else "unknown"
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    f"[freshness] この作業ツリーは origin/{base} より {behind} コミット遅れている"
                    f"（origin/{base} の最新コミットは {age}）。"
                    "派生データ（index/REPORT_INDEX.md・reports.json）や CHANGELOG を"
                    "作業ツリーから読むと古い内容になる。過去レポート検索は必ず "
                    "`python index/search_reports.py <キーワード>` を使う"
                    "（origin/main から取得するため陳腐化しない）。"
                    f"作業ツリーを直接使う場合は先に `git fetch origin {base}` で同期すること。"
                ),
            }
        }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
