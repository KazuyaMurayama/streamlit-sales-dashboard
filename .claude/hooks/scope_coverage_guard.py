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

REDESIGN 2026-11-03 (C02 recurred 12 times after adoption; reports/CORRECTION_DIGEST_20261102.md)
-------------------------------------------------------------------------------------------
Three of the 12 were this hook's class and it missed or misfired on all three:
  2026-10-30「5本も直して」 -- 3 reports fixed; the answer said the other 5 had the same defect and
      ended 「直すなら「5本も直して」と言ってください」. Dated names (GENAI_*_20261020.md) are no family.
  2026-10-14「それらも当然、検証して行を追加しろ」 -- a parameter grid: 「h=0.04 と 0.06 は計算していません」.
      Not files at all.
  2026-10-22「両方ともタスクです」 -- 「片方しかない63冊の作成は未対応…始めてよいかだけ決めてください」.
      The hook DID fire, but on the wrong set (119 drafts, 0 edited: a read-only glob whose output went
      to `> $S/matrix.txt` counted as a write), and 「全119本中0本を変更」 satisfied it.
Class, stated without names: the answer itself names a same-kind remainder of the work just done as
undone and stops -- with no reason belonging to those members, or by handing the go-ahead to the user.
6. Deferred remainder (any kind of set -- files, books, grid points): in the FINAL message, a sentence
   that names a remainder of >= 2 (他の/残り N本・冊・件…, N本にも…同じ, 同じ…N章にも, x=a・b は,
   未対応: …N冊, N冊は未対応) together with an undone marker (未対応/未評価/…/残っています/同じ問題/
   計算していません), or a rest-count (残りの/他の/次の/片方… N本, N本も) in a sentence asking the user to
   decide. It blocks only when the message hands the go-ahead to the user (「…なら言ってください」
   「決めてください」「ご判断ください」「お返事」「進めますか」): REQUIRE_DEFER = True. Not checked when
   the turn wrote nothing, the prompt limited the job (「3本だけ」「まず3つ」「そこまで」「実行はまだ」) or
   asked for a status listing (「…どれかを表形式で報告して」). Own once-per-instruction mark (suffix _r),
   own message 【残りの先送り検査（1回のみ）】.
7. A shell command whose ONLY write signals are redirects into a scratch path (`> $S/x.txt`, %TEMP%,
   scratchpad) writes no deliverable: its sliced/templated globs and literal doc paths were read. Its
   unsliced literal globs still count as edited (that direction can only silence).
CALIBRATION 2026-11-03 (tests/calibrate_scope_coverage_guard.py --days 7 --fast; HEAD copy via --hook,
both runs at the same time on the same transcripts): 76 instructions, HEAD fires 6 (7.9%), new 7 (9.2%)
-- the one new fire is the 2026-10-29T23:53 answer the user corrected (「5本も直して」); C02 recall in
the window 2/6 -> 3/6. Upper bound counting every message of a turn as a possible stop: also 9.2%.
30 days, remainder check alone (506 instructions): final message 3 (0.6%), any message 8 (1.6%): 3 were
corrected (10-14 grid, 10-22 63冊, 10-29 5本), 2 the same pattern uncorrected (「残りの6本も同じ手順で
直すか決めてください」「残りの15本は…書き直してよいか決めてください（推奨: 待たずに書き直す）」), 3 staged
plans (「次の10本に進めてよければ…」「段階2の33本も同じ流れで進めるか決めてください」×2).
Rejected: blocking a named remainder with no own reason even without a hand-off (REQUIRE_DEFER False)
-> 7 days 14.5% with earlier stops (+6.6 points; progress notes such as 「未着手: 第5・6波の51本」 during
a wave job); any count + 「決めてください」 without a rest anchor -> 30 days 4.7% (「次の2点をご判断ください」).
Tests: tests/test_scope_coverage_guard_remainder.py (HEAD 10/17, new 17/17).
ROUND 2 2026-11-03 (Sonnet attack, tests/fixtures/scope_coverage_guard_attack_20261103.json, 73 cases):
- A remainder sentence is dropped when it says the rest needs no work (NEGATED: 同じ問題がない / 残って
  いません / 0件 / 修正済み / 対象外 / 範囲外 / スキップ / 必要がない) or carries a reason of the members' own
  (OWN_REASON, in it or the sentence before: 権限 / 取り消せない / 購入・費用 / deny・あなたの操作).
- The hand-off must be bound to the remainder: in it, within the next two sentences, or later when it
  names the rest (残り / それら / 全部); a generic invite (「ほかに…あれば言ってください」「ご不明点があれば」)
  is not one. Wider hand-off forms (続けますか / どうしますか / やってよいですか / ご希望でしたら /
  ご指示をいただければ / 指示してください / should I / want me to) and remainder forms (残りは5本 / 残り五本 /
  **5本** / 「他にも5本あります。いずれも未対応です。」 / a 未対応 heading over its list / English
  「the other 5 … still」 / 「他の…にも同じ問題があります」 without a count).
- The prompt cut-outs no longer silence the whole check: 「まず…1本」 is overridden by 全部 / とも / そのあと,
  「報告して」 counts only when the prompt orders no work (「全8本を直して、結果を報告して」 is checked).
- A final 「以上です。」 written right after the hand-off (no tool call between) is skipped.
- Scratch = the OS temp folder, the scratchpad, or $TEMP/$TMP/$S-style variables; a repo folder that is
  merely named temp/ and $DOCS/... are deliverable paths.
- Overlap with delegation_guard (C03): when delegation_guard.stalled() stops the same hand-off sentence
  (a continuation Claude could decide), this check steps aside -- unless delegation_guard's once-per-
  instruction mark is already spent. SCOPE_REM_NO_DELEGATION=1 measures this hook alone.

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
DEFER_TO_DELEGATION = os.environ.get("SCOPE_REM_NO_DELEGATION") != "1"  # remainder check: leave a self-decidable go-ahead to delegation_guard.stalled() (C03)
REQUIRE_DEFER = True      # remainder check: block only when the answer hands the go-ahead to the user (see REDESIGN)
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


_TMP_ROOTS = None


def _tmp_roots():
    """The OS temp folders (and their long/short spellings), lower-cased with forward slashes."""
    global _TMP_ROOTS
    if _TMP_ROOTS is None:
        import tempfile
        roots = {tempfile.gettempdir()} | {os.environ.get(k) or "" for k in ("TEMP", "TMP", "TMPDIR")}
        out = set()
        for r in roots:
            if r:
                for v in (r, os.path.realpath(r)):
                    out.add(v.replace("\\", "/").rstrip("/").lower())
        out |= {"/tmp", "/var/tmp"}
        _TMP_ROOTS = sorted(x for x in out if x)
    return _TMP_ROOTS


# shell variables that name a scratch folder: $TEMP / $TMP / $TMPDIR / $env:TEMP / %TEMP% / $S / $SP / $SCRATCH...
_SCRATCH_VAR = re.compile(r"(?i)^(?:\$\{?(?:env:)?(?:temp|tmp|tmpdir|s|sp|scratch\w*|scratchpad)\}?|%(?:temp|tmp)%)(?:[\/]|$)")


def _scratch_redirect(sig):
    """A `> target` / `>> target` write signal whose target is scratch: the OS temp folder, the session
    scratchpad, or a variable that names one. A folder that only happens to be called temp/tmp inside a
    repo (docs/temp/a.md) is a deliverable path, and so is $DOCS/report.md."""
    m = re.match(r">>?\s*[\"']?(.+?)[\"']?$", sig.strip())
    if not m:
        return False
    t = m.group(1).strip()
    if t.lower() in ("/dev/null", "nul", "$null"):
        return True
    if _SCRATCH_VAR.match(t) or re.search(r"(?i)[\/]scratchpad(?:[\/]|$)", t):
        return True
    n = t.replace("\\", "/").lower()
    if re.match(r"^/[a-z]/", n):                         # Git Bash /c/Users/... -> c:/users/...
        n = n[1] + ":" + n[2:]
    return any(n == r or n.startswith(r + "/") for r in _tmp_roots())


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
    sigs = list(WRITE_SIG.finditer(cmd))
    # A command whose ONLY write signals are redirects / tee into a scratch path ($S/x.txt, %TEMP%\x.md,
    # .../scratchpad/...) writes no deliverable: the globs it names were read (2026-10-22: `python - <<EOF
    # ... glob(nt-*-DRAFT.md)[:n] ... EOF > $S/matrix.txt` fired on 119 drafts with 0 edited, and the
    # answer 「全119本中0本を変更」 satisfied the block while the real remainder went unaddressed).
    # An unsliced literal glob in such a command still counts as edited: that direction can only silence.
    scratch_only = bool(sigs) and all(_scratch_redirect(m.group(0)) for m in sigs)
    if not sigs:
        return [], [], (cwd if script else "")
    edited, templ, from_glob = [], [], []
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
                from_glob.extend(glob.glob(p))
                resolved = True
        else:
            p = _norm(tok, cwd)
            if p:
                edited.append(p)
                resolved = resolved or os.path.exists(p)
    if scratch_only:
        # read-only as far as documents go: keep only the silencing direction (unsliced glob = edited)
        return from_glob, [], (cwd if script else "")
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
    if text:
        t = _text(d.get("message")).strip()
        if t:
            cur["answer"] = t
            cur["texts"].append(t)
            # was there a tool call between the previous text and this one (a text is written before its calls)
            cur.setdefault("gaps", []).append(bool(cur.get("_tool_since")))
            cur["_tool_since"] = False
    if isinstance(c, list):
        for b in c:
            _use(cur, b, cwd)
            if isinstance(b, dict) and b.get("type") == "tool_use":
                cur["_tool_since"] = True


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


# --------------------------------------------------------------------------- deferred remainder
# Invariant (any kind of set, not only file families): when the answer ITSELF says that members of the
# same set as the work just done are still undone -- 「他の5本にも同じ問題が残っています」「h=0.04 と 0.06 は
# 計算していません」「片方しかない63冊の作成は未対応」 -- the left-out members need a reason of their own
# (not applicable / no permission / ...). 「直すなら言ってください」「決めてください」 is not such a reason:
# the same change applies, so it is applied now. Only the final message is read (each stop is checked).
_COUNTERS = r"(?:本|件|冊|点|個|記事|ファイル|章|話|通り|ケース|セル|種類|レポート|ページ|か所|箇所)"
_QTY = r"(\d[\d,]*)\s*" + _COUNTERS
_UNDONE_STRONG = r"(?:未対応|未着手|未作成|未評価|未適用|未修正|未実施|未計算|未検証|未処理)"
# the rest of a set: 他の5本 / 他にも5本 / 残りは5本 / 残り五本 / 5本にも同じ / 同じ…5本にも / the other 5 reports
REM_QTY = re.compile(r"(?:他|ほか|残り|残る|残った|あと|その他|それ以外|以外)(?:の|に|にも|は|が|も)?\s*" + _QTY
                     + r"|" + _QTY + r"\s*(?:に|で|は)?\s*も[^。\n]{0,30}(?:同じ|同様)"
                     + r"|(?:同じ|同様)[^。\n]{0,30}?" + _QTY + r"\s*(?:に|で)?\s*も"
                     + r"|(?i:\b(?:the\s+)?(?:other|remaining|rest of the|another)\s+(\d+)\s+[a-z]+)")
# a parameter grid named by its values: h=0.04 と 0.06 は / x=1, x=2 も
REM_PARAM = re.compile(r"(?<![\w.])[A-Za-z]\w{0,15}\s*=\s*-?\d[\d.]*(?:\s*(?:[・、,/]|と|や|および)\s*"
                       r"(?:[A-Za-z]\w{0,15}\s*=\s*)?-?\d[\d.]*)+\s*(?:は|も|が|について)")
# 「未対応: …63冊の作成」「63冊は未対応」: the undone marker labels the count (a status cell such as
# 「| …2本) | ほぼ未着手 |」 or 「未作成の11冊にしました」 is not a remainder of this turn's work)
REM_BOUND = re.compile(_UNDONE_STRONG + r"\W{0,3}[:：][^。\n]{0,40}?" + _QTY
                       + r"|" + _QTY + r"\s*[はがも]\s*(?:まだ\s*)?" + _UNDONE_STRONG)
# no count, but the same defect named on the rest of the set: 他のレポートにも同じ問題があります
REM_NOQTY = re.compile(r"(?:他|ほか|残り|以外)の[^。\n]{1,15}?(?:に|で)も\s*(?:同じ|同様の)\s*(?:問題|不具合|誤り|欠陥|症状|崩れ|バグ)"
                       r"(?:が|は)?\s*(?:あり|残って|見られ|見つか|出て)")
UNDONE = re.compile(_UNDONE_STRONG + r"|手つかず|手を付けて(?:い|お)|残って(?:い|お)|残ります|同じ(?:問題|不具合|誤り|欠陥|症状|崩れ)"
                    r"|同様の(?:問題|不具合|誤り)|(?:評価|計算|検証|修正|対応|作成|適用|実行|直|作|書)(?:して|し|って|いて)"
                    r"(?:いません|いない|おらず|ません)|まだ(?:直|手を|作|書|や)"
                    r"|(?i:\bstill\b|\bnot\s+(?:yet\s+)?(?:fixed|done|updated|started|touched|handled)|\buntouched\b"
                    r"|\bsame\s+(?:bug|issue|problem|error))")
# the answer hands the go-ahead to the user: an offer, a proceed question, a request to decide
DEFER = re.compile(r"(?:なら|れば|場合は|ときは|でしたら|たら|であれば)[^。\n]{0,40}(?:言って|お知らせ|ご?指示|お申し付け|教えて|ご連絡|お声がけ)"
                   r"|(?:ご?指示|ご?希望|ご?要望|ご?依頼|必要|よろしけれ|よけれ|一言)(?:が|を|で|さえ)?"
                   r"(?:あれば|でしたら|なら|であれば|いただければ|いただけたら|もらえれば|くだされば)"
                   r"|(?:決めて|お決め|ご判断|判断して|ご指示|ご検討|指示して|お申し付け)(?:ください|下さい|いただ)"
                   r"|(?:始めて|進めて|直して|作って|広げて|適用して|やって|続けて|対応して)(?:も)?(?:よい|いい|よろしい)(?:か|です|でしょう)"
                   r"|お返事|ご返事|ご返答|(?:進め|直し|広げ|続け|やり|対応し|修正し|作り)(?:ますか|ましょうか)|どうしますか|どうしましょう|いかがしますか"
                   r"|(?i:\blet me know\b|\bshall i\b|\bif you want me to\b|\bwant me to\b|\bshould i\b)")
# a closing that invites feedback in general, not a go-ahead for the remainder
GENERIC_INVITE = re.compile(r"(?:ほかに|他に|何か|ご不明|不明点|気になる|質問|疑問|違和感|問題が|修正点|ご意見)[^。\n]{0,20}"
                            r"(?:あれば|ば|なら|でしたら|ございましたら)")
# the deferral points at the remainder (「残りも直すなら」「それらは」「全部」)
REM_REF = re.compile(r"残り|それら|これら|続き|全部|すべて|全て|他の|ほかの|同じ手順|同様に|(?i:\bthem\b|\bthe rest\b)")
# a sentence that says the rest needs no work: no problem / none left / already fixed / out of scope
NEGATED = re.compile(r"(?:問題|不具合|誤り|欠陥|症状|崩れ|バグ)(?:は|が|も)?\s*(?:なく|ない|無く|無い|ありません|見つかりません|見当たりません|見つからな)"
                     r"|残って(?:い)?(?:ない|ません)|残っていません|(?<![\d.])0\s*(?:件|本|冊|点|個)|修正済|対応済|直し済|作成済|適用済"
                     r"|(?:すべて|全て|全部)(?:修正|対応|直し|作成|適用)|必要(?:は|が)?(?:ない|ありません|なし)|不要|スキップ"
                     r"|範囲外|対象外|当てはまらな|当てはまりません|該当しな|該当しません"
                     r"|(?i:\bno\s+(?:issue|problem|bug)s?\b|\bnone\b|\balready\s+fixed\b|\bout of scope\b)")
# a reason that belongs to the left-out members themselves (the user alone can grant / undo / pay)
OWN_REASON = re.compile(r"権限|ユーザー指定|ご指定|依頼(?:の範囲|に含ま)|意図的|別の?(?:セッション|担当)|できな|できません|不可能"
                        r"|取り消せ|元に戻せ|不可逆|購入|課金|費用|有料|支払|契約|ログイン|本人(?:の|しか)"
                        r"|deny|(?:あなた|ユーザー|ご本人)(?:の|が)(?:操作|手作業|手動)|手動で"
                        r"|(?i:not applicable|no permission|irreversible|requires? (?:purchase|payment|access))")
# the user limited this instruction to part of the set (「3本だけ」「まず3つ」「そこまで」「実行はまだ」)
USER_PARTIAL = re.compile(r"\d+\s*(?:本|件|冊|つ|個|点|記事|章)\s*(?:だけ|のみ|まで)|そこまで|(?:まず|試しに|最初に|先に)[^。\n]{0,30}"
                          r"\d+\s*(?:本|件|冊|つ|個|点|記事|章)|(?:実行|着手|適用)は(?:まだ(?!考え)|しない|せず|不要)|計画(?:だけ|のみ)"
                          r"|(?i:\bonly\s+(?:the\s+)?(?:first\s+)?\d+\b)")
# ... unless the same prompt orders the whole set (「5本とも直して。まず1本目の方針を書いて、そのあと全部」)
USER_WHOLE = re.compile(r"全部|すべて|全て|全件|全\s*\d+|\d+\s*(?:本|件|冊|章|個)\s*(?:とも|全部|すべて)|そのあと|その後|残りも"
                        r"|(?i:\ball\b)")
# a count that is a REST of a set (残りの6本 / 片方しかない63冊 / 次の10本 / 33本も), not 「2点をご判断ください」
REM_ANCHOR = re.compile(r"(?:残り|残る|他の|ほかの|あと|次の|続きの|片方|以外の)[^。\n]{0,12}?" + _QTY
                        + r"|" + _QTY + r"\s*(?:に|で)?\s*も")
# the user asked only for a status listing (「適応できていない記事がどれかを…表形式で報告して」): the undone
# list IS the answer. A prompt that also orders the work (「全8本を直して、結果を報告して」) is not one.
USER_STATUS = re.compile(r"(?:報告|一覧に|リストアップ|洗い出)して|表(?:形式)?で(?:報告|まとめ|出)")
USER_WORK = re.compile(r"(?:直|作|書|修正|対応|追加|反映|適用|実行|進め|回|計算|評価|検証|改稿|更新|生成)(?:して|せよ|しろ|って)"
                       r"|(?i:\b(?:fix|make|write|update|apply|run)\b)")
CLOSING_ONLY = re.compile(r"^\W*(?:以上|以上です|以上となります|終わりです|done)\W*$", re.I)
_KANJI_D = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _kanji_num(s):
    v, cur = 0, 0
    for ch in s:
        if ch in _KANJI_D:
            cur = _KANJI_D[ch]
        else:
            v += (cur or 1) * {"十": 10, "百": 100, "千": 1000}[ch]
            cur = 0
    return v + cur


def _rem_clean(text):
    a = _clean(text)
    a = re.sub(r"`[^`\n]*`", " ", a)
    a = re.sub(r"\*\*|__", "", a)                               # **5本** -> 5本
    a = re.sub(r"(?m)^\s*>\s?", "", a)                          # a quoted hand-off is still a hand-off
    return re.sub(r"[〇一二三四五六七八九十百千]+(?=\s*" + _COUNTERS + ")", lambda m: str(_kanji_num(m.group(0))), a)


def _plural(m):
    """A matched remainder count of at least 2 (「FAIL 1件」 is one finding, not the rest of a set)."""
    nums = [g for g in m.groups() if g] if m else []
    return bool(m) and any(int(g.replace(",", "")) >= 2 for g in nums if g.replace(",", "").isdigit())


def _units(a):
    """Sentences / lines, keeping blank lines as paragraph breaks (None)."""
    out = []
    for line in a.split("\n"):
        if not line.strip():
            out.append(None)
            continue
        for s in re.split(r"(?<=[。！？!?])|(?<=\.)\s+(?=[A-Z])", line):
            if s and s.strip():
                out.append(s.strip())
    return out


def _defer(s):
    return bool(s and DEFER.search(s) and not (GENERIC_INVITE.search(s) and not REM_REF.search(s)))


def _is_rem(s):
    anchor = REM_ANCHOR.search(s)
    return bool(((_plural(REM_QTY.search(s)) or REM_PARAM.search(s)) and UNDONE.search(s))
                or _plural(REM_BOUND.search(s)) or REM_NOQTY.search(s)
                or (_plural(anchor) and not re.search(r"\d\s*点", anchor.group(0)) and _defer(s)))


def remainder_units(text):
    """[(sentence, index of its last unit, units)] for each sentence that states a same-kind remainder as undone, with no
    statement in it that the rest needs no work (NEGATED) and no reason of the members' own (OWN_REASON,
    in it or in the sentence just before: 「削除は取り消せません。残り30本は未実施です。」)."""
    us = _units(_rem_clean(text))
    out = []
    for i, s in enumerate(us):
        if s is None:
            continue
        cand, end = s, i
        if not _is_rem(s):
            nxt = next((u for u in us[i + 1:i + 2] if u), None)
            if re.match(r"^\W*" + _UNDONE_STRONG + r"\W*(?:" + _QTY + r"\W*)?$", s):    # 「**未対応**」 + its list lines
                lst = []
                for u in us[i + 1:]:
                    if u is None or not re.match(r"^\s*(?:[-*・+]|\d+[.)])", u):
                        break
                    lst.append(u)
                cand, end = s + ": " + " ".join(lst), i + len(lst)
                if not (_plural(re.search(_QTY, cand)) or len(lst) >= 2):
                    continue
            elif nxt and (_plural(REM_QTY.search(s)) or _plural(REM_ANCHOR.search(s))) and UNDONE.search(nxt) \
                    and not re.search(_QTY, nxt):           # 「他にも5本あります。いずれも未対応です。」
                cand, end = s + nxt, us.index(nxt, i + 1)
            else:
                continue
        prev = next((u for u in reversed(us[:i]) if u), "") if i else ""
        if NEGATED.search(cand) or OWN_REASON.search(cand) or OWN_REASON.search(prev or ""):
            continue
        out.append((cand, end, us))
    return out


def remainder_sentences(text):
    """Sentences of the text that state a same-kind remainder as undone."""
    return [c for c, _i, _us in remainder_units(text)]


def _bound_defer(i, us):
    """The hand-off sentence tied to the remainder at units[i]: in it, in the next two sentences (across a
    blank line), or anywhere after it when it names the rest (「残りも直すなら言ってください」)."""
    seen = 0
    for u in us[i:]:
        if u is None:
            continue
        if _defer(u) and (seen <= 2 or REM_REF.search(u)):
            return u
        seen += 1
    return None


def _delegation_stalls(text, prompt, sents):
    """True when delegation_guard (C03) already stops one of these hand-off sentences as a continuation
    Claude could decide itself: the go-ahead is self-decidable, so that hook owns the block."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import delegation_guard
        st = delegation_guard.stalled(text, prompt)
    except Exception:
        return False
    if not st:
        return False
    s = re.sub(r"\*\*", "", unicodedata.normalize("NFKC", st[1] or "")).strip()
    return bool(s) and any(s in x or x in s for x in sents)


def deferred_remainder(turn, text=None, defer_to_delegation=None):
    """[sentences] when the answer leaves a same-kind remainder it names as undone and hands the go-ahead
    for it to the user (REQUIRE_DEFER), without a reason of the members' own; else []."""
    if not turn or not (turn.get("edited") or turn.get("templ") or turn.get("roots")):
        return []                                    # nothing was worked on: a status answer, not a partial job
    pr = unicodedata.normalize("NFKC", turn.get("prompt") or "")
    if USER_PARTIAL.search(pr) and not USER_WHOLE.search(pr):
        return []
    if USER_STATUS.search(pr) and not USER_WORK.search(pr):
        return []
    if text is None:
        texts = turn.get("texts") or [turn.get("answer", "")]
        gaps = turn.get("gaps") or []
        text = texts[-1]
        if CLOSING_ONLY.match(_clean(text).strip()) and len(texts) > 1 and len(gaps) == len(texts) and not gaps[-1]:
            text = texts[-2]                             # 「以上です。」 right after the real answer (no work between)
    hits = remainder_units(text)
    if not hits:
        return []
    if not REQUIRE_DEFER:
        return [c for c, _i, _us in hits]
    out = []
    for c, i, us in hits:
        d = _bound_defer(i, us)
        if d:
            out.append((c, d))
    if not out:
        return []
    if defer_to_delegation is None:
        defer_to_delegation = DEFER_TO_DELEGATION and not turn.get("_dlg_spent")
    if defer_to_delegation and _delegation_stalls(text, turn.get("prompt") or "", [x for p in out for x in p]):
        return []
    return [c for c, _d in out]


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
    """First uncovered family touched by this turn as a dict (kind "family"; with "remainder" when the
    answer also defers a named remainder), or {"kind": "remainder", "sentences": [...]}, or None.
    """
    if not turn or not turn.get("prompt"):
        return None
    rem = deferred_remainder(turn)
    fam = decide_family(turn, now)
    if fam:
        fam["remainder"] = rem
        return fam
    return {"kind": "remainder", "sentences": rem} if rem else None


def decide_family(turn, now=None):
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
        fam = {"kind": "family", "key": k, "members": live, "dead": dead, "edited_ids": mine, "unedited_ids": rest,
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
REM_HEAD = "【残りの先送り検査（1回のみ）】"


def reason_remainder(sentences):
    q = " / ".join("「%s」" % s[:120] for s in sentences[:3])
    return (REM_HEAD + "回答が、いま手を付けた集合と同じ種類の残りを自分で挙げながら、適用せずに止めている: %s。"
            "同じ変更・同じ評価が当てはまるなら、今このターンで残り全部に適用し、回答に「全N件中M件」の形で総数と処理数を書け。"
            "適用しないものは1件ずつ（同じ理由なら範囲でまとめて）、そのもの自体の理由を書け"
            "（当てはまらない・権限がない・購入など取り消せない費用が要る 等）。"
            "「直すなら言ってください」「決めてください」「お返事待ち」は理由にならない"
            "（CLAUDE.md §11.2・依頼の取りこぼし C02）。" % q)


def reason_for(fam):
    if fam.get("kind") == "remainder":
        return reason_remainder(fam["sentences"])
    extra = (" " + reason_remainder(fam["remainder"])) if fam.get("remainder") else ""
    return _reason_family(fam) + extra


def _reason_family(fam):
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
    if turn:
        # delegation_guard blocks once per instruction (same key): after its block, a hand-off it would stop
        # again goes through, so the remainder check must not step aside for it any more
        dk = hashlib.sha1((turn.get("ts", "") + (turn.get("prompt") or "")).encode("utf-8", "replace")).hexdigest()[:16]
        turn["_dlg_spent"] = os.path.exists(os.path.join(
            os.path.expanduser("~"), ".claude", "state", "delegation_guard_seen",
            "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_") + "_" + dk))
    fam = decide(turn, now=time.time())
    if not fam:
        return
    key = hashlib.sha1((turn.get("ts", "") + (turn.get("prompt") or "")).encode("utf-8", "replace")).hexdigest()[:16]
    if fam.get("kind") == "remainder":
        key += "_r"                    # its own once-per-instruction mark: a family block earlier does not hide it
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
