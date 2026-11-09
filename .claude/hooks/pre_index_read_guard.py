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

Part 2 (2026-11-09, C09): the same file also runs on PreToolUse Write|Edit|MultiEdit|NotebookEdit and
on Stop. When the latest prompt names a remote file (a GitHub blob/tree URL, or an undated living ledger
such as tasks.md with a freshness word), it denies the edit / blocks the answer once until this turn
has read that file from origin and its last-update date. See the Part 2 block above main().

Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, not chosen)
---------------------------------------------
Fired on 0 of 600 real Grep/Read/Bash calls replayed from 27 production
transcripts = 0.00%. Zero firings in the replay -- which on its own is
NOT evidence that the guard works. Per CLAUDE.md §14 F2 (「無反応は故障と
区別がつかない」), silence cannot be told apart from a hook that early-
returns on every payload, which is exactly how a guard died unnoticed on
2026-08-04.

RESOLVED by forcing a firing (2026-09-04): planted an index whose build
timestamp was 200h old (MAX_AGE_HOURS = 48) in a scratch directory and
sent a Read of index/REPORT_INDEX.md. The guard returned
permissionDecision "deny" reporting 「index が 8.3 日前のビルドで古い」.
So the 0.00% is the first reading (the index was fresh in all 27
transcripts), not the second (dead code). The replay measures how often
this fires in ordinary work; the forced firing is what proves it can.

Both numbers are needed. A rate alone would have left the ambiguity in
place, and this hook is precisely the kind that should almost never fire
-- the index is rebuilt daily, so a stale one is an exception, not a
routine event.
"""
import datetime as dt
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

MAX_AGE_HOURS = 48  # workflow runs daily; >48h means the working copy is behind
INDEX_NAMES = ("report_index.md", "reports.json")
SANCTIONED = ("search_reports.py", "origin/main:", "build_report_index.py")


# --- Codex blocking contract (F10g, 2026-09-18) -----------------------------
# Claude Code blocks on stdout JSON + exit 0. Codex blocks ONLY on exit code 2
# with the reason on stderr; its binary carries the string "PreToolUse hook
# exited with code 2 but did not write a blocking reason to stderr", and its
# TUI shows "Hook failed" (not "Blocked by hook") for anything else.
#
# Measured: these guards fired 28 times against a future-dated file under Codex
# and the file was written anyway. The guard was right; the decision was
# discarded. So "the hook fired" was never evidence of enforcement.
#
# Rather than edit each deny site (several sit inside `try/except: pass`, which
# would swallow a SystemExit), capture stdout and translate at process exit.
_CODEX_EXIT2_INSTALLED = True
if True:
    import atexit as _atexit
    import io as _io
    import json as _json
    import os as _os
    import sys as _sys

    class _TeeOut(_io.TextIOBase):
        """Pass stdout through while keeping a copy for the exit translator."""

        def __init__(self, real):
            self._real = real
            self.buf = []

        def write(self, s):
            self.buf.append(s)
            try:
                return self._real.write(s)
            except ValueError:
                # Interpreter shutdown can close the real stream before this
                # object is finalized. Keep buffering so the exit translator
                # still sees the decision; never raise from write().
                return len(s)

        def flush(self):
            # Called during interpreter finalization too, where the underlying
            # stream may already be closed. A raise here surfaces as
            # "Exception ignored in: <_TeeOut object>" noise on stderr, which
            # under Codex is exactly where a blocking reason is read from.
            try:
                self._real.flush()
            except ValueError:
                pass

    def _under_codex():
        if _os.environ.get("CLAUDE_HOOK_RUNTIME") == "claude":
            return False
        if _os.environ.get("CODEX_HOOK_RUNTIME") == "codex":
            return True
        return bool(_os.environ.get("CODEX_HOME"))

    _tee = _TeeOut(_sys.stdout)
    _sys.stdout = _tee

    def _codex_exit2():
        _sys.stdout = _tee._real
        if not _under_codex():
            return
        text = "".join(_tee.buf)
        reason = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = _json.loads(line)
            except Exception:
                continue
            hso = d.get("hookSpecificOutput") or {}
            if hso.get("permissionDecision") == "deny":
                reason = hso.get("permissionDecisionReason") or "blocked"
                break
        if reason is None:
            return
        try:
            _sys.stderr.write(reason + _os.linesep)
            _sys.stderr.flush()
        except Exception:
            pass
        _os._exit(2)   # bypass further atexit handlers and any except: pass

    _atexit.register(_codex_exit2)
# --- end Codex blocking contract -------------------------------------------


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


# =====================================================================================================
# Part 2 (2026-11-09, C09 「文脈・既出情報の見落とし」, reports/CORRECTION_DIGEST_20261109.md):
# a remote file the user pointed at must be read from origin before it is edited or answered about.
# =====================================================================================================
#
# DEFECT CLASS (no proper nouns): the user names a file that lives in a remote repository -- a GitHub
# blob/tree URL, or an undated living ledger by name -- and the turn edits it or answers about it from
# the local working copy or from memory, without reading the current origin version and its last-update
# date. The local clone rots silently (same root cause as Part 1: a stale copy answers as if current).
#   Real prompts (index/correction_history.jsonl, C09): 2026-11-06 「https://github.com/.../tasks.md
#   これ古くないか？」; 2026-10-25 and 2026-11-04 「https://github.com/.../REVIEW_REQUIRED_FILES_
#   20260918.md これ、古いままでは？更新して」.
#
# WHY HERE AND NOT IN external_state_claim_guard: that guard reads the ANSWER for state claims
# (「push 済み」「表示されています」) and does not treat a URL in the prompt as anything. Here the trigger
# is the PROMPT (the user handed over a remote file) and the answer need not contain a claim at all --
# 「更新しました」 after editing a stale copy is not an external-state sentence. This part never reads
# the answer text, so the two do not double-block the same sentence.
#
# INVARIANT
#   The latest human prompt names a remote file target --
#     URL    github.com/<owner>/<repo>/(blob|tree)/<branch>/<path> (outside code fences / IDE context)
#     LEDGER an undated living-document file name (AGENTS.md §3 「日付サフィックスを付けないもの」:
#            tasks / todo / readme / changelog / backlog / pipeline / *index / *ledger / current_*),
#            only when the SAME SENTENCE asks about or changes its current state (古い / 最新 / 更新 ...),
#            and only if the turn used it (a tool input names it) or answered with no tool call at all
#   and, before a Write/Edit of a non-temp file (PreToolUse) or before the final answer (Stop), THIS
#   TURN shows for every target:
#     FETCH  a read of the origin version: git show|ls-tree|log|diff|cat-file on origin/... after a
#            fetch/pull in this turn, the Contents API / raw / gh api / GitHub MCP / WebFetch naming the
#            path, or a local read (Read / Grep / cat / sed ...) of the path after `git pull` (or a
#            reset/merge/rebase onto origin/...) in this turn;
#     DATE   (blob targets, Stop only, and only when a freshness question -- 古い / 最新 / 最終更新 /
#            抜けて ... -- sits within 60 chars before / 120 after the target) its last-update date:
#            `git log` naming the path after the sync, a commits API call with path=, or a date
#            (YYYY-MM-DD) in the output of the FETCH read itself (the file's 最終更新日 line).
#   Write phase: a successful pull anywhere in the turn also counts as FETCH (the tree being edited is fresh).
#   -> deny the Write/Edit once (FETCH only) / block the answer once (FETCH and DATE) per instruction.
#   v2 (2026-11-09, after an independent Fable attack, scratchpad cm_fable_attack.md):
#     the Write/Edit is denied only when the edited file IS a target or lies in the target URL's repo (A1);
#     a LEDGER in a repo with no remote (`git remote -v` without a (fetch) line, or a no-remote pull
#     failure) is out of scope (A3); a pull that stopped on CONFLICT is not a pull (A9); raw.githubusercontent
#     and github.com/.../(blame|raw|commits)/ URLs are targets too (A6); URLs inside <pasted_content> are
#     quoted material, not handed-over files (A5).
#   A fetch whose `git status -sb` shows the branch level with origin (no [behind]) counts as a pull.
#   Contact counts, not identity (same rule as external_state_claim_guard): which clone was pulled is
#   not checked. A subagent's report is not evidence (AGENTS.md §5.3): Agent calls are ignored.
#
# FAIL-OPEN; once per (instruction, phase) with phase = write | stop; stop_hook_active -> return;
# CLAUDE_HEADLESS_JOB=1 -> skip. Transcript reading is imported from external_state_claim_guard
# (read_turn / Turn) and codex_transcript (resolve), not copied.
# Tests: tests/test_pre_index_read_guard_c09.py. Calibration: tests/calibrate_pre_index_read_guard_c09.py.

C09_STATE = os.path.join(os.path.expanduser("~"), ".claude", "state", "pre_index_read_guard_c09_seen")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
# groups: owner, repo, kind (blob|tree|blame|raw|commits; None for raw.githubusercontent), branch, path
GH_URL = re.compile(r"https?://(?:(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/(blob|tree|blame|raw|commits)/|"
                    r"raw\.githubusercontent\.com/([\w.-]+)/([\w.-]+)/)([\w.\-]+)/"
                    r"([A-Za-z0-9._~%/+@!$&*,;=:\-]+)", re.I)
# path is ASCII only: a URL copied from the browser is %-encoded, and 「…/tasks.mdこれ古い」 must not
# swallow the prose that follows it.
# AGENTS.md §3: files that are continuously updated and therefore carry no date suffix.
LEDGER_NAME = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*"
                         r"(?:tasks|todo|readme|changelog|backlog|pipeline|file_index|"
                         r"[\w-]*index|[\w-]*ledger|current_[\w-]+)"
                         r"\.(?:md|json|jsonl|csv|ya?ml))(?![\w.])", re.I)
FRESHNESS = re.compile(r"古い|古く|最新|更新|反映|追加して|追記|消して|削除して|直して|今の|現状|最終更新|"
                       r"載って|入って|抜けて|漏れ")
_CTX_BLOCK = re.compile(r"<(ide_[a-z_]+|system-reminder|command-[a-z-]+|local-command-[a-z-]+)>.*?</\1>", re.S)
# pasted material (logs, lists of past utterances, report bodies): a URL inside it is quoted, not handed over
_PASTED = re.compile(r"<pasted_content\b[^>]*>.*?(?:</pasted_content\b[^>]*>|$)", re.S)
_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
SHELLS = ("Bash", "PowerShell")
SYNC = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:fetch|pull)\b", re.I)
# after a fetch, a status line that shows the branch level with origin means the working tree IS origin
LEVEL = re.compile(r"^## [\w./-]+\.\.\.origin/[\w./-]+\s*$|Your branch is up to date with 'origin/|Already up to date",
                   re.M)
PULLED = re.compile(r"git\s+(?:-C\s+\S+\s+)?pull\b|"
                    r"git\s+(?:-C\s+\S+\s+)?(?:reset\s+--hard|merge|rebase)\s+(?:\S+\s+)*?\S*origin/", re.I)
ORIGIN_READ = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:show|ls-tree|log|diff|cat-file)\b[^\n;|&]*origin/", re.I)
API_READ = re.compile(r"api\.github\.com/repos/|raw\.githubusercontent\.com/|\bgh\s+api\b", re.I)
GIT_LOG = re.compile(r"git\s+(?:-C\s+\S+\s+)?log\b", re.I)
COMMITS_API = re.compile(r"/commits\?[^\s\"']*path=", re.I)
DATE_IN = re.compile(r"20\d\d-[01]\d-[0-3]\d|20\d\d/[01]?\d/[0-3]?\d|20\d\d年[01]?\d月")
# a git / HTTP failure in the output of the read itself (not any "error:" printed by other commands in the line)
FAILED = re.compile(r"fatal:|error: (?:cannot|could not|failed|Your local changes|pathspec)|Could not resolve host|"
                    r"Authentication failed|\"message\":\s*\"(?:Not Found|Bad credentials)|"
                    r"CONFLICT \(|Automatic merge failed", re.I)
# the working repo has no remote: a ledger there has no origin version to read (Fable attack A3)
NO_REMOTE_OUT = re.compile(r"No remote repository specified|does not appear to be a git repository|"
                           r"No such remote|There is no tracking information", re.I)
# The date is what answers a freshness question; it is required only when one is asked near the target.
STALE_Q = re.compile(r"古い|古く|最新|最終更新|いつの|更新されて(?:い)?な|反映されて(?:い)?な|抜けて|漏れて")
GITHUB_MCP_READ = re.compile(r"^mcp__.*github.*(?:get_file|contents)", re.I)
TEMP_PATH = re.compile(r"[\\/](?:AppData[\\/]Local[\\/]Temp|tmp|temp|scratchpad)[\\/]", re.I)


def _norm(s):
    try:
        from urllib.parse import unquote
        s = unquote(s)
    except Exception:
        pass
    return s.replace("\\\\", "/").replace("\\", "/").lower()


NEAR_BEFORE, NEAR_AFTER = 60, 120     # chars around a target in which a freshness word is "about" it


def _clean_prompt(prompt):
    return _FENCE.sub(" ", _PASTED.sub(" ", _CTX_BLOCK.sub(" ", prompt or "")))


def _near(text, start, end, rx):
    return rx.search(text[max(0, start - NEAR_BEFORE):end + NEAR_AFTER]) is not None


def _sentence(text, start, end):
    a = max(text.rfind(c, 0, start) for c in "。\n！？!?") + 1
    ends = [i for i in (text.find(c, end) for c in "。\n！？!?") if i >= 0]
    return text[a:min(ends) if ends else len(text)]


def prompt_targets(prompt):
    """[(kind, path, is_dir)] remote files the prompt names. path is repo-relative, lower-case, '/'.
    A LEDGER name counts only when a freshness word (FRESHNESS) is in the same sentence as the name."""
    return [t[:3] for t in _targets(prompt)]


def _targets(prompt):
    """[(kind, path, is_dir, stale_q, repo)]; stale_q = a freshness question (STALE_Q) sits near the target;
    repo = the repository name from the URL (None for a bare ledger name)."""
    text = _clean_prompt(prompt)
    out, seen = [], set()
    for m in GH_URL.finditer(text):
        path = _norm(m.group(7)).rstrip("/.,。、")
        repo = (m.group(2) or m.group(5) or "").lower() or None
        if path and path not in seen:
            seen.add(path)
            out.append(("URL", path, (m.group(3) or "").lower() == "tree",
                        _near(text, m.start(), m.end(), STALE_Q), repo))
    rest = GH_URL.sub(lambda mm: " " * len(mm.group(0)), text)
    for m in LEDGER_NAME.finditer(rest):
        path = _norm(m.group(1))
        if path in seen or any(t[1].endswith("/" + path) for t in out):
            continue
        if not FRESHNESS.search(_sentence(rest, m.start(), m.end())):
            continue
        seen.add(path)
        out.append(("LEDGER", path, False, _near(rest, m.start(), m.end(), STALE_Q), None))
    return out


def _blob(inp):
    try:
        return json.dumps(inp, ensure_ascii=False)
    except Exception:
        return str(inp)


def _mentions(blob_n, path):
    """The tool input names the path: the full relative path, or -- for a bare file name -- the name
    standing alone (README.md does not match X_README.md)."""
    if "/" in path:
        return path in blob_n
    return re.search(r"(?<![\w.-])" + re.escape(path) + r"(?![\w.-])", blob_n) is not None


def target_evidence(tools, path, is_dir, write_phase=False):
    """(fetched, dated) for one target over this turn's tool calls [(name, input, result)], in order.
    write_phase: a successful pull anywhere in the turn is enough -- the working tree being edited is fresh."""
    synced = pulled = fetched = dated = False
    for t in tools:
        name = t[0] or ""
        inp = t[1] if isinstance(t[1], dict) else {}
        res = (t[2] if len(t) > 2 else "") or ""
        hit = _mentions(_norm(_blob(inp)), path)
        if name in SHELLS:
            cmd = str(inp.get("command") or "")
            ok = not FAILED.search(res[:3000])
            if ok and SYNC.search(cmd):
                synced = True
            if ok and (PULLED.search(cmd) or (synced and LEVEL.search(res) and "behind" not in res)):
                pulled = True
            if hit and ok:
                if API_READ.search(cmd) or pulled or (synced and ORIGIN_READ.search(cmd)):
                    fetched = True
                    if DATE_IN.search(res):
                        dated = True
                if COMMITS_API.search(cmd) or ((pulled or synced) and GIT_LOG.search(cmd) and DATE_IN.search(res)):
                    dated = True
        elif name in ("Read", "Grep", "Glob", "NotebookRead"):
            if hit and pulled:
                fetched = True
                if DATE_IN.search(res):
                    dated = True
        elif name == "WebFetch" or GITHUB_MCP_READ.search(name) or "browser_navigate" in name:
            if hit and not FAILED.search(res[:500]):
                fetched = True
                if DATE_IN.search(res):
                    dated = True
    if write_phase and pulled:
        fetched = True
    return fetched, (dated or is_dir)


def _no_remote(tools):
    """This turn showed that the working repo has no remote: `git remote -v` printed no (fetch) line, or a
    pull/fetch failed with a no-remote message."""
    for t in tools:
        if (t[0] or "") not in SHELLS:
            continue
        cmd = str((t[1] if isinstance(t[1], dict) else {}).get("command") or "")
        res = (t[2] if len(t) > 2 else "") or ""
        if re.search(r"git\s+(?:-C\s+\S+\s+)?remote\s+-v\b", cmd) and "(fetch)" not in res:
            return True
        if SYNC.search(cmd) and NO_REMOTE_OUT.search(res):
            return True
    return False


def _related(edit_path, path, repo):
    """The file being edited is the target itself, or lies in the target's repository."""
    e = _norm(edit_path)
    if e == path or e.endswith("/" + path):
        return True
    return bool(repo) and ("/" + repo + "/") in ("/" + e)


def c09_decide(prompt, tools, need_date=True, write_phase=False, edit_path=None):
    """[(kind, path, missing)] targets this turn has not read from origin; missing = 'FETCH' | 'DATE'.
    need_date=False is the write phase: editing needs a fresh copy; the date is checked before the answer,
    and only when the prompt asks a freshness question (STALE_Q: 古い / 最新 / 最終更新 / 抜けて ...)."""
    tools = [tuple(t) for t in (tools or [])]
    miss = []
    no_remote = _no_remote(tools)
    for kind, path, is_dir, stale_q, repo in _targets(prompt):
        # write phase: only an edit of the target, or inside its repository, can be made on a stale copy;
        # a new file elsewhere that merely uses the URL as a reference is not (Fable attack A1)
        if edit_path is not None and not _related(edit_path, path, repo):
            continue
        if kind == "LEDGER" and no_remote:
            continue
        # a ledger the turn never touched and did not answer from memory (it called tools) was not used
        # stale -- not reading it is a different defect (an instruction skipped), not this one
        if kind == "LEDGER" and tools and not any(_mentions(_norm(_blob(t[1])), path) for t in tools):
            continue
        fetched, dated = target_evidence(tools, path, is_dir, write_phase=write_phase)
        if not fetched:
            miss.append((kind, path, "FETCH"))
        elif need_date and stale_q and not dated:
            miss.append((kind, path, "DATE"))
    return miss


C09_REASON = (
    "【提示されたファイルを origin から読む（1回のみ）】依頼文が {targets} を指しているが、このターンに"
    "その origin の現物{what}を取得した記録が無い。ローカルの作業コピーや記憶の要約は黙って古くなる"
    "（2026-11-06「…/tasks.md これ古くないか？」、2026-10-25「…/REVIEW_REQUIRED_FILES… 古いままでは？」）。"
    "{phase}前に次を行え。"
    "①`git fetch origin -q` の後に `git show origin/<branch>:<path>`（または `git pull --rebase --autostash` の後に"
    "そのファイルを Read）。private リポのリンクなら認証付き Contents API（repo-retrieval スキル）で取る。"
    "②最終更新日を確かめる: `git log -1 --format=%ci origin/<branch> -- <path>` か、本文の最終更新日の行。"
    "③取得した版と依頼の前提（古い・抜けている等）を照らしてから{phase2}。"
    "サブエージェントの報告は証拠にならない（AGENTS.md §5.3）。"
)


def _c09_turn(ev):
    try:
        from external_state_claim_guard import read_turn as _read_turn
        from codex_transcript import resolve as _resolve
    except Exception:
        sys.stderr.write("[pre_index_read_guard] external_state_claim_guard.py / codex_transcript.py not found "
                         "next to this hook; the C09 check is NOT running." + os.linesep)
        return None
    tp = _resolve(ev.get("transcript_path") or "")
    if not tp or not os.path.isfile(tp):
        return None
    return _read_turn(tp)


def _c09_once(ev, turn, phase):
    """True the first time this (session, instruction, phase) is seen; marks it."""
    import hashlib
    ident = (turn.uid or turn.ts or "#%d" % turn.ordinal) + "|" + turn.prompt + "|" + phase
    key = hashlib.sha1(ident.encode("utf-8", "replace")).hexdigest()[:16]
    sid = "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")
    mark = os.path.join(C09_STATE, sid + "_" + key)
    if os.path.exists(mark):
        return False
    try:
        os.makedirs(C09_STATE, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    return True


def c09_main(ev, phase):
    if os.environ.get("CLAUDE_HEADLESS_JOB") == "1":
        return
    if phase == "stop" and ev.get("stop_hook_active"):
        return
    if phase == "write":
        ti = ev.get("tool_input") or {}
        if TEMP_PATH.search(str(ti.get("file_path") or ti.get("notebook_path") or "")):
            return          # a scratch script (often the one that does the fetch) is not the guarded edit
    turn = _c09_turn(ev)
    if turn is None:
        return
    edit_path = None
    if phase == "write":
        ti = ev.get("tool_input") or {}
        edit_path = str(ti.get("file_path") or ti.get("notebook_path") or "")
    miss = c09_decide(turn.prompt, turn.tool_list(), need_date=(phase == "stop"), write_phase=(phase == "write"),
                      edit_path=edit_path)
    if not miss or not _c09_once(ev, turn, phase):
        return
    _record_firing("pre_index_read_guard", ev)
    targets = "、".join("`%s`" % p for _k, p, _m in miss[:4]) + (" ほか" if len(miss) > 4 else "")
    what = "の最終更新日" if all(m == "DATE" for _k, _p, m in miss) else "と最終更新日"
    if phase == "write":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": C09_REASON.format(targets=targets, what=what, phase="編集の",
                                                          phase2="編集する")}}, ensure_ascii=True))
    else:
        reason = C09_REASON.format(targets=targets, what=what, phase="回答の", phase2="回答し直す")
        # print, not sys.stdout.buffer: stdout is the Codex tee (_TeeOut), which has no .buffer
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True))


def main():
    # If a same-named repo-local copy exists and we are the global copy, defer to it.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks",
                                            os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        # stdin はバイトで読んで UTF-8 復号する（cp932 既定で日本語 payload が落ちる。2026-09-15）
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        event = data.get("hook_event_name")
        if event == "Stop" or (event is None and "stop_hook_active" in data and "tool_name" not in data):
            c09_main(data, "stop")
            return
        if data.get("tool_name") in WRITE_TOOLS:
            c09_main(data, "write")
            return
        if not targets_index(data):
            return
        age = index_age_hours()
        if age is None or age <= MAX_AGE_HOURS:
            return
        # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
        _record_firing("pre_index_read_guard", data)
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
