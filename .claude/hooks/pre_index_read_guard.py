"""PreToolUse hook (Grep|Read|Bash): block searches against a STALE report index.

Why this exists (incident 2026-07-30):
    index/REPORT_INDEX.md is bot-generated derived data, rebuilt every day on
    main by .github/workflows/report-index.yml. A session branch cut from main
    starts rotting immediately. A stale index answers keyword searches with
    "0 hits", which is indistinguishable from "the report does not exist" —
    so a false negative gets reported to the user as a verified fact.
    That happened: a working tree 11 days behind main missed
    deep-research/outputs/CLASSICS_READING_LIST_20260727.md and the user was
    told the report did not exist.

Mechanism: the index self-declares its build time on line 3
("自動生成: YYYY-MM-DD HH:MM UTC / ..."). If that build is older than
MAX_AGE_HOURS, any direct read/grep of the index files is denied and the
caller is redirected to index/search_reports.py, which sources the index from
origin/main and therefore cannot go stale. No subprocess, no network.

Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import datetime as dt
import json
import os
import re
import sys

MAX_AGE_HOURS = 48  # workflow runs daily; >48h means the working copy is behind
INDEX_NAMES = ("report_index.md", "reports.json")
SANCTIONED = ("search_reports.py", "origin/main:", "build_report_index.py")


def targets_index(data):
    ti = data.get("tool_input") or {}
    blob = " ".join(str(ti.get(k) or "") for k in
                    ("file_path", "path", "pattern", "glob", "command")).lower()
    if not blob:
        return False
    if any(s in blob for s in SANCTIONED):
        return False  # already fresh-sourced or is the indexer itself
    return any(n in blob for n in INDEX_NAMES)


def index_age_hours():
    """Age of the working-tree index build, or None if undeterminable."""
    path = os.path.join(os.getcwd(), "index", "REPORT_INDEX.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        head = [next(f, "") for _ in range(6)]
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})\s*UTC", "".join(head))
    if not m:
        return None
    built = dt.datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}",
                                "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - built).total_seconds() / 3600.0


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
        data = json.load(sys.stdin)
        if not targets_index(data):
            return
        age = index_age_hours()
        if age is None or age <= MAX_AGE_HOURS:
            return
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"作業ツリーの index が {age / 24:.1f} 日前のビルドで古い（日次自動更新のはず）。"
                    "この状態で検索すると『0件』と『存在しない』が区別できず、"
                    "誤って『該当なし』と報告する事故になる（2026-07-30 の古典レポート見落とし）。"
                    "代わりに origin/main から取得して検索する "
                    "`python index/search_reports.py <キーワード>` を使うこと。"
                    "作業ツリーを直接使うなら先に `git fetch origin main` して同期する。"
                ),
            }
        }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
