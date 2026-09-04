"""Stop hook: session-end guard (rule 1 & 7 enforcement).

Blocks the FIRST attempt to end the turn when the working repo is in a
rule-violating state (non-main branch / unpushed commits), feeding the exact
remediation back to Claude. Second attempt is allowed (stop_hook_active),
so this can never loop.

Fail-open by design: any error -> exit 0 (never breaks a session).
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Replaying 28 real transcripts fired this guard 0/28 times (0.00%). Replay
alone cannot distinguish a dead guard from one that is correctly silent
(CLAUDE.md §14 F2), so a forced-firing check was also run: a disposable git
repo was switched to a `feature-x` branch and a Stop payload was sent to the
hook directly, which returned `{"decision":"block"}` with the remediation
text citing rule 1 (branch must be main before completion). That confirms
the 0.00% reflects "every replayed session was already on main" rather than
a broken or unreachable guard.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False


# A table that GitHub does NOT render (blank line between the delimiter row and
# the first body row) and one with a header/delimiter column mismatch. The
# checker MUST flag both. If it does not, the checker is broken or has been
# replaced by an inert copy, and we say so instead of staying silent — a guard
# that cannot prove it works must not be trusted to have found nothing.
_CANARY = (
    "| a | b |\n|---|---|\n\n| 1 | 2 |\n",
    "| a | b | c |\n|---|---|\n| 1 | 2 |\n",
)


# Every repo wires its Stop hook to its OWN .claude/hooks/ copy, so a repo whose
# copy predates a fix keeps running the old logic with no outward sign. Compare
# against the canonical template when it is reachable on this machine and say so
# — a guard that has silently drifted must not look identical to a current one.
_CANON = os.path.join(os.path.expanduser("~"), "Desktop", "repos",
                      "claude-governance", "templates", "hooks")


def _stale_copies():
    out = []
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.normcase(here) == os.path.normcase(_CANON):
        return out
    for name in ("session_guard.py", "md_table_check.py"):
        canon = os.path.join(_CANON, name)
        mine = os.path.join(here, name)
        try:
            if not os.path.exists(canon) or not os.path.exists(mine):
                continue
            with open(canon, "rb") as a, open(mine, "rb") as b:
                if a.read() != b.read():
                    out.append(name)
        except Exception:
            continue
    return out


def _git_bytes(*args, **kw):
    """git returning raw bytes: filenames may not be valid UTF-8 in this locale."""
    p = subprocess.run(["git"] + list(args), capture_output=True,
                       timeout=15, cwd=kw.get("cwd"))
    return p.stdout if p.returncode == 0 else b""


def _md_table_problems(git):
    """Check .md files touched in this working tree for non-rendering tables."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import md_table_check
    except Exception:
        return ["MDテーブル検査器を読み込めなかった（md_table_check.py）。検査は実行されていない。"]

    # Fail-closed canary: prove the checker still detects known-broken markup.
    # One probe per invariant — a canary that only exercises some of them would
    # let a partially-blinded checker pass.
    for probe in _CANARY:
        try:
            criticals, _ = md_table_check.analyze_text(probe)
        except Exception:
            criticals = []
        if not criticals:
            return ["MDテーブル検査器が既知の壊れた表を検出できない（カナリア失敗）。"
                    "検査は無効化されている。md_table_check.py を修復するまで .md の描画は保証されない。"]
    try:
        if not md_table_check.unclosed_fence_line("```\nx\n"):
            raise ValueError
    except Exception:
        return ["コードフェンス検査が既知の未閉フェンスを検出できない（カナリア失敗）。"
                "md_table_check.py を修復するまで .md の描画は保証されない。"]

    # Paths are resolved against the repository ROOT, not the current directory:
    # `git status` reports root-relative paths, so opening them from a nested cwd
    # silently fails and the guard reports nothing. Byte mode (-z) is required
    # because non-ASCII filenames are otherwise octal-escaped (and `text=True`
    # can raise UnicodeDecodeError outright). `-uall` is required because git
    # otherwise reports an untracked DIRECTORY, hiding every .md inside it.
    root = ""
    try:
        r = git("rev-parse", "--show-toplevel")
        if r.returncode == 0:
            root = r.stdout.strip()
    except Exception:
        pass
    if not root:
        return []

    def _abs(rel):
        return os.path.join(root, rel.replace("/", os.sep))

    paths = set()
    try:
        r = _git_bytes("status", "--porcelain", "-z", "-uall", cwd=root)
        fields = [f for f in (r or b"").split(b"\x00") if f]
        i = 0
        while i < len(fields):
            f = fields[i].decode("utf-8", "replace")
            status, name = f[:2], f[3:]
            i += 1
            # Rename/copy entries are followed by the ORIGIN path as its own
            # field; consume it so it is never mistaken for a status entry.
            if status and status[0] in ("R", "C"):
                i += 1
            if name.lower().endswith(".md"):
                paths.add(name)
        r = git("diff", "--name-only", "@{u}..HEAD")
        if r.returncode != 0:
            r = git("diff", "--name-only", "HEAD~1..HEAD")
        if r.returncode != 0:
            # Zero-commit repo: nothing is committed yet, so the working tree
            # scan above is already the complete picture.
            r = None
        if r is not None and r.returncode == 0:
            for p in (r.stdout or "").splitlines():
                if p.strip().lower().endswith(".md"):
                    paths.add(p.strip())
    except Exception:
        return ["MDテーブル検査の対象ファイルを列挙できなかった。検査は実行されていない。"]

    bad = []
    unreadable = []
    for p in sorted(paths):
        ap = _abs(p)
        if not os.path.exists(ap):
            continue  # deleted in this change; nothing to render
        try:
            with open(ap, encoding="utf-8-sig") as f:
                text = f.read()
        except Exception:
            unreadable.append(p)
            continue
        try:
            criticals, _ = md_table_check.analyze_text(text)
        except Exception:
            unreadable.append(p)
            continue
        for c in criticals:
            kind = "区切り行の直後に本文行が無い" if c["sep"] == 0 else \
                   f"ヘッダー{c['header']}列≠区切り行{c['sep']}列"
            bad.append(f"{p}:{c['line']} ({kind})")

        # An unclosed code fence swallows every heading, table and paragraph
        # after it into one code block — a larger rendering failure than a
        # broken table, and invisible in the source. Same defect class:
        # a visually broken artifact shipped without anyone noticing.
        opened = md_table_check.unclosed_fence_line(text)
        if opened:
            bad.append(f"{p}:{opened} (コードフェンスが閉じていない→以降が全てコード扱いになる)")

    out = []
    if bad:
        shown = " / ".join(bad[:6])
        more = ""
        if len(bad) > 6:
            more = (f" ほか{len(bad) - 6}件（全{len(bad)}件。"
                    f"全件は `python .claude/hooks/md_table_check.py --scan .` で列挙）")
        out.append("描画されないMDテーブルがある: " + shown + more + "。修正してから完了とすること。")
    if unreadable:
        # Never treat "could not check" as "nothing found".
        out.append(f"MDテーブルを検査できなかったファイルが{len(unreadable)}件ある"
                   f"（{', '.join(unreadable[:3])}）。読めない理由を確認すること。")
    return out


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
        # Test repo-ness directly. `rev-parse --abbrev-ref HEAD` fails on a repo
        # with zero commits too, which would skip every check below on exactly
        # the repos where a brand-new file is most likely to be sitting.
        if git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return  # not a git repo
        r = git("rev-parse", "--abbrev-ref", "HEAD")
        branch = r.stdout.strip() if r.returncode == 0 else ""
        problems = []
        if branch and branch not in ("main", "master", "HEAD"):
            problems.append(
                f"現在ブランチが '{branch}'。ルール1: 完了 = main へマージ → ブランチ削除 → push。"
                "ブランチに成果物を残したまま終了しない。"
            )
        r2 = git("rev-list", "--count", "@{u}..HEAD")
        if r2.returncode == 0 and r2.stdout.strip().isdigit() and int(r2.stdout.strip()) > 0:
            problems.append(f"未 push コミットが {r2.stdout.strip()} 件。push を完了させ、成果物URLを検証すること。")

        stale = _stale_copies()
        if stale:
            problems.append(
                f"このリポの hook が正典より古い（{', '.join(stale)}）。"
                "claude-governance/templates/hooks/ から再配布すること。"
                "古い copy は修正済みの検査を素通りさせる。"
            )

        problems.extend(_md_table_problems(git))

        if problems:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("session_guard", data)
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
