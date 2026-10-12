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
Since 2026-10-06 it also requires that the countermeasure is executable,
deployed and fire-checked -- proofs (a)-(e), see the dated section below.

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

2026-10-06: TWO GAPS, MEASURED (weekly digest C08「再発防止が不十分」)
-------------------------------------------------------------------
Gap 1 -- the trigger missed the real requests. The three verbatim C08 prompts
(reports/CORRECTION_DIGEST_20261005.md #2) were replayed through the trigger:
2 of 3 did NOT fire. 「再発防止対策をしなさい」 and 「…ミスを防ぐべきでは
ないでしょうか？」 carry their request only as 〜なさい / 〜べき, neither of
which IMPERATIVE_RE knew. The third fired only by luck (a ください elsewhere in
the message). Today's own request 「再発防止をすべきだと思います」 also missed.
Fix: IMPERATIVE_RE / FIX_VERB_RE gained なさい, べき, やめて/やめる.
Calibration (tests/calibrate_countermeasure_gate.py, 669 deduped real human
prompts from the last 30 days, compaction summaries excluded):

    old trigger fires on 23/669 (3.44%)
    new trigger fires on 27/669 (4.04%)   +4 newly triggered, 0 lost
    newly triggered judged by hand: 4 TP / 0 FP (all are live 再発防止 asks:
    「〜しなさい」「〜べきではないでしょうか」「〜しておくべきである」
    「〜修正する必要があります」)

Gap 2 -- the gate checked the wrong things. It required only (d) the audit and
(e) an adversarial model. `DEPLOY_RE` was defined and NEVER USED. So a turn
that ran the audit, launched Fable, and shipped a paragraph in one repo's
markdown passed -- precisely 欠陥③ (散文で終わる) and 欠陥① (1リポ). The
invariant is now five proofs, all read from TOOL CALLS of this turn
(including subagent transcripts under <session>/subagents/, because the
normal shape of a large countermeasure is delegated):

    (a) an executable countermeasure (.py/.sh/.js/.ps1 under hooks/ or
        scripts/, templates/hooks/ included; tests/, test_*, calibrate_* do
        not count) was written -- Write/Edit, or a shell redirect/cp/tee
    (b) deploy_all.py was actually run (--dry-run does not count)
    (c) a test / calibration / firing check was EXECUTED (test_*.py,
        calibrate_*.py, pytest, verify_hook_firing.py; `cat` does not count)
    (d) audit_countermeasures.py or countermeasure_ledger.py ran
    (e) a different model was dispatched to attack it

(a)-(c) are waived only when this turn wrote a non-empty "reason" into
index/COUNTERMEASURE_EXEMPT.json. The block message names exactly which of
(a)-(e) are missing.

Gap 2b, found while fixing gap 2: `_read_turn` never collected the `model`
key of a Task/Agent call, so a REAL `Agent(model="fable")` could not satisfy
(e) -- only the test fixtures, which fake the call as a Bash string, could.
Verified red-green: that case BLOCKS on the pre-2026-10-06 gate.

STOP replay on the 27 real triggered turns (same 30 days): old gate would have
let 5 pass, new lets 7 pass (4 newly pass because subagent work and the real
`model` key are now seen; 2 that passed old are now blocked for missing
(a)-(c)). Missing under new: a=11, b=18, c=11, d=13, e=13 -- (b) deploy is the
most-skipped proof. Caveat: a countermeasure finished across several turns is
nagged once per answer (stop_hook_active), not blocked forever.

ADVERSARIAL 2026-10-06 (Fable attack on the version above)
----------------------------------------------------------
Fable ran 65 verbatim cases through the real hook (+1 long-turn case added
afterwards). Replayed with the fixture against the pre-hardening copy:
60 of 66 mismatched the correct verdict; after this hardening 65/66 match and
the one left is an accepted residual (below). Every case is a verbatim test:
tests/fixtures/countermeasure_gate_adversarial_20261006.json, replayed by
tests/test_countermeasure_gate.py (--adversarial-only [--hook PATH] replays it
against any copy -- that is how the pre-hardening FAIL count was measured).
Classes and fixes:

  trigger misses (15)  「二度とやらないで」「再発させないように仕組みを」「仕組みで
      防いで」「フックで止めて」「ルール化して」「同じことが起きないように」「もう
      繰り返さないで」「再発防止をお願い/が必要です/策は？/を頼みます/を実装する
      こと/を忘れずに」「…恒久対策。」 and English "never happens again".
      -> ASK_RE / IMPERATIVE_RE widened; SELF_REQUEST_RE for 「再発防止策は？」
      and the bare noun sentence 「恒久対策。」.
  false triggers (8)   再発防止 as the NAME of a thing (〜ゲート/ガード/系フック/
      レポート/策の一覧表), questions/debugging/disabling it, quoted mail.
      -> _neutralize(): NAME uses are masked unless an artifact noun is
      followed by a build verb (「再発防止フックを作って」 still fires); quoted
      spans are masked when the message says it quotes/reads/translates.
  (b)(c)(d) substring matching (17)  echo/grep/cat/ls/Read, commented lines,
      python -c "print(...)", --help/-h/--version/--collect-only/--dry_run/-n,
      pip install pytest, deploy --only <bogus> (argparse rejects it), an
      Agent PROMPT naming the command, and an unrelated test suite.
      -> _invocations(): each segment must START with a python interpreter (or
      pytest) whose script/module is the named one; no-op flags and unknown
      deploy_all.py options void it; tool calls of Task/Agent are never read
      as commands; (c) must share a distinctive word with this turn's edited
      countermeasure (article_quality_check <-> test_article_quality_gate).
  (e) substring matching (5)  'subagent_type'/'fable' in any text, an old
      fixture listed, a fable agent asked to summarise, a sonnet agent whose
      prompt mentions fable. -> _adversarial_dispatched(): a real Task/Agent
      call whose model (explicit, or from the agent definition) is not Opus /
      inherit AND whose prompt instructs an attack (壊せ/攻撃/回避/反証/突破/
      break/attack/bypass/adversarial...). Writing a fixture no longer counts.
  (a) weak edits (5)  comment-only edits/appends and a .py that is one comment
      line (no code line), an edit to ONE repo's deployed .claude/hooks copy,
      an unrelated app's scripts/build.js. -> code-line check; deployed copies
      excluded; outside templates/hooks/ and claude-governance/{hooks,scripts}
      only guard-named files (guard/gate/check/lint/audit/verify...) count.
  exemption (5)  reason 'x'/'TODO'/'まだやっていない', echo of the JSON, a copy in
      a temp dir. -> reason >=15 chars and no placeholder words, written by
      Write/Edit to <repo>/index/COUNTERMEASURE_EXEMPT.json outside temp dirs.
  turn boundary (4)  a Skill injection, a teammate agent-message, another Stop
      hook's feedback row, or >4000 rows of tool calls hid the real prompt;
      subagent rows timestamped before the turn counted. -> the turn starts at
      the last REAL prompt (promptSource != system, delegation_guard
      _is_prompt; synthetic transcripts fall back to isMeta/prefix filters);
      the full file is re-read when the tail window holds no prompt.

Accepted residuals (documented, not chased):
  * stop_hook_active: the second stop after one block passes (loop safety).
  * (a) can still be met by a meaningless CODE edit to a real hook file
    (e.g. `x = 1`); the gate checks that code changed, not that it matters.
  * (c) a whole-suite pytest run (no .py positional) counts without checking
    that the suite contains the new guard's test.
  * (e) the attack instruction is a keyword in the prompt; a prompt that says
    "attack" but asks for nothing adversarial still counts.

Calibration after hardening (669-673 deduped real prompts, last 30 days):
  trigger: pre-hardening 28/672 (4.17%) -> 28/672 (4.17%), +0 / -0;
           vs committed HEAD 24/673 (3.57%) -> 28/673 (4.16%), +4 (the C08
           fixes above). The 15 new phrasings and 8 name/quote exclusions
           changed no real fire in 30 days -- they cover forms the corpus has
           not yet produced. One candidate pattern (同じこと…起きる) fired on a
           pasted description during calibration and was narrowed to the
           negated form before shipping.
  STOP replay on the 28 triggered real turns: pre-hardening passes 7, now 4.
           All 3 that now block were checked by hand: no different-model
           Agent call existed (2 turns, (e) had passed on a substring) and the
           in-progress turn that had only grep'ed deploy_all/audit (b)(d).

NO HEADLESS EXEMPTION: CLAUDE_HEADLESS_JOB=1 (unattended auto-implementation
runs) is deliberately not a skip condition. An unattended run is the one with
nobody watching for a prose-only countermeasure.

LOOP SAFETY: `stop_hook_active` -> return, so at most one block per answer.
FAIL-OPEN: any exception -> exit 0.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import shlex
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
STATE_DIR = (os.environ.get("COUNTERMEASURE_GATE_STATE_DIR")   # tests
             or os.path.join(os.path.expanduser("~"), ".claude", "state",
                             "countermeasure_gate"))


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
    u"(?:再発防止|恒久対策|再発を?防|再発(?:させ|し)な|二度と(?:起こ|同じ|繰り返)"
    u"|同じ(?:ミス|問題|失敗)を?(?:繰り返|起こ)さな"
    u"|同様の(?:問題|ミス|失敗)[^。\n]{0,10}(?:防|起こ)"
    # ADVERSARIAL 2026-10-06 (Fable, 15 trigger misses). Real phrasings:
    u"|二度と[^。\n]{0,15}(?:ないで|ないよう|ません|な(?:い|く)|させな)"
    u"|同じ(?:ミス|問題|失敗|こと|過ち|間違い|事故|誤り)[がをはも]?[^。\n]{0,8}"
    # negated only: 「同じことが主セッションでも起きる」 (a description, found
    # in calibration) must not match; 「同じことが起きないように」 must.
    u"(?:繰り返さ|起こさ|起き|起こら|再発さ?せ|再発し|し|やら)な(?:い|く)"
    u"|もう[^。\n]{0,10}繰り返さ(?:ない|ず)"
    u"|仕組み(?:で|化して|によって|として)[^。\n]{0,12}(?:防|止め|ブロック|検出)"
    u"|フック(?:で|を使って)[^。\n]{0,10}(?:止め|防|ブロック|拒否|弾)"
    u"|機械的に[^。\n]{0,8}(?:止め|防|ブロック|拒否|検出|弾)"
    u"|ルール化して"
    u"|never (?:happens?|occurs?) again|(?:happen|occur)s? again"
    u"|prevent(?:ing)? (?:this |it |that )?(?:from )?(?:happening|recurr)"
    u"|prevent recurrence|recurrence prevention"
    u"|don'?t (?:let|make) (?:this|it) happen again)",
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
    u"|終わったこと|限定すぎ|ほとんど発火"
    # ADVERSARIAL 2026-10-06 (Fable): 「再発防止をお願い。」「〜を頼みます」
    # 「〜が必要です」「〜を実装すること」「〜を忘れずに」「フックで止めて」
    # 「もう繰り返さないで。」 all commission the work without any form above.
    u"|お願い|頼(?:み|む|ん)|必要(?:です|だ|がある|があります|。|$)"
    u"|すること|忘れずに|止めて|塞いで|入れて|追加して|実装して|ルール化して"
    u"|ないで(?:ね|よ|。|！|!|$)|ないように(?:して|。|！|!|$)"
    u"|(?i:\\b(?:please|add|make|build|implement|ensure|set up|put)\\b)")

# ADVERSARIAL 2026-10-06 (Fable): requests that carry topic AND request in one
# breath, with no separate imperative: 「再発防止策は？」「…ですね。恒久対策。」
SELF_REQUEST_RE = re.compile(
    u"(?:再発防止|恒久対策)(?:策|案)?(?:は|を|も)?(?:どう(?:する|します)?)?"
    u"(?:ですか|でしょうか)?\\s*[？?]"
    u"|(?:^|[。！!\\n、])\\s*(?:再発防止|恒久対策)(?:策)?(?:を|も)?\\s*(?:[。！!]|$)")

# 再発防止 used as the NAME of a thing, not as a request: 「再発防止ゲートは何回
# 発火？」「再発防止系フックを無効化して」「再発防止レポートを要約して」「再発防止策
# の一覧表を作って」. Such mentions are neutralized before the trigger runs --
# unless an ARTIFACT noun (gate/guard/hook/rule...) is directly followed by a
# BUILD verb in the same sentence (「再発防止フックを作って」「再発防止ゲートが甘い
# ので直して」), which does commission countermeasure work.
_NAME_ARTIFACT = u"ゲート|ガード|フック|ルール|スクリプト|仕組み|チェッカー|チェック|機能|gate|guard|hook"
_NAME_DOC = (u"レポート|報告書?|一覧表?|リスト|表|台帳|監査結果|監査|章|ログ|件数|資料"
             u"|テスト|発火率?|まとめ|履歴|メモ|記事|ドキュメント|report")
NAMED_TOPIC_RE = re.compile(
    u"(?:再発防止|恒久対策)(?:策の|策|系の?|用の?|の)?"
    u"(?:(?P<art>" + _NAME_ARTIFACT + u")|(?P<doc>" + _NAME_DOC + u"))",
    re.IGNORECASE)
BUILD_VERB_RE = re.compile(
    u"作っ|作成|作る|追加|導入|実装|強化|改善|直し|直す|直せ|修正|入れ|厳し|塞|拡張"
    u"|増や|設け|仕込|組み込")

# Quoted material is not the user's own request: 「以下はメール引用です。『恒久
# 対策を講じるべき』。英訳して」. Quoted spans are dropped only when the message
# says it is quoting / reading / translating something.
QUOTE_CTX_RE = re.compile(
    u"引用|転送|英訳|和訳|翻訳|要約|読んで|読み|章|メール|文面|抜粋|原文|quote", re.I)
QUOTED_SPAN_RE = re.compile(u"「[^」]*」|『[^』]*』|“[^”]*”")


def _neutralize(ask):
    """The ask with quoted material and NAME-uses of 再発防止 removed."""
    t = ask or ""
    if QUOTE_CTX_RE.search(t):
        t = QUOTED_SPAN_RE.sub(u"〔引用〕", t)
        t = re.sub(u"(?m)^\\s*>.*$", u"", t)

    def repl(m):
        if m.group("art"):
            tail = re.split(u"[。！!？?\\n]", m.string[m.end():m.end() + 24])[0]
            if BUILD_VERB_RE.search(tail):
                return m.group(0)
        return u"〔名称〕"
    return NAMED_TOPIC_RE.sub(repl, t)

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
# dispatched to break the thing. Since ADVERSARIAL 2026-10-06 only a real
# Task/Agent call on a non-Opus model with an attack instruction counts
# (_adversarial_dispatched); a written fixture no longer does. What does NOT count is
# saying the words -- this matches TOOL CALLS in the transcript, not prose.
# ADVERSARIAL 2026-10-06 (Fable): the old regex matched the bare word
# 'subagent_type' / 'fable' anywhere in a command or prompt (`echo
# subagent_type`, an Agent asked to summarise README, `ls` of an old fixture).
# (e) now needs a real Task/Agent tool call whose MODEL differs from the Opus
# parent AND whose prompt instructs it to attack. ADVERSARIAL_RE is kept as the
# old name only for the calibration script's old/new replay.
ADVERSARIAL_RE = re.compile(
    r"claude-fable|model[\"'\s:=]+fable|subagent_type"
    r"|adversarial\w*\.md|_adversarial_|攻撃コーパス|attack_corpus")
ATTACK_INSTR_RE = re.compile(
    u"壊せ|壊して|壊す|攻撃|回避|反証|突破|すり抜|穴を|抜け道|迂回"
    u"|break|attack|bypass|adversar|evade|evasion|red[- ]?team|circumvent",
    re.IGNORECASE)
AGENT_TOOLS = ("Task", "Agent")


def _agent_model(inp):
    """The model a Task/Agent call runs on, as far as the call says.
    An explicit `model` wins; otherwise the subagent definition's frontmatter
    (~/.claude/agents/<type>.md or ./.claude/agents/<type>.md); codex agents
    are GPT. '' = inherits the parent (Opus)."""
    m = inp.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip().lower()
    st = inp.get("subagent_type")
    if not isinstance(st, str) or not st:
        return ""
    if "codex" in st.lower():
        return "codex"
    name = st.split(":")[-1]
    for base in (os.path.expanduser("~"),
                 os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()):
        f = os.path.join(base, ".claude", "agents", name + ".md")
        try:
            with io.open(f, encoding="utf-8", errors="replace") as fh:
                head = fh.read(2000)
            mm = re.search(r"(?m)^model:\s*['\"]?([\w.\-\[\]]+)", head)
            if mm:
                return mm.group(1).lower()
        except Exception:
            continue
    return ""


def _adversarial_dispatched(uses):
    for name, inp in uses:
        if name not in AGENT_TOOLS:
            continue
        model = _agent_model(inp)
        if not model or "opus" in model or model == "inherit":
            continue
        text = " ".join(v for k in ("prompt", "description")
                        for v in [inp.get(k)] if isinstance(v, str))
        if ATTACK_INSTR_RE.search(text):
            return True
    return False

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
# ADVERSARIAL 2026-10-06 (Fable): an edit to ONE repo's deployed copy
# (<repo>/.claude/hooks/x.py, ~/.claude/hooks/x.py) is overwritten by the next
# deploy and is 欠陥① by construction; an unrelated app's scripts/build.js is
# not a guard at all. A countermeasure is a canonical template
# (templates/hooks/), anything under claude-governance's hooks/ or scripts/, or
# a guard-named file (guard/gate/check/lint/audit/verify/validate) elsewhere.
DEPLOYED_COPY_RE = re.compile(r"(?:^|[/\\])\.claude[/\\]hooks[/\\]", re.I)
CANONICAL_RE = re.compile(
    r"(?:^|[/\\])templates[/\\]hooks[/\\]|claude-governance[/\\](?:scripts|hooks)[/\\]",
    re.IGNORECASE)
GUARD_NAME_RE = re.compile(
    r"(?:guard|gate|check|lint|audit|verify|validat|enforce|block)[^/\\]*$", re.I)
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
# Shell verbs that write the file named last on the segment.
SHELL_WRITE_VERB_RE = re.compile(
    r"^\s*(?:sudo\s+)?(?:tee|cp|mv|install|sed\s+-i\S*|perl\s+-[a-z]*i\S*"
    r"|Copy-Item|Move-Item|Set-Content|Out-File|Add-Content)\b", re.IGNORECASE)
SHELL_REDIRECT_RE = re.compile(r">{1,2}\s*['\"]?([^\s'\";&|<>]+)")
PATH_TOKEN_RE = re.compile(r"[^\s'\";&|<>()]+\.(?:py|sh|js|ps1)\b", re.IGNORECASE)
# A line that is only a comment / blank / docstring delimiter changes nothing
# that runs (Fable: `echo '# note' >> scripts/x.py`, Edit '# x' -> '# touched',
# Write of a .py that is one comment line).
_CODE_LINE_RE = re.compile(r"^\s*(?:#|//|<#|#>|\"\"\"|\x27\x27\x27|$)")

# Python invocations ------------------------------------------------------
# (b)(c)(d) used to be substring regexes over the command text, so `echo
# python scripts/deploy_all.py`, `grep "...deploy_all.py" README`, a commented
# line, `python -c "print('...deploy_all.py')"`, `--help`, `pytest --version`,
# `pip install pytest` all counted (Fable 2026-10-06, 13 cases). Now the
# command is tokenised per segment and must START with a python interpreter
# (or pytest) whose script / module is the named one.
SEGMENT_SPLIT_RE = re.compile(r"\n|;|&&|\|\||(?<![|>])\|(?!\|)")
_INTERP_RE = re.compile(
    r"^(?:.*/)?(?:python(?:3(?:\.\d+)?)?w?|py)(?:\.exe)?$", re.IGNORECASE)
_WRAPPERS = ("env", "sudo", "time", "nohup", "exec", "command", "&", "call")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Options that make a run do nothing real (print help / version / plan only).
NOOP_ARGS = ("--help", "-h", "--version", "-V", "--collect-only", "--co",
             "--dry-run", "--dry_run", "--dryrun", "--setup-plan",
             "--fixtures", "--markers")
# deploy_all.py's argparse accepts exactly these (scripts/deploy_all.py
# main()); anything else -- `--only no_such_hook`, `-n` -- exits 2 unrun.
DEPLOY_OK_ARGS = ("--global", "--codex", "--commit", "--root")
EXEMPT_PATH_RE = re.compile(r"(?:^|[/\\])index[/\\]COUNTERMEASURE_EXEMPT\.json$",
                            re.IGNORECASE)
TEMP_DIR_RE = re.compile(r"(?:^|[/\\])(?:tmp|temp|scratchpad)[/\\]", re.I)
REASON_STR_RE = re.compile(r"\"reason\"\s*:\s*\"((?:[^\"\\]|\\.)*)\"")
# A reason that only says "not done yet" is not a reason (docstring/CLAUDE.md:
# 「まだやっていない」は理由ではない). Fable: 'x', 'TODO', 'まだやっていない'.
PLACEHOLDER_REASON_RE = re.compile(
    u"todo|tbd|fixme|later|n/a|まだ|未実施|未対応|未着手|あとで|後で|後日|追って|検討中",
    re.IGNORECASE)
MIN_REASON_CHARS = 15


def _segments(cmd):
    return [s for s in SEGMENT_SPLIT_RE.split(cmd or "") if s.strip()]


def _tokens(seg):
    t = seg.replace("\\", "/")
    try:
        return shlex.split(t)
    except ValueError:
        return t.split()


_REDIR_RE = re.compile(r"^(?:\d*|&)(?:>>?|<<?)(?:&\d+)?(.*)$")


def _strip_redirects(toks):
    """Drop shell redirections (`> f`, `2>&1`, `>>f`, `<<EOF`) so they are not
    read as script names or arguments (calibration: `python deploy_all.py
    --commit > "$TMP/dep.txt" 2>&1` is a real deploy)."""
    out, skip = [], False
    for t in toks:
        if skip:
            skip = False
            continue
        m = _REDIR_RE.match(t)
        if m:
            skip = not m.group(1) and not re.search(r"&\d+$", t)
            continue
        out.append(t)
    return out


def _invocations(cmd):
    """[(kind, target, args)] for segments that actually execute Python.
    kind 'script' -> target = script basename; 'module' -> module name."""
    out = []
    for seg in _segments(cmd):
        s = seg.strip()
        if s.startswith("#"):
            continue
        s = re.sub(r"^(?:if\s*\(\$\?\)\s*\{|\(|\{)\s*", "", s)
        toks = [t for t in _strip_redirects(_tokens(s))
                if t not in ("}", ")", "{")]   # PowerShell `if ($?) { ... }`
        while toks and (toks[0] in _WRAPPERS or _ENV_ASSIGN_RE.match(toks[0])
                        or toks[0] == "timeout"):
            toks = toks[2:] if toks[0] == "timeout" else toks[1:]
        if not toks:
            continue
        head = toks[0].strip("'\"")
        base = head.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if base in ("pytest", "py.test", "pytest.exe"):
            out.append(("module", "pytest", toks[1:]))
            continue
        if base == "uv" and toks[1:2] == ["run"]:
            toks = toks[2:]
            if not toks:
                continue
            head = toks[0]
            base = head.rsplit("/", 1)[-1].lower()
            if base in ("pytest", "py.test"):
                out.append(("module", "pytest", toks[1:]))
                continue
        if not _INTERP_RE.match(head):
            continue
        i = 1
        while i < len(toks) and toks[i].startswith("-"):
            o = toks[i]
            if o == "-c" or o.startswith("-c"):
                i = None
                break
            if o == "-m":
                if i + 1 < len(toks):
                    out.append(("module", toks[i + 1], toks[i + 2:]))
                i = None
                break
            i += 2 if o in ("-X", "-W") else 1
        if i is None or i >= len(toks):
            continue
        script = toks[i].strip("'\"").rsplit("/", 1)[-1]
        out.append(("script", script, toks[i + 1:]))
    return out


def _real_runs(uses):
    """All python invocations from Bash/PowerShell tool calls (never prompts)."""
    out = []
    for name, inp in uses:
        c = inp.get("command")
        if isinstance(c, str) and name not in AGENT_TOOLS:
            out.extend(_invocations(c))
    return out


def _noop(args, extra=()):
    return any(a.split("=", 1)[0] in NOOP_ARGS + tuple(extra) for a in args)


def _is_cm_path(p):
    p = (p or "").strip().strip("'\"")
    if not COUNTERMEASURE_PATH_RE.search(p) or NOT_COUNTERMEASURE_RE.search(p):
        return False
    if DEPLOYED_COPY_RE.search(p) and not CANONICAL_RE.search(p):
        return False
    return bool(CANONICAL_RE.search(p) or GUARD_NAME_RE.search(p))


def _has_code(text):
    return any(not _CODE_LINE_RE.match(ln) for ln in (text or "").splitlines())


def _edit_body(inp):
    body = inp.get("content") or inp.get("new_string") or inp.get("new_source") or ""
    for e in (inp.get("edits") or []):
        if isinstance(e, dict):
            body += "\n" + (e.get("new_string") or "")
    return body if isinstance(body, str) else ""


_GENERIC_WORDS = {"guard", "gate", "check", "checks", "hook", "hooks", "test",
                  "tests", "calibrate", "verify", "audit", "lint", "script",
                  "scripts", "main", "utils", "util", "common", "realmsgs"}


def _stem(p):
    b = re.split(r"[/\\]", (p or "").strip().strip("'\""))[-1]
    return b.rsplit(".", 1)[0].lower()


def _shell_writes_cm(cmd):
    """Path of an executable countermeasure this shell command writes with
    real code, else None. Redirect target, or the LAST path token of a writing
    verb (cp src dst: only dst is written)."""
    for seg in _segments(cmd):
        for m in SHELL_REDIRECT_RE.finditer(seg):
            if _is_cm_path(m.group(1)):
                payload = re.sub(r"^\s*(?:echo|printf|Write-Output)\s+", "",
                                 seg[:m.start()]).strip().strip("'\"")
                if _has_code(payload):
                    return m.group(1)
        if SHELL_WRITE_VERB_RE.search(seg):
            toks = PATH_TOKEN_RE.findall(seg)
            if toks and _is_cm_path(toks[-1]):
                return toks[-1]
    return None


def _valid_reason(raw):
    try:
        r = json.loads('"%s"' % raw)
    except Exception:
        r = raw
    r = (r or "").strip()
    return len(r) >= MIN_REASON_CHARS and not PLACEHOLDER_REASON_RE.search(r)


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


def _subagent_uses(transcript_path, since, until=None):
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
            if until is not None:   # replay of a past turn (calibration)
                rows = [r for r in rows
                        if (_ts(r.get("timestamp")) or until) <= until + 1]
            out.extend(_tool_uses(rows))
    except Exception:
        pass
    return out


NON_PROMPT_PREFIX = (
    "<task-notification", "<local-command", "<command-", "Caveat:",
    "<system-reminder", "<bash-", "<user-prompt-submit-hook",
    "[Request interrupted", "Base directory for this skill",
    "Another Claude session sent a message", "<agent-message",
    "<teammate-message", "Stop hook feedback:", "PreToolUse:", "PostToolUse:",
    "This session is being continued")


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

    # ADVERSARIAL 2026-10-06 (Fable): ANY user row with text used to start a
    # new turn -- so a Skill injection (isMeta, "Base directory for this
    # skill"), a teammate's agent-message, or another Stop hook's feedback row
    # became "the ask", and invoking the mandatory verification skill silenced
    # this gate. The turn starts at the last REAL human prompt
    # (delegation_guard._is_prompt): real transcripts mark it with
    # promptSource != "system"; synthetic ones without that key fall back to
    # isMeta / prefix filtering.
    strict = any(r.get("type") == "user" and "promptSource" in r for r in rows)

    def _is_prompt(r):
        if r.get("type") != "user" or r.get("isMeta") or r.get("isSidechain"):
            return False
        if strict and ("promptSource" not in r
                       or r.get("promptSource") == "system"):
            return False
        t = _text(r)
        return bool(t and t.strip()) and not t.lstrip().startswith(
            NON_PROMPT_PREFIX)

    user_idx = [i for i, r in enumerate(rows) if _is_prompt(r)]
    if not user_idx and len(rows) >= 4000:
        # A long countermeasure turn can push its own prompt out of the tail
        # window; re-read the whole file rather than conclude "no ask".
        rows = _load_rows(transcript_path, tail=10 ** 9)
        strict = any(r.get("type") == "user" and "promptSource" in r
                     for r in rows)
        user_idx = [i for i, r in enumerate(rows) if _is_prompt(r)]
    if not user_idx:
        return "", "", []
    start = user_idx[-1]
    ask = _text(rows[start]) or ""

    uses = _tool_uses(rows[start + 1:])
    uses += _subagent_uses(transcript_path, _ts(rows[start].get("timestamp")))
    # C08 2026-10-12: context for the continuation / self-claim / schedule /
    # sibling-copy checks, kept on the function so the 3-tuple API is intact.
    _read_turn_full.ctx = {
        "prior_asks": [_text(rows[i]) or "" for i in user_idx[-7:-1]][::-1],
        "prior_idx": user_idx[-7:-1][::-1],
        "rows": rows,
        "tp": transcript_path,
        "cwd": rows[start].get("cwd"),
        "final_text": _final_text(rows[start + 1:]),
        "turn_text": _text_after_last_sched(rows[start + 1:]),
        "start_ts": _ts(rows[start].get("timestamp")),
    }
    return ask, _blob(uses), uses


_read_turn_full.ctx = {}


def _final_text(rows, every=False):
    """The last assistant text of the turn (what the user reads as the answer);
    every=True: all assistant texts of the turn, joined (S accepts a first-firing
    plan stated in any message, e.g. the answer before a later 補足)."""
    allt = []
    for r in reversed(rows):
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        tx = [b.get("text") for b in ((r.get("message") or {}).get("content") or [])
              if isinstance(b, dict) and b.get("type") == "text"
              and isinstance(b.get("text"), str) and b.get("text").strip()]
        if tx and not every:
            return "\n".join(tx)
        allt[:0] = tx
    return "\n".join(allt)


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
    """Return {'a','b','c','d','e','exempt'} -> bool from this turn's tool calls."""
    stems = set()
    exempt = False
    for name, inp in uses:
        fp = inp.get("file_path") or inp.get("notebook_path") or ""
        if name in EDIT_TOOLS and isinstance(fp, str):
            body = _edit_body(inp)
            if _is_cm_path(fp) and _has_code(body):
                stems.add(_stem(fp))
            if EXEMPT_PATH_RE.search(fp) and not TEMP_DIR_RE.search(fp):
                if any(_valid_reason(m.group(1))
                       for m in REASON_STR_RE.finditer(body)):
                    exempt = True
    for name, inp in uses:
        c = inp.get("command")
        if isinstance(c, str) and name not in AGENT_TOOLS:
            w = _shell_writes_cm(c)
            if w:
                stems.add(_stem(w))
    runs = _real_runs(uses)

    def deploy_ok(args):
        if _noop(args, ("-n",)):
            return False
        rest = list(args)
        while rest:
            a = rest.pop(0)
            if a == "--root":
                rest = rest[1:]
            elif a.split("=", 1)[0] not in DEPLOY_OK_ARGS and a.startswith("-"):
                return False
            elif not a.startswith("-") and not re.match(r"^\d?>|^&?>", a):
                return False
        return True
    b = any(k == "script" and t.lower() == "deploy_all.py" and deploy_ok(a)
            for k, t, a in runs)

    # (c) a test / calibration / firing check of THIS turn's countermeasure.
    # Fable: running an unrelated suite (the gate's own tests while a new
    # guard was built) is not evidence the new guard fires.
    # Related = shares a distinctive word with an edited countermeasure's
    # name (article_quality_check <-> test_article_quality_gate), generic
    # words (guard/gate/check/hook/test...) excluded. Calibration showed exact
    # stem matching rejected real, related test runs.
    stem_words = set()
    for st in stems:
        stem_words |= {w for w in re.split(r"[^a-z0-9]+", st)
                       if len(w) >= 4 and w not in _GENERIC_WORDS}

    def related(text):
        text = text.lower()
        if not stems:
            return True
        if any(st and st in text for st in stems):
            return True
        return bool(stem_words & set(re.split(r"[^a-z0-9]+", text)))
    c_ = False
    for k, t, a in runs:
        tl = t.lower()
        if k == "script" and re.match(r"^(?:test_\w+|calibrate_\w+)\.py$", tl):
            if not _noop(a, ("-n",)) and related(tl):
                c_ = True
        elif k == "script" and tl == "verify_hook_firing.py":
            if not _noop(a, ("-n",)) and related(" ".join(a)):
                c_ = True
        elif k == "module" and t == "pytest":
            pos = [x for x in a if not x.startswith("-")]
            # a positional naming the new guard's test, or a whole-suite run
            # (no positional / a tests directory) -- residual: the suite is
            # not checked to CONTAIN the new guard's test.
            whole = (not pos) or all(not x.lower().endswith(".py") for x in pos)
            if not _noop(a) and (whole or related(" ".join(pos))):
                c_ = True
        elif k == "module" and t == "unittest":
            if not _noop(a) and related(" ".join(a)):
                c_ = True
    d = any(k == "script" and t.lower() in ("audit_countermeasures.py",
                                            "countermeasure_ledger.py")
            and not _noop(a) for k, t, a in runs)
    e = _adversarial_dispatched(uses)
    return {"a": bool(stems), "b": b, "c": c_, "d": d, "e": e,
            "exempt": exempt}


# =========================================================================
# C08 REDESIGN 2026-10-12 (correction digest: 撤回・再設計, 3 recurrences)
# -------------------------------------------------------------------------
# Measured on the 3 real recurrences (index/correction_history.jsonl) by
# replaying the turn that shipped each defective countermeasure through the
# gate as of beab694:
#   A 2026-10-02 06:47 「4時半頃/9時半ごろ…再発防止が必要です」 (RemoteTrigger
#     edits): triggered, blocked once for (e), then passed -- (c) was met by
#     test_routine_data.py and a manual `RemoteTrigger run`. Neither exercises
#     the SCHEDULED firing (UTC date, 5h usage window); the job broke at its
#     next 4:20 run (complaint 10-07 00:37).
#   B 2026-10-07 10:30 「すすめて」 (evidence_search.py fixed in the template,
#     cp'd to 3 repos; youtube-to-presentation kept an old copy): NOT
#     triggered -- the ask is a continuation, the countermeasure was named two
#     prompts earlier. No check anywhere compares same-name copies in other
#     repos (scope_coverage_guard covers ID-named DOCUMENT families only).
#   C 2026-10-09 08:54 「一般預りと伝えたはず」 (assistant chose 再発防止 itself,
#     saved a memory file, wrote 「再発防止は、記憶への保存までは済んでいます」):
#     NOT triggered -- the user never said 再発防止, so (e) was never asked.
# CLASS (one sentence): the gate keyed on the wording of the CURRENT user
# prompt and on in-turn evidence only, so countermeasures commissioned by
# context (continuations, the assistant's own decision) and countermeasures
# whose real firing / real scope lies outside the turn (schedules, copies in
# other repos) were never held to the proofs.
# INVARIANTS added:
#   T2  a continuation prompt (すすめて/実行して/OK...) inherits the request
#       status of the last substantive prompt (<= 3 back).
#   T3  the turn's FINAL answer claims a countermeasure is (partly) in place
#       (「再発防止は…済んでいます」「再発しないよう…追加しました」) -> proofs (a)-(e).
#   S   a schedule was created/changed (RemoteTrigger create/update,
#       CronCreate, schtasks /create|/change, Register/Set-ScheduledTask,
#       crontab, a workflow `cron:`) -> the final answer must name the first
#       scheduled firing and say it will be / was checked. A manual run does
#       not exercise the schedule.
#   X   a code file was edited in repo R and an equivalent copy (same
#       distinctive basename, >= 30% shared lines, content differs) exists in
#       another repo under the same parent, not written during the turn and
#       not named in the final answer -> block with the list.
# S and X apply to every turn (B and A were not phrased as 再発防止); T2/T3
# only widen when (a)-(e) are demanded.
# =========================================================================
CONTINUATION_RE = re.compile(
    u"^\\s*(?:[①-⑳\\d]+\\s*(?:から|を)?\\s*)?"
    u"(?:すすめて|進めて|実行して|続けて|つづけて|続行|やって|お願いします|おねがい"
    u"|はい|ok|OK|オーケー|了解|それで|どうぞ|go|continue|proceed|yes)"
    u"(?:ください|下さい|ね|よ)?\\s*[。！!.]?\\s*$", re.IGNORECASE)
# Fable 2026-10-12: a short status check / nudge between a request and its
# continuation (「すすめてる？」「どうなった？」) must not break the chain.
NUDGE_RE = re.compile(
    u"[？?]\\s*$|どう(?:なっ|です|でしょ)|まだ|進捗|終わ|状況|すすめ|進め|続き", re.I)


# Fable 2026-10-12 (2): a short approval or choice 「はい」「いいよ」「承認」
# 「全部やって」「B案で」「push して」 continues the same request.
APPROVAL_RE = re.compile(
    u"はい|いいよ|いいです|良いです|承認|了解|ok|おk|全部|すべて|全て|案で|でお願い"
    u"|で進め|でいい|push|プッシュ|やって|進めて|すすめて|それで|お願い|頼む|どうぞ"
    u"|マージ|merge|go", re.I)


def _is_continuation(ask):
    a = (ask or "").strip()
    if CONTINUATION_RE.match(a[:40]):
        return True
    return (len(a) <= 20
            and bool(NUDGE_RE.search(a) or APPROVAL_RE.search(a))
            and not is_countermeasure_request(a))


def _commission_origin(ask, prior_asks):
    """0 = this prompt asked (T1); k >= 1 = inherited from prior_asks[k-1]
    through a chain of continuations (T2); None = not commissioned."""
    if is_countermeasure_request(ask):
        return 0
    if not _is_continuation(ask):
        return None
    for k, p in enumerate(prior_asks or [], 1):
        if _is_continuation(p):
            continue
        return k if is_countermeasure_request(p) else None
    return None


def _user_commissioned(ask, prior_asks):
    return _commission_origin(ask, prior_asks) is not None


# T3: the answer says a countermeasure exists. Completion verb (or a noun
# stop 「…記憶に保存。」) in the same clause. Not: negated completion
# (「まだ完了していません」), a NAME use (neutralized), a past/dated history
# (「前回の再発防止で…」「（2026-09-03）導入しました」).
_DONE_NOUN = u"(?:保存|追加|導入|配布|登録|設定|反映|記録|実装|作成|組み込み)"
SELF_CLAIM_RE = re.compile(
    u"(?:再発防止|恒久対策|再発を?防(?:止|ぐ)|再発しない(?:よう|ため)"
    u"|同じ(?:ミス|こと|失敗|誤り|問題)[がをは]?(?:繰り返さ|起こさ|起き)ない(?:よう|ため))"
    u"[^。\\n]{0,60}?"
    u"(?:済(?:み|ん)|完了(?:し|です|。|$)"
    u"|(?:入れ|追加し|導入し|配布し|保存し|登録し|設定し|反映し|記録し|組み込み"
    u"|仕込み|実装し|作成し|作り)(?:ました|てあります|ています|た。)"
    u"|" + _DONE_NOUN + u"(?:済み?|\\s*[。．]|\\s*$))", re.M)
_NEG_AFTER_RE = re.compile(u"^[^。\\n]{0,8}?(?:ません|ていない|てない|ない[。、]|ず[。、]|未)")
_DATE_RE = re.compile(u"\\d{4}-\\d{1,2}-\\d{1,2}|\\d{1,2}/\\d{1,2}|\\d{1,2}月\\d{1,2}日")
_CODE_BLOCK_RE = re.compile(u"```.*?```", re.S)


def _self_claimed(final_text):
    t = _CODE_BLOCK_RE.sub(u"", final_text or "")
    t = _neutralize(t)
    for m in SELF_CLAIM_RE.finditer(t):
        head = t[max(0, m.start() - 20):m.start()]
        if re.search(u"(?:前回|以前|過去|先週|昨日|既存)の?[^。\\n]*$", head):
            continue
        if _NEG_AFTER_RE.search(t[m.end() - 2:m.end() + 12]):
            continue
        if _DATE_RE.search(head + m.group(0)):
            continue
        return True
    return False


# S: schedule changes ------------------------------------------------------
SCHED_CMD_RE = re.compile(
    r"schtasks(?:\.exe)?[\"']?\s+(?:-ArgumentList\s+)?[\"'(@]*/(?:create|change)\b|Register-ScheduledTask\b"
    r"|Set-ScheduledTask\b|New-ScheduledTaskTrigger\b|\$\w+\.Triggers\b"
    r"|\bcrontab\s+(?!-l\b)\S|launchctl\s+(?:load|bootstrap)\b"
    r"|systemctl\s+(?:enable|edit)\s+\S+\.timer", re.IGNORECASE)
_READONLY_HEAD_RE = re.compile(
    r"^\s*(?:echo|printf|grep|rg|cat|type|less|head|tail|Select-String|Write-Output"
    r"|Write-Host|git\b|ls\b|dir\b|#)", re.IGNORECASE)
SCHED_MCP_RE = re.compile(r"(?i)^mcp__.*(?:schedul|cron|trigger|routine).*(?:create|update)")
WORKFLOW_RE = re.compile(r"[/\\]\.github[/\\]workflows[/\\][^/\\]+\.ya?ml$", re.I)
# Fable 2026-10-12: the plan is judged over the WHOLE answer written after the
# last schedule change, and needs BOTH a concrete datetime and a promise to
# check (or an observed run). A sentence break between them is fine
# (「次の予定実行: 2026-10-13 04:31 JST。起動後にログを確認します。」); a check
# with no datetime (「次回の実行ログを確認します」) is not.
_REL_DAY = u"(?:明朝|明日|明晩|今夜|今晩|今朝|翌朝|本日|今日|毎朝|毎日|次回|初回|tomorrow|tonight)"
_CLOCK = u"(?:\\d{1,2}[:：]\\d{2}|\\d{1,2}時(?:\\d{1,2}分|半)?)"
FIRING_DATETIME_RE = re.compile(
    u"\\d{4}-\\d{1,2}-\\d{1,2}|\\d{1,2}/\\d{1,2}(?!\\d)|\\d{1,2}月\\d{1,2}日"
    u"|" + _REL_DAY + u"[^。\\n]{0,15}?" + _CLOCK
    + u"|" + _CLOCK + u"[^。\\n]{0,6}?" + _REL_DAY
    + u"|(?:次回|次の)?(?:ログオン|ログイン|サインイン|再起動)(?:時|後)|next logon",
    re.IGNORECASE)
FIRING_EVENT = u"(?:(?<!テストを)(?<!テスト)(?:起動|実行|発火)|ログ|run|log)"
FIRING_CHECK = u"(?:確認|確かめ|チェック|点検|見届|検証|check|verif)"
# A promise is FUTURE (確認します/する/予定); a past 「確認しました」 is the manual
# run, not the scheduled one.
_FUTURE = u"(?=[^。\\n]{0,6}?(?:します|する|しましょう|予定|ます|てください|check|verify))"
FIRING_PROMISE_RE = re.compile(
    FIRING_EVENT + u"[^。\\n]{0,50}?" + FIRING_CHECK + _FUTURE
    + u"|" + FIRING_CHECK + u"[^。\\n]{0,15}?" + FIRING_EVENT + _FUTURE, re.I)
# An observed run counts only with a clock time (「4:20:41 に起動していました」):
# the 2026-10-02 defective answer passed on 「遅くとも 9/23 から…毎日起動して
# いました」, a diagnosis of the OLD failure.
FIRING_OBSERVED_RE = re.compile(
    _CLOCK + u"(?:[:：]\\d{2})?[^。\\n]{0,8}?(?:に|で)"
    u"(?:起動し|実行され|発火し|動い)(?:てい)?(?:まし)?た")
SCHED_WORD_RE = re.compile(u"次回|次の|予定|実行|起動|発火|next run|scheduled", re.I)


def _schedule_changes(uses):
    out = []
    for name, inp in uses:
        if name == "RemoteTrigger" and str(inp.get("action")).lower() in (
                "create", "update"):
            out.append("RemoteTrigger %s" % inp.get("action"))
        elif name == "CronCreate" or SCHED_MCP_RE.match(name or ""):
            out.append(name)
        elif name in EDIT_TOOLS:
            fp = inp.get("file_path") or ""
            if (isinstance(fp, str) and WORKFLOW_RE.search(fp)
                    and re.search(r"\bcron\s*:", _edit_body(inp))):
                out.append(os.path.basename(fp))
        elif name not in AGENT_TOOLS and isinstance(inp.get("command"), str):
            hit = _sched_in_command(inp["command"])
            if hit:
                out.append(hit)
    return out


# 2026-10-12 実測の偽陽性: 検証役のテストが heredoc の Python に書いた文字列
# （SCH = "schtasks /create ..."）を「このターンで変えた予定」と数えて止めた。
# 予定を変えるのは「実行されるコマンド」だけ。heredoc の本文・変数への代入・python/node に
# 渡したスクリプトの行は数えない。クォート内は除かない（Fable: 引用付きフルパスの schtasks.exe・
# Start-Process -ArgumentList・bash -c・Invoke-Expression を取りこぼす回帰になった）。
_HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
_ASSIGN_HEAD_RE = re.compile(r"^\s*(?:\$?[A-Za-z_]\w*)\s*=(?!=)")
_SCRIPT_HEAD_RE = re.compile(r"^\s*(?:python\w*|py|node|pytest|perl|ruby)(?:\.exe)?\b", re.IGNORECASE)


def _strip_heredoc_bodies(cmd):
    """Drop heredoc bodies line by line (linear; an unterminated heredoc drops the rest)."""
    out, tag = [], None
    for line in cmd.split("\n"):
        if tag is not None:
            if line.strip() == tag:
                tag = None
            continue
        out.append(line)
        m = _HEREDOC_START_RE.search(line)
        if m:
            tag = m.group(2)
    return "\n".join(out)


def _sched_in_command(cmd):
    cmd = _strip_heredoc_bodies(cmd or "")
    for seg in _segments(cmd):
        if _READONLY_HEAD_RE.match(seg) or _SCRIPT_HEAD_RE.match(seg) or _ASSIGN_HEAD_RE.match(seg):
            continue
        if SCHED_CMD_RE.search(seg):
            return seg.strip()[:80]
    return ""


def _text_after_last_sched(rows):
    """Assistant texts written AFTER the turn's last schedule change (parent
    transcript). The plan must follow the change: in the 2026-10-02 turn the
    mid-turn diagnosis named times and 確認 long before the last update, and
    joining every message let that real defective turn pass in calibration.
    Falls back to the final text when the change was made by a subagent."""
    last = None
    for i, r in enumerate(rows):
        if r.get("type") == "assistant" and _schedule_changes(_tool_uses([r])):
            last = i
    if last is None:
        return _final_text(rows)
    return _final_text(rows[last + 1:], every=True) or _final_text(rows)


def _sentences(t):
    return [x for x in re.split(u"(?<=[。！!？?])|\\n", t) if x and x.strip()]


def _firing_planned(final_text):
    """Fable 2026-10-12 (2): an unrelated date (「最終更新日 2026-10-12」) plus
    「テストを実行して結果を確認します」 passed. Now: an observed run with a
    clock time passes alone; otherwise a datetime must sit in the same or an
    adjacent sentence as a schedule word (次回/次の/予定/実行/起動/発火), AND a
    future check promise must name the run (起動/実行/発火/ログ)."""
    t = _CODE_BLOCK_RE.sub(u"", final_text or "")
    if FIRING_OBSERVED_RE.search(t):
        return True
    if not FIRING_PROMISE_RE.search(t):
        return False
    ss = _sentences(t)
    for n, x in enumerate(ss):
        if FIRING_DATETIME_RE.search(x):
            near = u"".join(ss[max(0, n - 1):n + 2])
            if SCHED_WORD_RE.search(near):
                return True
    return False


# X: equivalent copies in sibling repos ------------------------------------
CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1", ".gs")
GENERIC_BASENAMES = {
    "__init__.py", "main.py", "setup.py", "conftest.py", "utils.py", "util.py",
    "config.py", "app.py", "run.py", "cli.py", "common.py", "helpers.py",
    "settings.py", "manage.py", "server.py", "test.py", "index.js", "build.js",
    "main.js", "app.js", "utils.js", "config.js", "index.ts", "main.ts",
    "code.gs", "install.sh", "setup.sh", "run.sh", "build.sh"}
INDEX_TTL = 6 * 3600
MIN_SHARED = 0.30
_SKIP_COPY_RE = re.compile(
    r"(?:^|[/\\])(?:\.claude[/\\]hooks|node_modules|\.venv|venv|site-packages"
    r"|__pycache__|\.git|tests?|fixtures)(?:[/\\]|$)", re.IGNORECASE)


def _repo_root(path):
    d = os.path.dirname(os.path.abspath(path))
    for _ in range(12):
        if os.path.exists(os.path.join(d, ".git")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd
    return None


def _edited_code_paths(uses, cwd=None):
    """Code files this turn wrote by Write/Edit or by a shell cp/mv/redirect
    destination. Relative shell paths resolve against `cwd` (Fable
    2026-10-12: `cp ../claude-governance/... scripts/` was invisible). Files
    rewritten by a script (`python -c`, a scratch .py) are found by the mtime
    scan in _unsynced_copies, not here."""
    out = set()
    for name, inp in uses:
        fp = inp.get("file_path") if name in EDIT_TOOLS else None
        cands = [fp] if isinstance(fp, str) else []
        c = inp.get("command")
        if name not in AGENT_TOOLS and isinstance(c, str):
            for seg in _segments(c):
                for m in SHELL_REDIRECT_RE.finditer(seg):
                    cands.append(m.group(1))
                if SHELL_WRITE_VERB_RE.search(seg):
                    toks = PATH_TOKEN_RE.findall(seg)
                    if toks:
                        cands.append(toks[-1])
        for p in cands:
            p = (p or "").strip().strip("'\"")
            if not p.lower().endswith(CODE_EXT):
                continue
            if not os.path.isabs(p):
                if not cwd:
                    continue
                p = os.path.join(cwd, p)
            # (no temp-dir filter: a scratch file has no .git above it and is
            # dropped by _repo_root; the tests build their repos under %TEMP%)
            if not _SKIP_COPY_RE.search(p) and not NOT_COUNTERMEASURE_RE.search(p):
                out.add(os.path.normpath(p))
    return out


def _basename_index(parent):
    """{basename: [abs paths]} of tracked code files of every repo under
    `parent`, cached INDEX_TTL seconds in STATE_DIR."""
    key = re.sub(r"[^A-Za-z0-9]+", "_", os.path.normcase(parent))[-80:]
    cache = os.path.join(STATE_DIR, "basename_index_%s.json" % key)
    try:
        if os.path.getmtime(cache) > datetime.now().timestamp() - INDEX_TTL:
            with io.open(cache, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    import subprocess
    idx = {}
    for name in sorted(os.listdir(parent)):
        repo = os.path.join(parent, name)
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        try:
            p = subprocess.run(["git", "-C", repo, "ls-files", "-z"],
                               capture_output=True, timeout=10)
        except Exception:
            continue
        for rel in p.stdout.decode("utf-8", "replace").split("\0"):
            if not rel.lower().endswith(CODE_EXT) or _SKIP_COPY_RE.search(rel):
                continue
            b = rel.rsplit("/", 1)[-1]
            if b.lower() in GENERIC_BASENAMES or len(b.rsplit(".", 1)[0]) < 6:
                continue
            idx.setdefault(b, []).append(os.path.normpath(os.path.join(repo, rel)))
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(cache, "w", encoding="utf-8") as f:
            json.dump(idx, f)
    except Exception:
        pass
    return idx


def _lines(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


# Fable 2026-10-12 (2): `git pull --rebase --autostash` alone, a turn with
# no tool call, and sync_all.py were all flagged -- every pulled file has a
# fresh mtime. The mtime scan now needs WRITE EVIDENCE in the turn, is off
# when the turn moved the tree (pull/fetch/checkout/merge/rebase/stash/
# sync_all), and keeps only files git reports dirty or committed since the
# turn started.
_TREE_MOVE_RE = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:pull|fetch|checkout|switch|merge|rebase|stash"
    r"|reset|restore|clone|cherry-pick|revert|am)\b|sync_all\.py", re.I)
_SCRIPT_RUN_RE = re.compile(r"(?:^|[\s;&|(])(?:node|npx|deno|bun)\s+\S", re.I)


def _write_evidence(uses):
    for name, inp in uses:
        if name in EDIT_TOOLS:
            return True
        c = inp.get("command")
        if name in AGENT_TOOLS or not isinstance(c, str):
            continue
        if _invocations(c) or _SCRIPT_RUN_RE.search(c):
            return True
        for seg in _segments(c):
            if SHELL_REDIRECT_RE.search(seg) or SHELL_WRITE_VERB_RE.search(seg):
                return True
    return False


def _tree_moved(uses):
    return any(isinstance(inp.get("command"), str) and name not in AGENT_TOOLS
               and _TREE_MOVE_RE.search(inp["command"]) for name, inp in uses)


def _git_changed(repo, start_ts):
    """normcase'd abs paths dirty in `repo` or in its commits since start."""
    import subprocess
    out = set()
    try:
        st = subprocess.run(["git", "-C", repo, "status", "--porcelain", "-z"],
                            capture_output=True, timeout=10).stdout
        for ent in st.decode("utf-8", "replace").split("\0"):
            if len(ent) > 3:
                out.add(os.path.normcase(os.path.normpath(os.path.join(repo, ent[3:]))))
        lg = subprocess.run(["git", "-C", repo, "log", "--since=@%d" % int(start_ts - 5),
                             "--name-only", "--format="],
                            capture_output=True, timeout=10).stdout
        for rel in lg.decode("utf-8", "replace").splitlines():
            if rel.strip():
                out.add(os.path.normcase(os.path.normpath(os.path.join(repo, rel.strip()))))
    except Exception:
        pass
    return out


def _distinctive(b):
    return b.lower() not in GENERIC_BASENAMES and len(b.rsplit(".", 1)[0]) >= 6


def _unsynced_copies(uses, start_ts, final_text, until=None, cwd=None):
    """[(edited, copy)] for equivalent copies in OTHER repos left stale.

    edited = Write/Edit/shell destinations, PLUS every tracked code file of a
    repo this turn touched (cwd's repo, a repo of an edited path, a repo whose
    name appears in a command or path) whose mtime falls inside the turn --
    that is how `python -c` / scratch-script rewrites are seen."""
    until = until or datetime.now(timezone.utc).timestamp()
    edited = _edited_code_paths(uses, cwd)
    roots = {r for r in (_repo_root(p) for p in edited) if r}
    if cwd and os.path.isdir(cwd):
        r = _repo_root(os.path.join(cwd, "x"))
        if r:
            roots.add(r)
    if not roots:
        return []
    parent = os.path.dirname(sorted(roots)[0])
    idx = _basename_index(parent)
    if start_ts is not None and _write_evidence(uses) and not _tree_moved(uses):
        text = "\n".join(str(inp.get(k)) for _, inp in uses
                         for k in ("command", "file_path", "path")
                         if isinstance(inp.get(k), str)).lower()
        try:
            names = [n for n in os.listdir(parent)
                     if os.path.isdir(os.path.join(parent, n, ".git"))]
        except Exception:
            names = []
        touched = set(roots) | {os.path.join(parent, n) for n in names
                                if n.lower() in text}
        tpre = tuple(os.path.normcase(t + os.sep) for t in touched)
        changed = set()
        for t in touched:
            changed |= _git_changed(t, start_ts)
        for paths in idx.values():
            for c in paths:
                if (os.path.normcase(c).startswith(tpre)
                        and os.path.normcase(c) in changed):
                    try:
                        mt = os.path.getmtime(c)
                    except Exception:
                        continue
                    if start_ts - 5 <= mt <= until + 5:
                        edited.add(os.path.normpath(c))
    named = (final_text or "").lower()
    out, seen = [], set()
    for e in sorted(edited):
        b = os.path.basename(e)
        if not _distinctive(b):
            continue
        root = _repo_root(e)
        body = _lines(e)
        if not root or body is None:
            continue
        mine = {ln.strip() for ln in body.splitlines() if ln.strip()}
        for c in _basename_index(os.path.dirname(root)).get(b, []):
            if os.path.normcase(c).startswith(os.path.normcase(root + os.sep)):
                continue
            if os.path.normcase(c) in seen:
                continue
            cb = _lines(c)
            if cb is None or cb == body:
                continue
            try:
                mt = os.path.getmtime(c)
                if start_ts is not None and start_ts - 5 <= mt <= until + 5:
                    continue          # written during the turn (cp loops too)
            except Exception:
                continue
            theirs = {ln.strip() for ln in cb.splitlines() if ln.strip()}
            if not mine or not theirs:
                continue
            if len(mine & theirs) / float(len(mine | theirs)) < MIN_SHARED:
                continue
            repo = os.path.relpath(c, os.path.dirname(root)).split(os.sep)[0]
            if repo.lower() in named:
                continue
            seen.add(os.path.normcase(c))
            out.append((e, c))
    return out


MISSING_SCHEDULE = u"""⛔ 定期実行の設定を変えたが、初回の実発火を確かめる予定が回答に無い

このターンで変えた予定: {items}

手動実行（run）やテストの合格は「予定の時刻に、その環境（UTC の日付・利用枠・
資格情報）で動く」ことを示さない。2026-10-02 の 4:20 予約は手動実行で成功を
確かめて完了扱いにしたが、10-07 の 4:20 実行では UTC 日付の取り違えと利用枠の
区切りずれで目的を果たさなかった（ユーザーが翌朝に気づいた）。

いま行うこと: 回答に **次の予定実行の日時** と **それを確認すること**
（例:「明朝 4:31 の実起動時刻とログを確認します」）を書く。
既に予定時刻の実行を観測したなら、その時刻と結果を書く。
"""

MISSING_COPIES = u"""同じツールの写しが他のリポにあるが、直したのは一部だけかもしれない

このターンで直したファイルと、同等の写し（同名・行の30%以上が共通・内容が異なる・
このターン中に書かれていない）:
{items}

2026-10-07、evidence_search.py を正典と3リポに配って「使う3つのリポすべてに配った」と
報告したが、youtube-to-presentation の古い写しが漏れていた（ユーザーが指摘）。

いま行うこと: 各写しに同じ修正を入れる。直さないものは、そのリポ名を回答に挙げて
「対象外（理由）」と書く（リポ名が回答に出ていれば通る）。
"""


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

いま行うこと:
  Task/Agent で **model: claude-fable-5**（Opus 以外のモデル）のサブエージェントを
  起動し、prompt に「この対策を壊せ。回避経路を逐語の再現ケースで出せ」のような
  **攻撃の指示**を書く（壊せ/攻撃/回避/反証/突破/break/attack/bypass/adversarial）。
  戻ってきた回避経路を **テストケースに逐語で追加**し、
  **当時の欠陥版に当てて FAIL することを確認**する。
  （2026-10-06 以降、既存コーパスの ls・fixture の書き込み・要約だけの Fable
   起動・'subagent_type' という文字列は (e) に数えない）

「攻撃的検証を行いました」と書くだけでは通らない。
本ゲートはツール呼び出しを見ており、文章は見ていない。
"""


MISSING_MECHANICAL = u"""⛔ 対策が「機械的・配布済み・発火確認済み」になっていない

このターンのツール呼び出しから、次が確認できなかった（文章は見ていない）:
{items}

  (a) 実行可能な対策ファイル: templates/hooks/・claude-governance の hooks/scripts、
      または guard/gate/check 等の名前の .py/.sh/.js/.ps1 に**コード行**を書いたか
      （コメントだけの編集・1リポの .claude/hooks 配布コピー・tests/ は対象外）
  (b) 配布: python scripts/deploy_all.py（および --global）を実行したか（--dry-run は不可）
  (c) 発火確認: 今回の対策に対応する test_*.py / calibrate_*.py / pytest /
      scripts/verify_hook_firing.py を python で実行したか（echo・grep・cat・--help・
      --collect-only・無関係なテストは不可）
  免除: index/COUNTERMEASURE_EXEMPT.json の reason は15字以上・「まだ/TODO/後で」等の
      先送り語なし・Write/Edit でリポの index/ に書いたものだけ有効

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
    t = _neutralize(ask)
    if SELF_REQUEST_RE.search(t):
        return True
    if not (ASK_RE.search(t) and IMPERATIVE_RE.search(t)):
        return False
    if BACKGROUND_RE.search(t) and not FIX_VERB_RE.search(t):
        return False
    return True


def _missing(tools, uses):
    """Ordered list of missing proof keys among a..e.
    `tools` (the text blob) is kept for signature compatibility only: since
    ADVERSARIAL 2026-10-06 every proof is read from structured tool calls."""
    m = _mechanical_checks(uses)
    miss = []
    if not m["exempt"]:
        miss += [k for k in ("a", "b", "c") if not m[k]]
    miss += [k for k in ("d", "e") if not m[k]]
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

    # Condition 1: a countermeasure was commissioned -- by the user's own
    # words (T1), by a continuation of such a prompt (T2), or by the answer
    # itself claiming one is in place (T3, C08 2026-10-12). S and X below
    # apply to every turn.
    ctx = getattr(_read_turn_full, "ctx", {}) or {}
    final = ctx.get("final_text", "")
    origin = _commission_origin(ask, ctx.get("prior_asks"))
    commissioned = origin is not None or _self_claimed(final)
    proof_uses = uses
    if origin:
        # T2 (Fable 2026-10-12): proofs accumulate from the inherited request
        # onward -- a continuation 「はい」 after a finished countermeasure
        # must not be blocked for proofs made in the earlier turns.
        try:
            oi = ctx["prior_idx"][origin - 1]
            rows = ctx["rows"]
            proof_uses = (_tool_uses(rows[oi + 1:]) + _subagent_uses(
                ctx["tp"], _ts(rows[oi].get("timestamp"))))
        except Exception:
            proof_uses = uses

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
    problems = []
    if commissioned:
        missing = _missing(tools, proof_uses)
        if missing:
            problems.append(_reason(missing))
    sched = _schedule_changes(uses)
    if sched and not _firing_planned(ctx.get("turn_text") or final):
        problems.append(MISSING_SCHEDULE.replace(
            u"{items}", u" / ".join(sched[:5])))
    copies = _unsynced_copies(uses, ctx.get("start_ts"), final,
                              cwd=ctx.get("cwd"))
    # X is a WARNING (Fable 2026-10-12 (2)): 16 of 48 repos hold same-name,
    # differing, >=30%-shared copies today (claim_check.py x5, vite.config.ts
    # ...), and real-data precision is not calibrated. Shown, never blocks.
    warn = u""
    if copies:
        warn = MISSING_COPIES.replace(u"{items}", u"\n".join(
            u"  %s  ->  %s" % (e, c) for e, c in copies[:10]))
    if not problems and not warn:
        return

    _record_fired(ev)

    out = {}
    if problems:
        out = {"decision": "block", "reason": u"\n".join(problems)}
    if warn:
        out["systemMessage"] = u"⚠️ (警告・ブロックしない) " + warn
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
