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

Not covered: promises made by subagents; whether the scheduled prompt actually does the promised
work (the block message asks for the job id and time to be written in the answer so the user can see it).

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
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

NUM = r"(?:\d+(?:[.,]\d+)?|[一二三四五六七八九十数半]+)"
DELAY = re.compile(
    NUM + r"\s*(?:〜\s*" + NUM + r"\s*)?(?:分|時間|日|週間?)(?:ほど|くらい|ぐらい|程度|ばかり)?(?:後|ご|経っ|たっ|置いて|おいて|空けて)"
    r"|時間を(?:置|お|空)いて|しばらく(?:して|後|経っ|たっ)|後ほど|のちほど|あとで"
    r"|\d{1,2}[:：]\d{2}\s*(?:ごろ|頃|以降|過ぎ|に|から)|\d{1,2}時(?:半)?(?:ごろ|頃|以降|過ぎ)"
    r"|明日|明朝|明晩|今夜|今晩|夕方に|週明け|来週|翌朝|夜に"
    r"|(?:終わっ|終え|完了し|済ん|揃っ|そろっ|出|上がっ|落ち着い|回っ|戻っ|止まっ)たら|(?:終わり|完了|終了|到着)次第"
    r"|(?:が|を)?(?:終わる|終える|完了する|出る)(?:まで待って|のを待って)")
# the agent itself will act (future, first person). Sentence-final.
SELF_VERB = re.compile(r"(?:し|かけ|入れ|入れ直し|回し|直し|確かめ|確認し|報告し|伝え|見|調べ|測り|測り直し|起動し|再開し|"
                       r"走らせ|流し|やり|行い|進め|書き|送り|まとめ|消し|片付け|仕上げ|検査し|点検し)"
                       r"ます(?:ね|よ)?[。．!！]?\s*$")
TO_USER = re.compile(r"ください|下さい|お願いします|お願いいたします|してほしい|していただ|頂けますか|もらえますか|ませんか")
# waiting on the user is not a lapse: their next message wakes the agent
USER_WAIT = re.compile(r"(?:指示|返事|返信|回答|決定|判断|承認|許可|OK|ＯＫ|一言|連絡|確認結果|ログイン|入力)"
                       r"(?:が|を|は)?(?:あれば|あったら|いただければ|いただいたら|もらえたら|もらったら|来たら|届いたら|次第|頂ければ)"
                       r"|(?:決まっ|決めて|選んで|答えて|教えて|押して|済ませて|終えて|ログインして)(?:たら|いただいたら|もらったら|くれたら)"
                       r"|(?:いただければ|いただけたら|頂ければ|もらえれば|くだされば|いただき次第)"
                       r"|(?:ユーザー|あなた|ご本人|本人)(?:が|の)")
# the actor is a system, not the agent (「毎朝のダイジェストが自動で判定し直します」)
SYSTEM_ACTOR = re.compile(r"自動(?:で|的に|実行|起動)|ひとりでに|勝手に")
# a caveat line describes a risk, not a promise
CAVEAT_LINE = re.compile(r"^\s*\**\s*(?:留保|代替案|注意|リスク)\s*\**\s*[:：]")
NO_TIMER = re.compile(r"(?:タイマー|予約|スケジュール)[^。\n]{0,12}(?:設定しない|入れない|置かない|不要|しない理由|使わない)")

SCHED_TOOL = re.compile(r"^(?:CronCreate|ScheduleWakeup|RemoteTrigger)$|schedul|cron|trigger|wakeup", re.I)
UNSCHED_TOOL = re.compile(r"CronDelete|CronList|list|delete|get_", re.I)
SCHED_CMD = re.compile(r"schtasks(?:\.exe)?\s+/create|Register-ScheduledTask|\bat\s+\d{1,2}:\d{2}\b|crontab\s", re.I)


def _strip(text):
    text = re.sub(r"```.*?```", "", text or "", flags=re.S)
    return re.sub(r"`[^`\n]*`", "X", text)


def promises(final):
    """Sentences in the final message that promise a later action by the agent itself."""
    out = []
    for line in _strip(final).splitlines():
        if CAVEAT_LINE.search(line):
            continue
        line = re.sub(r"^\s*(?:[-*>]|\d+[.)])\s*", "", line).replace("**", "")
        for s in re.split(r"(?<=[。！!？?])", line):
            s = s.strip()
            if not s or not DELAY.search(s) or not SELF_VERB.search(s):
                continue
            if TO_USER.search(s) or USER_WAIT.search(s) or SYSTEM_ACTOR.search(s):
                continue
            out.append(s)
    return out


def _is_sched(name, inp):
    if name in ("Bash", "PowerShell"):
        return bool(SCHED_CMD.search(str((inp or {}).get("command") or "")))
    return bool(SCHED_TOOL.search(name)) and not UNSCHED_TOOL.search(name.split("__")[-1])


def woken(turn_calls, session_calls):
    """True when something will wake the agent: a scheduler / watcher in this turn, a background
    task (any turn) whose completion notice has not arrived yet, or a cron job created earlier in
    the session and not deleted since. A background task that already finished wakes nobody
    (2026-11-16: the allcheck run had notified before the promise was written)."""
    for name, inp in turn_calls:
        if _is_sched(name, inp) or name == "Monitor":
            return True
    # only tasks started in THIS turn: ids from earlier turns go stale (compaction, killed sessions;
    # measured 2026-11-16: 5 never-notified ids from days earlier made every later promise pass)
    bg = {i.get("id") for n, i in turn_calls if n == "__bg__"}
    done = {i.get("id") for n, i in session_calls if n == "__done__"}
    if bg - done:
        return True
    created = sum(1 for n, _ in session_calls if n == "CronCreate")
    deleted = sum(1 for n, _ in session_calls if n == "CronDelete")
    return created > deleted


def decide(final, turn_calls, session_calls=()):
    if NO_TIMER.search(final or ""):
        return None
    p = promises(final)
    if not p or woken(turn_calls, session_calls):
        return None
    return p


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
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def turns(lines):
    """Yield (prompt, timestamp, calls, final, session_calls_before_and_in_turn) per turn."""
    prompt, pts, calls, final, sess = None, "", [], "", []
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            if prompt is not None:
                yield prompt, pts, calls, final, list(sess)
            prompt, pts, calls, final = _text(d.get("message")).strip(), d.get("timestamp", ""), [], ""
        elif d.get("type") == "assistant":
            t = _text(d.get("message")).strip()
            if t:
                final = t
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    got = (b.get("name", ""), b.get("input") or {})
                    calls.append(got)
                    sess.append(got)
                    if got[1].get("run_in_background") is True:
                        calls.append(("__bg__", {"id": b.get("id")}))
                        sess.append(("__bg__", {"id": b.get("id")}))
        elif d.get("type") == "user":
            # background-task completion notice (promptSource=system) and the tool results of
            # commands the harness moved to the background on timeout
            t = _text(d.get("message"))
            if "<task-notification" in t and re.search(r"<status>(?:completed|failed|killed|stopped|error)", t):
                for i in re.findall(r"<tool-use-id>([^<]+)</tool-use-id>", t):
                    sess.append(("__done__", {"id": i.strip()}))
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and "moved to the background" in json.dumps(b.get("content"), ensure_ascii=False):
                        calls.append(("__bg__", {"id": b.get("tool_use_id")}))
                        sess.append(("__bg__", {"id": b.get("tool_use_id")}))
    if prompt is not None:
        yield prompt, pts, calls, final, list(sess)


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
