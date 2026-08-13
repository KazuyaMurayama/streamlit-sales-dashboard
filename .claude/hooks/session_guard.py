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


# A table that GitHub does NOT render (blank line between the delimiter row and
# the first body row) and one with a header/delimiter column mismatch. The
# checker MUST flag both. If it does not, the checker is broken or has been
# replaced by an inert copy, and we say so instead of staying silent — a guard
# that cannot prove it works must not be trusted to have found nothing.
_CANARY = (
    "| a | b |\n|---|---|\n\n| 1 | 2 |\n",
    "| a | b | c |\n|---|---|\n| 1 | 2 |\n",
)


def _md_table_problems(git):
    """Check .md files touched in this working tree for non-rendering tables."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import md_table_check
    except Exception:
        return ["MDテーブル検査器を読み込めなかった（md_table_check.py）。検査は実行されていない。"]

    # Fail-closed canary: prove the checker still detects known-broken tables.
    for probe in _CANARY:
        try:
            criticals, _ = md_table_check.analyze_text(probe)
        except Exception:
            criticals = []
        if not criticals:
            return ["MDテーブル検査器が既知の壊れた表を検出できない（カナリア失敗）。"
                    "検査は無効化されている。md_table_check.py を修復するまで .md の描画は保証されない。"]

    # Uncommitted .md changes, plus .md files in commits not yet on the remote.
    # When there is no upstream (@{u} fails) we fall back to the last commit, so
    # a repo without a remote is still covered rather than silently skipped.
    paths = set()
    try:
        r = git("status", "--porcelain")
        for line in (r.stdout or "").splitlines():
            p = line[3:].strip().strip('"')
            if p.lower().endswith(".md"):
                paths.add(p)
        r = git("diff", "--name-only", "@{u}..HEAD")
        if r.returncode != 0:
            r = git("diff", "--name-only", "HEAD~1..HEAD")
        if r.returncode == 0:
            for p in (r.stdout or "").splitlines():
                if p.strip().lower().endswith(".md"):
                    paths.add(p.strip())
    except Exception:
        return []

    bad = []
    for p in sorted(paths):
        try:
            with open(p, encoding="utf-8-sig") as f:
                criticals, _ = md_table_check.analyze_text(f.read())
        except Exception:
            continue
        for c in criticals:
            kind = "区切り行の直後に本文行が無い" if c["sep"] == 0 else \
                   f"ヘッダー{c['header']}列≠区切り行{c['sep']}列"
            bad.append(f"{p}:{c['line']} ({kind})")

    if bad:
        return ["描画されないMDテーブルがある: " + " / ".join(bad[:6])
                + (f" ほか{len(bad) - 6}件" if len(bad) > 6 else "")
                + "。修正してから完了とすること。"]
    return []


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
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
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

        problems.extend(_md_table_problems(git))

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
