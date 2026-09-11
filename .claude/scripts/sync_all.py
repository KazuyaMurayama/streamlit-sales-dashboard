# -*- coding: utf-8 -*-
"""Fetch every local clone and report which ones are stale.

WHY THIS EXISTS: on 2026-08-26 a cross-repo search answered "does not exist"
for two reports that were present on the remote. The local clones were 7 and 11
commits behind, hiding 13 .md files. `find`/`grep -r` cannot see unpulled
files, so a local sweep silently searched an old snapshot.

This is the remedy that notfound_guard.py tells you to run. It is NOT a habit
you are expected to remember — the hook fires first and points here.

`fetch` only: never merges, never touches the working tree, safe to run any
time. Use --pull to fast-forward clean repos that are strictly behind.

Usage:
  python scripts/sync_all.py            # fetch all, print staleness table
  python scripts/sync_all.py --pull     # also fast-forward clean+behind repos
  python scripts/sync_all.py --quiet    # only print repos that are stale
"""
import argparse
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def git(repo, *args):
    try:
        p = subprocess.run(["git"] + list(args), cwd=repo,
                           capture_output=True, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return 1, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    parent = os.path.dirname(a.root)
    repos = sorted(d for d in os.listdir(parent)
                   if os.path.isdir(os.path.join(parent, d, ".git")))

    rows, stale, pulled = [], 0, 0
    for name in repos:
        repo = os.path.join(parent, name)
        git(repo, "fetch", "origin", "-q")

        _, branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        rc, up = git(repo, "rev-parse", "--abbrev-ref", "@{u}")
        if rc != 0 or not up:
            rows.append((name, branch, "NO-UPSTREAM", "", ""))
            continue

        _, behind = git(repo, "rev-list", "HEAD..%s" % up, "--count")
        _, ahead = git(repo, "rev-list", "%s..HEAD" % up, "--count")
        behind = behind or "0"
        ahead = ahead or "0"

        md = ""
        if behind != "0":
            _, diff = git(repo, "diff", "--name-only", "--diff-filter=A",
                          "HEAD", up)
            md = str(len([x for x in diff.splitlines()
                          if x.endswith(".md")]))
            stale += 1
            if a.pull:
                _, dirty = git(repo, "status", "--porcelain")
                if not dirty and ahead == "0":
                    rc, _ = git(repo, "merge", "--ff-only", up)
                    if rc == 0:
                        pulled += 1
                        behind += " (pulled)"

        if behind != "0" or ahead != "0" or not a.quiet:
            rows.append((name, branch, behind, ahead, md))

    print("%-46s %-10s %-12s %-6s %s"
          % ("repo", "branch", "behind", "ahead", "unseen.md"))
    print("-" * 92)
    for r in rows:
        print("%-46s %-10s %-12s %-6s %s" % r)
    print("\n%d repos scanned | %d stale | %d fast-forwarded"
          % (len(repos), stale, pulled))
    if stale and not a.pull:
        print("\n⚠ Local search over these repos is UNRELIABLE. Either rerun "
              "with --pull, or search the remote tree directly:\n"
              "    git ls-tree -r origin/<branch> --name-only | grep -i <KEY>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
