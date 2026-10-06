# -*- coding: utf-8 -*-
"""Stop hook: a 再発防止 turn cannot end with prose and a single repo.

THE DEFECT THIS EXISTS FOR (measured 2026-09-03)
------------------------------------------------
The user has repeatedly asked for 再発防止 (recurrence prevention). The answers
repeatedly produced countermeasures that could not work. The user named five
failure modes; every one is measurable, and every one was present in the
archive at the moment they complained:

    5 hooks registered in  0/44 repos   (built, shipped nowhere)
    2 hooks not installed globally at all
   11 of 19 hooks had no test whatsoever
   11 of 19 hooks had never been calibrated on real data
   18 of 19 hooks kept no firing record, so nobody could tell a
            never-fired guard from a working one

The proximate case: asked to prevent fabricated URLs from reaching the user,
the previous session shipped ONE memory file plus a §7.6 section in ONE repo's
markdown. Prose, 1 of 44 repos, nothing mechanical, nothing tested.

THIS IS A REPEAT. On 2026-08-14 the same shape was recorded in
deploy_md_date_guard.py's own docstring about ITS predecessor: "present in 8 of
42 repos, wired into zero hooks and zero CI, inert unless --today was passed by
hand". The class has now recurred at least twice, which is why the fix is a
gate and not another paragraph.

WHY PROSE COULD NOT HAVE PREVENTED IT
-------------------------------------
CLAUDE.md §14 F2 already says: 「無反応＝正常と解釈しない。発火する条件を1つ
作って実際に発火させ、初めて『動いている』と言える」. That rule was in force
while 18 of 19 guards sat with no firing record. A rule that must be recalled
by the author, at the end of a long task, does not survive contact with a
finished-feeling answer.

WHAT THIS GATE DOES
-------------------
When the turn is ABOUT 再発防止 (the user asked for it, in their own words),
the answer may not end until the countermeasure audit has actually been run in
this turn. It does not grade the countermeasure -- it forces the measurement
that the author would otherwise skip, and the audit prints the five numbers.

Trigger is the USER's request, not the answer's self-description. An answer
that fails at 再発防止 tends to describe itself as thorough; the request is the
one part of the turn the author cannot rewrite.

DELIBERATELY NOT DONE
---------------------
Does not run the audit itself. A Stop hook that shells out to a 44-repo scan on
every answer would add seconds to unrelated turns and would be muted. It checks
whether the author ran it, and says exactly which command to run.

Does not fire on turns that merely mention 再発防止 in passing (a report that
cites a past countermeasure). It requires an imperative from the user -- see
ASK_RE below.

LOOP SAFETY: `stop_hook_active` -> return, so at most one block per answer.
FAIL-OPEN: any exception -> exit 0.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:  # adapter missing: say so, do not fail silently
    def _codex_transcript(p, *_a, **_k):
        # Without this, a Codex transcript is walked with Claude's schema,
        # finds no rows, and the hook concludes "nothing happened this turn"
        # -- silence indistinguishable from a clean turn (QC 2026-09-18).
        if p:
            sys.stderr.write(
                "[%s] codex_transcript.py not found next to this hook; "
                "Codex transcripts are NOT being read."
                % os.path.basename(__file__) + chr(10))
        return p


# --- Firing-log recording (defect 2, 2026-09-03) ----------------------------
#
# WHY: the countermeasure ledger's V2_NO_FIRING_LOG check reads
# ~/.claude/state/<hook>/ to ask "has this hook ever actually fired?". This
# gate previously never wrote there, so it audited every OTHER hook for
# self-violation while committing the exact same violation itself -- a gate
# about "did you measure this" that never measured itself.
#
# Format matches notfound_guard.py's convention: one JSON file per session
# under ~/.claude/state/countermeasure_gate/<session_id>.json, holding
# last_fired (ISO8601 UTC) and a cumulative count. Failures here must never
# break the gate itself, so every step is wrapped and swallowed.
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "countermeasure_gate")


def _fire_sid(ev):
    s = ev.get("session_id") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64]


def _record_fired(ev):
    """Best-effort: write/update ~/.claude/state/countermeasure_gate/<sid>.json
    with last_fired (ISO8601 UTC) and a cumulative count. Never raises."""
    try:
        path = os.path.join(STATE_DIR, _fire_sid(ev) + ".json")
        prev = {}
        try:
            with io.open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
        count = prev.get("count", 0)
        if not isinstance(count, int):
            count = 0
        data = {
            "last_fired": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "count": count + 1,
        }
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

# --- Is the USER asking for a countermeasure? -----------------------------
#
# Needs the topic AND a request. 「再発防止を計画して」「二度と起こらないように」
# 「恒久対策」. A bare mention ("前回の再発防止では...") must not trigger.
ASK_RE = re.compile(
    u"(?:再発防止|恒久対策|再発を?防|二度と(?:起こ|同じ|繰り返)"
    u"|同じ(?:ミス|問題|失敗)を?(?:繰り返|起こ)さな"
    u"|同様の(?:問題|ミス|失敗)[^。\n]{0,10}(?:防|起こ))",
    re.IGNORECASE)

# An imperative aimed at Claude, OR a complaint that the countermeasure was
# inadequate. Both commission work; only the first is phrased as a request.
#
# The second half was added after a measured miss: the user's real 2026-09-03
# message was a COMPLAINT ("...施策のみで終わったこと"), grammatically a noun
# phrase with no imperative verb anywhere. Requiring an imperative silently
# exempted the single most important turn in the corpus -- the one where the
# countermeasure had actually just failed. A complaint about a weak
# countermeasure is a demand for a better one.
IMPERATIVE_RE = re.compile(
    u"(?:して|し て|を)?(?:ください|下さい|ほしい|欲しい)"
    u"|(?:立てて|計画して|実行して|対策して|考えて|作って|やって|防いで|直して)"
    u"|(?:せよ|しろ|してくれ)"
    u"|お願いします"
    # 2026-10-06: 命令形「〜しなさい」と当為「〜すべき／べきではないでしょうか」、
    # 中止要求「やめて／やめるべき」。実ユーザーの 再発防止 依頼3件中2件が
    # この形だけで書かれており、旧パターンでは沈黙した（docstring 参照）。
    u"|なさい|べき|やめ(?:て|る|なさい)"
    # complaint forms -- the countermeasure was judged inadequate
    u"|意味が(?:ほぼ)?無|意味がない|応えな|不十分|甘い|できていない"
    u"|終わったこと|限定すぎ|ほとんど発火")

# --- Did the author actually measure? -------------------------------------
#
# The audit prints the five numbers the user's five complaints map to. Running
# it is the cheapest possible proof that the countermeasure was checked against
# them rather than asserted to be fine.
AUDIT_RE = re.compile(
    r"audit_countermeasures\.py|countermeasure_ledger\.py")

# --- Did a DIFFERENT model actually attack it? ----------------------------
#
# ⛔ THE GAP THIS CLOSES (2026-09-15, found by the user, not by me).
# The rules have always said 「攻撃的検証: 自作テストの合格は証拠にならない」 and
# 「独立QC: 自分の計画を自分でQCしない」. But nothing CHECKED it: reqspec_gate
# injects that sentence as prose at prompt time, and this gate only verified
# that the audit script ran. Prose plus an unverified intention is exactly the
# 「散文追記で終わる」 defect (欠陥③) the whole countermeasure meta-rule names.
#
# The cost was measured, on this very feature. I shipped summary_freshness
# reporting "PASS, 違反なし" with THREE fatal bypasses in it, including one
# where following CLAUDE.md §10b (bump 最終更新日) silenced the guard entirely.
# They were found only because I happened to run Fable by hand afterwards. Had
# I not, the audit would still have said PASS and the guard would have been
# decorative. Then the FIX for those introduced two more silent-failure paths.
#
# So: a countermeasure turn must show that a different model was actually
# dispatched to break the thing. A Task/Agent call naming a non-Opus model, or
# a written adversarial-findings fixture, both count. What does NOT count is
# saying the words -- this matches TOOL CALLS in the transcript, not prose.
ADVERSARIAL_RE = re.compile(
    r"claude-fable|model[\"'\s:=]+fable|subagent_type"
    r"|adversarial\w*\.md|_adversarial_|攻撃コーパス|attack_corpus")

# A countermeasure mentioned in the PAST, as background to something else:
# 「前回の再発防止でフックを入れましたが…」. Past tense plus a retrospective
# time word; a live request does not describe its own countermeasure as
# already installed.
BACKGROUND_RE = re.compile(
    u"(?:前回|前の|先ほど|さっき|以前|昨日|この前|先週)[^。\n]{0,24}"
    u"(?:再発防止|恒久対策|対策|ガード|フック)"
    u"[^。\n]{0,24}(?:入れ|導入し|作っ|やっ|実施し|し)(?:まし|た|てい)")

# Verbs that commission actual remediation. If any of these is present the
# turn is a countermeasure turn even when a past one is also mentioned --
# 「前回の再発防止では不十分なので直して」 must still fire.
FIX_VERB_RE = re.compile(
    u"(?:立てて|計画して|実行して|対策して|考えて|作って|やって|防いで|直して"
    u"|修正して|改善して|反映して|更新して|検討して"
    u"|お願いし|してください|して下さい|してほしい|して欲しい"
    u"|せよ|しろ|してくれ|なさい|べき|やめて|やめる)"
    u"|(?:不十分|甘い|できていない|意味が(?:ほぼ)?無|意味がない|応えな"
    u"|終わったこと|限定すぎ|ほとんど発火|繰り返して)")

# --- (a)(b)(c): was the countermeasure MECHANICAL, DEPLOYED, and FIRED? -----
#
# ⛔ THE GAP THIS CLOSES (2026-10-06). Until today DEPLOY_RE was defined and
# never used, and nothing looked at WHAT the turn produced. A turn that ran the
# audit, dispatched Fable, and then shipped a paragraph in one repo's markdown
# passed -- which is exactly 欠陥③「散文追記で終わる」 and 欠陥①「1リポ」, the two
# defects this gate was built to stop. Each check below reads TOOL CALLS
# (Write/Edit file_path, Bash/PowerShell command), never prose, and never a
# subagent's prompt text: telling a helper "run deploy_all.py" is not running it.

# (a) An executable countermeasure lives under a hooks/ or scripts/ directory
# (templates/hooks/ included). Tests and calibrators are NOT the countermeasure:
# writing only test_x.py proves nothing was built.
COUNTERMEASURE_PATH_RE = re.compile(
    r"(?:^|[/\\])(?:hooks|scripts)[/\\](?:[^/\\]+[/\\])*[^/\\]+\.(?:py|sh|js|ps1)$",
    re.IGNORECASE)
NOT_COUNTERMEASURE_RE = re.compile(
    r"(?:^|[/\\])tests?[/\\]|(?:^|[/\\])(?:test_|calibrate_)[^/\\]*$",
    re.IGNORECASE)
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
# Shell verbs that write the file named last on the segment.
SHELL_WRITE_VERB_RE = re.compile(
    r"^\s*(?:sudo\s+)?(?:tee|cp|mv|install|sed\s+-i\S*|perl\s+-[a-z]*i\S*"
    r"|Copy-Item|Move-Item|Set-Content|Out-File|Add-Content)\b", re.IGNORECASE)
SHELL_REDIRECT_RE = re.compile(r">{1,2}\s*['\"]?([^\s'\";&|<>]+)")
PATH_TOKEN_RE = re.compile(r"[^\s'\";&|<>()]+\.(?:py|sh|js|ps1)\b", re.IGNORECASE)

# (b) The deployment actually ran. A dry run deploys nothing.
DEPLOY_RE = re.compile(r"deploy_all\.py")
DEPLOY_RUN_RE = re.compile(
    r"\b(?:python3?|py)(?:\.exe)?\s+(?:-\S+\s+)*['\"]?\S*deploy_all\.py",
    re.IGNORECASE)

# (c) Something was EXECUTED that would show it fires: a test, a calibration
# against real data, pytest, or the cross-hook firing verifier. Reading the
# test file (cat test_x.py) is not executing it.
FIRING_CHECK_RE = re.compile(
    r"\b(?:python3?|py)(?:\.exe)?\s+(?:-\S+\s+)*['\"]?\S*"
    r"(?:test_\w+|calibrate_\w+|verify_hook_firing)\.py"
    r"|\bpytest\b", re.IGNORECASE)

# Exemption for (a)-(c): a reason written into COUNTERMEASURE_EXEMPT.json in
# this turn. An empty reason is not a reason (the audit enforces the same).
EXEMPT_FILE_RE = re.compile(r"COUNTERMEASURE_EXEMPT\.json$", re.IGNORECASE)
EXEMPT_REASON_RE = re.compile(r"\"reason\"\s*:\s*\"[^\"\s]")

SEGMENT_SPLIT_RE = re.compile(r"\n|;|&&|\|\||(?<![|>])\|(?!\|)")


def _is_cm_path(p):
    p = (p or "").strip().strip("'\"")
    return bool(COUNTERMEASURE_PATH_RE.search(p)
                and not NOT_COUNTERMEASURE_RE.search(p))


def _segments(cmd):
    return [s for s in SEGMENT_SPLIT_RE.split(cmd or "") if s.strip()]


def _shell_writes_cm(cmd):
    """Best-effort: does this shell command write an executable countermeasure
    file? Redirect target, or the LAST path token of a writing verb (cp src
    dst: only dst is written)."""
    for seg in _segments(cmd):
        for m in SHELL_REDIRECT_RE.finditer(seg):
            if _is_cm_path(m.group(1)):
                return True
        if SHELL_WRITE_VERB_RE.search(seg):
            toks = PATH_TOKEN_RE.findall(seg)
            if toks and _is_cm_path(toks[-1]):
                return True
    return False


def _ts(v):
    """ISO8601 timestamp -> epoch seconds, or None."""
    if not isinstance(v, str) or not v:
        return None
    try:
        return datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def _tool_uses(rows):
    out = []
    for r in rows:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_use":
                inp = b.get("input")
                out.append((b.get("name") or "",
                            inp if isinstance(inp, dict) else {}))
    return out


def _load_rows(path, tail=4000):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-tail:]
    except Exception:
        return []
    rows = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _subagent_uses(transcript_path, since):
    """Tool calls made by subagents dispatched in this turn.

    Claude Code stores each subagent's transcript at
    <transcript minus .jsonl>/subagents/agent-*.jsonl, NOT in the parent file
    (measured 2026-10-06: 1,371 such files under ~/.claude/projects). Without
    this, a parent that delegates the hook edit -- the normal shape of a large
    countermeasure -- could never satisfy (a)-(c). Only rows timestamped at or
    after the turn's user message count.
    """
    out = []
    try:
        d = os.path.join(os.path.splitext(transcript_path)[0], "subagents")
        if not os.path.isdir(d):
            return out
        files = [os.path.join(d, n) for n in os.listdir(d)
                 if n.endswith(".jsonl")]
        if since is not None:
            files = [f for f in files if os.path.getmtime(f) >= since - 5]
        for f in sorted(files, key=os.path.getmtime)[-50:]:
            rows = _load_rows(f)
            if since is not None:
                rows = [r for r in rows
                        if (_ts(r.get("timestamp")) or since) >= since - 1]
            out.extend(_tool_uses(rows))
    except Exception:
        pass
    return out


def _read_turn_full(transcript_path):
    """Return (user_ask, tool_blob, uses) for the latest turn.

    uses = [(tool_name, input_dict), ...] from the parent transcript plus any
    subagent transcripts written during this turn.

    Windowed to the last 4000 rows, matching the other guards: bounds parsing
    cost on very large transcripts. readlines() still does full I/O.
    """
    rows = _load_rows(transcript_path)
    if not rows:
        return "", "", []

    def _text(r):
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result"
                   for b in c):
                return None
            return next((b.get("text") for b in c
                         if isinstance(b, dict) and b.get("type") == "text"),
                        None)
        return c if isinstance(c, str) else None

    user_idx = [i for i, r in enumerate(rows)
                if r.get("type") == "user" and _text(r)]
    if not user_idx:
        return "", "", []
    start = user_idx[-1]
    ask = _text(rows[start]) or ""

    uses = _tool_uses(rows[start + 1:])
    uses += _subagent_uses(transcript_path, _ts(rows[start].get("timestamp")))
    return ask, _blob(uses), uses


def _blob(uses):
    """The text AUDIT_RE / ADVERSARIAL_RE search: selected input fields."""
    tools = []
    for name, inp in uses:
        for k in ("command", "file_path", "path", "prompt", "query"):
            v = inp.get(k)
            if isinstance(v, str):
                tools.append(v)
        # 2026-10-06: the `model` key was never collected, so a real
        # Agent(model="fable") call could not match ADVERSARIAL_RE -- only the
        # test fixtures (which fake it as a Bash string) could. Serialize it.
        if name in ("Task", "Agent") and isinstance(inp.get("model"), str):
            tools.append(json.dumps({"tool": name, "model": inp["model"]}))
    return "\n".join(tools)


def _read_turn(transcript_path):
    """Backward-compatible (user_ask, tool_blob)."""
    ask, blob, _ = _read_turn_full(transcript_path)
    return ask, blob


def _commands(uses):
    return [inp.get("command") for _, inp in uses
            if isinstance(inp.get("command"), str)]


def _mechanical_checks(uses):
    """Return {'a','b','c','exempt'} -> bool from this turn's tool calls."""
    cmds = _commands(uses)
    a = exempt = False
    for name, inp in uses:
        fp = inp.get("file_path") or inp.get("notebook_path") or ""
        if name in EDIT_TOOLS and isinstance(fp, str):
            if _is_cm_path(fp):
                a = True
            if EXEMPT_FILE_RE.search(fp):
                body = (inp.get("content") or inp.get("new_string") or "")
                for e in (inp.get("edits") or []):
                    if isinstance(e, dict):
                        body += e.get("new_string") or ""
                if EXEMPT_REASON_RE.search(body):
                    exempt = True
    for c in cmds:
        if _shell_writes_cm(c):
            a = True
        if "COUNTERMEASURE_EXEMPT.json" in c and EXEMPT_REASON_RE.search(c):
            exempt = True
    b = any(DEPLOY_RUN_RE.search(seg) and "--dry-run" not in seg
            for c in cmds for seg in _segments(c))
    c_ = any(FIRING_CHECK_RE.search(seg) for c in cmds for seg in _segments(c))
    return {"a": a, "b": b, "c": c_, "exempt": exempt}


REASON = u"""⛔ 再発防止を指示されたターンだが、対策の実効性を一度も測っていない

ユーザーは「再発防止」を求めている。しかしこのターンでは
`audit_countermeasures.py` も `countermeasure_ledger.py` も実行していない。

なぜ止めるか（2026-09-03 にユーザーが名指しした5欠陥・すべて実測値）:
  1本のリポにしか入らない  → 実測: 5フックが 0/44 リポ、2フックはグローバル未導入
  ほとんど発火しない        → 実測: 19フック中18が発火記録ゼロ（動いてるか誰も知らない）
  機械的手法がない          → 実例: 直近の再発防止は「メモ1件＋1リポの .md に追記」だけ
  類似問題を防げない        → 固有名詞で塞ぐと同じクラスの次の事例で素通りする
  実環境で検証していない    → 実例: 自作テスト16/16通過のフックが実測35.9%発火の代物だった

これは初犯ではない。2026-08-14 にも同じ形が記録されている
（deploy_md_date_guard.py の docstring:「present in 8 of 42 repos, wired into
zero hooks and zero CI」）。**少なくとも2回再発したクラス**である。

いま行うこと（claude-governance で実行）:
  1. python scripts/countermeasure_ledger.py     # 台帳を再生成
  2. python scripts/audit_countermeasures.py     # 5欠陥を全数検査（違反があれば exit 1）
  3. 新しいフックを作ったなら index/HOOK_MANIFEST.json に登録してから
     python scripts/deploy_all.py  および  python scripts/deploy_all.py --global
  4. 監査の違反件数を回答に**実出力で**貼る（「対応済み」という自己申告は証拠にならない）

⛔ 検査は「直した版で PASS」ではなく「**当時の欠陥版に当てて FAIL する**」ことを
確認して初めて意味を持つ。直った版で通しても何も証明していない。

⛔ 除外したい場合は index/COUNTERMEASURE_EXEMPT.json に**理由付きで**書く。
理由が空なら除外は無効になる。「まだやっていない」は除外理由ではない。

正典: ~/.claude/CLAUDE.md §14 F2 / claude-governance/index/HOOK_MANIFEST.json
"""


MISSING_ADVERSARIAL = u"""⛔ **独立した攻撃的検証（別モデル）を行っていない**。

「自作テストの合格は証拠にならない」「自分の計画を自分でQCしない」は
ルールに明記されているが、守られたことが一度も検査されていなかった。
その代償は実測済みである——2026-09-11、summary_freshness を
「監査 PASS・違反なし」として出荷したが、致命的な発火漏れが3件あった。
うち1件は **CLAUDE.md §10b（最終更新日の更新）を守るとガードが沈黙する**
というもので、ルール遵守者ほど検査されない構造だった。
後から手動で別モデルに当てたから見つかっただけで、やらなければ
監査は PASS のまま、ガードは飾りのままだった。

いま行うこと（どちらか）:
  1. Task/Agent で **model: claude-fable-5** のサブエージェントを起動し、
     「この対策を壊せ。回避経路を逐語の再現ケースで出せ」と指示する。
     戻ってきた回避経路を **テストケースに逐語で追加**し、
     **当時の欠陥版に当てて FAIL することを確認**する。
  2. 既存の攻撃コーパス（tests/fixtures/*_adversarial_*.md 等）に対して
     今回の対策を実際に走らせ、実出力を貼る。

「攻撃的検証を行いました」と書くだけでは通らない。
本ゲートはツール呼び出しを見ており、文章は見ていない。
"""


MISSING_MECHANICAL = u"""⛔ 対策が「機械的・配布済み・発火確認済み」になっていない

このターンのツール呼び出しから、次が確認できなかった（文章は見ていない）:
{items}

  (a) 実行可能な対策ファイル: hooks/ または scripts/ 配下（templates/hooks/ を含む）の
      .py/.sh/.js/.ps1 をこのターンで作成・編集したか（tests/・test_*・calibrate_* は対象外）
  (b) 配布: python scripts/deploy_all.py（および --global）を実行したか（--dry-run は不可）
  (c) 発火確認: test_*.py / calibrate_*.py / pytest / scripts/verify_hook_firing.py を
      実行したか

散文1リポで終わる対策が、このゲートを素通りしていた（2026-10-06 実測: 監査と
Fable 起動だけで通過でき、DEPLOY_RE は定義されたまま一度も使われていなかった）。

構造的に当てはまらない場合のみ、index/COUNTERMEASURE_EXEMPT.json に
**理由付きで**書けば (a)〜(c) は免除される（理由が空なら無効）。
"""

LABELS = {
    "a": u"(a) 実行可能な対策ファイルの作成・編集",
    "b": u"(b) deploy_all.py による配布",
    "c": u"(c) テスト／較正／発火確認の実行",
    "d": u"(d) audit_countermeasures.py / countermeasure_ledger.py の実行",
    "e": u"(e) 別モデル（Fable 等）による攻撃的検証",
}


def is_countermeasure_request(ask):
    """True when the USER commissioned a countermeasure in this message.

    Topic (ASK_RE) + request (IMPERATIVE_RE), minus a past-tense background
    mention that commissions only a lookup (BACKGROUND_RE without FIX_VERB_RE).
    Compaction summaries are excluded by the caller.
    """
    if not (ASK_RE.search(ask) and IMPERATIVE_RE.search(ask)):
        return False
    if BACKGROUND_RE.search(ask) and not FIX_VERB_RE.search(ask):
        return False
    return True


def _missing(tools, uses):
    """Ordered list of missing proof keys among a..e."""
    m = _mechanical_checks(uses)
    miss = []
    if not m["exempt"]:
        miss += [k for k in ("a", "b", "c") if not m[k]]
    if not AUDIT_RE.search(tools):
        miss.append("d")
    if not ADVERSARIAL_RE.search(tools):
        miss.append("e")
    return miss


def _reason(missing):
    head = (u"⛔ 再発防止ターンの完了条件が未充足: "
            + u" / ".join(LABELS[k] for k in missing) + u"\n\n")
    parts = []
    if any(k in missing for k in ("a", "b", "c")):
        parts.append(MISSING_MECHANICAL.replace(
            u"{items}",
            u"\n".join(u"  ❌ " + LABELS[k] for k in missing if k in "abc")))
    if "d" in missing:
        parts.append(REASON)
    if "e" in missing:
        parts.append(MISSING_ADVERSARIAL)
    return head + u"\n".join(parts)


def main():
    # Defer to a registered repo-local copy, matching the existing convention.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        return

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return

    if ev.get("stop_hook_active"):
        return

    tp = _codex_transcript(ev.get("transcript_path"))
    if not tp:
        return
    ask, tools, uses = _read_turn_full(tp)
    if not ask:
        return

    # A compaction summary is not a request. It QUOTES past requests verbatim,
    # so it matches every pattern below while commissioning nothing.
    # Measured: 39 of 47 matches across 3256 real user messages were summaries
    # (83%). Left in, the gate would have demanded an audit at the start of
    # most resumed sessions -- the fastest possible route to being muted.
    if ("This session is being continued" in ask
            or "ran out of context" in ask):
        return

    # Condition 1: the user asked for a countermeasure, in their own words.
    if not is_countermeasure_request(ask):
        return

    # ...but not when 再発防止 is merely BACKGROUND to a different request.
    # The false positive to avoid: 「前回の再発防止でフックを入れましたが、いまの
    # NASDAQ のベスト戦略の CAGR を教えてください」 -- topic and imperative both
    # present, yet the commissioned work is a lookup.
    #
    # ⚠️ DISTANCE WAS THE WRONG DISCRIMINATOR (measured 2026-09-11).
    # This used to require the imperative within 40 characters of the topic
    # word, reasoning that a real request keeps them in one clause. Its own
    # docstring warned that "a false negative here silently exempts a real
    # countermeasure turn, which is the failure this whole hook exists to
    # prevent" -- and then it did exactly that. Replayed over 1,770 real user
    # messages from 29 transcripts:
    #
    #     ask + imperative present        33 messages
    #     window  40 chars -> fires on     9   (27%)   73% of real asks MISSED
    #     window 200 chars -> fires on    14   (42%)
    #     no window        -> fires on    14   (42%)
    #
    # Cost of removing it entirely: 0.51% -> 0.79% of all user messages. It
    # bought nothing and lost almost everything. The user's real request of
    # 2026-09-11 put 再発防止 in sentence one and the imperative 179 characters
    # later -- the ordinary shape of a real request, not an exception.
    #
    # Worse, the FP it was built for never occurred once in those 1,770
    # messages: it was hypothetical, and it was traded against a measured
    # failure. Of 19 deduped ask+imperative messages, 17 were genuine requests.
    #
    # The real signal is not distance but GRAMMAR: a background mention is
    # PAST TENSE about an already-installed countermeasure, and what it
    # commissions is a LOOKUP. Both must hold to stay silent -- so a message
    # that mentions a past countermeasure and then asks for a FIX still fires.
    # (The check itself lives in is_countermeasure_request() so the
    # calibration script replays exactly the code that runs here.)

    # Condition 2: ALL five proofs must be present in this turn's tool calls.
    #   (a) an executable countermeasure file was written (not prose)
    #   (b) deploy_all.py actually ran (not one repo)
    #   (c) a test / calibration / firing check was executed (it fires)
    #   (d) the audit ran (the five defects were measured, not asserted)
    #   (e) a different model was dispatched to break it (self-testing is not
    #       evidence; see ADVERSARIAL_RE for what this cost when it was missing)
    # (a)-(c) are waived when this turn wrote a non-empty reason into
    # index/COUNTERMEASURE_EXEMPT.json.
    #
    # ⛔ NO HEADLESS EXEMPTION. CLAUDE_HEADLESS_JOB=1 (unattended
    # auto-implementation runs) is deliberately NOT a skip condition here: an
    # unattended run is the one with nobody watching for a prose-only
    # countermeasure, so it must satisfy the same five proofs.
    missing = _missing(tools, uses)
    if not missing:
        return

    _record_fired(ev)

    out = {"decision": "block", "reason": _reason(missing)}
    # ensure_ascii=True + buffer.write: CP932 consoles mangle kanji whose
    # second byte is 0x5C (「表」= 0x95 0x5C) through a text stream, which
    # corrupts the JSON. Learned on md_date_guard.py.
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
