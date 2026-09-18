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

REPORT_NAME = re.compile(r"_\d{8}(?:-v\d+)?\.md$", re.I)
# Numbered pipeline stage (01_search_plan.md, 04_synthesis.md, ...): an
# intermediate artefact of a research run, regenerated wholesale next run.
# True intermediates only. 05_report.md is the pipeline's FINAL deliverable
# (README Phase 5; 23 of them are indexed as レポート) and must stay in scope.
PIPELINE_STAGE = re.compile(
    r"^(?:0[0-4])_(?:search_plan|search|screening|synthesis|plan|extract|collect|dedup|rank)[a-z0-9_\-]*\.md$", re.I)
DATED_DOC = re.compile(r"^\d{4}-\d{2}-\d{2}[-_]", re.I)
# In step with summary_freshness_check.SCOPE_DIRS, which also carries _meta/.
# Without it the two guards disagreed on every Soulful-Content/_meta report,
# including COCONALA_COPY_20260820.md -- the case this guard was built from.
DEFAULT_DIRS = ("outputs/", "reports/", "docs/", "output/", "report/", "_meta/")
# Directories holding generated or third-party material, not our own analysis.
# Kept in step with summary_freshness_check.EXCLUDE_DIRS (2026-09-18): plan,
# spec, prompt, skill, rules, retro documents and document fragments are not
# reports, so the "conclusion first" rule does not apply to them. They were
# 59 of 74 files in the measured backlog; nagging about them is how a guard
# gets muted.
# Two tiers, mirroring summary_freshness_check (2026-09-18).
# HARD: generated data / vendored / fixtures -- nothing overrides.
# SOFT: "not a report KIND" -- a dated report name overrides.
# Kept in step with summary_freshness_check.HARD_EXCLUDE_DIRS. The three
# prefix markers at the end are substring, not segment, matches -- an
# archived tree is archived however it is spelled. Measured 2026-09-19:
# without them the two guards disagreed on 10 real files, including
# career_dev/_archived_do_not_reference/ (which the repo name itself asks
# nobody to reference) and deep-research/_data/paper_pdfs/.
HARD_EXCLUDE = ("data/", "materials/", "drafts/", "node_modules/",
                "session/", ".git/", "vendor/", "fixtures/", "tests/",
                "_data/", ".venv/",
                "_archived", "_archive/")
# In step with summary_freshness_check.SOFT_EXCLUDE_DIRS: plans/, specs/ and
# retros/ were dropped 2026-09-19 after measuring that they excluded nothing
# (every file under them is date-named and returned via the name rule).
SOFT_EXCLUDE = ("prompts/", "skills/", "agents/", "parts/", "_tmp/", "tmp/",
                "rules/")
DEFAULT_EXCLUDE = HARD_EXCLUDE + SOFT_EXCLUDE


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


try:
    import summary_freshness_check as _SFC
except Exception:                                    # pragma: no cover
    class _SFC(object):                              # fail-open stub
        @staticmethod
        def structure_regression(_b, _a):
            return []

        @staticmethod
        def _looks_like_report(_t):
            return False      # no content override when the library is absent

        @staticmethod
        def read_text(_p):
            return ""        # caller falls back to utf-8-sig


def _in_scope(fp, cfg, text=None, path_only=False):
    """Only analyse our own report prose.

    `text` is the post-edit content when the caller has it. Like
    summary_freshness_check.in_scope(), a document carrying a 結論/サマリー
    section LIFTS a SOFT (document-kind) veto -- but it does not grant scope on
    its own: the path must still land in an allowed tree. `path_only=True` skips
    that lift, for a cheap rejection before reading the file.
    """
    if not fp.lower().endswith(".md"):
        return False
    try:
        rel = os.path.relpath(fp, os.getcwd())
    except Exception:
        rel = fp
    norm = rel.replace("\\", "/").lower()
    if norm.startswith("../"):          # outside the project
        norm = os.path.basename(norm)

    bn = os.path.basename(norm)
    inc = cfg.get("include")

    # A repo's own "exclude" ADDS to the built-in hard list; it never replaces
    # it. Measured 2026-09-19: 4 repos set exclude (data/, session/,
    # data/drafts/ ...). Treating their list as the whole hard list would have
    # re-admitted node_modules/ and fixtures/ in exactly those repos.
    for ex in tuple(HARD_EXCLUDE) + tuple(cfg.get("exclude") or ()):
        e = ex.lower()
        # Entries ending in "/" are whole path SEGMENTS; entries without one
        # are PREFIX markers matched as substrings. Appending "/" to every
        # entry (the previous behaviour) turned "_archived" into "_archived/",
        # which never matched career_dev/_archived_do_not_reference/ -- the
        # directory whose own name asks nobody to reference it.
        if e.endswith("/"):
            if "/" + e.strip("/") + "/" in "/" + norm:
                return False
        elif e in norm:
            return False

    # A dated report name is scope-bearing on its own, and is NOT bounded by a
    # repo's "include". Round-2 adversarial review measured the alternative:
    # gating the name check behind include split the two guards on 75 real
    # files -- Soulful-Content sets include ["_meta/references/"], so 54 dated
    # _meta reports got the Stop freshness check but never the 初回作成時
    # structure check. COCONALA_COPY_20260820.md, the case this whole guard was
    # built from, was one of them.
    #
    # "include" still bounds everything that is NOT a dated report, which is
    # what the 20 repos setting it actually meant by it.
    if REPORT_NAME.search(bn) or DATED_DOC.match(bn):
        return True

    if inc and not any(i.lower().rstrip("/") + "/" in "/" + norm for i in inc):
        return False

    for ex in SOFT_EXCLUDE:
        if ex.lower().rstrip("/") + "/" in "/" + norm:
            # Content clears the veto only; SCOPE/include below still decides.
            # Uses the SAME two-signal test as summary_freshness_check (a
            # 結論 section AND a dated front-matter line), so the two guards
            # cannot drift on what counts as a report.
            #
            # path_only is the CHEAP PRE-PASS run before the file is read. It
            # must not veto here: a SOFT hit is exactly the case whose answer
            # depends on content, so vetoing would make the content check
            # unreachable. Round-4 adversarial review caught precisely that --
            # piping a real Write payload for _meta/prompts/new_report.md with
            # 作成日 + ## 結論 + a violation produced SILENCE, while the unit
            # tests passed because they called _in_scope() directly and never
            # went through main(). Tests on dead code prove nothing.
            if path_only:
                break                      # undecidable without the content
            if text and _SFC._looks_like_report(text):
                break
            return False

    if PIPELINE_STAGE.match(bn):
        return False
    if inc:
        return True                    # already inside an allowed tree
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
        data = _codex_normalize(json.loads(raw.decode("utf-8", "replace")))
        tool_name = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        # Cheap path-only rejection first: if the path is out of scope no matter
        # what the file says, do not read anything.
        if not _in_scope(fp, cfg, path_only=True):
            return

        # Decode whatever encoding the file is in, not just UTF-8. A cp932 or
        # UTF-16 report used to read as "" -- and since an Edit is applied as
        # before.replace(old, new), `after` came out "" too, so the checks found
        # nothing and the hook was silent (round-5 probe E6/E7). PowerShell's
        # Set-Content still defaults to ANSI on this machine, so this is
        # reachable. summary_freshness_check.read_text already handles it.
        try:
            before = _SFC.read_text(fp)
        except Exception:
            before = ""
        if not before:
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

        # Now judge by CONTENT as well. Round-3 adversarial review found the R2
        # fix was half-applied: summary_freshness_check.in_scope() learned to
        # read the document, but this guard stayed path-only, so four real
        # reports under _meta/prompts/ (dx-article 337 lines, book-seed 296,
        # book-seed-conversion 122, book-article-duel 100) got the Stop
        # freshness check and never the 初回作成時 structure check -- and a NEW
        # undated 結論-report written to prompts/ escaped both, because a new
        # file has no snapshot for the Stop path to compare against.
        # Judge on BEFORE or AFTER. An edit that deletes the 作成日/最終更新日
        # lines in the same call that adds a violation would otherwise erase the
        # document's own evidence of being a report and go silent -- measured
        # round-5 against the deployed hook: identical edit WITH the deletion
        # was silent, WITHOUT it fired. summary_freshness_check is immune
        # because its snapshot judges the pre-edit text; this is the PreToolUse
        # equivalent of that.
        if not (_in_scope(fp, cfg, text=after)
                or _in_scope(fp, cfg, text=before)):
            return

        f_before = _analyze(before, cfg, mods)
        f_after = _analyze(after, cfg, mods)

        # 冒頭構成の検査（2026-09-15 追加）。ユーザー規則の
        # 「初回作成時や更新、常に、結論が各章の重要事項を含む」に対応する。
        # summary_freshness_guard は UPDATE の差分しか見られないため、
        # 新規作成レポートは原理的に対象外だった。ここで補う。
        # regression-only は既存と同じ方針（実測: リモート796本中292本=36.7%が
        # 結論節を持たない。全部止めれば初日で無効化される）。
        struct = []
        if cfg.get("structure", True):
            try:
                struct = _SFC.structure_regression(before, after)
            except Exception:
                struct = []

        if len(f_after) <= len(f_before) and not struct:
            return  # regression-only: pre-existing debt never blocks

        seen = set(f_before)
        added = [x for x in f_after if x not in seen]
        added += [("structure", d) for _c, d in struct]
        if not added:
            added = f_after[-1:]
        # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
        _record_firing("pre_report_quality_guard", data)
        _emit(added, cfg.get("mode", "warn"))
    except Exception:
        pass


def _struct_hint(findings):
    """Extra guidance when a finding is about the opening's STRUCTURE.

    Deliberately states what the check cannot see. A message implying the
    machine had verified 「結論が各章の重要事項を含む」 would be false: it knows
    only whether a summary section exists and whether the opening names the
    later chapters. Whether the summary states each chapter's point is a human
    judgement, and saying otherwise is how a guard teaches people to trust it
    for something it does not do.
    """
    if not any(k == "structure" for k, _v in findings):
        return ""
    return ("\n【冒頭構成】レポートは初回作成時も更新時も、冒頭の結論が全章の"
            "重要事項を含み、重要なものが前半に来る構成にすること"
            "（冒頭20%で全体の価値の80%をカバーする）。"
            "\n※本検査が見ているのは「結論節の有無」と「冒頭が各章に触れて"
            "いるか」までで、要点が実際に書けているかは判定していない。"
            "そこは自分で確認すること。")


def _emit(findings, mode):
    lines = [f"・[{k}] {v}" for k, v in findings[:4]]
    body = "\n".join(lines)
    if mode == "deny":
        reason = ("レポート品質ルール違反をこの編集で新規に追加しています:\n" + body +
                  "\n有効数字は4桁（表示値のみ・引用実測値/法定定数は対象外）。"
                  "網羅主張には根拠か留保（未検証/対象外/前提 等）を近傍に添える。"
                  + _struct_hint(findings))
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason}}))
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                "⚠ レポート品質チェック（warn・ブロックはしない）:\n" + body +
                _struct_hint(findings) +
                "\n※誤検知なら .claude/report_quality.json で調整可。")}}))


if __name__ == "__main__":
    main()
    sys.exit(0)
