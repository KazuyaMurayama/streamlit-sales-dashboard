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

# Deploying is not a substitute for auditing, but a turn that deployed AND
# audited is the intended shape; deploy alone is explicitly not enough, because
# "I shipped it" was the claim that kept turning out to be false.
DEPLOY_RE = re.compile(r"deploy_all\.py")


def _read_turn(transcript_path):
    """Return (user_ask, tool_blob) for the latest turn.

    Windowed to the last 4000 rows, matching the other guards: bounds parsing
    cost on very large transcripts. readlines() still does full I/O.
    """
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-4000:]
    except Exception:
        return "", ""

    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue

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
        return "", ""
    start = user_idx[-1]
    ask = _text(rows[start]) or ""

    tools = []
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_use":
                inp = b.get("input") or {}
                for k in ("command", "file_path", "path", "prompt", "query"):
                    v = inp.get(k)
                    if isinstance(v, str):
                        tools.append(v)
    return ask, "\n".join(tools)


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


def main():
    # Defer to a registered repo-local copy, matching the existing convention.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        return

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return

    if ev.get("stop_hook_active"):
        return

    tp = ev.get("transcript_path")
    if not tp:
        return
    ask, tools = _read_turn(tp)
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
    if not (ASK_RE.search(ask) and IMPERATIVE_RE.search(ask)):
        return

    # ...but not when 再発防止 is merely BACKGROUND to a different request.
    # Measured false positive: 「前回の再発防止でフックを入れましたが、いまの
    # NASDAQ のベスト戦略の CAGR を教えてください」 -- the topic word and an
    # imperative both appear, yet the commissioned work is a lookup.
    #
    # Discriminator: distance. In a real countermeasure request the topic and
    # the imperative sit in the same clause (「再発防止を計画して」). When the
    # mention is background, the imperative belongs to a later, unrelated
    # clause. Anything past ~40 chars is treated as a different sentence.
    #
    # Deliberately generous (40, not 15): a false negative here silently
    # exempts a real countermeasure turn, which is the failure this whole hook
    # exists to prevent. A false positive merely costs one extra audit run.
    near = False
    for m in ASK_RE.finditer(ask):
        window = ask[m.start():m.start() + 40]
        if IMPERATIVE_RE.search(window):
            near = True
            break
    if not near:
        return

    # Condition 2: the audit was never run this turn.
    if AUDIT_RE.search(tools):
        return

    _record_fired(ev)

    out = {"decision": "block", "reason": REASON}
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
