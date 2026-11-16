# -*- coding: utf-8 -*-
"""Stop hook: an answer that promises to do something LATER must set the thing that wakes it up.

WHY (2026-11-16, user request for every repo)
---------------------------------------------
「時間を置いてもう一度やるっていうか、時間を置いて何かタスクを行うっていう時に、いつもあなたが
実行できていないミスをいろんなリポジトリで繰り返しているので、すべてのリポジトリでそれができる
ようにしておいてね」
and the turn before:
「2時間後に検査をもう一度かけるって言ってるんだったら、ちゃんと自分でやってほしい。タイマーを
設定して実行するみたいな機能もあるでしょ。それをClaude Codeが設定し忘れてるよね？」

The agent cannot act after its final message unless something wakes it. Twice in that session the
final answer ended with 「2時間ほど後に、305本の検査をもう一度全部かけ…ます」 /
「17本が終わったら（約2時間後）検査をもう一度かけ…ます」 and nothing was scheduled, so the promise
silently lapsed until the user asked 「どうなった？」. delegation_guard v4 even pushed the other way
(「このターンで続けて実行し」), which cannot work for a wait measured in hours.

WHAT IT DOES
------------
Looks at the main agent's final message of the turn. A sentence is a DEFERRED PROMISE when it has
  - a delay: N分/時間/日 後・経ったら, 時間を置いて, HH:MM ごろ, 明日/今夜/週明け, 後ほど/あとで,
    or an event: 終わったら/完了したら/終わり次第/結果が出たら/揃ったら, and
  - the agent as the actor: the sentence ends in a first-person future verb (〜します/かけます/
    報告します/確認します …), not a request to the user (ください/お願いします), not past (ました).
It passes when something will wake the agent:
  - a scheduler call in this turn or a not-yet-deleted one earlier in the session
    (CronCreate, ScheduleWakeup, RemoteTrigger, any *schedul*/*cron*/*trigger* MCP tool,
     schtasks /create or Register-ScheduledTask in a shell command), or
  - a watcher started in this turn (Monitor, a shell/Agent call with run_in_background=true),
or when the wait is on the USER (ご指示があれば / 決まったら / 返事をいただいたら …), or the final
message states why no timer is set (タイマーを設定しない理由 / 予約しない: …).
Otherwise blocks once per instruction and tells the agent which mechanism to use.

v2 (2026-11-16, after an adversarial Fable run: v1 missed 75/77 crafted promises and stopped 50/51
harmless sentences): wider delay words (後で・追って・次第・〜てから・翌日・今日中・2h後 …), clause-level
analysis (a request to the user in a later clause no longer hides the promise), quotes / code / noun
modifiers (「3日後の日付」「07:00 に実行されたジョブ」) and passive / progressive / possibility endings
excluded, scheduler tools on an allowlist of create verbs (list / query / disable do not count), CronCreate
counted net of CronDelete and of one-shot jobs already fired, background tasks from earlier turns
counted only within 6 hours, dev servers / watchers never counted, subagents (Agent, SendMessage) count.
Measured: crafted set 114/121 caught, 74/74 harmless passed; 30 days of real turns 0.68% fired.

Not covered: promises made by subagents; a promise split across two sentences (「2時間かかります。
その後、検査をかけます」); whether the scheduled prompt actually does the promised work (the block
message asks for the job id and time to be written in the answer so the user can see it).

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

NAME = "deferred_action_guard"
TAIL_BYTES = 16 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

# v2 (2026-11-16, after the Fable attack: 75/77 misses, 50/51 false stops on its crafted set).
NUM = r"(?:\d+(?:[.,]\d+)?|[一二三四五六七八九十数半]+)"
UNIT = r"(?:分|時間|日|週間?|か月|ヶ月|h|hr|hrs|min|mins)"
DELAY = re.compile(
    r"(?:約|あと|およそ)?" + NUM + r"\s*(?:[〜~～-]\s*" + NUM + r"\s*)?" + UNIT + r"(?:ほど|くらい|ぐらい|程度|ばかり)?"
    r"(?:後|経っ|たっ|置いて|おいて|空けて|あけて|ごろ|したら|して(?:から)?|以内|経過|が経|が過ぎ)"
    r"|時間を(?:置いて|おいて|空けて|あけて)|少し(?:して|後|経っ|たっ|時間)|しばらく(?:して|後|経っ|たっ)"
    r"|後ほど|のちほど|あとで|後で|追って|その(?:時|とき|際|時点)(?!は)|次回|次の(?:セッション|回|ターン|周)|週末"
    r"|\d{1,2}[:：]\d{2}\s*(?:ごろ|頃|以降|過ぎ|に|から|の)|\d{1,2}時(?:半)?(?:ごろ|頃|以降|過ぎ|に)"
    r"|明日(?![香葉菜美])|明朝|明晩|今夜|今晩|夕方|週明け|来週|翌朝|翌日|翌週|夜に|朝に|午後に|午前中に|昼に|数日|後日|今日中|本日中"
    r"|(?:実行|完了|終了|処理|検査|作業|反映|公開|再起動|更新)後"
    r"|(?:終わっ|終え|完了し|済ん|揃っ|そろっ|出|上がっ|落ち着い|回っ|戻っ|止まっ|届い|来)たら"
    r"|(?:出|揃い|そろい|分かり|わかり|届き|返り|終わり|戻り|入り|でき|済み|まとまり)次第|を待って|待ってから|(?:終わっ|終え|済ん|完了し|揃っ|そろっ)てから|一晩"
    r"|\b(?:in \d+ (?:min(?:ute)?s?|hours?|days?)|tomorrow|tonight|later|once\b[^.]{0,40}\b(?:finish(?:es)?|complete[sd]?|(?:is|are) done))\b",
    re.I)
# the agent itself will act: a future / volitional predicate at the end of the clause
SELF_END = re.compile(r"(?:(?<!てい)(?<!でい)ます(?:ね|よ)?|ておきます|でおきます|てみます|でみます|予定です|つもりです|ことにします|しましょう)\s*$"
                      r"|(?:する|行う|かける|進める|見る|直す|送る|伝える|確かめる|調べる|回す|流す|書く|出す|やる|報告する|確認する)\s*$"
                      r"|(?:再検査|再実行|再確認|再開|確認|報告|検査|実行|対応|集計|反映)(?:予定)?\s*$"
                      r"|\b(?:I(?:'ll| will)|we(?:'ll| will))\b|^\s*will\b", re.I)
# predicates that describe a state, a passive, a possibility or a recommendation, not the agent's act
NOT_SELF = re.compile(r"(?:され|られ|になり|があり|がい|でき|残り|かかり|わかり|分かり|なり|りえ|得|勧め|推奨し|げ|見え)ます\s*$")
TO_USER_END = re.compile(r"(?:ください|下さい|お願いします|お願いいたします|ませんか|いただけますか|もらえますか)\s*$")
TO_USER = re.compile(r"(?<!せ)(?:して|て)(?:ほしい|いただ|もらえ)")
USER_WAIT = re.compile(r"(?:指示|返事|返信|回答|決定|判断|承認|許可|OK|ＯＫ|一言|連絡|確認結果|入力)"
                       r"(?:が|を|は)?(?:あれば|あったら|いただければ|いただいたら|もらえたら|もらったら|来たら|届いたら|次第|頂ければ)"
                       r"|(?:決まっ|決めて|選んで|答えて|教えて|押して|済ませて|ログインして)(?:たら|いただいたら|もらったら|くれたら)"
                       r"|(?:いただければ|いただけたら|頂ければ|もらえれば|くだされば|いただき次第)"
                       r"|届いたら|(?:ユーザー|あなた|ご本人|本人|依頼者|管理者|担当者|先方|相手|誰か)(?:が|から)[^。]{0,16}(?:たら|れば|次第)"
                       r"|(?:レビュー|フィードバック|指摘|コメント|返答|データ|資料)(?:が|を)?(?:戻っ|届い|来|返っ|揃っ|そろっ|もらっ|いただい|頂い)たら"
                       r"|ご(?:提供|要望|指示|返信|依頼|判断|承認|希望)")
# a system / program is the subject, or the sentence is a standing description
SYSTEM_ACTOR = re.compile(r"自動(?:で|的に|実行|起動)|ひとりでに|毎(?:日|朝|晩|週|時|回)|ごとに"
                          r"|(?:cron|スクリプト|ジョブ|ワーカー|プロセス|ルーティン|ダイジェスト|bot|ボット|GAS|トリガー|システム|Actions|CI|"
                          r"ワークフロー|ウォッチドッグ|関数|メソッド|ガード|ツール|"
                          r"サーバー|PC|スケジューラ|フック|定時確認|監視|巡回|工程|supervisor|routine)[^。、]{0,12}(?:が|は)"
                          r"|^[A-Za-z][\w .\-]{1,30}\s*(?:が|は)", re.I)
NOW = re.compile(r"今から|いまから|これから|今すぐ|直ちに|この後すぐ|続けて|このまま|このターンで|いま(?![すせし])|今のうちに|今は|今、|right now", re.I)
RISK = re.compile(r"ないと[、,]|としても|(?:が|で)あれば|れば[、,]|得る|うる|可能性|おそれ|恐れ|かもしれ|場合(?:は|に)|と再発|すると|なると|リスク|前提|想定|仮定|もし|なら(?:ば)?[、,]")
HABIT = re.compile(r"今後は|以後は|これからは|必ず|常に|毎回|都度|運用に|ようにします|ルール")
# a line that is not the agent speaking for itself
SKIP_LINE = re.compile(r"^\s*>|^\s*(?:手順|Step|ステップ|例)\s*\d*\s*[:：.)]", re.I)
NO_TIMER = re.compile(r"(?:タイマー|予約|スケジュール)(?:を)?(?:設定|入れ)?(?:し)?ない理由\s*[:：]")
NEXT_ACTION = re.compile(r"^\s*\**\s*Next Action\s*\**\s*[:：]", re.I)
# the time word modifies a noun or a relative clause, not the agent's predicate:
# 「3日後の日付」「07:00 に実行されたジョブ」「後ほど述べる理由」「明日以降の分」
MODIFIER = re.compile(r"\s*(?:の(?:日付|日時|時刻|日|値|データ|版|会議|資料|予定表)|以降の|以前の|までの"
                      r"|に?\s*[^、。をでにはが\s]{0,10}(?:[一-龥][ぁ-ん]?[うくぐすつぬぶむる]|する|される|した|された|れた|った|いた|んだ)"
                      r"[一-龥ァ-ヶー]{1,8}(?:を|と|の|は|が|に|により))")

SCHED_CMD = re.compile(r"(?:^|[;&|\n(]\s*)(?:schtasks(?:\.exe)?\s+/create\b|Register-ScheduledTask\b|at\s+(?:now\b|\d)|crontab\s+(?!-l))", re.I | re.M)
LONG_BG = re.compile(r"\b(?:npm run (?:dev|start|serve)|yarn (?:dev|start)|serve\b|http\.server|uvicorn|flask run|--watch|tail -f|watch\b)", re.I)


def _strip(text):
    text = re.sub(r"```.*?```", "", text or "", flags=re.S)
    text = re.sub(r"`(\d{1,2}[:：]\d{2})`", r"\1", text)
    text = re.sub(r"`[^`\n]*`", "X", text)
    return re.sub(r"「[^」\n]*」|『[^』\n]*』|\"[^\"\n]*\"|“[^”\n]*”", "X", text)


def _clauses(s):
    # 「…かけますので、お待ちください」「2分おいて取得した値も同じだったので、そのまま報告します」
    return [c for c in re.split(r"(?<=ます)(?:ので|から|が|けど|けれど)[、,]?|(?:ので|から|が|けど|けれど)[、,]", s) if c.strip()]


def _delay(c):
    for m in DELAY.finditer(c):
        rest = c[m.end():]
        g = m.group(0)
        if rest[:1] == "の" and not re.search(r"\d|後|次第|ごろ|頃|次回|次の", g) and not re.match(r"の(?:朝|夜|夕方|午前|午後|昼|晩|うち|時点)", rest):
            continue    # 「明日の会議用の資料」
        if MODIFIER.match(rest):
            continue
        return True
    return False


def _tail(c):
    while True:
        n = re.sub(r"(?:（[^（）]*）|\([^()]*\))(?:[^\w]|_)*$", "", c)
        n = re.sub(r"(?:[^\w]|_)+$", "", n)
        if n == c:
            return c
        c = n


def promises(final):
    """Sentences that promise a later action by the agent itself."""
    out = []
    for line in _strip(final).splitlines():
        if SKIP_LINE.search(line):
            continue
        if line.strip().startswith("|"):
            line = "、".join(x.strip() for x in line.strip().strip("|").split("|") if x.strip() and not re.match(r"^[-: ]+$", x.strip()))
        na = bool(NEXT_ACTION.search(line))
        line = re.sub(r"^\s*(?:[-*・]|\d+[.)])\s*(?:\[[ xX]\]\s*)?", "", line).replace("**", "").replace("__", "")
        for s in re.split(r"(?<=[。！!？?])|(?<=\.)\s", line):
            s = s.strip()
            body = _tail(re.sub(r"^(?:[^\w]|_)+", "", s))
            if not body:
                continue
            for c in _clauses(body):
                c = _tail(c)
                if not c or TO_USER_END.search(c) or not _delay(c) or NOW.search(c):
                    continue
                self_end = SELF_END.search(c) or (na and not re.search(r"(?:ます|ました|です|でした|だ|ている|でいる)$", c))
                if not self_end or NOT_SELF.search(c) or TO_USER.search(c) or USER_WAIT.search(c) or SYSTEM_ACTOR.search(c) or RISK.search(c) or HABIT.search(c):
                    continue
                out.append(s)
                break
    return out


def _is_sched(name, inp):
    inp = inp or {}
    if name in ("Bash", "PowerShell"):
        return bool(SCHED_CMD.search(str(inp.get("command") or "")))
    if name in ("ScheduleWakeup", "Monitor"):
        return not inp.get("stop")
    if name == "RemoteTrigger":
        return bool(re.match(r"(?:create|add|schedule|update|run|set)", str(inp.get("action") or "create"), re.I)) and inp.get("enabled") is not False
    if name.startswith("mcp__") and re.search(r"schedul|cron|remote_?trigger|routine", name, re.I):
        verb = name.split("__")[-1]
        return bool(re.search(r"(?:^|_)(?:create|add|schedule|set|run|update)(?:_|$)", verb, re.I)) and inp.get("enabled") is not False
    return False


def _ts(x):
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _oneshot_fired(inp, now):
    """A one-shot CronCreate ("M H D Mo *", recurring=false) whose local time has already passed."""
    if inp.get("recurring", True) is not False:
        return False
    f = str(inp.get("cron") or "").split()
    if len(f) != 5 or not all(x.isdigit() for x in f[:4]):
        return False
    import datetime as _dt
    try:
        n = _dt.datetime.fromtimestamp(now or __import__("time").time())
        at = _dt.datetime(n.year, int(f[3]), int(f[2]), int(f[1]), int(f[0]))
    except Exception:
        return False
    return at <= n


def woken(turn_calls, session_calls):
    """True when something will wake the agent:
    - a scheduler or watcher anywhere in the session (ScheduleWakeup, Monitor, RemoteTrigger create,
      schtasks /create, scheduling MCP create) -- they outlive the turn that set them;
    - live CronCreate jobs: created minus deleted > 0 over the session, one-shot jobs already fired excluded;
    - a background task not yet notified, started in this turn or within 6 hours of now
      (older never-notified ids are stale: compaction, killed sessions); dev servers / watchers never notify."""
    now = max([_ts(i.get("ts")) or 0 for n, i in turn_calls if n == "__now__"] or [0])
    for name, inp in session_calls:
        if _is_sched(name, inp):
            return True
    if any(n == "SendMessage" for n, _ in turn_calls):
        return True     # a resumed subagent notifies when it finishes
    live = sum(1 for n, i in session_calls if n == "CronCreate" and not _oneshot_fired(i, now))
    if live > sum(1 for n, _ in session_calls if n == "CronDelete"):
        return True
    done = {i.get("id") for n, i in session_calls if n == "__done__"}
    long_ids = set()
    for seq in (turn_calls, session_calls):
        prev = None
        for n, i in seq:
            if n == "__bg__" and prev is not None and LONG_BG.search(str(prev.get("command") or "")):
                long_ids.add(i.get("id"))
            prev = i if n != "__bg__" else None
    if {i.get("id") for n, i in turn_calls if n == "__bg__"} - done - long_ids:
        return True
    for n, i in session_calls:
        if n == "__bg__" and i.get("id") not in done and i.get("id") not in long_ids:
            t = _ts(i.get("ts"))
            if t is None or not now or now - t < 6 * 3600:
                return True
    return False


def decide(final, turn_calls, session_calls=()):
    sess = list(session_calls)
    for c in turn_calls:
        if c not in sess:
            sess.append(c)
    if NO_TIMER.search(final or ""):
        return None
    p = promises(final)
    if not p or woken(turn_calls, sess):
        return None
    return p


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _result_text(b):
    c = b.get("content")
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c if isinstance(x, dict))
    return c if isinstance(c, str) else ""


def _is_prompt(d):
    """A prompt the user typed -- not a tool result or harness notification."""
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def turns(lines):
    """Yield (prompt, timestamp, calls, final, session_calls_before_and_in_turn) per turn."""
    prompt, pts, calls, final, sess, now = None, "", [], "", [], ""
    task2tool, tool_since = {}, False
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            if prompt is not None:
                yield prompt, pts, calls + [("__now__", {"ts": now})], final, list(sess)
            prompt, pts, calls, final = _text(d.get("message")).strip(), d.get("timestamp", ""), [], ""
        elif d.get("type") == "assistant":
            now = d.get("timestamp") or now
            t = _text(d.get("message")).strip()
            if t:   # every text written after the last tool call (the answer may span several blocks)
                final = (final + "\n" + t) if (final and not tool_since) else t
                tool_since = False
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    got = (b.get("name", ""), b.get("input") or {})
                    tool_since = True
                    calls.append(got)
                    sess.append(got)
                    if got[1].get("run_in_background") is True or (got[0] in ("Agent", "Task") and got[1].get("run_in_background") is not False):
                        calls.append(("__bg__", {"id": b.get("id"), "ts": now}))
                        sess.append(("__bg__", {"id": b.get("id"), "ts": now}))
        elif d.get("type") == "user":
            # background-task completion notice (promptSource=system) and the tool results of
            # commands the harness moved to the background on timeout
            t = _text(d.get("message"))
            if "<task-notification" in t and re.search(r"<status>(?:completed|failed|killed|stopped|error)", t):
                ids = re.findall(r"<tool-use-id>([^<]+)</tool-use-id>", t)
                ids += [task2tool[k.strip()] for k in re.findall(r"<task-id>([^<]+)</task-id>", t) if k.strip() in task2tool]
                if not ids:     # a notice we cannot map: it is for the oldest background task still open
                    done = {i.get("id") for n, i in sess if n == "__done__"}
                    ids = [i.get("id") for n, i in sess if n == "__bg__" and i.get("id") not in done][:1]
                for i in ids:
                    sess.append(("__done__", {"id": i.strip()}))
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        for k in re.findall(r"(?:with ID|\(ID): ?([A-Za-z0-9_-]+)", _result_text(b)):
                            task2tool[k] = b.get("tool_use_id")
                    if isinstance(b, dict) and b.get("type") == "tool_result" and re.match(
                            r"\s*Command did not complete within \S+ timeout and was moved to the background \(ID: ", _result_text(b)):
                        calls.append(("__bg__", {"id": b.get("tool_use_id"), "ts": now}))
                        sess.append(("__bg__", {"id": b.get("tool_use_id"), "ts": now}))
    if prompt is not None:
        yield prompt, pts, calls + [("__now__", {"ts": now})], final, list(sess)


def read_turn(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    last = None
    for t in turns(data):
        last = t
    return last


REASON = ("【時間を置いた作業の予約漏れ（1回のみ）】最終回答が、後で自分が作業すると約束している（「%s」）が、"
          "このターンに自分を起こす仕組みを設定していない。回答を終えると、起こされない限り何もできない。"
          "ユーザー指示（2026-11-16・全リポ）:「時間を置いて何かタスクを行うっていう時に、いつもあなたが実行できていない"
          "ミスをいろんなリポジトリで繰り返しているので、すべてのリポジトリでそれができるようにしておいてね」。"
          "今このターンで、次のどれかを設定してから回答し直せ。"
          "①時刻で起きる: CronCreate（このセッション内・最長7日・入力待ちの間に発火。一度きりは recurring=false）。"
          "②セッションを閉じても動かす: /schedule（RemoteTrigger・クラウド）か、Windows のタスク スケジューラ"
          "（schtasks /create）で処理そのものを起動する。"
          "③処理の終わりを待つ: その処理の完了まで待つコマンドを run_in_background で走らせる（終わると通知で起きる）か Monitor。"
          "回答には、設定したもの（ジョブ ID・次に動く時刻）を1文で書く。"
          "待つ相手がユーザーなら（ご指示があれば〜等）その旨を書けば通る。本当に予約しないなら「タイマーを設定しない理由: 〜」と書く。")


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
    t = read_turn(tp)
    if not t:
        return
    prompt, pts, calls, final, sess = t
    hit = decide(final, calls, sess)
    if not hit:
        return
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
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": REASON % hit[0][:120]}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
