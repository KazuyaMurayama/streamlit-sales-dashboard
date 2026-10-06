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
  T2 FAIL  書いた時刻が現在 JST から 30 分超前、または 5 分超先（推測で書いた時刻）。
  T3 FAIL  既存ファイルの本文を変えたのに、最終更新日が 30 分より古いまま（時刻なしも古い扱い）。
           「先に最終更新日を更新してから本文を編集する」を強制する。Edit は連続した
           old_string しか持てず、本文の編集と冒頭の日付行を1回で直せないため。
           旧 D5（追記80字以上で WARN）は警告では守られなかった型なので T3 に置き換えた。
  T4 FAIL  新規の日付付きレポート（*_YYYYMMDD.md）に 作成日・最終更新日 の行が無い。
  時刻の検査は冒頭 HEADER_LINES 行に限る。本文の表や引用にある「更新日:」を
  冒頭の日付と取り違えないため。

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
STALE = timedelta(minutes=30)   # これより古い最終更新日のまま本文を変えたら止める
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
    r"(?:最終更新日|最終更新|更新日|Last\s+updated|Updated)\**\s*[:：]\s*\**\s*" + ISO + TIME,
    re.I)
RE_CREATED = re.compile(r"(?:作成日|Created)\**\s*[:：]\s*\**\s*" + ISO + TIME, re.I)
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


def _head(rx, text):
    """First match of rx inside the first HEADER_LINES lines, else None."""
    m = rx.search(text)
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
            fails.append("%sの時刻 %s が現在（%s）と30分以上離れています。"
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
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        if not _in_scope(fp, cfg):
            return

        try:
            with open(fp, encoding="utf-8-sig") as f:
                before = f.read()
            is_new = False
        except Exception:
            before, is_new = "", True

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
