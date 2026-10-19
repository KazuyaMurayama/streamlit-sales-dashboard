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
    _N + r"(?:つ|点|件|項目|個|問)(?=\s*(?:を|について|——|―|（|\(|:|：|とも|すべて|全て|、(?!の)|,|あり|ある"
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
    r"|お願い(?:します|いたします|できますか|できれば)"
    r"|お待ち(?:して|し)(?:い|お)ります|お待ちしています"
    r"|(?:て|で)(?:いただ|頂)(?:く必要|けますか|きたい|ければ|けたら)"
    r"|(?:て|で)もら(?:う必要|えますか|いたい|えれば|えたら)"
    r"|ご(?:判断|指示|確認|共有|返信|連絡|回答|提供|手配)(?:を|ください|いただ|頂|お願い)"
    r"|お(?:知らせ|決め|送り|伝え)(?:ください|いただ|頂)"
    r"|(?:おっしゃって|言って|仰って)(?:いただ|頂|もら|くだされ)")
# Asking the user to read or review the deliverable is the deliverable's purpose.
# Fable QC 2026-10-19 (32.0% fired on 14 days): 「push しました。ご確認ください。」 and
# 「詳細は REPORT.md を確認してください」 point at a delivered result, not a hand-off.
READ_ONLY = re.compile(r"読んで|読み、|お読み|ご覧|目を通|見てください|見ていただ|見てほし|眺め|レビューして|比べ"
                       r"|^(?:ご確認|確認)(?:ください|下さい|をお願いします)[。！]?$"
                       r"|(?:\.md|\.html|\.csv|レポート|ファイル|リンク|成果物|URL|表|§\s*\d)[^。]{0,24}(?:ご確認|確認して|確認くだ)")
# a numbered step of a procedure the user asked for is not a request to them
STEP = re.compile(r"^(?:\d+[.)．、]|[①-⑳]|[-*・]\s*\d+[.)．])\s*")
DECISION = re.compile(r"決め|決定|判断|選ん|選択|選び|お選|採否|採用|可否|承認|方針|どちら|どれ|返して|返信|ご回答|回答して|指示")
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
    t = re.sub(r"「[^」]{0,200}」", "「」", t)
    t = re.sub(r"(?m)^\s*\|.*\|\s*$", " ", t)          # tables (deliverables rows)
    t = re.sub(r"(?m)^\s*>.*$", " ", t)                # quotes
    return t


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
NOT_AN_ACT = re.compile(r"(?:考え|思っ|みなし|捉え|ご理解|ご了承|ご安心|お待ち(?:くだ|下)"
                        r"|(?:完了|終了|終わる|処理|実行|通知|結果)(?:を|の)?お待ち)")
USER_ONLY_ACT = re.compile(r"入金|出金|送金|振込|振り込|購入|買っ|売っ|発注|注文|建玉を|ログイン|パスワード|署名|押印|郵送|送信|電話|"
                           r"窓口|受け取|支払|承認|接続を|拡張機能|再起動|操作して|サインイン|2段階|二段階|新しい会話|新しいセッション")


def requests(text):
    """Sentences that ask the user to do, send, compute, decide or wait for something."""
    out = []
    for s in _sentences(text):
        m = ASK.search(s)
        if not m or READ_ONLY.search(s) or FEEDBACK_INVITE.search(s) or STEP.match(s):
            continue
        act = s[max(0, m.start() - 14):m.end()]
        if NOT_AN_ACT.search(act) or USER_ONLY_ACT.search(act):
            continue
        out.append(s)
    return out


def attempted(sentence, tools):
    """True if a tool call of this turn plausibly tried what the sentence asks for."""
    kws = [k.lower() for k in keywords(sentence)]
    for name, inp in tools:
        if name in NON_ATTEMPT_TOOLS:
            continue
        if name == "ToolSearch" or name.startswith("mcp__"):
            return True               # explored means (the digest's 探索ログ)
        low = (inp or "").lower()
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
    recommend = bool(RECOMMEND.search(_clean(final)))
    for s in requests(final):
        if DECISION.search(s):
            if not recommend:
                return ("decision", s)
            continue
        if not attempted(s, tools):
            return ("action", s)
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
    v3 = None
    if prompt and not hit and not batch:
        _p, _t, final, tools = read_turn_full(tp)
        v3 = unattempted(final, tools)
    if not hit and not batch and not v3:
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
        _record_firing(NAME, ev)
        sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))
        return
    if v3:
        kind, sent = v3
        if kind == "decision":
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
        _record_firing(NAME, ev)
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
