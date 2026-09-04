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
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

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

# 最終更新日 / Last updated. Bold markers may sit on EITHER side of the word
# (`**最終更新日**:` vs `**最終更新日:**`). Assuming one form let the original
# I6 implementation pass straight through the defect file — caught only by
# red-green testing. Both forms are matched here.
# Label variants are not hypothetical: a corpus survey (2026-08-14, 2,337 .md
# files) found 最終更新日: (457), 最終更新: (95), **最終更新日**: (45),
# Last updated: (10), 更新日: (4) and bold-on-either-side forms. Matching only
# the form in front of you is how the original I6 silently passed the defect.
RE_UPDATED = re.compile(
    r"(?:最終更新日|最終更新|更新日|Last\s+updated|Updated)\**\s*[:：]\s*\**\s*" + ISO,
    re.I)
RE_CREATED = re.compile(r"(?:作成日|Created)\**\s*[:：]\s*\**\s*" + ISO, re.I)
RE_HEADING = re.compile(r"^#{2,4}\s*\**\s*" + ISO, re.M)
RE_ANY_DATE = re.compile(ISO)


def _registered_local_copy_exists():
    """True only if a DIFFERENT repo-local copy exists AND is registered in the
    project's settings. Existence alone must NOT silence the global hook — that
    gap silently deactivated the hook layer in 44 repos (QC 2026-07-14)."""
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", base))
        if me == local or not os.path.exists(local):
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


def _check(after, before, today, is_new):
    """Return (fails, warns). `before` is '' for a new file."""
    fails, warns = [], []
    t = today.isoformat()

    m = RE_UPDATED.search(after)
    if m:
        got = "%s-%s-%s" % m.groups()
        if got != t:
            fails.append(
                "最終更新日が %s ですが、システム日付は %s です。"
                "前回セッションの日付を引き写していませんか。" % (got, t))

    m = RE_CREATED.search(after)
    if m and is_new:
        got = "%s-%s-%s" % m.groups()
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

    # D5: content changed today but 最終更新日 still shows an older date.
    # The mirror image of D1: D1 catches a date copied from the previous
    # session onto new work; D5 catches real work landing in an old document
    # whose date nobody bumped. Both leave the file claiming a date that is not
    # when it was actually last written.
    #
    # WARN, not FAIL, and deliberately so: typo fixes and formatting passes are
    # legitimately not "updates". Blocking them would make the guard something
    # to be switched off. Only fires when prose actually grew, and only when the
    # stale date was NOT introduced by this edit (that is D1's job, already
    # reported above — reporting both would double-count one mistake).
    if before and m and not is_new:
        got = "%s-%s-%s" % m.groups()
        grew = len(after) - len(before)
        unchanged_date = bool(RE_UPDATED.search(before)) and \
            ("%s-%s-%s" % RE_UPDATED.search(before).groups()) == got
        if got < t and grew >= 80 and unchanged_date:
            warns.append(
                "本文を %d 文字追記していますが、最終更新日は %s のままです"
                "（本日 %s）。実質的な更新なら %s に更新してください。"
                % (grew, got, t, t))

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
        data = json.loads(raw.decode("utf-8", "replace"))
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

        today = date.today()
        fails, warns = _check(after, before, today, is_new)

        # Regression-only on FAILs: never block because of a date that was
        # already wrong on disk before this edit.
        if not is_new and fails:
            pre_f, _ = _check(before, before, today, False)
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
