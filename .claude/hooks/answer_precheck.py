# -*- coding: utf-8 -*-
"""Run every Stop hook against a DRAFT answer, before the answer is written.

WHY (2026-11-03, user)
----------------------
「ほとんど回答しているのに、ほとんど同じ文言でもう一度同じような回答をしている…
最終的なチェックの上、1回の回答にまとめてくれないと…読む文章が増えてしまって鬱陶しい」

Replay of 262 human turns (2026-10-20 .. 11-03, all projects): 99 (37.8%) showed
two or more answers carrying the report format (留保 / Next Action / 成果物表).
The second answer comes from two places:
  * a Stop hook blocks AFTER the answer is on screen (review_gate, report_render_guard,
    scope_coverage_guard, request_ledger_guard, ... 26 Stop hooks), and the model
    writes the answer again;
  * the model reports while its own background work is still running, then reports
    again when the task notification wakes it.
A Stop hook cannot withdraw text already shown, so blocking harder only adds a
third answer. The checks have to run BEFORE the answer is written. This script is
that "final check": the model pipes its draft in, gets every Stop hook's verdict
on it, fixes the draft, and writes the answer once.

HOW
---
    python ~/.claude/hooks/answer_precheck.py <<'EOF'
    <draft answer>
    EOF
  1. Locates this session's transcript (CLAUDE_CODE_SESSION_ID).
  2. Builds a copy of it with the draft appended as the final assistant text.
  3. Runs every Stop hook registered in ~/.claude/settings.json and the project's
     .claude/settings*.json against that copy, in an isolated HOME / TEMP: the
     hooks' "once per instruction" state is a copy, so the real Stop run still
     checks the real answer.
  4. Adds its own checks: background work still running (do not report yet) and
     repetition of an answer already shown in this human turn.
  5. Prints the findings and records {turn, hash(draft), ok}. review_gate skips
     its forced re-review when the final answer is this draft and ok (the review
     checklist was shown here, before the answer). Every other Stop hook still
     runs on the real answer.

Exit code is always 0; the verdict is the first output line (PASS / FIX).

CALIBRATION (実測 2026-11-03)
  * Repetition check = response_length_guard.repetition. On 30 days of real turns
    (649 human turns) it flags 24.2% of turns (14 days: 29.7%, 78/263); a random
    sample of 12 flagged turns read by hand: about 8-9 were a second answer that
    restated the first (the user's complaint, incl. the 11-03 screenshot turn), 3-4
    were a genuinely new status report that shared format lines. A false hit costs
    one rewrite of a draft that has not been shown yet, so the threshold is kept.
  * Runtime: 25 Stop hooks in parallel, 10.7-11.2 s per run on this machine.
  * The user's 11-03 example (d192b99a, 交差検証の2本目) is FIX here
    (tests/fixtures/reanswer_20261103.json); HEAD without this file: no check at all.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import response_length_guard as R  # noqa: E402

NAME = "answer_precheck"
REAL_HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(REAL_HOME, ".claude", "state", NAME)
ADVISORY = {"review_gate.py": u"最終チェック（review_gate の点検項目。思考内で行い、答えに書かない）"}
SKIP = {"session_guard.py"}          # not about the answer
STATE_RECENT_S = 24 * 3600
HOOK_TIMEOUT_S = 90
REASON_MAX = 900


def norm_hash(text):
    t = re.sub(r"\s+", "", text or "")
    return hashlib.sha256(t.encode("utf-8", "replace")).hexdigest()[:24]


def _sid_key(sid):
    return hashlib.sha256((sid or "nosession").encode("utf-8", "replace")).hexdigest()[:16]


def find_transcript(sid):
    cands = glob.glob(os.path.join(REAL_HOME, ".claude", "projects", "*", sid + ".jsonl"))
    return max(cands, key=os.path.getmtime) if cands else None


def project_dir(rows):
    """The directory the session was started in (hooks get it as CLAUDE_PROJECT_DIR
    and defer to a repo-local copy registered there)."""
    for r in rows[:50]:
        if r.get("cwd"):
            return r["cwd"]
    return None


def session_start(tp):
    try:
        with io.open(tp, encoding="utf-8", errors="replace") as f:
            for _ in range(200):
                ln = f.readline()
                if not ln:
                    break
                ts = (json.loads(ln) if ln.strip() else {}).get("timestamp")
                if ts:
                    import calendar
                    return calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) - 3600
    except Exception:
        pass
    return None


def turn_key(rows):
    for r in reversed(rows):
        if R._is_boundary(r):
            return r.get("uuid") or norm_hash(json.dumps(r, sort_keys=True))
    return None


def final_text(rows):
    """The answer the turn ends with: text after the last tool call or mark."""
    ev = R.turn_events(rows) or []
    ans = R.answers_of_turn(ev)
    if not ev or ev[-1][0] != "text":
        return ""
    return ans[-1] if ans else ""


# ---------------------------------------------------------------- own checks
def changed_since_last_answer(ev):
    """Basenames of files written after the last answer shown in this turn."""
    last = max([i for i, e in enumerate(ev) if e[0] == "mark"], default=-1)
    out = set()
    for e in ev[last + 1:]:
        if e[0] == "tool" and e[1] in R.WRITE_TOOLS:
            fp = (e[2] or {}).get("file_path") or (e[2] or {}).get("notebook_path") or ""
            if fp:
                out.add(os.path.basename(fp.replace("\\", "/")))
    return out

def own_checks(rows, draft):
    out = []
    ev = R.turn_events(rows) or []
    try:
        launched, done = R.pending_tasks(rows)
        pending = len(launched - done)
    except Exception:
        pending = 0
    if pending:
        out.append(u"[待ち] 自分で起動したバックグラウンド作業が%d件まだ終わっていない。結果が報告に入るなら、"
                   u"いま最終回答を書かずに終え、全件そろってから1回だけ書く（途中で書くと同じ報告が2本になる）。" % pending)
    prevs = R.answers_of_turn(ev)
    why = R.repetition(prevs, draft, changed_since_last_answer(ev))
    if why:
        out.append(u"[再掲] この指示ですでに表示した回答と重なる（%s）。前に書いた結論・成果物表・留保・"
                   u"Next Action は書かず、変わった点だけを書く。" % u"・".join(why))
    return out


# ------------------------------------------------------- isolated environment
def _junction(src, dst):
    try:
        import _winapi
        _winapi.CreateJunction(src, dst)
        return True
    except Exception:
        try:
            os.symlink(src, dst, target_is_directory=True)
            return True
        except Exception:
            return False


def build_home(base, since=None):
    """HOME whose .claude/state is a fresh copy of the recent real state; every
    other entry points at the real one (hooks read repos, settings, memory)."""
    home = os.path.join(base, "home")
    dot = os.path.join(home, ".claude")
    if not os.path.isdir(dot):
        os.makedirs(dot)
        for name in os.listdir(REAL_HOME):
            src = os.path.join(REAL_HOME, name)
            if name == ".claude" or not os.path.isdir(src):
                continue
            _junction(src, os.path.join(home, name))
        real_dot = os.path.join(REAL_HOME, ".claude")
        for name in os.listdir(real_dot):
            src = os.path.join(real_dot, name)
            if name == "state":
                continue
            dst = os.path.join(dot, name)
            if os.path.isdir(src):
                _junction(src, dst)
            else:
                try:
                    os.link(src, dst)
                except Exception:
                    pass
    st = os.path.join(dot, "state")
    if os.path.lexists(st):
        if os.path.islink(st) or _is_junction(st):
            raise RuntimeError("isolated state is a link: refusing to delete " + st)
        shutil.rmtree(st, ignore_errors=True)
    real_st = os.path.join(REAL_HOME, ".claude", "state")
    # Everything written since the session started (its *_seen / once-per-instruction
    # state) and the last 24h (shared files). A 24h cut alone dropped 56 of 70 state
    # files of a 2-day session and re-fired once-only hooks here (Fable I1).
    cut = min(time.time() - STATE_RECENT_S, since or time.time())
    for root, dirs, files in os.walk(real_st):
        for fn in files:
            src = os.path.join(root, fn)
            try:
                if os.path.getmtime(src) < cut:
                    continue
                dst = os.path.join(st, os.path.relpath(src, real_st))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            except Exception:
                pass
    os.makedirs(st, exist_ok=True)
    return home


def _is_junction(p):
    try:
        return bool(getattr(os.path, "isjunction", lambda _p: False)(p))
    except Exception:
        return False


def stop_commands(cwd, settings_paths=None):
    paths = settings_paths or [
        os.path.join(REAL_HOME, ".claude", "settings.json"),
        os.path.join(cwd, ".claude", "settings.json"),
        os.path.join(cwd, ".claude", "settings.local.json"),
    ]
    cmds, seen = [], set()
    for p in paths:
        try:
            with io.open(p, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            continue
        for grp in (cfg.get("hooks") or {}).get("Stop") or []:
            for h in grp.get("hooks") or []:
                c = h.get("command")
                if h.get("type", "command") != "command" or not c:
                    continue
                name = os.path.basename(c.strip().strip('"').split('"')[-1].strip().strip('"'))
                m = re.findall(r"([\w.-]+\.(?:py|js|sh|ps1))", c)
                name = m[-1] if m else name
                if name in SKIP or name == os.path.basename(__file__) or c in seen:
                    continue
                seen.add(c)   # a repo-local copy runs too; the global one defers to it
                cmds.append((name, c))
    return cmds


def git_bash():
    """Claude Code runs hook commands with Git Bash on Windows; repo settings use
    POSIX commands (`P=$(command -v python3 ...); exec "$P" ...`). cmd.exe fails on
    them and the global copy defers to the failed local one: zero checks, PASS
    (Fable review 2026-11-03 C1). WSL's System32\\bash.exe is not Git Bash."""
    if os.name != "nt":
        return shutil.which("bash")
    cands = [os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or ""]
    g = shutil.which("git")
    if g:
        root = os.path.dirname(os.path.dirname(g))
        cands += [os.path.join(root, "bin", "bash.exe"), os.path.join(root, "usr", "bin", "bash.exe")]
    cands += [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]
    for c in cands:
        if c and os.path.isfile(c) and "system32" not in c.lower():
            return c
    return None


def run_hooks(cmds, payload, home, tmpd, cwd):
    env = dict(os.environ)
    env.update({"USERPROFILE": home, "HOME": home, "TEMP": tmpd, "TMP": tmpd,
                "ANSWER_PRECHECK": "1", "CLAUDE_PROJECT_DIR": cwd,
                "PYTHONIOENCODING": "utf-8"})
    data = json.dumps(payload).encode("utf-8")
    procs = []
    bash = git_bash()
    for name, c in cmds:
        try:
            argv = [bash, "-c", c] if bash else c
            p = subprocess.Popen(argv, shell=not bash, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            procs.append((name, p))
        except Exception as e:
            procs.append((name, e))
    out = []
    for name, p in procs:
        if isinstance(p, Exception):
            out.append((name, "error", str(p)))
            continue
        try:
            so, se = p.communicate(data, timeout=HOOK_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            p.kill()
            out.append((name, "timeout", ""))
            continue
        so = so.decode("utf-8", "replace").strip()
        se = se.decode("utf-8", "replace").strip()
        if p.returncode == 2:
            out.append((name, "block", se or so))
            continue
        if p.returncode != 0:
            out.append((name, "error", "exit %d: %s" % (p.returncode, (se or so)[-200:])))
            continue
        try:
            j = json.loads(so) if so else {}
        except Exception:
            j = {}
        if isinstance(j, dict) and (j.get("decision") == "block" or j.get("continue") is False):
            out.append((name, "block", j.get("reason") or j.get("stopReason") or ""))
    return out


# --------------------------------------------------------------------- state
def _state_path(sid):
    return os.path.join(STATE_DIR, _sid_key(sid) + ".json")


def _records(sid):
    try:
        with io.open(_state_path(sid), encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, list) else [st]
    except Exception:
        return []


def save_state(sid, rec):
    # A list, not one record: a subagent runs with its parent's session id, and its
    # precheck must not erase the parent's PASS (Fable I5).
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        p = _state_path(sid)
        recs = (_records(sid) + [rec])[-20:]
        with io.open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(recs, f)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


def passed(transcript_path, session_id):
    """True when the turn's final answer is a draft this script passed (review_gate)."""
    try:
        recs = [r for r in _records(session_id) if r.get("ok")]
        if not recs:
            return False
        rows = R.read_rows(transcript_path, need_boundary=True)
        tk, fin = turn_key(rows), final_text(rows)
        if not fin.strip():
            return False
        h = norm_hash(fin)
        return any(r.get("turn") == tk and r.get("hash") == h for r in recs)
    except Exception:
        return False


# ---------------------------------------------------------------------- main
def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="draft file (default: stdin)")
    ap.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--transcript")
    ap.add_argument("--cwd", help="project dir (default: the session's start dir)")
    ap.add_argument("--settings", action="append", help="settings file(s) to read Stop hooks from (tests)")
    a = ap.parse_args(argv)
    if a.file:
        draft = io.open(a.file, encoding="utf-8-sig").read()
    else:
        draft = sys.stdin.buffer.read().decode("utf-8", "replace").lstrip(u"﻿")
    if not draft.strip():
        print(u"FIX: 下書きが空。最終回答の下書きを標準入力か --file で渡す。")
        return 0
    sid = a.session or ""
    tp = a.transcript or (find_transcript(sid) if sid else None)
    if not tp or not os.path.exists(tp):
        print(u"FIX: このセッションの transcript が見つからない（CLAUDE_CODE_SESSION_ID=%s）。"
              u"--transcript で渡す。" % (sid or u"未設定"))
        return 0

    rows = R.read_rows(tp, need_boundary=True)
    if not a.cwd:
        try:
            with io.open(tp, encoding="utf-8", errors="replace") as f:
                head = [json.loads(ln) for ln in [f.readline() for _ in range(50)] if ln.strip()]
        except Exception:
            head = []
        a.cwd = project_dir(head) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    findings = own_checks(rows, draft)

    base = os.path.join(tempfile.gettempdir(), NAME, _sid_key(sid))
    os.makedirs(base, exist_ok=True)
    tmpd = os.path.join(base, "tmp")
    shutil.rmtree(tmpd, ignore_errors=True)
    os.makedirs(tmpd, exist_ok=True)
    home = build_home(base, session_start(tp))
    fake = os.path.join(base, "transcript.jsonl")
    shutil.copyfile(tp, fake)
    row = {"type": "assistant", "uuid": str(uuid.uuid4()), "sessionId": sid,
           "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
           "message": {"role": "assistant", "type": "message",
                       "content": [{"type": "text", "text": draft}]}}
    with io.open(fake, "ab") as f:
        f.write(b"\n" + json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n")
    payload = {"session_id": sid, "transcript_path": fake, "cwd": a.cwd,
               "hook_event_name": "Stop", "stop_hook_active": False}
    results = run_hooks(stop_commands(a.cwd, a.settings), payload, home, tmpd, a.cwd)

    blocks = [(n, r) for n, k, r in results if k == "block" and n not in ADVISORY]
    advice = [(n, r) for n, k, r in results if k == "block" and n in ADVISORY]
    broken = [(n, k + (": " + r[:120] if r else "")) for n, k, r in results if k in ("timeout", "error")]
    ok = not blocks and not findings and not broken   # a crashed check is not a pass (C2)
    save_state(sid, {"turn": turn_key(rows), "hash": norm_hash(draft), "ok": ok,
                     "t": int(time.time()), "blocks": [n for n, _ in blocks],
                     "own": len(findings)})

    lines = []
    if ok:
        lines.append(u"PASS: 下書きをそのまま最終回答として1回だけ書く。変えたらもう一度通す"
                     u"（review_gate は一致した下書きのときだけ差し戻しを省く）。")
    else:
        lines.append(u"FIX: 指摘%d件。直した下書きをもう一度通してから最終回答を書く。"
                     % (len(blocks) + len(findings) + len(broken)))
    for f in findings:
        lines.append(u"- " + f)
    for n, r in blocks:
        r = re.sub(r"\n{2,}", "\n", (r or "").strip())
        lines.append(u"- [%s] %s" % (n, r[:REASON_MAX] + (u"…" if len(r) > REASON_MAX else "")))
    for n, r in advice:
        r = (r or "").strip()
        lines.append(u"【%s】%s" % (ADVISORY[n], r[:REASON_MAX * 2]))
    if broken:
        lines.append(u"- [実行できなかった検査] %s。本番の Stop では動くかもしれないが、ここでは未確認なので PASS にしない。"
                     % u"、".join(u"%s=%s" % (n, k) for n, k in broken))
    sys.stdout.buffer.write((u"\n".join(lines) + u"\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        sys.stdout.buffer.write((u"FIX: 事前チェック自体が失敗した（%s: %s）。"
                                 u"最終回答はそのまま書いてよいが、Stop フックが差し戻すことがある。\n"
                                 % (type(e).__name__, e)).encode("utf-8"))
        sys.exit(0)
