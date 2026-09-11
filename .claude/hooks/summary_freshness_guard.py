# -*- coding: utf-8 -*-
"""Stop hook: a report update must refresh the opening, not just append.

THE RULE (user, 2026-09-11)
---------------------------
「更新の指示をした時に更新箇所を追記するのがレポートの後半の章になっていたり、
あるいは単純に新しく最後の章を追加していくというスタイル…全く妥当ではありません。
むしろ更新では、重要な漏れ／改善余地を指摘していることが多く、重要な情報ほど
手前に来る設計にすべきです。」

WHY A Stop HOOK AND NOT PreToolUse
-----------------------------------
PreToolUse(Write|Edit) cannot see the write at all when the file is produced by
a Bash heredoc or sed. Measured in one real session: 0 of 3 report writes went
through Write|Edit. A guard that only watches the tool the model happens to use
is not a guard. This one diffs the DISK at end of turn, so every write path --
Write, Edit, MultiEdit, heredoc, sed, a script -- is covered by construction.

The cost of Stop is that it reports after the fact rather than blocking the
write. That is the right trade here: the invariant is about the SHAPE OF THE
FINISHED TURN ("you touched the late body and left the opening stale"), which
is not even knowable until the turn ends. A per-edit check would fire on the
first Edit of a sequence that ends perfectly correct.

HOW THE BASELINE IS TAKEN
-------------------------
`summary_freshness_snapshot.py` (PreToolUse, matcher Write|Edit|MultiEdit|Bash
|PowerShell) records each in-scope report file's content the FIRST time the
turn touches it, keyed by prompt_id. At Stop this compares that baseline with
what is now on disk. Files with no baseline are skipped: without a "before"
there is no update to judge, and a brand-new report is a different rule.

WHAT IT REPORTS
  I1 WARN  >= K lines changed outside the opening block, opening unchanged.
  I2 INFO  sections the opening block never references (advisory; naming a
           section is not summarising it, so this can never be a block).

Warn, not deny. A Stop-block forces a re-answer, and the correct response to
this finding is often a judgement call ("the appendix genuinely belongs late").
Promote to deny per repo via .claude/report_quality.json once warn-mode shows a
clean week -- the same path post_bash_guard and pre_report_quality_guard took.

CALIBRATION, on git history as ground truth (337 real report updates, 43 repos):

    the bare diff invariant, K=5        107/337 (31.8%)
    + document must HAVE a summary       26/337 ( 7.7%)  <- SHIPPED
    + late change must add a heading     14/337 ( 4.2%)  <- rejected

7.7% is what this hook is held to; precision there is ~18 of 26 by reading all
of them. An earlier 30-file sample claimed 20.0% for the bare invariant and was
simply wrong -- the full corpus says 31.8%. The 4.2% variant was rejected for
reopening three bypasses (a bolded verdict line, a blockquote, a table row)
that match how this author actually appends findings. See
summary_freshness_check.py for the full tables, the worked examples, and why
the vocabulary-based design that preceded all of this died at precision ~3/10.

FAIL-OPEN: any exception -> silent exit 0.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
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
    import summary_freshness_check as SFC
except Exception:
    SFC = None

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "summary_freshness")


def _cfg():
    cfg = {"mode": "warn", "k": 5}
    try:
        p = os.path.join(os.getcwd(), ".claude", "report_quality.json")
        with io.open(p, encoding="utf-8-sig") as f:
            user = json.load(f)
        if isinstance(user, dict):
            if isinstance(user.get("summary_mode"), str):
                cfg["mode"] = user["summary_mode"]
            if isinstance(user.get("summary_k"), int):
                cfg["k"] = user["summary_k"]
    except Exception:
        pass
    return cfg


def _turn_key(ev):
    raw = str(ev.get("prompt_id") or ev.get("session_id") or "")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", raw)[:80]


def _load_snapshot(key):
    if not key:
        return {}
    try:
        with io.open(os.path.join(STATE_DIR, key + ".json"),
                     encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def main():
    # Defer to a registered repo-local copy (existing convention).
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        return

    if SFC is None:
        return

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return                      # already blocked once; never loop

    cfg = _cfg()
    if cfg.get("mode") == "off":
        return

    snap = _load_snapshot(_turn_key(ev))
    if not snap:
        return                      # nothing touched this turn

    findings = []
    for path, before in snap.items():
        if not isinstance(before, str):
            continue
        if not os.path.isfile(path):
            continue
        after = SFC.read_text(path)
        f = SFC.analyze(before, after, k=cfg.get("k", 5))
        if not f:
            continue
        unref = SFC.unreferenced_sections(after)
        findings.append((path, f, unref))

    if not findings:
        return

    # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
    _record_firing("summary_freshness_guard", ev)

    lines = []
    for path, f, unref in findings[:3]:
        rel = os.path.basename(path)
        lines.append(
            u"・%s: 冒頭ブロック(L1-L%d)は逐語で不変のまま、L%d 以降を %d 行変更"
            % (rel, f["opening_end"], f["first_late_line"], f["outside"]))
        if unref:
            lines.append(
                u"  冒頭が参照していない章: %s"
                % ", ".join(u"§%s" % n for n, _t in unref[:6]))

    body = u"\n".join(lines)
    reason = (
        u"⛔ 更新が後半だけに入り、冒頭の結論が古いままです。\n" + body +
        u"\n\n更新で見つかった事項は「重要な漏れ・改善余地」であることが多く、"
        u"最も手前に来るべきものです。末尾に章を足して終えないこと。\n"
        u"冒頭ブロック（結論/サマリー）に今回の変更の要点を反映してから完了と"
        u"すること。巻末の詳細は残してよい——冒頭に要点が無いことが問題です。\n"
        u"※付録・出典など本当に巻末が正しい変更なら、このまま完了してよい。")

    if cfg.get("mode") == "deny":
        # ensure_ascii + binary write: several kanji end in byte 0x5C under
        # CP932 (「表」= 0x95 0x5C) and corrupt JSON through a text stream.
        out = json.dumps({"decision": "block", "reason": reason},
                          ensure_ascii=True)
        sys.stdout.buffer.write(out.encode("ascii"))
        sys.stdout.buffer.flush()
    else:
        # Same CP932 hazard as the deny path above, and it really bit: the
        # end-to-end test read this stream as UTF-8 and got mojibake, because
        # sys.stderr on Windows encodes to the console codepage. Every kanji in
        # the warning was unreadable in the terminal too. Write UTF-8 bytes.
        try:
            sys.stderr.buffer.write((reason + u"\n").encode("utf-8"))
            sys.stderr.buffer.flush()
        except Exception:
            sys.stderr.write(reason.encode("ascii", "replace").decode() + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
