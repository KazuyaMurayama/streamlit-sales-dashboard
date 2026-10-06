# -*- coding: utf-8 -*-
"""Stop hook: when a turn edits SOME files of a family of same-kind deliverables,
the answer must account for the WHOLE family.

WHY (2026-10-06, loop action C02 -- reports/CORRECTION_DIGEST_20261005.md)
-------------------------------------------------------------------------
Defect class C02「依頼の取りこぼし」was #1 in the weekly digest: 8 corrections
in 7 days, e.g.
  「他の本を題材にした記事もすべて同様の基準でチェックしたのか。更新済みである、
   それらの記事ドラフトのリンクをあなたは送るべきである。なぜ1冊だけで…」
  「ちゃんと修正対象を同様のものすべてにし、…対象ファイルもれないようにしろよ」
  「当然、残りの5本も進めるべきです」
Cause: Claude edits the files it started on and never enumerates the full set
of same-kind files (nt-001…nt-086 drafts, chapter files, per-item sheets).
The user then has to do the enumeration -- the most tiring kind of correction.

WHAT IT DOES
------------
Invariant (a class, not a string): when a turn edits some members of a family
of same-kind deliverable files, the answer states how many exist, which
were changed, and which were left alone and why.

1. Edited files of the current turn (last human prompt -> end) are read from
   the transcript: Write / Edit / MultiEdit / NotebookEdit paths, mcp__*write*
   style tools (path / file_path keys), document paths inside Bash / PowerShell
   commands that carry a write signal (git add, .write(, sed -i, > redirect,
   Set-Content, Out-File, cp/mv ...), inline sidechain rows, and subagent
   transcripts <session>/subagents/*.jsonl timestamped inside the turn (same
   source as countermeasure_gate). A templated path (nt-$n-*DRAFT.md, %s, {n})
   or a SLICED literal glob (glob(...)[:3], Select-Object -First 3) marks its
   family as touched; an unsliced literal glob counts all matches as edited.
   Opaque writes -- a script run (python x.py, node, npm run, a .ps1), a
   sliced/templated glob, or a write command whose doc paths do not resolve --
   switch on an mtime scan: documents under that command's cwd (depth <= 4,
   <= 6000 entries) modified inside the turn count as edited. The scan is off
   when the turn ran git pull/checkout/stash/... (pulled files are not edits).
   A Write whose result says create (toolUseResult.type == create /「File
   created successfully」) or a path no longer on disk is a NEW member: it is
   neither an edit of the family nor an unedited sibling.
   The transcript tail is read in a 4 MB window, widened x4 until the turn's
   prompt is inside it.
2. Only document-like files count (.md .markdown .html .txt .rst .tex .adoc),
   not code, tests, config, scratch/temp. CSV/TSV/JSON stay out: in calibration
   every CSV fire was a script's result table (final_cr1.csv ...).
3. Family = files in the SAME directory with the same extension whose names
   share a prefix + ID number of 1-5 digits (+ a tail tag: UPPERCASE or one of
   draft/final/wip/review/proof, case-insensitive, -v2 stripped):
   nt-013-xxx-DRAFT.md ~ nt-021-yyy-draft.md ~ nt-022-zzz-DRAFT-v2.md.
   Also 第3章.md (第N章/話/回/節/部/巻/講), number-first names when the rest is the
   same word (01_chapter.md, 02_chapter.md -- not 01_title / 02_body), and
   per-ID folders holding the same file name (_posts/nt-001/body.md ~
   _posts/nt-002/body.md). Several files with one ID (nt-001-DRAFT.md +
   nt-001-DRAFT-v2.md) are ONE member. Names with a date (YYYYMMDD /
   YYYY-MM-DD) are per-topic reports or versions, not members. Files marked
   「⛔ 廃盤」/ status: deprecated are not members. Fires only with >= 3 members
   and >= 1 member not edited.
4. Passes when the turn (code blocks and 「quoted」 text removed) accounts for
   coverage. FINAL message, any form: a scope count equal to the family size
   (「全80本」「80本中4本」「計80本」「80本の記事を全数確認」"all 80" "3 of 80"),
   or every unedited member named (nt-045, ranges nt-038〜041, 第4〜12章), or a
   scope word (対象外 / 不要（ / 除外 / out of scope ...) together with a named
   unedited member, a count >= the number left, or 「残りN本」/"the other N"
   with N == the number left. EARLIER messages of the turn count only in the
   two strong forms (total / every unedited member named) -- mid-turn notes
   are full of scope words + IDs. Each message is checked on its own.
   Also passes when the user's prompt restricted the scope to exactly the
   edited member(s): 「nt-002 だけ直して」/ "only chapter-03".
5. Otherwise the stop is blocked ONCE per instruction with the family pattern,
   total N, edited M, up to 10 unedited names, and the demand: apply the same
   change now, or list each as 「不要（理由）」 in a coverage table, with links
   for every changed file. The message also offers the one-line form for a
   user-named single file:「全N本中1本（ユーザー指定）、残りは対象外」(tested).

CALIBRATION (measured 2026-10-07 after the adversarial hardening,
tests/calibrate_scope_coverage_guard.py, the hook's own turns()/decide()/
add_subagents() imported; families are globbed against the CURRENT disk and
the mtime scan sees only each file's LAST modification, so past turns are
approximated -- files created later count as siblings, files deleted since are
missing, script edits later overwritten are invisible):
    404 real instructions in 30 days; 134 touched an ID-named document family;
    fires on 28 (6.9%; before hardening 26 = 6.5%). Recall on C02: 6 of 24
    corrected answers (unchanged). Most of the 24 are not about sibling files
    at all (添付の見落とし・判断材料不足・手順の未提示); of the 7 that are, 4 are
    caught (2026-09-30「有料部分…全体が載っている MD ファイル」, 2026-10-01
    「修正対象を同様のものすべてに」, 2026-10-02「8冊くらいがまだ」, 2026-10-03
    「他の本を題材にした記事もすべて」). The real pre-correction answer of
    2026-09-30T23:17 still BLOCKS (test_scope_coverage_guard.py).
    Fire diff vs the pre-hardening hook: +5 new (4 Soulful-Content nt-*-DRAFT
    families with M of 79 edited, 1 career_dev part<ID>.md touched by a
    templated write), -3 (one was a newly created draft = the FP2 fix; two no
    longer form a family -- not individually diagnosed).
    Variants measured: SIBLING_DIRS on -> 6.7% but recall 5/24 (loses one C02
    catch) -> off; PER_ID_DIRS off -> same 6.9% / 6/24 (no real fire from the
    per-ID layout yet) -> on; MTIME_SCAN off -> same numbers (the replay cannot
    see past mtimes; its effect is live-only, verified by the fixture tests).
    Rejected while hardening: joining all messages of the turn (a count in one
    and a scope word in another) and letting the weak form count in earlier
    messages each lost a C02 catch; treating `| head` as a slice lost one.
    Rejected 2026-10-06: counting an unsliced literal glob (nt-*.md) as
    "touched" instead of "edited" -> 10.5% firing and recall 5/24.
    All fires but one came from one repo (Soulful-Content): ID-numbered
    deliverable families are rare elsewhere.

ADVERSARIAL 2026-10-06 (Fable, 40 cases run through the real hook; verbatim in
tests/fixtures/scope_coverage_adversarial_20261006.json + 5 added cases, all
asserted by test_scope_coverage_guard.py):
    Before: 27 of 27 evasion cases passed, 7 of 9 legit cases were blocked.
    After: 15 of 27 evasions now BLOCK -- sliced globs (E4, E5), repo script
    (E6), os.path.join bare names (E7), inline/subagent edits (E8, E8b), >4 MB
    turn (E9), MCP write (E10), pathlib iterdir()[:3] (E12), -draft/-DRAFT
    (E13), per-ID folders (E15), 01_chapter (E16), 第N章 (E17), 5-digit IDs
    (E18), .tex (E22), -DRAFT-v2 (E25). Legit cases: 0 of 7 still blocked
    (FP1/FP7 via the user-scope rule, FP2 new member, FP3 earlier table, FP4/
    FP5 phrasings, FP9 regenerated by a script).
    Accepted residuals (asserted as PASS, documented, not chased): pure
    self-report (E1 「全41本を確認」 when untrue, E2, E3, E11 -- the hook cannot
    verify a claimed check), families split across sibling folders (E14, see
    SIBLING_DIRS), same-date names (E19), CSV/JSON items (E20, E21), families
    of 2 (E23), deprecated-marked siblings (E24 -- the mark is the user's own
    rule), block-once re-answer (E26 -- a second block loops), a deliverable
    folder literally named tests/ (E28), and deliberate gaming in general.

Skipped entirely when CLAUDE_HEADLESS_JOB=1 (scheduled `claude -p` jobs have
no user to account to).

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import calendar
import glob
import hashlib
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

NAME = "scope_coverage_guard"
TAIL_BYTES = 4 * 1024 * 1024          # first read window; widened x4 until the turn's prompt is inside it
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")
# Layout options measured in calibration (see docstring). Module flags so the calibrator can toggle them.
SIBLING_DIRS = False      # note/a/nt-001.md + note/b/nt-021.md as one family
PER_ID_DIRS = True        # _posts/nt-001/body.md + _posts/nt-002/body.md as one family
MTIME_SCAN = True         # opaque writes (scripts, sliced globs): docs modified during the turn count as edited

DOC_EXT = (".md", ".markdown", ".html", ".htm", ".txt", ".rst", ".tex", ".adoc")
_EXT_ALT = r"(?:md|markdown|html?|txt|rst|tex|adoc)"
# scratch / temp / test trees never hold deliverables ($TEMP/t0.md, t1.md ... would form a fake family).
# SCOPE_COVERAGE_SKIP_RE overrides it -- for the subprocess tests, whose fixtures live in %TEMP%.
SKIP_DIR = re.compile(os.environ.get("SCOPE_COVERAGE_SKIP_RE") or
                      r"(?i)[\\/](?:appdata[\\/]local[\\/]temp|tmp|temp|scratchpad|node_modules|\.git|tests?|fixtures|__pycache__)(?:[\\/]|$)")
WALK_SKIP = {"node_modules", ".git", "__pycache__", ".venv", "venv", "site-packages", "dist", "build", ".next", ".cache"}
DATE_IN_NAME = re.compile(r"(?<!\d)(?:20\d{6}|20\d{2}-\d{2}-\d{2})(?!\d)")
# prefix (starts with a letter) + ID number of 1-5 digits, followed by a separator or the end
ID_NAME = re.compile(r"^(?P<pre>[A-Za-z][A-Za-z_\-]*?)(?P<id>\d{1,5})(?=[-_.]|$)(?P<rest>.*)$")
NUM_FIRST = re.compile(r"^(?P<id>\d{1,5})[-_ .](?P<rest>.*[A-Za-z].*)$")                 # 01_chapter, 12-chapter
JA_NAME = re.compile(r"^第\s*(?P<id>\d{1,4})\s*(?P<kind>[章話回節部巻講])(?P<rest>.*)$")   # 第3章, 第12話_xxx
ID_DIR = re.compile(r"^(?P<pre>[A-Za-z][A-Za-z_\-]*?)(?P<id>\d{1,5})$")                   # _posts/nt-001/
TAG_WORDS = {"draft", "final", "wip", "review", "proof", "edited", "todo"}
WRITE_SIG = re.compile(
    r"git\s+add\b|\.write\(|write_text\(|\bsed\s+(?:-[A-Za-z]+\s+)*-i|\btee\b|Set-Content|Out-File|Add-Content"
    r"|(?:^|[;&|\s])(?:cp|mv|Copy-Item|Move-Item)\s|shutil\.(?:copy|move)|os\.replace\(|\.rename\("
    r"|>>?\s*[\"']?[^\s>&|;]+\." + _EXT_ALT + r"\b")
SCRIPT_RUN = re.compile(
    r"(?:^|[;&|\s(])(?:python3?|py|node|ruby|perl|bash|sh|pwsh|powershell)(?:\.exe)?\s+(?:-[\w-]+\s+)*[\"']?[^\s\"';&|<>]+"
    r"\.(?:py|js|mjs|cjs|ts|rb|pl|sh|ps1)\b|\bnpm\s+run\b|(?:^|[;&|]\s*)make\b|&\s*[\"']?\.?[\\/][^\s\"']+\.ps1")
GIT_TREE_CHANGE = re.compile(r"\bgit\s+(?:pull|checkout|switch|merge|rebase|stash|reset|restore|clone|cherry-pick|revert|am)\b")
# selects SOME of a glob's matches as write targets. `| head` is deliberately absent: it trims displayed output.
SLICE = re.compile(r"\]\s*\[\s*-?\d*\s*:\s*-?\d+\s*\]|\)\s*\[\s*-?\d*\s*:\s*-?\d+\s*\]|Select(?:-Object)?\s+-(?:First|Last|Skip)\b|islice\(")
PATH_TOKEN = re.compile(r"((?:[A-Za-z]:)?[\w.~/\\$%{}*?\[\]\-]*[\w$%}*\]]\." + _EXT_ALT + r")(?![\w.])")
CD_RE = re.compile(r"(?:^|[;&|]\s*)(?:cd|Set-Location|pushd)\s+[\"']?([^\"';&|\n]+?)[\"']?\s*(?:&&|;|\n|$)")
DEPRECATED = re.compile(r"⛔\s*廃盤|^status:\s*deprecated", re.M)
MCP_WRITE = re.compile(r"(?i)^mcp__.*(?:write|edit|create|update|save|append|put|move|copy)")
MCP_PATH_KEYS = ("path", "file_path", "filePath", "filename", "file", "destination", "target")


# --------------------------------------------------------------------------- paths
def _norm(p, cwd):
    p = (p or "").strip().strip("\"'")
    if not p:
        return ""
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)          # /c/Users/... (Git Bash)
    if m:
        p = m.group(1).upper() + ":/" + m.group(2)
    if p.startswith("~"):
        p = os.path.expanduser(p)
    if not os.path.isabs(p) and not re.match(r"^[A-Za-z]:", p):
        if not cwd:
            return ""
        p = os.path.join(cwd, p)
    return os.path.normpath(p)


def is_doc(path):
    return path.lower().endswith(DOC_EXT) and not SKIP_DIR.search(path)


def _tag(rest):
    toks = [t for t in re.split(r"[-_. ]", rest) if t]
    while toks and re.fullmatch(r"(?i)v\d{1,2}", toks[-1]):           # -DRAFT-v2 is still a DRAFT
        toks.pop()
    if toks and (re.fullmatch(r"[A-Z]{2,}", toks[-1]) or toks[-1].lower() in TAG_WORDS):
        return toks[-1].upper()                                       # -DRAFT == -draft
    return ""


def parse_name(path):
    """(family key, ID) or (None, None). key = (dir, ext, prefix, tag); for per-ID folders
    (_posts/nt-001/body.md) dir is the grandparent, prefix 'dir:<pre>' and tag the file name."""
    d, base = os.path.split(path)
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    pdir, dname = os.path.split(d)
    if PER_ID_DIRS:
        m = ID_DIR.match(dname)
        if m and m.group("pre").lower() not in ("v", "ver", "rev") and not ID_NAME.match(stem):
            return (os.path.normcase(pdir), ext, "dir:" + m.group("pre").lower(), base.lower()), int(m.group("id"))
    if DATE_IN_NAME.search(stem):
        return None, None
    m = ID_NAME.match(stem)
    if m and m.group("pre").lower() not in ("v", "ver", "rev"):
        return (os.path.normcase(d), ext, m.group("pre").lower(), _tag(m.group("rest"))), int(m.group("id"))
    m = JA_NAME.match(stem)
    if m:
        return (os.path.normcase(d), ext, "第" + m.group("kind"), _tag(m.group("rest"))), int(m.group("id"))
    m = NUM_FIRST.match(stem)
    if m:
        # number-first only when the rest is the same word (01_chapter, 02_chapter); 01_title / 02_body
        # are parts of ONE item, not a family of same-kind deliverables.
        rest = re.sub(r"(?i)[-_ .]v\d{1,2}$", "", m.group("rest")).lower()
        return (os.path.normcase(d), ext, "#" + rest, ""), int(m.group("id"))
    return None, None


def family_key(path):
    return parse_name(path)[0]


def _deprecated(path):
    try:
        with open(path, "rb") as f:
            head = f.read(2048).decode("utf-8", "replace")
    except Exception:
        return False
    return bool(DEPRECATED.search(head))


def _scan_paths(key):
    d, ext, pre, tag = key
    if pre.startswith("dir:"):
        try:
            subs = [os.path.join(d, s) for s in os.listdir(d)]
        except Exception:
            return []
        return [os.path.join(s, tag) for s in subs if os.path.isfile(os.path.join(s, tag))]
    dirs = [d]
    if SIBLING_DIRS:
        par = os.path.dirname(d)
        try:
            dirs += [os.path.join(par, s) for s in os.listdir(par)
                     if os.path.isdir(os.path.join(par, s)) and os.path.normcase(os.path.join(par, s)) != d
                     and s.lower() not in ("archive", "_archive", "old", "backup", "deprecated", "trash")]
        except Exception:
            pass
    out = []
    for x in dirs:
        try:
            out += [os.path.join(x, n) for n in os.listdir(x)]
        except Exception:
            pass
    return out


def members(key):
    """({ID: [live paths]}, number of deprecated IDs) of a family, from disk. Several files with the
    same ID (nt-001-DRAFT.md + nt-001-DRAFT-v2.md) are ONE member."""
    groups, dead = {}, set()
    for p in _scan_paths(key):
        k, i = parse_name(p)
        if k is None or not os.path.isfile(p):
            continue
        if (k[1:] != key[1:]) if (SIBLING_DIRS and not key[2].startswith("dir:")) else (k != key):
            continue
        if _deprecated(p):
            dead.add(i)
        else:
            groups.setdefault(i, []).append(p)
    dead -= set(groups)
    return groups, len(dead)


# --------------------------------------------------------------------------- transcript
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _epoch(ts):
    try:
        return calendar.timegm(time.strptime(ts.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def _is_prompt(d):
    """A prompt the user typed -- not a tool result or harness notification."""
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def shell_paths(cmd, cwd):
    """(edited paths, templated globs, opaque root or "") named by a shell command.
    opaque root = the directory whose docs a script / sliced glob / unresolvable write may have changed."""
    if not cmd:
        return [], [], ""
    m = CD_RE.search(cmd)
    if m:
        c2 = _norm(m.group(1), cwd)
        if c2:
            cwd = c2
    script = bool(SCRIPT_RUN.search(cmd))
    if not WRITE_SIG.search(cmd):
        return [], [], (cwd if script else "")
    edited, templ = [], []
    sliced = bool(SLICE.search(cmd))
    resolved = False
    for tok in PATH_TOKEN.findall(cmd):
        if re.match(r"[\"']?\$\{?[A-Za-z_]", tok) or "$(" in tok:   # $TEMP/x.md, $HOME/...: not a repo path
            continue
        if re.search(r"[$%{]", tok):
            g = re.sub(r"\$\{?\w+\}?|%[sd0-9]+|\{[^}]*\}", "*", tok)
            p = _norm(g, cwd)
            if p:
                templ.append(p)
        elif re.search(r"[*?\[]", tok):
            p = _norm(tok, cwd)
            if not p:
                continue
            if sliced:
                # glob(...)[:3] / Select -First 3: only some matches were written -> touched, not edited
                templ.append(p)
            else:
                # an unsliced literal glob is expanded and counted as edited (conservative: it can only
                # silence the hook). Counting it as "touched only" measured 10.5% firing, LOWER C02 recall.
                edited.extend(glob.glob(p))
                resolved = True
        else:
            p = _norm(tok, cwd)
            if p:
                edited.append(p)
                resolved = resolved or os.path.exists(p)
    opaque = script or bool(templ) or not resolved
    return edited, templ, (cwd if opaque else "")


def _new_turn(d):
    ts = d.get("timestamp", "")
    return {"prompt": _text(d.get("message")).strip(), "ts": ts, "end": ts, "answer": "", "texts": [],
            "edited": set(), "templ": set(), "created": set(), "roots": set(), "tree_change": False}


def _use(cur, b, cwd):
    if not isinstance(b, dict) or b.get("type") != "tool_use":
        return
    inp = b.get("input") or {}
    name = b.get("name") or ""
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = _norm(inp.get("file_path") or inp.get("notebook_path") or "", cwd)
        if p:
            cur["edited"].add(p)
    elif name in ("Bash", "PowerShell"):
        cmd = inp.get("command") or ""
        e, t, root = shell_paths(cmd, cwd)
        cur["edited"].update(e)
        cur["templ"].update(t)
        if root:
            cur["roots"].add(root)
        if GIT_TREE_CHANGE.search(cmd):
            cur["tree_change"] = True
    elif MCP_WRITE.search(name):
        for k in MCP_PATH_KEYS:
            v = inp.get(k)
            if isinstance(v, str) and v:
                p = _norm(v, cwd)
                if p:
                    cur["edited"].add(p)
                break


def _result(cur, d):
    """Write results tell a NEW file (create) from an overwrite (update)."""
    r = d.get("toolUseResult")
    if isinstance(r, dict) and r.get("type") == "create" and r.get("filePath"):
        cur["created"].add(_norm(r["filePath"], d.get("cwd") or ""))
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                t = b.get("content")
                t = t if isinstance(t, str) else "".join(x.get("text", "") for x in (t or []) if isinstance(x, dict))
                m = re.match(r"File created successfully at:\s*(.+?)(?:\s+\(|\s*$)", t or "", re.M)
                if m:
                    cur["created"].add(_norm(m.group(1).strip(), d.get("cwd") or ""))


def _feed(cur, d, text=True):
    if d.get("timestamp"):
        cur["end"] = max(cur["end"], d["timestamp"])
    if d.get("type") == "user":
        _result(cur, d)
        return
    if d.get("type") != "assistant":
        return
    cwd = d.get("cwd") or ""
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        for b in c:
            _use(cur, b, cwd)
    if text:
        t = _text(d.get("message")).strip()
        if t:
            cur["answer"] = t
            cur["texts"].append(t)


def turns(lines):
    """Yield one dict per human instruction: prompt, ts, end, answer (last text), texts (all text of
    the turn), edited, templ, created, roots, tree_change. Inline sidechain rows add edits, not text."""
    cur = None
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if _is_prompt(d):
            if cur:
                yield cur
            cur = _new_turn(d)
            continue
        if cur is not None:
            _feed(cur, d, text=not d.get("isSidechain"))
    if cur:
        yield cur


def add_subagents(turn, tp, until=None):
    """Edits made by subagents dispatched in this turn: <transcript minus .jsonl>/subagents/*.jsonl,
    rows timestamped inside the turn (same source as countermeasure_gate). until: epoch upper bound
    (the calibrator passes the next prompt's time; the live hook has none)."""
    lo = _epoch(turn.get("ts") or "")
    d = os.path.join(os.path.splitext(tp)[0], "subagents")
    if lo is None or not os.path.isdir(d):
        return
    try:
        files = [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl")]
    except Exception:
        return
    end = turn["end"]
    for f in sorted(files, key=os.path.getmtime)[-100:]:
        try:
            if os.path.getmtime(f) < lo - 5:
                continue
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    t = _epoch(r.get("timestamp") or "")
                    if t is None or t < lo - 1 or (until is not None and t > until):
                        continue
                    _feed(turn, r, text=False)
        except Exception:
            continue
    turn["end"] = end


def _has_prompt(line):
    if '"promptSource"' not in line and '"permissionMode"' not in line:
        return False
    try:
        return _is_prompt(json.loads(line))
    except Exception:
        return False


def read_turn(tp):
    """The last turn. Reads the tail; widens the window until the turn's prompt is inside it."""
    size = os.path.getsize(tp)
    win = TAIL_BYTES
    while True:
        start = max(0, size - win)
        with open(tp, "rb") as f:
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()
        if start:
            lines = lines[1:]
        idx = None
        for i in range(len(lines) - 1, -1, -1):
            if _has_prompt(lines[i]):
                idx = i
                break
        if idx is not None or start == 0:
            break
        win *= 4
    last = None
    for t in turns(lines[idx or 0:]):
        last = t
    if last:
        add_subagents(last, tp)
    return last


def _recent_docs(roots, lo, hi, cap=6000):
    """Document files under the roots (depth <= 4) whose mtime lies in [lo, hi]."""
    out, n = set(), 0
    for root in roots:
        if not os.path.isdir(root):
            continue
        base = os.path.normpath(root).count(os.sep)
        for dp, dns, fns in os.walk(root):
            dns[:] = [x for x in dns if x not in WALK_SKIP and not SKIP_DIR.search(os.path.join(dp, x) + os.sep)]
            if os.path.normpath(dp).count(os.sep) - base >= 4:
                dns[:] = []
            for fn in fns:
                n += 1
                if n > cap:
                    return out
                if not fn.lower().endswith(DOC_EXT):
                    continue
                p = os.path.join(dp, fn)
                try:
                    mt = os.path.getmtime(p)
                except Exception:
                    continue
                if lo <= mt <= hi:
                    out.add(os.path.normpath(p))
    return out


# --------------------------------------------------------------------------- coverage
_COUNTER = r"(?:本|件|ファイル|冊|記事|個|つ|点|章|話|files?)"
_EN_NOUN = r"(?:drafts?|files?|articles?|chapters?|pages?|posts?|items?|documents?|docs?|sheets?|notes?)"


def _clean(answer):
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    a = re.sub(r"「[^」]{0,200}」", "「」", a)
    return unicodedata.normalize("NFKC", a)


def _scope_counts(a):
    """Totals the answer claims for a set: 全N本 / 計N本 / N本中 / N件すべて / M/N本 /
    N本の記事を全数 / all N / M of N / out of N / N drafts checked."""
    out = set()
    pats = (r"全\s*(\d+)\s*" + _COUNTER,
            r"計\s*(\d+)\s*" + _COUNTER,
            r"(\d+)\s*" + _COUNTER + r"\s*(?:中|のうち|すべて|全て|全部|とも|ともに|が対象|を対象|を確認|を点検|を走査|を検査)",
            r"(\d+)\s*" + _COUNTER + r"\s*の[^\s、。,.]{0,8}?\s*(?:を|は)?\s*(?:全数|すべて|全て|全部)",
            r"(?i)\ball\s+(?:the\s+)?(\d+)\b",
            r"(?i)\bout\s+of\s+(?:the\s+)?(\d+)\b",
            r"(?i)\btotal(?:\s+of)?\s+(\d+)\b",
            r"(?i)\b(\d+)\s+" + _EN_NOUN + r"\s+(?:in\s+total|total|checked|reviewed|audited)\b",
            r"(?i)\b\d+\s+of\s+(?:the\s+|all\s+)?(\d+)\b")
    for p in pats:
        for m in re.finditer(p, a):
            out.add(int(m.group(1)))
    for m in re.finditer(r"(\d+)\s*/\s*(\d+)\s*" + _COUNTER, a):
        out.add(int(m.group(2)))
    return out


def _ranges(it, ids):
    for m in it:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi >= lo and hi - lo <= 300:
            ids.update(range(lo, hi + 1))


def _named_ids(a, pre):
    """ID numbers the text names, with ranges expanded (nt-038〜041, 038〜041, 第3〜5章)."""
    ids = set()
    if pre.startswith("第"):
        _ranges(re.finditer(r"第\s*(\d{1,4})(?:\s*[〜~～–-]\s*第?\s*(\d{1,4}))?\s*" + re.escape(pre[1:]), a), ids)
    else:
        p = re.escape(pre[4:] if pre.startswith("dir:") else pre)
        if p and not pre.startswith("#"):
            _ranges(re.finditer(r"(?i)(?:" + p + r")\s*(\d{1,5})(?:\s*[〜~～–]\s*(?:" + p + r")?\s*(\d{1,5}))?", a), ids)
    _ranges(re.finditer(r"(?<![\d\w])(0\d{1,4})(?:\s*[〜~～–]\s*(0?\d{1,5}))?(?![\d])", a), ids)   # bare padded 045 / 038〜041
    return ids


SCOPE_WORD = re.compile(r"対象外|不要\s*[（(]|除外|対象から外|変更不要|修正不要|手を付けていない|未対応|未着手|対象としない|残り\s*\d+|そのまま(?:に|残)"
                        r"|(?i:\bthe other \d+|\bremaining \d+|\bthe rest\b|out of scope|not applicable|no changes? needed|left as is)")
RESTRICT = re.compile(r"だけ|のみ|(?i:\bonly\b|\bjust\b)")


def _stem_in(p, text):
    return os.path.splitext(os.path.basename(p))[0] in text


def covered(fam, text, strong_only=False):
    a = _clean(text)
    n_live, n_all = len(fam["members"]), len(fam["members"]) + fam["dead"]
    counts = _scope_counts(a)
    if counts & {n_live, n_all}:
        return True
    named = _named_ids(a, fam["key"][2])
    hit = [i for i in fam["unedited_ids"] if i in named or any(_stem_in(p, a) for p in fam["members"][i])]
    if len(hit) == len(fam["unedited_ids"]):
        return True
    if strong_only:
        return False
    # weak form: a scope word plus a named unedited member, a count at least the size of the rest, or
    # 「残りN本」 / "the other N" with N == the number left. Any count at all (old rule) let 「4本とも…残り3本は
    # レビュー中」 in an earlier message of the turn cover a family of 79.
    rest_n = len(fam["unedited_ids"])
    left = {int(x) for x in re.findall(r"(?i)(?:残り|残る|ほか|他の?|the other|remaining)\s*(\d+)", a)}
    if SCOPE_WORD.search(a) and (hit or any(c >= rest_n for c in counts) or rest_n in left):
        return True
    return False


def user_scoped(fam, prompt):
    """The user named exactly the edited member(s) and restricted the scope (「nt-002 だけ」 / only)."""
    p = unicodedata.normalize("NFKC", prompt or "")
    if not RESTRICT.search(p) or not fam["edited_ids"]:
        return False
    named = _named_ids(p, fam["key"][2])
    return all(i in named or any(_stem_in(x, p) for x in fam["members"][i]) for i in fam["edited_ids"])


def pattern(key):
    d, ext, pre, tag = key
    if pre.startswith("dir:"):
        return os.path.join(d, pre[4:] + "<ID>", tag)
    if pre.startswith("#"):
        return os.path.join(d, "<ID>" + pre[1:] + ext)
    if pre.startswith("第"):
        return os.path.join(d, "第<ID>" + pre[1:] + "*" + ext)
    return os.path.join(d, pre + "<ID>" + ("*-" + tag if tag else "*") + ext)


def decide(turn, now=None):
    """First uncovered family touched by this turn as a dict, or None.
    now: end of the turn's window for the mtime scan (the hook passes time.time(); the calibrator
    leaves it None and the turn's last timestamp is used)."""
    if not turn or not turn.get("prompt"):
        return None
    edited = {os.path.normcase(p) for p in turn.get("edited", ())}
    created = {os.path.normcase(p) for p in turn.get("created", ())}
    if MTIME_SCAN and turn.get("roots") and not turn.get("tree_change"):
        lo = _epoch(turn.get("ts") or "")
        hi = now if now is not None else _epoch(turn.get("end") or "")
        if lo is not None and hi is not None:
            edited |= {os.path.normcase(p) for p in _recent_docs(turn["roots"], lo - 1, hi + 1)}
    keys, touched = {}, set()
    for p in edited:
        if not is_doc(p):
            continue
        k, i = parse_name(p)
        if not k:
            continue
        keys.setdefault(k, set())
        if p not in created and os.path.exists(p):           # a NEW member is not an edit of the family
            keys[k].add(i)
    for t in turn.get("templ", ()):
        if not is_doc(t):
            continue
        for p in glob.glob(t)[:500]:
            k = family_key(p)
            if k:
                keys.setdefault(k, set())
                touched.add(k)
    seen = set()
    for k in sorted(keys, key=lambda k: (-len(keys[k]), k)):     # the family this turn edited most first
        if not keys[k] and k not in touched:
            continue
        groups, dead = members(k)
        sig = frozenset(os.path.normcase(p) for ps in groups.values() for p in ps)
        if sig in seen:
            continue
        seen.add(sig)
        ids = set(keys[k])
        if SIBLING_DIRS:                                        # same family reached via a sibling dir's key
            for k2 in keys:
                if k2 != k and k2[1:] == k[1:]:
                    ids |= {i for i in groups if any(os.path.normcase(p) in edited for p in groups[i])}
        live = {i: ps for i, ps in groups.items() if not all(os.path.normcase(p) in created for p in ps)}
        if len(live) < 3:
            continue
        mine = sorted(i for i in live if i in ids)
        rest = sorted(i for i in live if i not in ids)
        if not rest:
            continue
        fam = {"key": k, "members": live, "dead": dead, "edited_ids": mine, "unedited_ids": rest,
               "edited": [sorted(live[i])[-1] for i in mine], "unedited": [sorted(live[i])[-1] for i in rest]}
        if user_scoped(fam, turn.get("prompt")):
            continue
        # The final answer may use any form. An EARLIER message of the turn (a coverage table before the
        # final 'push 完了') counts only in the strong forms -- the family total or every unedited member
        # named: mid-turn progress notes are full of scope words + IDs (「…nt-037 は対象から外し…」), and
        # letting those count lost the 2026-09-30 C02 catch. Messages are checked one by one: joined, a
        # count in one and a scope word in another combined.
        texts = turn.get("texts") or [turn.get("answer", "")]
        if not covered(fam, texts[-1]) and not any(covered(fam, t, strong_only=True) for t in texts[:-1]):
            return fam
    return None


# --------------------------------------------------------------------------- hook
def reason_for(fam):
    names = [os.path.basename(p) for p in fam["unedited"]]
    more = "" if len(names) <= 10 else "（他%d本）" % (len(names) - 10)
    m = len(fam["edited"])
    n = len(fam["members"])
    return ("【対象の取りこぼし検査（1回のみ）】このターンで同じ種類のファイル群の一部だけを変更した。"
            "ファイル群: %s（現存 %d本・廃盤除く）。このターンで変更を確認できたのは %s本、"
            "未変更は %d本: %s%s。"
            "同じ変更・同じ基準が残りにも当てはまるなら、今このターンで全部に適用せよ。"
            "当てはまらないものは、カバレッジ表（ファイル名｜変更した/不要｜理由）で「不要（理由）」と書け"
            "（同じ理由のものは nt-001〜037 のように範囲でまとめてよい）。"
            "回答には「全%d本中M本を変更」の形で総数と変更数を明記し、変更した全ファイルのリンクを載せよ"
            "（CLAUDE.md 絶対ルール2・依頼の取りこぼし C02）。"
            "ユーザーが特定の%d本だけを指定した依頼なら「全%d本中%d本（ユーザー指定）、残りは対象外」の1行で足りる。"
            % (pattern(fam["key"]), n,
               str(m) if m else "0（スクリプト・変数パス経由のため特定不能）",
               len(names), "、".join(names[:10]), more, n, max(m, 1), n, max(m, 1)))


def main():
    if os.environ.get("CLAUDE_HEADLESS_JOB") == "1":
        return
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return
    turn = read_turn(tp)
    fam = decide(turn, now=time.time())
    if not fam:
        return
    key = hashlib.sha1((turn.get("ts", "") + (turn.get("prompt") or "")).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_") + "_" + key)
    if os.path.exists(mark):
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason_for(fam)}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
