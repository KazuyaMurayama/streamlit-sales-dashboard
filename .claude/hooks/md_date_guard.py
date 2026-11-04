"""PreToolUse hook (Write|Edit): stale-date guard for .md reports.

WHY THIS IS A HOOK AND NOT A CHECKLIST / SKILL / SCRIPT
------------------------------------------------------
The 2026-08-14 defect (Soulful-Content/BUSINESS.md, 5 wrong dates) was caused by
copying the date from surrounding prose instead of reading the system clock.
The defining property of this bug class:

    **A wrong date looks correct to the author.**

The author wrote 2026-08-13 five times and re-read it five times without
noticing, because it matched the neighbouring text. Any countermeasure that
depends on the author choosing to look — a CLAUDE.md rule, a skill checklist, a
script that must be invoked with the right flag — fails for exactly the same
reason the original write failed: the author does not believe anything is wrong,
so they do not run the check.

The existing `_meta/qa/claim_check.py` I6 has three fatal gaps, all measured:
  1. It lives in 8 of 42 repos.
  2. It is wired into ZERO hooks and ZERO CI (verified by grep 2026-08-14).
  3. Its date check is inert unless `--today` is passed by hand. Running
     `claim_check.py --input BUSINESS.md` on the defect file reports FAIL 1
     (an unrelated I1) and stays SILENT on the wrong date.

So the guard must (a) fire without being asked, and (b) get the date from the
OS rather than from the model. Both are true here: the hook is invoked by the
harness on every Write/Edit, and `date.today()` runs in this process.

This is the same reason the date is read here rather than passed in. In
claim_check.py, reading the clock internally would be wrong — it audits files
written in the past. A PreToolUse hook has no such ambiguity: the write is
happening now, so "now" is the correct reference. That distinction is why this
is a separate tool rather than a flag on the old one.

WHAT IS CHECKED (deliberately narrow — see NON-GOALS)
  D1 FAIL  `最終更新日` / `Last updated` differs from today.
  D2 FAIL  Any date in the file is in the future (typo or fabrication).
  D3 FAIL  `作成日` on a NEW file differs from today.
  D4 WARN  Newest `## YYYY-MM-DD —` heading is older than today, when this edit
           adds content. Warn-only: appending to an old log entry is legitimate.

TIME OF DAY (2026-10-06 ユーザー指示「作成日と最終更新日に何時何分（日本時間）まで」):
  理由は「1日に何回も更新するので、日付だけでは開いている版が最新か判断できない」。
  書式は `最終更新日: 2026-10-06 14:32 JST`。時刻は JST の固定オフセットで計算する
  （Web 版のクラウド環境は UTC で動くため date.today() では 0〜9 時に日付がずれる）。
  T1 FAIL  この編集で書いた 最終更新日（新規なら 作成日 も）に時刻が無い。
  T2 FAIL  書いた時刻が現在 JST から 10 分超前、または 5 分超先（推測で書いた時刻）。
  T3 FAIL  既存ファイルの本文を変えたのに、最終更新日が 10 分より古いまま（時刻なしも古い扱い）。
           「先に最終更新日を更新してから本文を編集する」を強制する。Edit は連続した
           old_string しか持てず、本文の編集と冒頭の日付行を1回で直せないため。
           旧 D5（追記80字以上で WARN）は警告では守られなかった型なので T3 に置き換えた。
  T4 FAIL  新規の日付付きレポート（*_YYYYMMDD.md）に 作成日・最終更新日 の行が無い。
  時刻の検査は冒頭 HEADER_LINES 行に限り、先頭の YAML front matter（--- … ---）は除く。
  本文の表や引用の「更新日:」や、サイト生成器が日付型で読む `updated:` を
  冒頭の日付行と取り違えないため（front matter に時刻を足すと日付型が壊れる）。

CLOCK READ IN A SHELL / FILE WRITTEN BY A SCRIPT（2026-11-04 依頼者指摘）:
  Soulful-Content/_meta/REVIEW_REQUIRED_FILES_20260918.md に 19:10 JST の更新で
  「最終更新日: 2026-11-04 10:10 JST」と書かれた。原因は Bash で `TZ=Asia/Tokyo date` を
  読んだこと: Git Bash（Windows）はタイムゾーン表を持たず、知らない地域名を黙って UTC として
  扱う（実測: 19:44 JST に `TZ=Asia/Tokyo date` → 10:44 GMT）。書き込みは Bash の Python
  スクリプトだったので、Write|Edit しか見ない T2/T3 を素通りした。597本の冒頭時刻付き .md を
  コミット時刻と照らすと、同じ 9 時間ずれが17本あった（Web 版の UTC の時計も同じずれ方をする）。
  B1 FAIL  Windows の Bash/PowerShell で `TZ=<地域名>`（Asia/Tokyo 等）を付けて時刻を読む。
           POSIX の書き方 `TZ=JST-9` はどの環境でも JST になる（Git Bash で実測）。
  B2 FAIL  git commit される .md の冒頭の 最終更新日 が、そのファイルを最後に書いた時刻
           （作業ツリーの mtime）より 15 分超前、または現在 JST より 5 分超先。T3（10分）と同じ
           「本文を書いた時刻 ≒ 最終更新日」の不変条件を、どの道具で書いたかに関係なく commit で見る。
           判定は (a) 現在より5分超先 (b) mtime より8.5〜10.5時間前（UTC の典型）
           (c) 本文を変えたのに最終更新日が HEAD のまま・mtime より15分超前 (d) 時刻なしで今日でない。
           書き直したスタンプが mtime より数時間前なだけでは止めない（stash pop・checkout・整形で
           mtime だけ進む。Fable I1）。ステージ≠作業ツリーならステージ側を now と比べる（C3）。
           例外: 直前のコミットの UTC ずれ（その commit がスタンプの8.5〜10.5時間後）をちょうど9時間直す変更。
           Fable QC（2026-11-04）: C1 `TZ=:Asia/Tokyo`・C2 時刻なし・C3 add 後の再編集・I1〜I5 を反映。

NON-GOALS (stated so the next reader does not "fix" them by widening):
  Prose dates ("8/31 判定", "締切8月25日") are NOT checked. They are frequently
  correct references to other days, so flagging them trains the user to ignore
  the guard. A guard that cries wolf is worse than no guard: it converts a hard
  failure into a soft one that gets muted.

FAIL-OPEN: any internal error exits 0. A guard bug must never block real work.
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
HEADER_LINES = 30
# これより古い最終更新日のまま本文を変えたら止める。30分だと窓の中の2回目の更新が
# 同じ時刻のまま残り「開いている版が最新か」を判別できなかった（Fable QC 2026-10-06）。
STALE = timedelta(minutes=10)
AHEAD = timedelta(minutes=5)    # 時計のずれの許容

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

try:
    from codex_adapter import normalize as _codex_normalize
except Exception:  # adapter missing: say so, do not fail silently
    def _codex_normalize(d):
        # A hook that cannot convert Codex payloads reads empty values and
        # returns early -- silence indistinguishable from "no violation".
        # One line on stderr keeps a broken deployment visible (QC
        # 2026-09-18). stderr does not affect the hook's decision.
        if isinstance(d, dict) and d.get("tool_name") == "apply_patch":
            sys.stderr.write(
                "[%s] codex_adapter.py not found next to this hook; "
                "Codex apply_patch payloads are NOT being checked."
                % os.path.basename(__file__) + chr(10))
        return d

# Report-style names and doc trees. Mirrors pre_report_quality_guard.py so the
# two guards agree on what "a report" is.
REPORT_NAME = re.compile(r"_\d{8}(?:-v\d+)?\.md$", re.I)
DEFAULT_DIRS = ("outputs/", "reports/", "docs/", "output/", "report/", "_meta/")
DEFAULT_EXCLUDE = ("data/", "materials/", "drafts/", "node_modules/",
                   "session/", ".git/", "vendor/", "fixtures/", "archive/")

# Always-checked basenames: continuously-updated canon that carries 最終更新日
# but never a date suffix (per CLAUDE.md §10b).
ALWAYS = ("business.md", "claude.md", "readme.md", "tasks.md",
          "current_best_strategy.md", "strategy_registry.md")

ISO = r"(20\d{2})-(\d{2})-(\d{2})"
# 任意の時刻部（2026-10-06 追加）。「 14:32」「T14:32」「 14:32 JST」「 14:32（JST）」を受ける。
TIME = r"(?:[ T\u3000]+(\d{1,2}):(\d{2})(?:\s*[(（]?\s*JST\s*[)）]?)?)?"

# 最終更新日 / Last updated. Bold markers may sit on EITHER side of the word
# (`**最終更新日**:` vs `**最終更新日:**`). Assuming one form let the original
# I6 implementation pass straight through the defect file — caught only by
# red-green testing. Both forms are matched here.
# Label variants are not hypothetical: a corpus survey (2026-08-14, 2,337 .md
# files) found 最終更新日: (457), 最終更新: (95), **最終更新日**: (45),
# Last updated: (10), 更新日: (4) and bold-on-either-side forms. Matching only
# the form in front of you is how the original I6 silently passed the defect.
RE_UPDATED = re.compile(
    r"(?:最終更新日時|最終更新日|最終更新|更新日時|更新日|\bLast\s+(?:updated|modified)|\bUpdated)\**\s*[:：]\s*\**\s*" + ISO + TIME,
    re.I)
RE_CREATED = re.compile(r"(?:作成日時|作成日|\bCreated)\**\s*[:：]\s*\**\s*" + ISO + TIME, re.I)
RE_HEADING = re.compile(r"^#{2,4}\s*\**\s*" + ISO, re.M)
RE_ANY_DATE = re.compile(ISO)


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


def _registered_local_copy_exists():
    """True only if a DIFFERENT repo-local copy exists AND is registered in the
    project's settings. Existence alone must NOT silence the global hook — that
    gap silently deactivated the hook layer in 44 repos (QC 2026-07-14)."""
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", base))
        if os.path.normcase(me) == os.path.normcase(local) or not os.path.exists(local):
            return False
        for name in ("settings.json", "settings.local.json"):
            try:
                with open(os.path.join(os.getcwd(), ".claude", name),
                          encoding="utf-8-sig") as f:
                    if base in f.read():
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _load_config():
    """.claude/md_date_guard.json — {"mode": "deny"|"warn"|"off",
    "include": [...], "exclude": [...]}"""
    cfg = {"mode": "deny", "include": None, "exclude": None}
    try:
        p = os.path.join(os.getcwd(), ".claude", "md_date_guard.json")
        with open(p, encoding="utf-8-sig") as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in cfg})
    except Exception:
        pass
    return cfg


def _in_scope(fp, cfg):
    if not fp.lower().endswith(".md"):
        return False
    try:
        rel = os.path.relpath(fp, os.getcwd())
    except Exception:
        rel = fp
    norm = rel.replace("\\", "/").lower()
    if norm.startswith("../"):
        norm = os.path.basename(norm)
    return _scope_norm(norm, cfg)


def _scope_norm(norm, cfg):
    """norm: lower-case path relative to the repo root, '/' separators."""
    base = os.path.basename(norm)

    for ex in (cfg.get("exclude") or DEFAULT_EXCLUDE):
        if ex.lower().rstrip("/") + "/" in "/" + norm:
            return False
    inc = cfg.get("include")
    if inc:
        return any(i.lower().rstrip("/") + "/" in "/" + norm for i in inc)
    if base in ALWAYS or REPORT_NAME.search(base):
        return True
    return any(d in "/" + norm for d in DEFAULT_DIRS)


def _ymd(m):
    return "%s-%s-%s" % m.groups()[:3]


def _stamp(m):
    """datetime(JST) of a matched 作成日/最終更新日, or None when it has no time."""
    y, mo, d, hh, mm = m.groups()
    if hh is None:
        return None
    try:
        return datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=JST)
    except ValueError:
        return None


RE_FRONT = re.compile(r"\A\ufeff?---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def _head(rx, text):
    """First match of rx inside the first HEADER_LINES lines, else None.
    A leading YAML front matter block is skipped (its `updated:` is data)."""
    f = RE_FRONT.match(text)
    m = rx.search(text, f.end() if f else 0)
    if m and text.count("\n", 0, m.start()) < HEADER_LINES:
        return m
    return None


def _check(after, before, today, is_new, now=None, report_name=False):
    """Return (fails, warns). `before` is '' for a new file."""
    fails, warns = [], []
    t = today.isoformat()
    if now is None:
        now = datetime.now(JST)
    stamp = now.strftime("%Y-%m-%d %H:%M JST")

    m = RE_UPDATED.search(after)
    if m:
        got = _ymd(m)
        if got != t:
            fails.append(
                "最終更新日が %s ですが、システム日付は %s です。"
                "前回セッションの日付を引き写していませんか。" % (got, t))

    m = RE_CREATED.search(after)
    if m and is_new:
        got = _ymd(m)
        if got != t:
            fails.append("新規ファイルの作成日が %s ですが、本日は %s です。"
                         % (got, t))

    # Future dates. Tolerate +1 day: a genuine timezone edge, not a copy error.
    horizon = (today + timedelta(days=1)).isoformat()
    seen_before = set(RE_ANY_DATE.findall(before))
    for g in set(RE_ANY_DATE.findall(after)):
        d = "%s-%s-%s" % g
        if d > horizon and g not in seen_before:
            fails.append("未来の日付 %s を追加しています（本日 %s）。" % (d, t))

    # --- Time of day (T1-T4, 2026-10-06) ----------------------------------
    up_a, up_b = _head(RE_UPDATED, after), _head(RE_UPDATED, before)
    cr_a = _head(RE_CREATED, after)

    def _written(label, mm):
        dt = _stamp(mm)
        if dt is None:
            fails.append("%sに時刻がありません。`%s: %s` の形で何時何分（日本時間）まで"
                         "書いてください（1日に複数回更新するため日付だけでは最新か判別できない）。"
                         % (label, label, stamp))
        elif _ymd(mm) == t and not (now - STALE <= dt <= now + AHEAD):
            fails.append("%sの時刻 %s が現在（%s）と10分以上離れています。"
                         "推測で書かず現在時刻を書いてください。"
                         % (label, dt.strftime("%H:%M"), stamp))

    # T1/T2: only the value THIS edit writes. A date line the edit did not
    # touch is T3's business.
    if up_a and (is_new or not up_b or up_a.groups() != up_b.groups()):
        _written("最終更新日", up_a)
    if is_new and cr_a:
        _written("作成日", cr_a)

    # T3: the body changed but the stamp did not move and is already stale.
    if (not is_new and up_a and up_b and after != before
            and up_a.groups() == up_b.groups()):
        dt = _stamp(up_b)
        if dt is None or dt < now - STALE:
            old = up_b.group(0)
            new = old[:old.index(_ymd(up_b))] + stamp
            fails.append(
                "本文を変更する前に最終更新日を現在時刻へ更新してください。"
                "先にこの1行だけを置き換えてから、本文の編集をやり直します: "
                "old_string=`%s` → new_string=`%s`" % (old, new))

    # T4: a new date-suffixed report must carry both header lines.
    if is_new and report_name and not (cr_a and up_a):
        fails.append("新規レポートの H1 直下に `作成日: %s` と `最終更新日: %s` の"
                     "2行がありません。" % (stamp, stamp))

    heads = sorted({"%s-%s-%s" % g for g in RE_HEADING.findall(after)})
    past = [d for d in heads if d <= t]
    if past and past[-1] != t and len(after) > len(before):
        warns.append(
            "最新の日付見出しは %s で、本日 %s ではありません。"
            "本日分の追記なら `## %s — ` で新しい見出しを立ててください。"
            % (past[-1], t, t))
    return fails, warns


# ---------------------------------------------------------------- Bash / commit (B1, B2)
# `TZ=Asia/Tokyo date` / `TZ="Asia/Tokyo" python ...`: a region name, not a POSIX offset
# Only an assignment in command position (start, after ; & | ( newline, export/env/set) or
# PowerShell's $env:TZ. A commit message that *mentions* it is prose (2026-11-04 self-hit).
# No backtick: Markdown inline code (`TZ=Asia/Tokyo date`) in a heredoc / -m is prose too.
RE_TZ_REGION = re.compile(
    r"""(?:(?:^|[;&|(\n])\s*(?:(?:export|env|set|declare\s+-x)\s+)?TZ|\$env:TZ)\s*=\s*["']?:?"""
    r"""(?:[A-Za-z_]+/[A-Za-z_]+|Japan)\b""", re.I)
SKEW = timedelta(minutes=15)    # commit が作業ツリーの mtime より後ろへずれる余裕（T3 の10分＋整形・add の時間）
UTC_BAND = (8.5, 10.5)          # 9時間ずれ（UTC を JST と書いた）＋書いてから commit までの最大1.5時間


def _tz_region_reason(cmd):
    if os.name != "nt" or not RE_TZ_REGION.search(cmd):
        return None
    return ("[B1] Windows の Git Bash の date・perl 等は `TZ=Asia/Tokyo` を知らず、黙って UTC を返します"
            "（JST より9時間前。2026-11-04 に 19:10 の更新が「10:10 JST」と記録された）。"
            "時刻は `TZ=JST-9 date \"+%Y-%m-%d %H:%M JST\"` で読んでください（Git Bash・Linux・Web 版で同じ値）。")


def _commit_aliases(cwd):
    """git aliases whose expansion starts with `commit` (`git ci`), incl. -c alias.x=commit."""
    try:
        import topic_split_guard as T
        out = set()
        for ln in T._lines(T._git(cwd, ["config", "--get-regexp", r"^alias\."])):
            k, _, v = ln.partition(" ")
            if v.strip().startswith("commit"):
                out.add(k.split(".", 1)[1])
        return out
    except Exception:
        return set()


def _commit_re(cwd, cmd=""):
    import topic_split_guard as T
    names = {"commit"} | _commit_aliases(cwd)
    names |= set(re.findall(r"-c\s+[\"']?alias\.([\w-]+)=[\"']?commit", cmd))
    return re.compile(T._GIT_PREFIX + r"(?:" + "|".join(sorted(map(re.escape, names))) + r")\b" + T._Q)


_VAL_OPTS = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
             "--author", "--date", "-t", "--template", "--fixup", "--squash", "--cleanup", "--trailer"}


def _commit_pathspecs(seg):
    """Pathspecs given to `git commit` itself (after `--`, or bare words after the options)."""
    import shlex
    try:
        w = shlex.split(seg, posix=True)
    except Exception:
        w = seg.split()
    if "--" in w:
        return [x for x in w[w.index("--") + 1:] if x]
    out, skip = [], False
    for x in w:
        if skip:
            skip = False
        elif x in _VAL_OPTS:
            skip = True
        elif not x.startswith("-"):
            out.append(x)
    return out


def _commit_targets(cmd, cwd):
    """[(repo_root, [(repo-relative .md path, added by this command?)])]."""
    try:
        import topic_split_guard as T
    except Exception:
        return []
    out = []
    for m in _commit_re(cwd, cmd).finditer(cmd):
        d = T.effective_cwd(cmd, m.start(), cwd)
        root = T._root_for(m, d)
        if not root:
            continue
        seg = re.split(r"&&|\|\||;|\|", cmd[m.end():].split("\n")[0])[0]
        files = set(T._lines(T._git(root, ["diff", "--cached", "--name-only", "--diff-filter=AM"])))
        added = set()       # added by this command: what is committed is the file on disk
        # `git commit [-o|-i] [--] <pathspec>` commits those paths from the work tree
        cspecs = _commit_pathspecs(seg)
        if cspecs:
            added |= set(T._lines(T._git(d, ["diff", "--name-only", "HEAD", "--"] + cspecs)))
            added |= set(T._lines(T._git(d, ["ls-files", "--others", "--exclude-standard",
                                             "--full-name", "--"] + cspecs)))
        if re.search(r"(?:^|\s)(?:-[b-zA-Z]*a[a-zA-Z]*|--all)\b", seg):
            added |= set(T._lines(T._git(root, ["diff", "--name-only", "--diff-filter=AM"])))
        for am in T._ADD.finditer(cmd[:m.start()]):
            words = re.split(r"\s+", am.group("args").strip())
            specs = [T._unq(x) for x in words if x and not x.startswith("-")]
            if any(w in ("-A", "--all", "-u", "--update") for w in words):
                specs = specs or [":/"]       # the whole work tree
            if not specs:
                continue
            ad = T.effective_cwd(cmd, am.start(), cwd)
            added |= set(T._lines(T._git(ad, ["diff", "--name-only", "--diff-filter=AM", "--"] + specs)))
            added |= set(T._lines(T._git(ad, ["ls-files", "--others", "--exclude-standard",
                                              "--full-name", "--"] + specs)))
        out.append((root, sorted((f, f in added) for f in files | added if f.lower().endswith(".md"))))
    return out


def _norm_text(t):
    return t.lstrip("\ufeff").replace("\r\n", "\n")


def _commit_findings(cmd, cwd, cfg, now):
    try:
        import topic_split_guard as T
    except Exception:
        return []
    fails = []
    for root, rels in _commit_targets(cmd, cwd):
        for rel, will_add in rels:
            rel = rel.replace("\\", "/")
            if not _scope_norm(rel.lower(), cfg):
                continue
            ap = os.path.join(root, rel)
            try:
                with open(ap, "rb") as f:
                    work = _norm_text(f.read().decode("utf-8", "replace"))
                mtime = datetime.fromtimestamp(os.path.getmtime(ap), JST)
            except Exception:
                continue
            staged = T._git(root, ["show", ":" + rel])
            text, ref = work, mtime
            if not will_add and staged and _norm_text(staged) != work:
                # what is committed is the index, not the file on disk: check the index
                # against now (its mtime says nothing) — Fable C3
                text, ref = _norm_text(staged), now
            head = _norm_text(T._git(root, ["show", "HEAD:" + rel]))
            if head == text:
                continue
            m = _head(RE_UPDATED, text)
            if not m:
                continue
            st = _stamp(m)
            hm = _head(RE_UPDATED, head) if head else None
            if st is None:
                # date only: a script that read a UTC clock writes yesterday before 09:00 JST (Fable C2)
                if _ymd(m) != now.date().isoformat() and not (hm and _ymd(hm) == _ymd(m) and hm.group(0) == m.group(0)
                                                             and ref is now):
                    fails.append("[B2] %s: 本文を変えたのに 最終更新日 が %s のまま（時刻なし・今日 %s でない）" % (
                        rel, _ymd(m), now.date().isoformat()))
                continue
            hst = _stamp(hm) if hm else None
            if st > now + AHEAD:          # before the correction exception (Fable I4)
                fails.append("[B2] %s: 最終更新日 %s が現在 %s より先です" % (
                    rel, st.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M JST")))
                continue
            if hst is not None and abs((st - hst).total_seconds() - 9 * 3600) < 60 \
                    and _head_was_utc(T, root, rel, hst):
                continue        # correcting exactly this 9-hour slip of the previous commit
            gap = (ref - st).total_seconds() / 3600.0
            if UTC_BAND[0] <= gap <= UTC_BAND[1]:
                fails.append("[B2] %s: 最終更新日 %s が、このファイルを最後に書いた %s より %.1f 時間前です。"
                             "9時間前後のずれは UTC を JST と書いた典型（Git Bash の `TZ=Asia/Tokyo`・Web 版の素の date）" % (
                                 rel, st.strftime("%m-%d %H:%M JST"), ref.strftime("%m-%d %H:%M JST"), gap))
            elif ref is mtime and hst is not None and st == hst and gap * 60 > SKEW.total_seconds() / 60:
                # body changed, stamp not touched (T3 through a script). A stamp that WAS
                # rewritten but is older than mtime is not judged: checkout / stash pop /
                # formatters move mtime without a new edit (Fable I1)
                fails.append("[B2] %s: 本文を変えたのに 最終更新日 が %s のまま（ファイルを最後に書いたのは %s）" % (
                    rel, st.strftime("%m-%d %H:%M JST"), mtime.strftime("%m-%d %H:%M JST")))
    return fails


def _head_was_utc(T, root, rel, hst):
    """The previous commit's stamp really was UTC: committed 8.5-10.5h after it."""
    try:
        ct = int(T._git(root, ["log", "-1", "--format=%ct", "--", rel]).strip())
        g = (datetime.fromtimestamp(ct, JST) - hst).total_seconds() / 3600.0
        return UTC_BAND[0] <= g <= UTC_BAND[1]
    except Exception:
        return False


def _bash(data, cfg):
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    reasons = []
    r = _tz_region_reason(cmd)
    if r:
        reasons.append(r)
    cwd = data.get("cwd") or os.getcwd()
    if re.search(r"(?i)\bcommit\b", cmd) or (re.search(r"\bgit\b", cmd) and _commit_aliases(cwd)):
        reasons += _commit_findings(cmd, cwd, cfg, datetime.now(JST))
        if any(x.startswith("[B2]") for x in reasons):
            reasons.append("直し方: 冒頭の 最終更新日 を今の JST（`TZ=JST-9 date \"+%Y-%m-%d %H:%M JST\"`）"
                           "に書き直して add し直してから commit する。")
    if not reasons:
        return
    _record_firing("md_date_guard", data)
    body = "\n".join("・" + x for x in reasons[:8])
    if cfg.get("mode", "deny") == "deny":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "時刻のずれを検出しました:\n" + body}}))
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "additionalContext": "⚠ 時刻チェック:\n" + body}}))


def main():
    if _registered_local_copy_exists():
        return
    cfg = _load_config()
    if cfg.get("mode") == "off":
        return
    try:
        # Read stdin as BYTES and decode UTF-8 explicitly. json.load(sys.stdin)
        # uses the Windows locale encoding (CP932), which mojibakes every
        # Japanese payload — the checks then silently find nothing.
        raw = sys.stdin.buffer.read()
        data = _codex_normalize(json.loads(raw.decode("utf-8", "replace")))
        tool = data.get("tool_name") or ""
        if tool in ("Bash", "PowerShell"):
            _bash(data, cfg)
            return
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        if not _in_scope(fp, cfg):
            return

        try:
            with open(fp, "rb") as f:
                raw_before = f.read()
            is_new = False
        except Exception:
            raw_before, is_new = b"", True
        # A cp932 file must not be mistaken for a new one (Fable QC 2026-10-06).
        before = raw_before.decode("utf-8-sig", "replace")

        if tool == "Write":
            after = ti.get("content") or ""
        elif tool == "Edit":
            old, new = ti.get("old_string"), ti.get("new_string")
            if old is None or new is None:
                return
            after = (before.replace(old, new) if ti.get("replace_all")
                     else before.replace(old, new, 1))
        else:
            return

        now = datetime.now(JST)
        today = now.date()
        report_name = bool(REPORT_NAME.search(os.path.basename(fp)))
        fails, warns = _check(after, before, today, is_new, now, report_name)

        # Regression-only on FAILs: never block because of a date that was
        # already wrong on disk before this edit.
        if not is_new and fails:
            pre_f, _ = _check(before, before, today, False, now)
            fails = [f for f in fails if f not in pre_f] or []

        if not fails and not warns:
            return

        body = "\n".join("・" + x for x in (fails + warns)[:5])
        if fails and cfg.get("mode", "deny") == "deny":
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("md_date_guard", data)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "日付ずれを検出しました（システム日付 %s）:\n%s\n"
                    "日付は書いた本人には正しく見えるため目視では見つかりません。"
                    "上記を修正して再実行してください。"
                    "意図的な過去日付なら .claude/md_date_guard.json で調整可。"
                    % (today.isoformat(), body))}}))
        else:
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("md_date_guard", data)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "⚠ 日付チェック（システム日付 %s）:\n%s"
                    % (today.isoformat(), body))}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
