"""PreToolUse hook (Write|Edit): report quality guard.

Covers two chronically-violated rules that previously existed ONLY as prose
(or, worse, only in memory files, which arrive as advisory <system-reminder>
context and therefore never bound behaviour at all):

  1. 有効数字4桁 (2026-07-24 指示)  -> numeric_precision_check
  2. 根拠なき網羅主張の禁止          -> report_rigor_check
     (「本当にまだ試してないんですか？…検証計画に穴がありそう」2026-07-01)

Design decisions, all forced by measurement rather than assumption:

- REGRESSION-ONLY. Denies/warns only when an edit INCREASES the finding count
  versus the pre-edit file on disk. Pre-existing debt (2,161 .md files carry
  some) never blocks unrelated work.
- Write + Edit. Reports are built as one Write plus many Edits, so a
  Write-only hook would inspect just the first chunk.
- SCOPED to report-style files by default (`<TOPIC>_YYYYMMDD.md` and
  docs/reports/outputs trees). A 2026-08-04 corpus audit showed generated data
  (data/, materials/, drafts/) is where nearly all false positives live.
- MODE defaults to "warn": it surfaces the issue without blocking. Promote to
  "deny" per repo via .claude/report_quality.json once warn-mode shows a zero
  false-positive week. Rationale: the checkers' own false-positive rate was
  measured, not assumed, and it moved a lot during development.
- Fail-open: any error -> exit 0. A guard bug must never stop the user's work.

Per-repo configuration — .claude/report_quality.json (all keys optional):
  {"mode": "warn"|"deny"|"off",
   "checks": ["numeric","rigor"],
   "include": ["outputs/", "reports/"],
   "exclude": ["data/", "materials/"]}

Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import re
import sys

REPORT_NAME = re.compile(r"_\d{8}(?:-v\d+)?\.md$", re.I)
DEFAULT_DIRS = ("outputs/", "reports/", "docs/", "output/", "report/")
# Directories holding generated or third-party material, not our own analysis.
DEFAULT_EXCLUDE = ("data/", "materials/", "drafts/", "node_modules/",
                   "session/", ".git/", "vendor/", "fixtures/")


def _registered_local_copy_exists():
    """True only if a DIFFERENT repo-local copy exists AND is registered in the
    project's .claude/settings(.local).json. Existence alone must NOT silence
    the global hook — that gap deactivated the hook layer in 44 repos (QC
    2026-07-14)."""
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", base))
        if me == local or not os.path.exists(local):
            return False
        for name in ("settings.json", "settings.local.json"):
            try:
                with open(os.path.join(os.getcwd(), ".claude", name), encoding="utf-8-sig") as f:
                    if base in f.read():
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _load_config():
    cfg = {"mode": "warn", "checks": ["numeric", "rigor"],
           "include": None, "exclude": None}
    try:
        p = os.path.join(os.getcwd(), ".claude", "report_quality.json")
        with open(p, encoding="utf-8-sig") as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in cfg})
    except Exception:
        pass
    return cfg


def _in_scope(fp, cfg):
    """Only analyse our own report prose."""
    if not fp.lower().endswith(".md"):
        return False
    try:
        rel = os.path.relpath(fp, os.getcwd())
    except Exception:
        rel = fp
    norm = rel.replace("\\", "/").lower()
    if norm.startswith("../"):          # outside the project
        norm = os.path.basename(norm)

    for ex in (cfg.get("exclude") or DEFAULT_EXCLUDE):
        if ex.lower().rstrip("/") + "/" in "/" + norm:
            return False

    inc = cfg.get("include")
    if inc:
        return any(i.lower().rstrip("/") + "/" in "/" + norm for i in inc)
    if REPORT_NAME.search(os.path.basename(norm)):
        return True
    return any(d in "/" + norm for d in DEFAULT_DIRS)


def _analyze(text, cfg, mods):
    out = []
    if "numeric" in cfg["checks"] and mods[0]:
        for f in mods[0].analyze_text(text):
            out.append(("有効数字", f"L{f['line']} {f['value']}（{f['sigfigs']}桁）→ {f['suggestion']}"))
    if "rigor" in cfg["checks"] and mods[1]:
        for f in mods[1].analyze_text(text):
            out.append(("網羅主張", f"L{f['line']}「{f['claim']}」{f['text'][:50]}"))
    return out


def main():
    if _registered_local_copy_exists():
        return
    cfg = _load_config()
    if cfg.get("mode") == "off":
        return

    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        try:
            import numeric_precision_check as npc
        except Exception:
            npc = None
        try:
            import report_rigor_check as rrc
        except Exception:
            rrc = None
        if npc is None and rrc is None:
            return
        mods = (npc, rrc)

        # Read stdin as BYTES and decode UTF-8 explicitly. json.load(sys.stdin)
        # uses the Windows locale encoding (CP932 here), which mojibakes every
        # Japanese payload into 蜈ｨ繝代ち... — the checks then silently find
        # nothing. Caught 2026-08-04 by running the deployed hook end-to-end;
        # the subprocess unit tests passed because they pipe UTF-8 bytes.
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
        tool_name = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        if not _in_scope(fp, cfg):
            return

        try:
            with open(fp, encoding="utf-8-sig") as f:
                before = f.read()
        except Exception:
            before = ""

        if tool_name == "Write":
            after = ti.get("content") or ""
        elif tool_name == "Edit":
            old, new = ti.get("old_string"), ti.get("new_string")
            if old is None or new is None:
                return
            after = (before.replace(old, new) if ti.get("replace_all")
                     else before.replace(old, new, 1))
        else:
            return

        f_before = _analyze(before, cfg, mods)
        f_after = _analyze(after, cfg, mods)
        if len(f_after) <= len(f_before):
            return  # regression-only: pre-existing debt never blocks

        seen = set(f_before)
        added = [x for x in f_after if x not in seen] or f_after[-1:]
        _emit(added, cfg.get("mode", "warn"))
    except Exception:
        pass


def _emit(findings, mode):
    lines = [f"・[{k}] {v}" for k, v in findings[:4]]
    body = "\n".join(lines)
    if mode == "deny":
        reason = ("レポート品質ルール違反をこの編集で新規に追加しています:\n" + body +
                  "\n有効数字は4桁（表示値のみ・引用実測値/法定定数は対象外）。"
                  "網羅主張には根拠か留保（未検証/対象外/前提 等）を近傍に添える。")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason}}))
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                "⚠ レポート品質チェック（warn・ブロックはしない）:\n" + body +
                "\n※誤検知なら .claude/report_quality.json で調整可。")}}))


if __name__ == "__main__":
    main()
    sys.exit(0)
