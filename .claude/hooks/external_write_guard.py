# -*- coding: utf-8 -*-
"""PostToolUse(Write|Edit) recorder + Stop checker: external-write date guard.

WHY THIS EXISTS (2026-09-08)
----------------------------
md_date_guard.py and pre_report_quality_guard.py are PreToolUse hooks. They
see a write only when Claude Code performs it. During the Obsidian trial a
second writer exists: the human, editing .md files inside Obsidian. Nothing
inspects those edits at all, so a stale 最終更新日 written from Obsidian ships
silently -- the exact defect class md_date_guard was built for, arriving
through a door that guard does not watch.

WHY ONE FILE FOR TWO EVENTS
---------------------------
The check needs to know which changed files Claude itself wrote, so it can
inspect only the rest. That requires recording Claude's writes (PostToolUse)
and reading that record at end of turn (Stop). Splitting this into two files
would put one half of an invariant in each, and the 2026-09-03 audit showed
what happens to paired artifacts that can drift apart (10 deploy_*.py, 5 hooks
at 0/44 repos). One file, dispatched on stdin's `hook_event_name`.

WHY DIFFERENCING INSTEAD OF CHECKING EVERYTHING
-----------------------------------------------
Checking every changed .md at Stop would re-report what PreToolUse already
reported this turn, on every single turn. A guard that repeats known findings
is trained away within a day. Only the set difference (changed .md MINUS paths
Claude touched this session) is inspected -- by construction that is the set of
writes no PreToolUse guard ever saw.

WHY WARN AND NOT BLOCK
-----------------------
Stop-time blocking stops the user's work for a finding that is, by definition,
about a file the user edited by hand elsewhere. The firing rate is unmeasured
on day one; blocking on an uncalibrated guard is how guards get switched off.
Warn first (stderr), calibrate, then decide.

WHY THE CHECK LOGIC IS IMPORTED, NOT REIMPLEMENTED
--------------------------------------------------
CLAUDE.md §14 F2. On 2026-08-04 a self-written re-implementation of an
`include` matcher declared a config "verified" while the real implementation
disagreed with it on every pattern. md_date_guard._check and
pre_report_quality_guard._analyze are called here directly; if they change,
this guard changes with them.

CALIBRATION (measured 2026-09-08, not chosen)
---------------------------------------------
See --selftest, direction (a)/(b)/(c). Direction (a) constructs the DEFECTIVE
state (an external write carrying a week-old 最終更新日) in a disposable git
repo and asserts the guard reports it; direction (b) makes the identical file
content but records it as Claude-touched and asserts silence; direction (c)
asserts silence on a clean tree. A guard that only passes on the fixed version
proves nothing. 実測: 対象は Vault 登録された 2 リポのみで、他リポでは外部
書き込みが構造的に発生しない。

FAIL-OPEN: every path is wrapped; any error exits 0.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

STATE_DIRNAME = os.path.join(".claude", ".external_write_guard")
MAX_REPORTED = 6


def _sid(ev):
    """Filesystem-safe session id. Mirrors firing_log._sid."""
    try:
        s = (ev or {}).get("session_id") or "default"
    except Exception:
        s = "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64] or "default"


def _git(*args, **kw):
    return subprocess.run(["git"] + list(args), capture_output=True,
                          text=True, timeout=15, cwd=kw.get("cwd"))


def _git_bytes(*args, **kw):
    """git returning raw bytes: filenames may not be valid UTF-8 in this
    locale. Mirrors session_guard._git_bytes."""
    p = subprocess.run(["git"] + list(args), capture_output=True,
                       timeout=15, cwd=kw.get("cwd"))
    return p.stdout if p.returncode == 0 else b""


def _repo_root(cwd):
    try:
        r = _git("rev-parse", "--show-toplevel", cwd=cwd)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _norm(root, path):
    """Repo-root-relative, forward slashes, lowercase -- the join key between
    a tool_input file_path (absolute) and a `git status` name (relative)."""
    try:
        p = path if os.path.isabs(path) else os.path.join(root, path)
        rel = os.path.relpath(os.path.abspath(p), os.path.abspath(root))
    except Exception:
        rel = path
    return rel.replace("\\", "/").lstrip("./").lower()


def state_path(root, ev):
    return os.path.join(root, STATE_DIRNAME, _sid(ev) + ".txt")


def record_touch(root, ev, rel):
    """Append one repo-relative path to this session's touched-path file."""
    try:
        p = state_path(root, ev)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(rel + "\n")
        return True
    except Exception:
        return False


def load_touched(root, ev):
    try:
        with open(state_path(root, ev), encoding="utf-8") as f:
            return set(ln.strip() for ln in f if ln.strip())
    except Exception:
        return set()


def changed_md(root):
    """Changed/untracked .md paths, repo-root-relative.

    Byte mode (-z) because non-ASCII filenames are otherwise octal-escaped;
    -uall because git otherwise reports an untracked DIRECTORY and hides every
    .md inside it. Rename/copy entries are followed by the ORIGIN path as its
    own field, which must be consumed. Same shape as session_guard.py.
    """
    out = set()
    try:
        raw = _git_bytes("status", "--porcelain", "-z", "-uall", cwd=root)
        fields = [f for f in (raw or b"").split(b"\x00") if f]
        i = 0
        while i < len(fields):
            f = fields[i].decode("utf-8", "replace")
            status, name = f[:2], f[3:]
            i += 1
            if status and status[0] in ("R", "C"):
                i += 1
            if status.strip() == "D":
                continue
            if name.lower().endswith(".md"):
                out.add(name.replace("\\", "/"))
    except Exception:
        return set()
    return out


def read_before(root, rel):
    """(before_text, is_new). before is '' for a file not in HEAD."""
    try:
        p = subprocess.run(["git", "show", "HEAD:" + rel],
                           capture_output=True, timeout=15, cwd=root)
        if p.returncode == 0:
            return p.stdout.decode("utf-8", "replace"), False
    except Exception:
        pass
    return "", True


def _quality_mods(hooks_dir):
    """(numeric_precision_check, report_rigor_check) or (None, None)."""
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        import numeric_precision_check as npc
    except Exception:
        npc = None
    try:
        import report_rigor_check as rrc
    except Exception:
        rrc = None
    return (npc, rrc)


def inspect(root, rels, today=None):
    """Return [(rel, [message, ...]), ...] for the given repo-relative paths.

    Check logic is IMPORTED from the existing guards, never reimplemented
    (CLAUDE.md §14 F2). Anything that cannot be imported is skipped rather
    than approximated.
    """
    today = today or date.today()
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)
    try:
        import md_date_guard as mdg
    except Exception:
        mdg = None
    try:
        import pre_report_quality_guard as prq
    except Exception:
        prq = None
    if mdg is None and prq is None:
        return []

    mdg_cfg = mdg._load_config() if mdg else None
    prq_cfg = prq._load_config() if prq else None
    mods = _quality_mods(hooks_dir) if prq else (None, None)

    findings = []
    for rel in sorted(rels):
        ap = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(ap):
            continue
        try:
            with open(ap, encoding="utf-8-sig") as f:
                after = f.read()
        except Exception:
            continue
        before, is_new = read_before(root, rel)
        msgs = []

        if mdg is not None and mdg._in_scope(ap, mdg_cfg):
            try:
                fails, warns = mdg._check(after, before, today, is_new)
            except Exception:
                fails, warns = [], []
            if not is_new and fails:
                try:
                    pre_f, _ = mdg._check(before, before, today, False)
                except Exception:
                    pre_f = []
                fails = [x for x in fails if x not in pre_f]
            msgs.extend("[日付] " + x for x in fails)
            msgs.extend("[日付] " + x for x in warns)

        if prq is not None and prq._in_scope(ap, prq_cfg) and any(mods):
            try:
                f_before = prq._analyze(before, prq_cfg, mods)
                f_after = prq._analyze(after, prq_cfg, mods)
            except Exception:
                f_before, f_after = [], []
            if len(f_after) > len(f_before):
                seen = set(f_before)
                added = [x for x in f_after if x not in seen] or f_after[-1:]
                msgs.extend("[%s] %s" % (k, v) for k, v in added)

        if msgs:
            findings.append((rel, msgs))
    return findings


def external_paths(root, ev):
    """Changed .md MINUS paths Claude touched this session."""
    touched = load_touched(root, ev)
    return set(rel for rel in changed_md(root)
               if _norm(root, rel) not in touched)


def handle_post_tool_use(data):
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    if not fp.lower().endswith(".md"):
        return
    root = _repo_root(os.getcwd())
    if not root:
        return
    record_touch(root, data, _norm(root, fp))


def handle_stop(data):
    if data.get("stop_hook_active"):
        return
    root = _repo_root(os.getcwd())
    if not root:
        return
    rels = external_paths(root, data)
    if not rels:
        return
    findings = inspect(root, rels)
    if not findings:
        return
    _record_firing("external_write_guard", data)
    lines = []
    for rel, msgs in findings[:MAX_REPORTED]:
        for m in msgs[:3]:
            lines.append("・%s: %s" % (rel, m))
    more = ""
    if len(findings) > MAX_REPORTED:
        more = "\n（ほか %d ファイル）" % (len(findings) - MAX_REPORTED)
    sys.stderr.write(
        "⚠ Claude Code 以外が書いた .md に問題があります"
        "（Obsidian 等からの外部編集・warn のみでブロックはしません）:\n"
        + "\n".join(lines) + more +
        "\nこれらのファイルは PreToolUse ガードを通っていません。"
        "日付・数値表示を確認してから完了してください。\n")


def main():
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return
    try:
        ev = data.get("hook_event_name") or ""
        if ev == "PostToolUse":
            handle_post_tool_use(data)
        elif ev == "Stop":
            handle_stop(data)
    except Exception:
        pass


def _selftest():
    """Three directions (see CALIBRATION in the module docstring).

    Lives INSIDE the hook, not in a separate tests/ module, because deploy
    copies only this file: a selftest that imports tests/ passes in
    claude-governance and raises ModuleNotFoundError in all 44 deployed
    copies (found 2026-09-08 by running the deployed copy). A selftest that
    cannot run where the guard runs verifies nothing.
    """
    import io
    import shutil
    import tempfile
    from datetime import timedelta

    def _g(root, *args):
        return subprocess.run(["git"] + list(args), cwd=root,
                              capture_output=True, text=True, timeout=30)

    def _make_repo():
        tmp = tempfile.mkdtemp(prefix="ewg_selftest_")
        subprocess.run(["git", "init", "-q", tmp], check=True, timeout=30)
        _g(tmp, "config", "user.email", "t@t")
        _g(tmp, "config", "user.name", "t")
        os.makedirs(os.path.join(tmp, "outputs"))
        return tmp

    def _write(root, rel, text):
        p = os.path.join(root, rel.replace("/", os.sep))
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def _capture_stop(root, session_id):
        payload = {"hook_event_name": "Stop", "session_id": session_id,
                   "stop_hook_active": False}
        old_cwd, old_err = os.getcwd(), sys.stderr
        buf = io.StringIO()
        try:
            os.chdir(root)
            sys.stderr = buf
            handle_stop(payload)
        finally:
            sys.stderr = old_err
            os.chdir(old_cwd)
        return buf.getvalue()

    today = date.today()
    stale = (today - timedelta(days=7)).isoformat()
    good = today.isoformat()
    rel = "outputs/TRIAL_NOTE_%s.md" % today.strftime("%Y%m%d")
    results = []

    # (a) BROKEN FIXTURE: external write with a week-old date must be reported.
    root = _make_repo()
    try:
        _write(root, rel, "# Trial\n\n最終更新日: %s\n\n本文。\n" % good)
        _g(root, "add", "-A")
        _g(root, "commit", "-qm", "base")
        _write(root, rel, "# Trial\n\n最終更新日: %s\n\n本文。追記。\n" % stale)
        err = _capture_stop(root, "sess_a")
        ok = ("最終更新日" in err) and (stale in err) and (rel in err)
        results.append(("(a) broken fixture reported", ok))
        first = (err.strip().splitlines() or [""])[0]
        print("selftest 1/3 %s: %s" % ("PASS" if ok else "FAIL", first[:80]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # (b) SUPPRESSION: same defect, recorded as Claude-touched -> silent.
    root = _make_repo()
    try:
        _write(root, rel, "# Trial\n\n最終更新日: %s\n\n本文。\n" % good)
        _g(root, "add", "-A")
        _g(root, "commit", "-qm", "base")
        _write(root, rel, "# Trial\n\n最終更新日: %s\n\n本文。追記。\n" % stale)
        post = {"hook_event_name": "PostToolUse", "session_id": "sess_b",
                "tool_name": "Write",
                "tool_input": {"file_path": os.path.join(root, rel)}}
        old_cwd = os.getcwd()
        try:
            os.chdir(root)
            handle_post_tool_use(post)
        finally:
            os.chdir(old_cwd)
        err = _capture_stop(root, "sess_b")
        ok = (err.strip() == "")
        results.append(("(b) claude-touched suppressed", ok))
        print("selftest 2/3 %s: stderr=%r" % ("PASS" if ok else "FAIL", err[:80]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # (c) CLEAN: no changed .md -> silent.
    root = _make_repo()
    try:
        _write(root, rel, "# Trial\n\n最終更新日: %s\n\n本文。\n" % good)
        _g(root, "add", "-A")
        _g(root, "commit", "-qm", "base")
        err = _capture_stop(root, "sess_c")
        ok = (err.strip() == "")
        results.append(("(c) clean tree silent", ok))
        print("selftest 3/3 %s: stderr=%r" % ("PASS" if ok else "FAIL", err[:80]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    print("\n%d/%d passed" % (passed, len(results)))
    for name, ok in results:
        if not ok:
            print("  FAILED: %s" % name)
    if passed == len(results):
        print("SELFTEST OK")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # Piped stdout (CI, Claude Code's Bash tool) is cp932 on this host and
        # cannot encode ⚠ or many symbols -> UnicodeEncodeError masqueraded as
        # a selftest failure (2026-09-08). A real console is unaffected.
        for _s in (sys.stdout, sys.stderr):
            try:
                if not _s.isatty():
                    _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        sys.exit(_selftest())
    main()
    sys.exit(0)
