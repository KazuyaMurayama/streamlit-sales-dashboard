# -*- coding: utf-8 -*-
"""Stop hook: block an answer that hands the user work Claude could do itself.

WHY (2026-09-29, loop action C03 -- reports/CORRECTION_DIGEST_20260929.md)
-------------------------------------------------------------------------
Defect class C03「ユーザーへの丸投げ・不要な確認」: 20 corrections in 30 days
(「Claude Code側でできるのでは？」「言われなくてもやって」「明らかなミスは
ユーザーに聞くな」), and the most expensive class: answering them cost 2.65億
context tokens. In 18 of the 20 cases the answer before the correction put
the hand-off in its closing lines -- usually the Next Action -- as「〜を実行
して結果を教えてください」「ご指示いただければ実施します」「お決めください」.

The rule already exists in prose (CLAUDE.md §11.2: ask the user only for
①権限がない ②本人しか知らない情報 ③本人の意思決定). Prose did not stop it,
because the Next Action format itself pulls toward handing something over.

WHAT IT DOES
------------
If the closing part of the final answer asks the user to operate, report
back, or approve, the stop is blocked ONCE with the §11.2 test. Claude then
either does the work itself, or keeps the request and labels it with the
reason, e.g. 「（本人の判断）」「（権限）」「（本人のみ）」. A labelled request
passes, so a legitimate question costs one short rewrite, not a loop.

CALIBRATION (measured 2026-09-29, tests/calibrate_delegation_guard.py, 418
real instructions over 30 days, the hook's own decide() imported):
    fires on 11.7% of answers; catches 9 of the 20 answers the user corrected
    as C03. Rejected wider sets: every 「〜してください」+decision requests
    42.5% (15/20); adding 「〜してください」 alone 15.8% (10/20); decision
    requests without a recommendation 21.1% (9/20, no gain).
The 11 misses are decision requests (「お決めください」「ご判断ください」),
which look the same as legitimate ③本人の意思決定 questions.

BATCHED DECISIONS (2026-10-06)
------------------------------
User: 「その3つは、今決めるべきことですか？かつ、Claude側で決められないものですか？
推測はできないものですか？」 and then 「聞かなくていいことを6つも聞いたというような
ミスも、今後は繰り返さないでほしくて、このリポジトリでもそうですし、他のリポジトリ
でも同様です」. The answer had closed with 「Next Action: … の6つを決めてください
（レポート §5 A1〜A6）」. Of the six, three were already decided in the repo's own
documents, two had defaults Claude could set (reversible settings), one was a
real decision -- and none was needed that day.

A single decision request still passes (it may be a real ③). A request for
SEVERAL decisions at once is the shape of this defect: it is a to-do list
handed to the user instead of triage. It is blocked once with the triage
test (already decided? reversible? needed now?). The count is read from the
sentence itself: 「6つ」「3点」「A1〜A6」, or a 「・」-separated list of options.
Calibration: tests/calibrate_delegation_guard.py (BATCH line).

V3: ATTEMPT EVIDENCE (2026-10-19, loop action C03 -- reports/CORRECTION_DIGEST_20261019.md)
--------------------------------------------------------------------------------------
v2 was followed by 7 more C03 corrections. Replaying the 9 answers the user
corrected as C03 (2026-10-12..17) through v2's decide()/decide_batch() gave
0/9 fires. Each miss used a new wording outside the verb list (「画面を送って
ください」「実残高から計算してください」「回答と共有をお待ちしています」
「そうおっしゃっていただければ…整理します」), one closed with a bare 「以上」 so
the real hand-off sat in an earlier text block, and one carried the label
「（本人の判断）」 -- the label was meant as a justification but worked as a
free pass. v2 judged the WORDS; the defect is that Claude never TRIED. So v3
adds a second, wording-independent test on the turn's tool history:

  * request  = any sentence of the final answer (all text after the last tool
               call, plus the block before it when that is a stub like 「以上」)
               that asks the user to do, send, compute, decide or wait for
               something (broad ASK pattern; reading the deliverable is excluded)
  * decision = such a sentence about choosing/approving. It passes only if the
               answer gives a recommendation (推奨). A label does not excuse it.
  * other    = passes only if a tool call of this turn (not a Write/Edit of the
               report itself) shares a content word with the request, or the
               turn explored means (ToolSearch / an MCP tool). Labels such as
               （権限） no longer excuse a request nobody attempted.
Blocked once per instruction (same mark as v2). Calibration:
tests/calibrate_delegation_guard_v3.py.

V3.1 (2026-10-19, Fable QC I1 -- audits/hook_qc_20261019/HOOK_QC_20261019.md)
-----------------------------------------------------------------------------
Wordings outside v3's ASK passed: 「どちらで進めますか？」「〜いただけると助かります」
「〜いただけますでしょうか」「〜をお願いしたいです」, English (please / could you), and a
request in a table row. Added. Three wording-independent rules:
  * compute  = a request to calculate (計算・算出・集計) is never excused by tool calls
               (2026-10-17: 「円の金額は…実残高から計算してください」 passed on Bash calls)
  * weak evidence = a Grep/Read/WebSearch that names the asked-for thing counts only if the
               answer says how it ended (見つかりません・エラー); an MCP call counts only if it is
               the service the request names (a Calendar update is not a Gmail search)
  * batch    = decide_batch also runs on the whole final text, not only the last block
Calibration (tests/calibrate_delegation_guard_v3.py, same 7 days / 198 turns): firing
20.7% -> 22.7% (all 3 new fires are answers the user corrected as C03); C03 recall 3/7 -> 5/7.
Left: an answer that stops without any request (2026-10-15) and a request whose words the
turn's Bash calls happen to contain (2026-10-14 07:52). Regression: tests/test_hook_qc_20261019.py.
V3.2 (2026-10-19, second Fable QC): a table row is read by its last cell only, and not at all when it
is a numbered step or a status row (rule 8's request-mapping table quotes the request before the
answer); inline code is dropped; an English ask counts only in an answer without Japanese prose (a
draft for someone else); 「安心/理解/参考していただけると」「お願いしたいと考えています」「いずれの案でも
…ありますか」 are no asks; 〜てくれますか・〜てもらえますでしょうか・頂戴・どの〜で…ますか・kindly are.
Same 7 days / 200 turns: firing 22.0% (22.6% before), C03 recall 5/7.

V4: STALL (2026-11-02, loop action C03 -- reports/CORRECTION_DIGEST_20261102.md)
-------------------------------------------------------------------------------
v2/v3 was followed by 14 more C03 corrections. Replaying the 14 answers before them (2026-10-14..26)
through v3: 10 fired, 4 passed. Two of the 4 had no request at all -- the answer listed what was left
and stopped: 2026-10-26 「Next Action: EV-3 の記事5本（…）の改稿を進めます。」 after 「残りの本数をすべて…
一度の指示で進めて」 drew 「言われなくてもすすめるべきでは？」; 2026-10-15 「Next Action: 残りの課題のうち次に
進めるのは、nt-059 の要因数の訂正と…の確認です。」 drew 「いちいち報告するまでもなく…直して」. v2/v3 look for a
hand-off to the user; this defect hands over nothing -- it STOPS on a continuation Claude may decide.
Invariant (stalled()): the closing (Next Action section, else the last 300 chars; code, 「quotes」 and
> quotes removed) leaves work open --
  * ask      = a question whose only answer is "go on" (a proceed verb + 〜ますか／〜てよいですか／
               どうしますか／このまま…ですか, ending in ？), or English shall I / want me to
  * offer    = continuing is offered on the user's wish (必要なら／よければ／一言いただければ … 進めます)
  * announce = an own-future verb (〜ます non-past / 〜る予定, no ご/お honorific = not the user's act) in a
               Next Action line or next to 残り・未着手・次は; or 「次に進めるのは〜は」
-- and the closing names no stake only the user can settle (STAKE: irreversible/destructive, money,
publication/sending, the user's will or taste, no permission, an external event to wait for, a
/compact stop). Exempt by the instruction: it said not to go on yet (実行はまだ・計画だけ), it only asked
a question, or it bounded the batch (「まず最初の2つ」「次の2本」). Blocked once per instruction (same mark).
CALIBRATION (2026-11-02, tests/calibrate_delegation_guard_v4.py, real main-agent turns, answers
deduplicated, the hook's own functions imported): 21 days 313 turns -> v4 adds 24 fires (7.7%; v2+v3
already 20.8%, total 28.4%); 45 days 610 turns -> +44 (7.2%; total 35.9%). Eyeball of the 21-day 24:
~19 stalls after 「はい、進めて」「残りをすべて」「できるだけ10本以上」, 2 false (「改めるなら…直して配布します」
a hypothetical; 「この方針でよければ…直します」 a plan approval), 3 unclear. Removed before that: plan-only
prompts, question-only prompts and bounded batches (30 -> 24 fires; 6 of the removed were 「次の2本を
レポートにして」 followed by 「次は7本目…を進めます」). C03 recall on the 14: v3 10/14 -> v4 12/14. Left:
2026-10-22 「実行するタイミングはお任せしました」 (a reload Claude could run) and 2026-10-14 07:52
(ねんきんネット登録 + a Gmail search hidden behind a user-only act); and an answer that, once blocked,
adds an attempt (a permission denial) and stops again (10-19 23:48, 10-20 07:36). Tests:
tests/test_delegation_guard.py (FIRE_V4 / PASS_V4; HOOK=<old copy> shows v3 passes the FIRE_V4 cases).
V4.1 (2026-11-02, Sonnet adversarial review, fixtures/adversarial_delegation_v4_20261102.json: 118 stalls,
74 legit): v4.0 missed 78/118 (サ変「修正します」「対応予定」「後日」, a stake word anywhere in the closing
passed it, English, 名詞止め「次は記事7。」, 「残り12本です」) and stopped 25/74 (choices, approvals, waits,
all done, 「方針を教えて」). Now every excuse is read in the stall's own sentence/bullet (negated stakes
「通知は不要」 and 「公開済み」 do not count; 留保/代替案 lines are dropped), every sentence of the Next Action
paragraph is a candidate, an all-done closing without a remaining count passes, and only an instruction
that orders work (直して・進めて・全部…) can be stalled. Same 21 days / 313 turns: v4 adds 49 (15.7%; total
36.4%); eyeball of the 49: ~33 stalls, ~11 false (fact lines 「残りは次の理由で止まっています」, 「決まれば」
「わかり次第」 waits, 「認める場合は」), ~5 unclear.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
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

NAME = "delegation_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

# Two shapes only. Broader patterns (any 「〜してください」 or any request for a
# decision) fired on 42.5% of real answers -- a guard that fires on half
# of all answers is noise (calibration 2026-09-29, see WHY above).
DELEGATE = re.compile(
    # 1. a conditional offer addressed to the user: "tell me and I will do it".
    #    Bare 「〜があれば修正する」 is NOT here: that is Claude's own plan.
    r"(?:いただければ|いただけたら|頂ければ|もらえれば|もらえたら|くだされば|ご指示あれば|指示があれば"
    r"|ご希望(?:が)?あれば|お申し付け)[^。]{0,20}(?:実施|実行|着手|進め|対応|作成|修正|反映|直し)"
    r"|(?:着手|実施|実行|進め|修正|対応)(?:して)?(?:も)?(?:よければ|よろしければ|いいなら)"
    r"|よければ一言|進めてよいか|進めてよろしいですか|実施してよいか"
    # 2. run-and-report: the user operates, Claude waits for the output
    #    (may span a line break: 「1. 実行 / 2. 結果を貼ってください」)
    r"|(?:実行|試し|確認|開い|押し|起動|入れ|操作)[^。]{0,60}(?:結果|出力|表示|最終行|RESULT|エラー|届いたか|出たか|あるか|できたか)"
    r"[^。]{0,30}(?:教えて|貼って|送って|返して|返信して|お知らせ|ご共有|共有して)")
# Widened after the 2026-10-06 adversarial review (Fable, 12/15 evasions): 「決めてほしい」
# 「ご判断をお願いします」「決断してください」「お決めになってください」「選んでもらいたい」
# 「決定をお願いします」 were outside the first version.
DECIDE_REQ = re.compile(
    r"(?:決めて|お決め(?:になって)?|ご判断|判断して|選んで|お選び|ご選択|選択して|確定して|ご指定|指定して|"
    r"ご決定|決定して|決断して|ご決断|選定して|ご回答|回答して|答えて|ご返答)"
    r"(?:ください|下さい|いただ|頂|もら|ほし|欲し)"
    r"|(?:ご)?(?:判断|決定|決断|回答|指定|選択|選定)(?:を|の)(?:お願い|ください|いただ|頂)")
_N = r"(?:[2-9２-９]|[1-9１-９][0-9０-９]|[二三四五六七八九十]|ふた|みっ|よっ|いつ|むっ|なな|やっ)"
BATCH_COUNT = re.compile(
    # the count must name the things to decide: 「6つを」「3点（…）」「2点——①」「4点のご判断」「3つあります」.
    # Not 「3つの不具合」 (one decision about three bugs), 「80点へ」 (a score), 「変える3点、の分割」.
    _N + r"(?:つ|点|件|項目|個|問|行|箇所|か所|ヶ所)(?=\s*(?:を|について|——|―|（|\(|:|：|とも|すべて|全て|、(?!の)|,|あり|ある|への"
    r"|の(?:ご)?(?:判断|決定|決断|回答|指定|選択)|に(?:答え|ついて)))"
    # a labelled range of items: A1〜A6, 問1〜問3, A1 から A6 まで. A bare number range (nt-002〜032) is a list of files.
    r"|(?<![A-Za-zＡ-Ｚａ-ｚ\-])(?:[A-ZＡ-Ｚ]|問|Q)[0-9０-９]+\s*(?:[〜~～\-－]|から)\s*(?:[A-ZＡ-Ｚ]|問|Q)?[0-9０-９]+"
    r"(?:\s*(?:の|を|について|まで|に|（))"
    r"|[①-⑳]\s*[〜~～]\s*[①-⑳]|[①-⑳]{3,}")
# Several decisions written as a list rather than a count.
BATCH_LIST = re.compile(r"それぞれ|まとめて|各項目|一つずつ|1つずつ|ひとつずつ")
ONE_CHOICE = re.compile(r"(?:のうち|の中から|から)?(?:1つ|一つ|ひとつ|1本|1点|どれか|いずれか|どちらか|どちら|どれ)(?:を|に|か|だけ)")
LABEL = re.compile(r"（(?:権限|本人のみ|本人の判断|本人の意思決定|本人しか知らない)）"
                   r"|本人しか(?:知らない|できない)|権限が(?:ない|無い)|本人の意思決定")


def closing(answer):
    """The part of the answer that hands something over: from the last
    「Next Action:」 label (at a line start) if there is one, otherwise the last
    300 characters. Code blocks and 「quoted」 text are removed first -- an
    answer that quotes a hand-off phrase is not making one."""
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    a = re.sub(r"「[^」]{0,200}」", "「」", a)
    m = list(re.finditer(r"(?m)^\W{0,4}Next Action\W{0,4}[:：]", a))
    return a[m[-1].start():] if m else a[-300:]


def _sentence(tail, i, j):
    s = max(tail.rfind("。", 0, i), tail.rfind("\n\n", 0, i)) + 1
    e = tail.find("。", j)
    return tail[s:e if e >= 0 else len(tail)]


def decide_batch(answer):
    """Return the request when the closing asks the user for SEVERAL decisions at once."""
    tail = closing(answer)
    for hit in DECIDE_REQ.finditer(tail):
        sent = _sentence(tail, hit.start(), hit.end())
        sent = re.sub(r"^\W{0,4}Next Action\W{0,4}[:：]\s*", "", sent)   # the label's colon is not a list
        m = BATCH_COUNT.search(sent)
        if m:
            return m.group(0) + " → " + hit.group(0)
        if ONE_CHOICE.search(sent):
            continue    # 「A案・B案・C案のうち1つを選んで」: options of ONE decision
        # 「・」「／」 between two digits is a list of items to look at (記事4・6・42), not of decisions
        seps = len(re.findall(r"(?<![0-9０-９])[・／/](?![0-9０-９])", sent))
        commas = len(re.findall(r"[、,]", sent))
        alts = len(re.findall(r"か[、,／]|か——", sent))
        colon_list = re.search(r"[:：][^。]*[、,][^。]*[、,]", sent)
        if seps >= 2 or commas >= 3 or alts >= 2 or colon_list or BATCH_LIST.search(sent):
            return "列挙した複数項目 → " + hit.group(0)
    return None


def decide(answer):
    """Return the matched hand-off phrase, or None. A run-and-report may span
    a line break, so the whole closing is searched; a label excuses only the
    sentence it sits in."""
    tail = closing(answer)
    for hit in DELEGATE.finditer(tail):
        s = tail.rfind("。", 0, hit.start()) + 1
        e = tail.find("。", hit.end())
        if not LABEL.search(tail[s:e if e >= 0 else len(tail)]):
            return hit.group(0)
    return None


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    """A prompt the user typed -- not a tool result or harness notification."""
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":     # subagent hand-backs, task notifications
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def read_turn(tp):
    """(last human prompt, its timestamp, final assistant text of this turn)."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, answer = None, "", ""
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            prompt, pts, answer = _text(d.get("message")).strip(), d.get("timestamp", ""), ""
        elif d.get("type") == "assistant":
            t = _text(d.get("message")).strip()
            if t:
                answer = t
    return prompt, pts, answer


# ---- v3: attempt evidence (see V3 in the docstring) -------------------------
ASK = re.compile(
    r"(?:して|て|で)(?:ください|下さい|くださいませ|ほしい|欲しい)"
    r"|お願い(?:します|いたします|できますか|できれば|したい(?!と(?:考|思))|いたしたい|できると)"
    r"|お待ち(?:して|し)(?:い|お)ります|お待ちしています"
    r"|(?:て|で)(?:いただ|頂)(?:く必要|けますか|けますでしょうか|けませんか|けると(?!思)|きたい|ければ(?=[、,]?\s*(?:助か|幸い|ありがた|嬉し|うれし))|けたら)"
    r"|(?:て|で)もら(?:う必要|えますか|えませんか|えると(?!思)|えますでしょうか|いたい|えれば(?=[、,]?\s*(?:助か|幸い|ありがた|嬉し|うれし))|えたら)"
    r"|(?:て|で)くれ(?:ますか|ませんか)|(?:を|て)頂戴"
    r"|ご(?:判断|指示|確認|共有|返信|連絡|回答|提供|手配)(?:を|ください|いただ|頂|お願い)"
    r"|お(?:知らせ|決め|送り|伝え)(?:ください|いただ|頂)"
    r"|(?:おっしゃって|言って|仰って)(?:いただ|頂|もら|くだされ)"
    # English hand-offs (DLG-FN5)
    r"|(?i:\b(?:please|kindly)\s+(?!see\b|note\b|find\b|refer\b)[a-z]+|\b(?:could|can|would)\s+you\b|\blet\s+me\s+know\b"
    r"|\bi\s+need\s+you\s+to\b)"
    # a question that asks the user to choose (DLG-FN1 「どちらで進めますか？」). Only with a choice word:
    # 「他に気になる点はありますか？」 is not a hand-off.
    # 「いずれの案でも問題はありますか？」 asks no choice (QC2 I-3)
    r"|(?:どちら|どれ|どの[^。？?\s]{1,6}(?:で|を|に|が)|いずれ(?:に|を|で進|の案に))[^。？?]{0,30}(?:(?<!あり)ますか|でしょうか|ですか|します|する)\s*[？?]")
# Asking the user to read or review the deliverable is the deliverable's purpose.
# Fable QC 2026-10-19 (32.0% fired on 14 days): 「push しました。ご確認ください。」 and
# 「詳細は REPORT.md を確認してください」 point at a delivered result, not a hand-off.
READ_ONLY = re.compile(r"読んで|読み、|お読み|ご覧|目を通|見てください|見ていただ|見てほし|眺め|レビューして|比べ"
                       r"|^(?:ご確認|確認)(?:ください|下さい|をお願いします)[。！]?$"
                       r"|(?:\.md|\.html|\.csv|レポート|ファイル|リンク|成果物|URL|表|§\s*\d)[^。]{0,24}(?:ご確認|確認して|確認くだ)")
# a numbered step of a procedure the user asked for is not a request to them
STEP = re.compile(r"^(?:\d+[.)．、]|[①-⑳]|[-*・]\s*\d+[.)．])\s*")
DECISION = re.compile(r"決め|決定|判断|選ん|選択|選び|お選|採否|採用|可否|承認|方針|どちら|どれ|返して|返信|ご回答|回答して|答えて|お答え|指示")
RECOMMEND = re.compile(r"推奨|おすすめ|お勧め|お薦め|勧めます|推します")
NON_ATTEMPT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "SendMessage", "TodoWrite",
                     "TaskStop", "SubagentHandback", "ExitPlanMode"}
_KW = re.compile(r"[一-鿿]{2,}|[゠-ヿー]{3,}|[A-Za-z][A-Za-z0-9_.\-]{2,}")
KW_STOP = set(
    "ください 下さい 確認 必要 結果 実行 判断 内容 対応 場合 今回 次回 本人 権限 指示 共有 以下 上記 回答 作業 "
    "お願い 意思決定 進め 方法 手順 状態 状況 予定 可能 理由 以上 全体 一言 相当 部分 情報 決定 選択 承認 方針 "
    "直前 前回 最新 正確 簡単 一覧 何か 次の 後で 提示 返信 連絡 報告 説明 検討 実施 着手 修正 反映 the and for "
    "next action".split())


def keywords(s):
    out = []
    for w in _KW.findall(s or ""):
        if w in KW_STOP or w.lower() in KW_STOP:
            continue
        if w not in out:
            out.append(w)
    return out


def _clean(text):
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`[^`\n]*`", " ", t)                  # inline code: 「`please run npm install`」 (QC2)
    t = re.sub(r"「[^」]{0,200}」", "「」", t)
    t = re.sub(r"(?m)^\s*\|.*\|\s*$", lambda m: _table_row(m.group(0)), t)
    t = re.sub(r"(?m)^\s*>.*$", " ", t)                # quotes
    return t


# tables (DLG-FN6): 「| 残高 | 実残高を送ってください |」 is read, but only its last cell. A request-mapping
# row (CLAUDE.md ルール8: | 残高を計算してください | §2 で算出 |) quotes the request before its answer, and a
# numbered step row (| 1 | エディタを開いてください |) is a procedure (Fable QC2 I-1). A deliverables row
# (link), a separator and a status row (✅/済/完了 as a whole cell) are not requests.
_STATUS_CELL = re.compile(r"^(?:✅|☑|☐|済み?|完了|未対応|対応済み?|PASS|FAIL|OK|NG)(?:\s|[（(]|$)")


def _table_row(row):
    if re.search(r"\]\(|^\s*\|[\s:|-]+\|\s*$", row):
        return " "
    cells = [c.strip() for c in row.strip().strip("|").split("|") if c.strip()]
    if not cells or any(_STATUS_CELL.match(c) for c in cells):
        return " "
    if re.match(r"^(?:\d+|[①-⑳]|(?:手順|Step|STEP)\s*\d+)[.)．]?$", cells[0]):
        return " "
    return cells[-1] + "。"


def _sentences(text):
    for part in re.split(r"(?<=[。！？!?])|\n", _clean(text)):
        p = part.strip()
        if p:
            yield p


# Calibration 2026-10-19 (191 real turns, 28.8% fired before these exclusions):
# an invitation to correct an assumption (「違えば言ってください」, required by
# CLAUDE.md's 前提宣言), a way of reading a number (「〜と考えてください」), and acts
# only the account holder can perform (入金・発注・送信・パスワード変更・承認クリック)
# are not hand-offs. The act is read from the words just before the request.
FEEDBACK_INVITE = re.compile(r"(?:ば|たら|なら|場合は?|時は?|ときは?|あれば)、?[^。]{0,40}(?:教えて|言って|お知らせ|ご連絡|連絡して)"
                             # 「終わったら「」とだけ返信して」: the user finished an own-only step and hands back
                             r"|(?:たら|のであれば|であれば)、?[^。]{0,30}「」と(?:だけ)?(?:送って|返信|言って|伝え)")
NOT_AN_ACT = re.compile(r"(?:考え|思っ|みなし|捉え|ご理解|ご了承|ご安心|安心|理解|納得|参考|お待ち(?:くだ|下)"
                        r"|(?:完了|終了|終わる|処理|実行|通知|結果)(?:を|の)?お待ち)")
# 入金額・送金額 is an amount (data Claude can look up), not the act (DLG-FN7)
USER_ONLY_ACT = re.compile(r"入金(?!額|の?金額)|出金(?!額|の?金額)|送金(?!額|の?金額)|振込(?!額|の?金額)|振り込|購入(?!額|の?金額|価格|単価|代金)|買っ|売っ|発注|注文|建玉を|ログイン|パスワード|署名|押印|郵送|送信|電話|"
                           r"窓口|受け取|支払|承認|接続を|拡張機能|再起動|操作して|サインイン|2段階|二段階|新しい会話|新しいセッション"
                           r"|(?:会話|セッション|チャット)に(?:貼|送|入力|投げ)")


# Computing is never the user's job (CLAUDE.md §11.2: 再計算は自分で行う). 2026-10-17 miss: 「円の金額は、
# 入金の直前に口座の実残高から計算してください」 passed because the turn's Bash calls mentioned 口座.
COMPUTE = re.compile(r"(?:計算|算出|試算|集計|換算|合計|足し算|引き算)(?:して|を|し、|いただ|頂|願)|を求めて")
# A search or read that names the asked-for thing is an attempt only if the answer says how it ended
# (「見つかりません」「エラー」): otherwise reading a file whose path mentions the words passes (DLG-FN7).
# 「問題はなかった」「権限がある」 say nothing about the search (QC2 minor)
STUCK = re.compile(r"見つか(?:らな|りませ)|見当たら|(?:記録|結果|該当|情報|データ|ファイル|ヒット)[^。]{0,6}(?:ありませんでした|無かった|なかった)"
                   r"|存在しな|記録がな|記載がな|載っていな"
                   r"|エラー|失敗|拒否|弾かれ|権限が(?:な|不足|あり?ませ)|アクセスでき|取得でき|読めな|開けな|not found|error|denied", re.I)
WEAK_TOOLS = {"Grep", "Glob", "Read", "WebSearch", "WebFetch", "ToolSearch"}
# a service named in the request -> the word its tool names carry (mcp__claude_ai_Gmail__search_threads)
SERVICE = [(re.compile(r"メール|gmail|受信", re.I), "gmail"), (re.compile(r"カレンダー|予定|calendar", re.I), "calendar"),
           (re.compile(r"ドライブ|drive", re.I), "drive"), (re.compile(r"シート|スプレッドシート|sheet", re.I), "sheet"),
           (re.compile(r"ブラウザ|chrome", re.I), "playwright|chrome|browser")]


CLAUDE_CAN = re.compile(r"(?:検索|探|調べ|確認|計算|集計|照合|取得|ダウンロード|抽出|転記)し、")


def requests(text):
    """Sentences that ask the user to do, send, compute, decide or wait for something."""
    out = []
    t = re.sub(r"\s", "", text or "")
    jn = sum(1 for ch in t if ord(ch) > 0x3000)
    for s in _sentences(text):
        m = ASK.search(s)
        if not m or READ_ONLY.search(s) or FEEDBACK_INVITE.search(s) or STEP.match(s):
            continue
        # an English 「could you send…」 inside a Japanese answer is a draft for someone else (QC2 I-3)
        if jn >= 10 and all(ord(ch) < 0x3000 for ch in m.group(0)):
            continue
        # a condition clause is not the act: 「ログイン後、残高画面の共有をお願いしたい」 asks for the screen,
        # not the login (DLG-FN4). 「新しい会話を開き、「」と送って」 keeps both acts.
        lo = max(0, m.start() - 14)
        c = s.rfind("、", lo, m.start())
        if c > 0 and re.search(r"(?:後|あと|たら|てから|うえで|上で)$", s[:c]):
            lo = c + 1
        act = s[lo:m.end()]
        if NOT_AN_ACT.search(act):
            continue
        # 「メールで源泉徴収票を検索し、見つからなければ下書きを送信してください」: the send is the holder's,
        # the search before it is not (2026-10-14 C03 miss)
        if USER_ONLY_ACT.search(act) and not CLAUDE_CAN.search(s[:lo]):
            continue
        out.append(s)
    return out


def attempted(sentence, tools, final=""):
    """True if a tool call of this turn plausibly tried what the sentence asks for."""
    kws = [k.lower() for k in keywords(sentence)]
    services = [w for rx, w in SERVICE if rx.search(sentence)]
    stuck = bool(STUCK.search(_clean(final or sentence)))
    for name, inp in tools:
        name = name or ""
        if name in NON_ATTEMPT_TOOLS:
            continue
        low = (inp or "").lower()
        if name == "ToolSearch" or name.startswith("mcp__"):
            # explored means (the digest's 探索ログ) -- but the means must fit the request: a Calendar
            # update is not an attempt at 「メールで源泉徴収票を検索して」 (2026-10-14 C03 miss)
            if not services or any(re.search(w, name.lower() + " " + low) for w in services):
                return True
            continue
        if name in WEAK_TOOLS and not stuck:
            continue
        # one shared word is too weak: a subagent prompt that merely mentions 「口座」 is not an
        # attempt to compute the balance (2026-10-17 miss). Half the content words, at least 2.
        # a search/read tool that names the asked-for thing is an attempt (Fable QC: Grep 1 word)
        lo = 1 if name in ("Grep", "Glob", "Read", "WebSearch", "WebFetch") else 2
        need = min(len(kws), max(lo, (len(kws) + 1) // 2)) if kws else 1
        if kws and sum(1 for k in kws if k in low) >= need:
            return True
    return False


def unattempted(final, tools):
    """Return (kind, sentence) for the first request with no attempt evidence, else None."""
    # v2 reads only the last text block; the batch can sit in the block above it (2026-10-14 C03 miss:
    # 「計画書 §1 の7行に答えてください」 followed by a separate 「…お待ちしています」 block)
    b = decide_batch(final)
    if b:
        return ("batch", b)
    recommend = bool(RECOMMEND.search(_clean(final)))
    for s in requests(final):
        if DECISION.search(s):
            if not recommend:
                return ("decision", s)
            continue
        if COMPUTE.search(s):
            return ("compute", s)
        if not attempted(s, tools, final):
            return ("action", s)
    return None


# ---- v4: stall -- the answer stops on a continuation Claude could decide itself ----------------
# (see V4 in the docstring). v4.1 (2026-11-02, Sonnet adversarial ~100 cases): every excuse is judged
# on the SAME sentence (or bullet item, with a trailing （…） joined) as the stall, never on the closing
# as a whole -- a stake word in another line, the 留保 or a list no longer passes it. Inside a Next Action
# section every sentence is a candidate (the section IS "what happens next"); outside it a sentence is
# a candidate when it names remaining work, asks to go on, or offers to go on.
REMAIN_POS = re.compile(r"残り|残る|残って|残件|未着手|未対応|未処理|以降|引き続き|続き|続け|続行|継続|次は|次に|次の(?:作業|ステップ|バッチ|手順|段階)"
                        r"|後日|次回|別セッション|次のターン|次のメッセージ|順次|再開"
                        r"|(?i:\bremaining\b|\bnext\s+i'?ll\b|\bi\s+will\s+(?:proceed|continue|fix|do|work)|\bcontinue\s+with\b|\bproceed\s+(?:to|with)\b)")
# a count of work still open (「残り12本」「未着手」「除き」): it defeats an all-done statement in the closing
REMAIN_COUNT = re.compile(r"残り\s*(?:[1-9１-９][0-9０-９]*|[一二三四五六七八九十])|未着手|未対応|未処理|を除き|(?i:remaining:?\s*[1-9])")
PROCEED_Q = re.compile(r"(?:ますか|ましょうか|ませんか|ですか|でしょうか|いい|よい|良い|続ける|やる|進める)\s*[？?]|(?:ますか|ましょうか|でしょうか)[。]?$"
                       r"|(?i:\b(?:shall|should)\s+i\b|\bwant\s+me\s+to\b|\bdo\s+you\s+want\s+me\b|\bwould\s+you\s+like\s+me\b)")
OFFER = re.compile(r"(?:ご?指示|ご?希望|ご?要望|ご?依頼|必要|よろしけれ|よけれ|一言)(?:が|を|で|さえ)?(?:あれば|でしたら|なら|であれば|いただければ|いただけたら|もらえれば|もらえたら|くだされば)"
                   r"|お申し付け|(?i:\blet\s+me\s+know\s+(?:if|and|when)\b)")
# a choice between options or an approval of a plan/text/design is a real decision -- not "go on?"
CHOICE = re.compile(r"どちら|どれ|いずれ|[A-ZＡ-Ｚ]案|案[A-ZＡ-Ｚ]|か[、,]|好み|文体"
                    r"|(?:方針|文面|設計|構成|内容|書き方|宛先|順序|案|形|型|仕様|計画|方向性)(?:で|は|を)[^。？?]{0,12}(?:よろしい|よい|いい|良い|進め|問題|大丈夫|OK)"
    r"|(?:推奨|おすすめ)(?:どおり|通り)で(?:よければ|よろしければ)|意図(?:でしたら|なら)"
    r"|(?:でよければ|でよろしければ|で問題なければ|でよいなら)"
    r"|(?:改める|変える|採る|使う|まとめる|やる|採用する)(?:なら|つもりがあれば|のであれば)|つもりがあれば")
DECIDE = re.compile(r"(?:決め|選ん|選択し|承認し|判断し)(?:て|てください)|承認を(?:ください|お願い)|ご(?:判断|承認|決定)|お決め|お選び")
# stakes only the user can settle, read in the stall's own sentence. 「公開済み」「投稿用」 describe a thing;
# 「通知は不要」「公開は別途」「必要はありません」 negate the stake.
STAKE = re.compile(
    r"force|--force|強制|削除(?!済|した)|消去|取り消せ|元に戻せ|戻せな|不可逆|上書き|rm\s+-|drop\b|reset\s+--hard"
    r"|課金|料金|費用|有料|支払|購入|入金|出金|送金|振込|発注|注文|契約|売却|建玉"
    r"|公開(?!済|版|中|され)|投稿(?!済|用)|出品|送信(?!済)|メールを送|提出|申請|応募|publish|本番"
    r"|好み|本人|ご自身|お好み|価値観|既決定"
    r"|権限|denied|拒否され|ブロックされ|ログインが必要|サインイン|上限に達"
    r"|/compact|/clear|(?:私|こちら)(?:から|で)は?できません|できない操作|推奨|勧め", re.I)
NEG_AFTER = re.compile(r"^[^。]{0,8}?(?:は不要|は別|不要|は要りません|ではない|でなく|せず|しない|しません|なし|無し|の必要はな|する必要はな|必要はありません|はありません)")
# an external event to wait for, in the same sentence: time, a run, someone else's reply
WAIT = re.compile(
    r"(?:結果|ビルド|ジョブ|job|build|CI|テスト|レビュー|返信|返事|約定|反映|通知|処理|実行|承認|入金|審査|集計)[^。]{0,8}"
    r"(?:が出たら|が付いたら|がついたら|が終わったら|が終わり次第|が来たら|を受けて|を待|待ち|完了後|が完了したら|したら|されたら|後に|次第)"
    r"|来週|翌朝|明日|翌日|来月|[0-9０-９]+\s*(?:日|週間|か月|ヶ月|時間)後|[月火水木金土日]曜|定期(?!実行せず)|自動実行|cron|次の朝|朝の"
    r"|戻ったら|戻ってから|戻り次第|届いたら|届き次第|終わり次第|が出たら|が来たら"
    r"|作業中|決まるまで|決まったら|決まり次第|ログイン"
    r"|次回(?:から|の[^。]{0,8}(?:時|際)|セッションで結果)|作成時に|書くときに|以降の新規|今後"
    # a step that depends on the outcome of the waited-for event (「差分があれば修正する」 after 「自動実行を確認する」)
    r"|(?:差分|問題|不具合|エラー|失敗|違い|ずれ|異常|FAIL|NG)[^。]{0,4}(?:があれば|が出れば|が出たら|なら|の場合)"
    r"|(?i:\bwait|\bwhen\s+(?:it|the)\b|\bonce\s+(?:it|the)\b|\bafter\s+(?:it|the)\b|\bbackground\b|\bnotified\b|\brunning\b)", re.I)
DONE_LOCAL = re.compile(r"^\W*(?:なし|無し|特になし|特にありません|ありません|不要|完了|終了|以上|—|-|n/?a|none|nothing\s+further)\W*$"
                        r"|済み|済です|完了し|完了です|終わりです|これで(?:完了|終わ)|終わりました|終わったので|ありません|ゼロ|0\s*本|不要です"
                        r"|(?i:\bdid\s+everything\b|\ball\s+done\b|\bnothing\s+further\b)", re.I)
ALL_DONE = re.compile(r"(?:全部|すべて|全て|全件|[0-9０-９]+\s*本すべて)[^。]{0,10}?(?:直し(?!て(?:ください|ほしい))|完了|済|終わ|修正し|対応し)"
                      r"|依頼は(?:全て|すべて)?終わ|(?i:\bi\s+did\s+everything\b|\ball\s+done\b)")
PAST = re.compile(r"(?:ました|でした|済み|済)[。！]?$")
# the instruction itself said not to go on yet (「計画を立てて（実行はまだ）」「確認だけ」): stopping is the order
HOLD = re.compile(r"実行はまだ|まだ実行し(?:ない|なくて)|実行せず|実行しないで|着手しないで|着手はまだ|まだ(?:進め|着手|やら|手を付け)(?:ない|なくて|ずに)"
                  r"|計画(?:だけ|のみ)|案(?:だけ|のみ)|提案(?:だけ|のみ)|確認だけ|質問だけ|見るだけ|調べるだけ|待って|止めて|ストップ|中断して|一旦止")
# an instruction that orders work which can leave something open. 「教えて」「考えて」「計画を立てて」「調べて」
# 「確認して」 order an answer, not a batch of work: offering more after them is not a stall.
ACTION_ORDER = re.compile(r"(?:進め|すすめ|続け|やっ|直し|作っ|書い|まとめ|入れ|足し|変え|消し|実行し|対応し|修正し|反映し|改稿し"
                          r"|置い|使っ|実装し|更新し|追加し|処理し|検証し|移し|片づけ|片付け|仕上げ|作成し|整理し|適用し)て"
                          r"|お願い|やれ|しろ|せよ|しなさい|全部|すべて|残り|^(?:はい|OK|ok|うん|了解|GO|go)\b", re.M)
# the instruction bounded the batch (「まず最初の2つ」「次の2本」「1ファイルだけ」「5本目まで」): naming the next batch
# after finishing this one is the plan, not a stall. 「できるだけ10本以上」「残りをすべて」 bound nothing.
BOUNDED = re.compile(r"(?:まず|最初の|はじめの|初めの|次の|今回は?|この)[^。\n、]{0,12}?(?:[0-9０-９]+|[一二三四五六七八九十])\s*(?:つ|本|件|個|冊|回|科目|記事|行)"
                     r"|(?:[0-9０-９]+|[一二三四五六七八九十])\s*(?:つ|本|冊|回)目(?:まで)?|(?:[0-9０-９]+|[一二三四五六七八九十])\s*[^\s。、]{0,4}?(?:だけ|のみ)")
NA_LABEL = re.compile(r"(?m)^\W{0,4}Next Action\W{0,4}[:：]")


def _instruction_exempt(prompt):
    p = re.sub(r"<pasted_content.*?(?:</pasted_content>|$)", " ", prompt or "", flags=re.S)
    return bool(HOLD.search(p) or BOUNDED.search(p) or not ACTION_ORDER.search(p))


def _units(text):
    """Sentences / bullet items; a （…） right after 「。」 stays with its sentence."""
    out = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*(?:[-*・]|\d+[.)．])\s*", "", line).strip()
        for s in re.split(r"(?<=[。！？!?])(?![（(])|(?<=[.])\s+(?=[A-Z])", line):
            s = s.strip().strip("*").strip()
            if s:
                out.append(s)
    return out


def _stake_here(s):
    for m in STAKE.finditer(s):
        if not NEG_AFTER.search(s[m.end():]):
            return True
    return False


def stalled(answer, prompt=""):
    """Return (kind, sentence) when the closing stops on a continuation Claude could decide, else None."""
    if _instruction_exempt(prompt):
        return None
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    a = re.sub(r"`[^`\n]*`", " ", a)
    a = re.sub(r"「[^」]{0,200}」", "「」", a)
    a = re.sub(r"(?m)^\s*>.*$", " ", a)
    labels = list(NA_LABEL.finditer(a))
    # from the FIRST Next Action label (an earlier one can hold the stall, 「…進めます。／Next Action: なし」)
    tail = a[labels[0].start():] if labels else a[-300:]
    # the 留保 / 代替案 lines are the answer's caveats, not its next step, and never an excuse
    tail = re.sub(r"(?m)^\W{0,4}(?:留保|代替案|推奨)\W{0,4}[:：].*$", " ", tail)
    if ALL_DONE.search(a[-600:]) and not REMAIN_COUNT.search(tail):
        return None
    in_na, last = False, ""
    for raw in tail.split("\n"):
        if NA_LABEL.match(raw):
            in_na = True
            raw = NA_LABEL.sub("", raw, count=1)
        elif not raw.strip():
            in_na = False       # the section is the label's paragraph (and the bullets right under it)
            continue
        if re.match(r"^\s*\|", raw):
            continue            # a table row (deliverables, request mapping) is not the next step
        for s in _units(raw):
            prev, last = last, s
            q, o = PROCEED_Q.search(s), OFFER.search(s)
            if not (in_na or q or o or REMAIN_POS.search(s)):
                continue
            if _stake_here(s) or WAIT.search(s) or DECIDE.search(s):
                continue
            if CHOICE.search(prev + s if q else s):
                continue
            # a statement of fact in the section (「この節の更新は止まっています」「〜などです」) names no work left
            if not (q or o) and not REMAIN_POS.search(s) and re.search(r"(?:です|ています|ていません|ません|でした)[。！]?$", s):     # 「A案とB案があります。どうしますか？」
                continue
            if not o and (ASK.search(s) or re.search(r"ください|下さい", s)) and not REMAIN_COUNT.search(s):
                continue        # a request to the user: v3's job, not a stall
            if DONE_LOCAL.search(s) and not REMAIN_COUNT.search(s):
                continue
            if PAST.search(s) and not q and not REMAIN_POS.search(s):
                continue
            if re.search(r"(?:何か|気になる点|違え|問題が)[^。]{0,10}(?:あれば|ば)", s) and not o:
                continue
            return ("ask" if q else "offer" if o else "announce", s)
    return None


def read_turn_full(tp):
    """(prompt, ts, final text, [(tool name, input json)]) of the last turn.
    final = every text block after the last tool call; if that is a stub
    (「以上」), the block before it is included -- 2026-10-15 the hand-off sat
    in the block above a bare 「以上」."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, events = None, "", []
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            prompt, pts, events = _text(d.get("message")).strip(), d.get("timestamp", ""), []
        elif d.get("type") == "assistant":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        events.append(("tool", b.get("name") or "", json.dumps(b.get("input"), ensure_ascii=False)))
                    elif b.get("type") == "text" and (b.get("text") or "").strip():
                        events.append(("text", "", b["text"].strip()))
    return (prompt, pts) + final_and_tools(events)


def final_and_tools(events):
    """events: [("tool", name, input) | ("text", "", text)] in order."""
    tools = [(n, i) for k, n, i in events if k == "tool"]
    last_tool = max([i for i, e in enumerate(events) if e[0] == "tool"], default=-1)
    finals = [e[2] for e in events[last_tool + 1:] if e[0] == "text"]
    if len("".join(finals)) < 40:
        before = [e[2] for e in events[:last_tool + 1] if e[0] == "text"]
        finals = before[-1:] + finals
    return "\n\n".join(finals), tools


def main():
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
    prompt, pts, answer = read_turn(tp)
    hit = decide(answer) if prompt else None
    batch = None if hit or not prompt else decide_batch(answer)
    v3, final = None, ""
    if prompt and not hit and not batch:
        _p, _t, final, tools = read_turn_full(tp)
        v3 = unattempted(final, tools)
    if v3 and v3[0] == "batch":
        batch, v3 = v3[1], None
    stall = None
    if prompt and not hit and not batch and not v3:
        stall = stalled(final, prompt)
    if not hit and not batch and not v3 and not stall:
        return
    # keyed on the prompt's timestamp too: the same words sent again later
    # (「再開して」) are a new instruction and must be checked again
    key = hashlib.sha1((pts + (prompt or "")).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_") + "_" + key)
    if os.path.exists(mark):
        return          # already blocked once for this instruction
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    if batch:
        reason = ("【決定の一括依頼（1回のみ）】回答の締めで、ユーザーに複数の決定をまとめて求めている（%s）。"
                  "決定を頼む前に、1項目ずつ次の順で仕分けよ。"
                  "①既に決まっていないか: リポの正典（BUSINESS.md・戦略文書・tasks.md・CLAUDE.md・過去のレポート）を検索し、"
                  "決まっていれば「決定済み」と書いて聞かない。"
                  "②今決める必要があるか: 必要になる時点（その操作の直前など）まで聞かない。"
                  "③推測・既定値で進められないか: 取り消せる設定・あとから変えられる選択は、根拠を添えて既定値を置き、"
                  "「変えたければ言ってください」で済ませる。"
                  "残るのは、取り消せない・本人しか知らない・既決定を変える、のどれかに当たる項目だけで、"
                  "推奨と理由を添えて1つずつ聞く（CLAUDE.md §11.2）。仕分けの結果を書き直して回答し直せ。" % batch)
        sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))
        return
    if stall:
        kind, sent = stall
        what = {"ask": "続けてよいかをユーザーに尋ねて止まっている",
                "offer": "ユーザーの希望・指示があれば続けると申し出て止まっている",
                "announce": "残りの作業を自分の次の手順として書いたまま止まっている"}[kind]
        reason = ("【丸投げ検査v4・自分で決められる続行で停止（1回のみ）】回答の締めが、%s（「%s」）。"
                  "ユーザーにしか決められない争点（取り消せない操作・削除・お金・公開や送信・本人の意思や好み・権限が無い・"
                  "外部の出来事を待つ）が締めに書かれていない。その続行は自分で決めてよいので、このターンで続けて実行し、"
                  "終わった結果を報告し直せ（CLAUDE.md Top10 の6「事前確認しない」・§11.2）。止める理由が本当にあるなら、"
                  "どの争点か（例: 「削除は取り消せないため」「課金が発生するため」「/compact が必要なため」）を締めに1文で書け。"
                  % (what, sent[:120]))
        sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))
        return
    if v3:
        kind, sent = v3
        if kind == "compute":
            reason = ("【丸投げ検査v3・計算の依頼（1回のみ）】回答がユーザーに計算を求めている（「%s」）。計算は自分で行う"
                      "（CLAUDE.md §11.2）。入力の数値をシート・リポ・メールから取得し、Python で計算して結果を書け。"
                      "入力が本当に取得できない場合だけ、その入力の値だけを、どこを探して見つからなかったかを添えて聞け。" % sent[:120])
        elif kind == "decision":
            reason = ("【丸投げ検査v3・決定依頼（1回のみ）】回答がユーザーに決定を求めているが、推奨が書かれていない（「%s」）。"
                      "ラベル（本人の判断）だけでは通らない。①リポの正典で既に決まっていないか検索し、②取り消せる選択なら"
                      "根拠付きの既定値を置いて自分で進め、③本当に本人の決定が要るものだけ「推奨: 〜（理由）」を添えて1つずつ聞け"
                      "（CLAUDE.md §11.2）。" % sent[:120])
        else:
            reason = ("【丸投げ検査v3・試行の証跡なし（1回のみ）】回答がユーザーに作業・提供・計算を求めている（「%s」）が、"
                      "このターンのツール実行履歴に、自分で取得・計算・書き込みを試みた跡が無い（依頼の語を含むツール呼び出し・"
                      "ToolSearch・MCP 呼び出しのいずれも無い）。先に自分で試せ: 計算は Python で実行、データはシート・メール・"
                      "ドライブ・リポを MCP/検索で取得、書き込みは MCP/ブラウザ操作で実施。試して詰まった場合だけ、"
                      "どこで詰まったか（エラー文）を添えて依頼を残せ（ラベルだけでは通らない）。" % sent[:120])
        sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))
        return
    reason = ("【丸投げ検査（1回のみ）】回答の締めがユーザーへの作業・承認の依頼になっている（「%s」）。"
              "ユーザーに頼んでよいのは ①権限がない ②本人しか知らない情報 ③本人の意思決定 だけ（CLAUDE.md §11.2）。"
              "該当しないなら、今このターンで自分で実行し、結果を報告し直せ（確認・操作・結果取得・明らかなミスの修正・"
              "推奨が明確な次の手順は自分でやる）。該当するなら依頼は残してよいが、その行に理由を"
              "「（権限）」「（本人のみ）」「（本人の判断）」のいずれかで明記せよ。" % hit)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
