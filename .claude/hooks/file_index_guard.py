"""Stop hook: FILE_INDEX.md coverage guard.

WHY THIS IS A HOOK AND NOT A CHECKLIST
--------------------------------------
FILE_INDEX.md is a hand-maintained index. Its failure mode is silent: the index
only knows about files whose author remembered to add them. Nobody notices,
because the index still *looks* complete — every line in it is correct. What is
missing leaves no trace.

Measured 2026-09-07 (after scope narrowing, see EXCLUDE_DIRS):
    deep-research    27 uncovered  (outputs/ alone: 25 of 140 = 17.9%)
    NASDAQ_backtest  58 uncovered  (FILE_INDEX.md last touched 2026-07-17,
                                    repo active daily)
    Corpus firing rate: 16 of 40 indexed repos (40.0%). High because the
    omissions are real and accumulated; expected to fall as indexes are filled.
    Re-measure before assuming this rate still holds.

Both indexes are read by CLAUDE.md as navigation aids, so a stale index does not
merely omit — it actively asserts a smaller repo than exists. The user asked
Claude Code "the file index already knows every file's summary, so I can find
things by asking" and that premise was 17.9%/43.2% false.

A CLAUDE.md rule cannot fix this for the same reason the omission happened: the
author does not believe anything is missing, so they do not look.

WHAT IS CHECKED
  I1 WARN  Tracked .md files under the indexed scope that the index never names.
           Warn, not deny: adding a file and its index entry in one turn is
           normal, and blocking Stop would punish work in progress.

NON-GOALS (deliberate)
  - Does not auto-write the index. An auto-generated summary would be a
    fabricated summary; the point of the index is the human/Claude judgement in
    the description column. The hook reports WHAT is missing so the author can
    add real descriptions. `--list` prints the paths for that purpose.
  - Does not check description quality or freshness of existing entries.
  - Does not fire in repos with no FILE_INDEX.md (nothing to keep in sync).

CALIBRATION
  Threshold is 1 uncovered file (report anything missing) but the hook only
  emits on Stop, so it costs one line per turn at most. Measured firing rate on
  the 44-repo corpus is recorded in the countermeasure ledger.

SELFTEST
  python file_index_guard.py --selftest
  Builds a synthetic repo with a known-incomplete index and asserts the guard
  reports exactly the uncovered files; then completes the index and asserts
  silence. Both directions are required — a guard that only passes on the fixed
  version proves nothing.
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

INDEX_NAMES = ("FILE_INDEX.md", "file_index.md")

# Paths never expected in a curated index.
# Intermediate/working data, not deliverables. CLAUDE.md (deep-research) defines
# `session/` as 中間データ against `outputs/` 公開レポート, so an index that omits
# session files is correct, not stale. Measured 2026-09-07: including session/
# turned deep-research from 25 real omissions into 181 hits (154 = noise, 86%),
# which is exactly how a guard gets ignored. Narrowing the measurement, not the
# threshold.
EXCLUDE_DIRS = (
    ".claude/", ".github/", "node_modules/", "docs/superpowers/",
    "_archived", "_archive/", ".venv/", "vendor/",
    "session/", "audit_results/", "logs/", "tmp/",
)
EXCLUDE_BASENAMES = {
    "README.md", "CLAUDE.md", "FILE_INDEX.md", "file_index.md",
    "tasks.md", "CHANGELOG.md", "LICENSE.md", "AGENTS.md", "SPEC.md",
}


def _repo_root(start):
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.decode("utf-8", "replace").strip()
    except Exception:
        pass
    return None


def _tracked_md(root):
    try:
        # -z: NUL-separated and, crucially, NOT quoted/escaped. Without it git
        # renders non-ASCII paths as "outputs/\345\214\273..." which never
        # matches the real filename in the index, producing a permanent false
        # positive the author cannot clear. Measured 2026-09-07 on
        # deep-research: 1 Japanese-named file stuck at "uncovered" forever.
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "*.md"],
            capture_output=True, timeout=20,
        )
        if out.returncode != 0:
            return []
        raw = out.stdout.decode("utf-8", "replace")
    except Exception:
        return []
    return [p.strip() for p in raw.split("\0") if p.strip()]


def _is_candidate(path):
    if any(path.startswith(d) or ("/" + d) in path for d in EXCLUDE_DIRS):
        return False
    if os.path.basename(path) in EXCLUDE_BASENAMES:
        return False
    return True


def uncovered(root):
    """Return (index_path, [uncovered paths]). index_path None if no index."""
    index_path = None
    for name in INDEX_NAMES:
        cand = os.path.join(root, name)
        if os.path.isfile(cand):
            index_path = cand
            break
    if index_path is None:
        return None, []

    try:
        with open(index_path, "rb") as f:
            index_text = f.read().decode("utf-8", "replace")
    except Exception:
        return index_path, []

    missing = []
    for path in _tracked_md(root):
        if not _is_candidate(path):
            continue
        base = os.path.basename(path)
        # An entry counts as covered if the index names the file at all,
        # by basename or by repo-relative path. Deliberately permissive:
        # the invariant is "the index knows this file exists", not formatting.
        if base in index_text or path in index_text:
            continue
        missing.append(path)
    return index_path, sorted(missing)


def _selftest():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="fig_selftest_")
    try:
        subprocess.run(["git", "init", "-q", tmp], check=True, timeout=20)
        subprocess.run(["git", "-C", tmp, "config", "user.email", "t@t"], timeout=10)
        subprocess.run(["git", "-C", tmp, "config", "user.name", "t"], timeout=10)
        os.makedirs(os.path.join(tmp, "outputs"))
        for name in ("alpha.md", "beta.md", "gamma.md"):
            with open(os.path.join(tmp, "outputs", name), "w") as f:
                f.write("# " + name + "\n")
        # Index that knows only alpha -> beta and gamma must be reported.
        with open(os.path.join(tmp, "FILE_INDEX.md"), "w") as f:
            f.write("# FILE INDEX\n\n| file | role |\n|---|---|\n| outputs/alpha.md | a |\n")
        subprocess.run(["git", "-C", tmp, "add", "-A"], timeout=20)
        subprocess.run(["git", "-C", tmp, "commit", "-qm", "x"], timeout=20)

        _, miss = uncovered(tmp)
        expect = ["outputs/beta.md", "outputs/gamma.md"]
        assert miss == expect, "BROKEN-FIXTURE direction failed: %r != %r" % (miss, expect)
        print("selftest 1/3 PASS: incomplete index reports %d uncovered" % len(miss))

        # Complete the index -> must go silent.
        with open(os.path.join(tmp, "FILE_INDEX.md"), "a") as f:
            f.write("| outputs/beta.md | b |\n| outputs/gamma.md | g |\n")
        _, miss2 = uncovered(tmp)
        assert miss2 == [], "fixed-index direction failed: %r" % (miss2,)
        print("selftest 2/3 PASS: complete index is silent")

        # A repo with no index must be silent (not every repo curates one).
        os.remove(os.path.join(tmp, "FILE_INDEX.md"))
        idx3, miss3 = uncovered(tmp)
        assert idx3 is None and miss3 == [], "no-index direction failed"
        print("selftest 3/3 PASS: repo without an index is silent")
        print("SELFTEST OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    if "--list" in sys.argv:
        root = _repo_root(os.getcwd()) or os.getcwd()
        idx, miss = uncovered(root)
        if idx is None:
            print("no FILE_INDEX.md in %s" % root)
            sys.exit(0)
        print("index: %s" % idx)
        print("uncovered: %d" % len(miss))
        for m in miss:
            print("  %s" % m)
        sys.exit(0)

    cwd = os.getcwd()
    _payload = {}
    try:
        raw = sys.stdin.buffer.read()
        if raw:
            data = json.loads(raw.decode("utf-8", "replace"))
            _payload = data if isinstance(data, dict) else {}
            cwd = data.get("cwd") or cwd
    except Exception:
        pass

    root = _repo_root(cwd)
    if not root:
        sys.exit(0)
    try:
        _, miss = uncovered(root)
    except Exception:
        sys.exit(0)
    if not miss:
        sys.exit(0)

    # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む。
    # `data` is bound inside the try above and may not exist if stdin was
    # empty, so pass the payload explicitly rather than via locals().
    _record_firing("file_index_guard", _payload)

    sample = ", ".join(os.path.basename(m) for m in miss[:3])
    more = "" if len(miss) <= 3 else " ほか%d件" % (len(miss) - 3)
    sys.stderr.write(
        "[file_index_guard] FILE_INDEX.md に未収載の .md が %d 件あります: %s%s\n"
        "索引は「載っている行は正しい」ので欠落に気づけません。"
        "全件は `python .claude/hooks/file_index_guard.py --list` で確認し、"
        "説明を付けて索引に追記してください。\n" % (len(miss), sample, more)
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
