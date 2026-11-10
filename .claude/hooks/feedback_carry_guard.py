# -*- coding: utf-8 -*-
"""Feedback carry (UserPromptSubmit + PreToolUse + SessionStart + Stop): a correction the user makes while
delegated work is under way must reach that work, not only the chat answer.

WHY (2026-11-10, user: 「私の依頼や質問、指摘したあなたの間違いが全然更新されていない、踏まえられていない。やり直しなさい」)
---------------------------------------------------------------------------------------------------------------
Class (no proper nouns): ユーザーの指摘・依頼がチャットの回答では受け止められても、実行中・再開・次に渡す作業
（別の会話・サブエージェント・バックグラウンドの処理）に入らず、古い前提のまま結果が報告される。
Real case 2026-11-09 (host session d192b99a, container session 8516c259; times JST):
  09:22  the host wrote the brief of a delegated research round (r14_prompt.txt) and launched it in another
         Claude session (container\\start.ps1 -Prompt).
  10:42  the user sent 8 corrections about the method of that round (2択 -> 連続, 中央値 -> 累積の年率, 倍率の水準が
         多すぎ, 割引の線 ...). The answer met each in chat -- two with 「すでに〜です」 -- and closed with
         「回14は動いている最中で、途中から指示を足せません」. The round had in fact stopped at 09:56 (out of memory)
         and was waiting; nothing looked. request_ledger_guard was satisfied by the chat text.
  11:39  context compaction. (The summary DID keep 「after round 14: ledger row, re-judge」; it was not done.)
  15:13  the host resumed the round: 「再開してよい（依頼者の承認済みの回14の続き。確認は不要）…」 -- none of the
         10:42 corrections in it. The approval it cites predates the corrections.
  16:24  the result (all cash, 1.17%) was reported without saying it was measured with the rejected yardsticks.
  20:45  the user's complaint above.
Nothing carried the corrections from the chat to the handoff: every existing check reads the chat answer.
The same shape exists without containers: a background subagent (Agent runs in the background by default),
SendMessage to a running agent or another session, a Workflow, a scheduled / cloud prompt, `claude -p` /
`codex exec` -- each is briefed once, and later corrections reach it only if someone writes them in.

INVARIANT
---------
A user prompt that arrives after a RELATED handoff (it shares >= REL_MIN content words with the handoff's
text, within WINDOW) makes its correction / request sentences "stream feedback" (SF) items. An SF item
is closed only by
  * CARRY  -- a later related handoff (resume, SendMessage, re-launch, new brief) contains it
              (its words within one 400-char window), or
  * DISPOSITION -- a line 「未反映: <指摘> — 理由」(also 反映しない／変えない／変更しない) naming it. In an answer it
              closes the Stop checks only: the next handoff to the work must still carry it or say 未反映
              itself. Answering it in chat, or 「すでに対応済み」, closes nothing.
Checks:
  P  UserPromptSubmit -- the prompt created SF items: inject the list, the related handoff, and the rule
     (check the work's state with a tool; carry or 未反映).
  H  PreToolUse (Agent|Task|SendMessage|Workflow|RemoteTrigger|CronCreate|ScheduleWakeup, and Bash /
     PowerShell that start or resume another Claude / Codex session) -- a handoff that CONTINUES the work
     (resume / SendMessage / the same launcher or brief file) or names an item's own words, and leaves open
     SF items out, is DENIED with the list (a brief that cites an approval older than them is named); any
     other new handoff that merely shares words gets the list as context only. The same text is denied at
     most MAX_DENY times; an item let through that way stays undelivered for the report check.
  C  SessionStart (compact / resume) -- re-inject open SF items: the ledger is on disk, not in context.
  S  Stop (once per prompt) --
       - any answer related to the work while SF items are open: each must be carried or written as 未反映;
       - a REPORT of the work (a task notification, an Agent result, or result words) must name, in that
         answer, every SF item the work never received (未反映), so the user sees which yardstick produced it;
       - 「動いている最中／実行中／途中から指示を足せない」 about the work, while SF items are open, needs a
         look at the work's state in this turn (transcript / output / docker ps / git fetch ...).
Ledger: ~/.claude/state/feedback_carry/<session>.json (outside every repo; survives compaction).
Not covered: a background shell job whose brief is code, not text (its parameters change in files).

Calibration and red-green: tests/test_feedback_carry_guard.py, tests/replay_feedback_carry.py.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import request_ledger_guard as rlg  # noqa: E402  (shared item / keyword helpers)

try:
    from firing_log import record as _record_firing
except Exception:  # pragma: no cover
    def _record_firing(*_a, **_k):
        return False

NAME = "feedback_carry_guard"
STATE_DIR = os.environ.get("FCARRY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state", "feedback_carry")
WINDOW = 24 * 3600        # an open correction older than this is no longer about the running work
SEED_WINDOW = 12 * 3600   # a prompt is about a handoff only if that handoff is this recent (24h doubled the noise)
REL_MIN = 3               # shared content words that make a prompt and a handoff "the same work"
MAX_ITEMS = 12
MAX_DENY = 2              # the same item denies the same handoff text at most this many times (no deadlock)
MAX_HANDOFF_TEXT = 60000
TAIL_BYTES = 6 * 1024 * 1024

# a sentence that judges the work's method (a correction even without a request form)
FEEDBACK = re.compile(
    r"おかしい|違和感|不足|足りな|すぎ|過ぎ|妥当|べき|ベター|方が(?:良|よ|いい|妥当|自然|正し)|じゃないですか|ではないですか"
    r"|のでは(?:ない)?[かでし？?]|では[？?]|じゃない[？?か]|間違|誤り|誤って|違う|違います|ではなく|じゃなく|当たり前"
    r"|意味(?:が)?(?:わから|分から|不明)|意味不明|反映され|踏まえ|更新されて|やめて|[^\s→]\s*(?:→|⇒)\s*[^\s→]")
# a request for an explanation only (answered in chat; not a change to the work) -- wins over FEEDBACK
EXPLAIN_REQ = re.compile(r"(?:教えて|示して|見せて|説明して)(?:ください|下さい|ほしい|欲しい|くれ)?\s*[。？?]?\s*$")
EXPLAIN = re.compile(r"とは何|何の|どういう|どのよう|例を|ですか[？?]?$|ますか[？?]?$")
# a preface announcing the points of the next sentences (「違和感がある箇所があります。」「あと以下が意味不明。」)
PREFACE = re.compile(r"(?:箇所|点|ところ|もの|こと)が(?:あります|ある|あって|いくつか)[。]?$"
                     r"|^(?:あと|また|それと|まず)?[、,]?\s*(?:以下|下記|上記|次)(?:が|は|も|の)")
DISP = re.compile(r"未反映|反映しない|反映せず|反映していない|変えない|変更しない|入れない|入れていない|採らない|渡していない|渡さない")

HANDOFF_FIELDS = {
    "Agent": ("description", "prompt"), "Task": ("description", "prompt"),
    "SendMessage": ("to", "message", "content", "text"),
    "Workflow": ("name", "script", "args"),
    "RemoteTrigger": None, "CronCreate": None, "ScheduleWakeup": ("prompt", "reason"),
}
CONTINUE_TOOLS = {"SendMessage"}
EXEC = ("Bash", "PowerShell")
# a shell command that starts or resumes another agent session with a brief
LAUNCH = re.compile(
    r"(?i)\bclaude(?:\.exe|\.cmd)?\s+(?:[^|;&\n]*\s)?(?:-p|--print|-c|--continue|-r|--resume)\b"
    r"|\bcodex(?:\.exe|\.cmd)?\s+(?:exec|e|resume)\b"
    r"|[\"']claude[\"']\s*,\s*[\"']-(?:p|-print|c|-continue|r|-resume)[\"']"     # argv list in a .py launcher
    r"|\bclaude(?:\.exe|\.cmd)?\s+[\"'][^\"']{6,}"                                 # interactive claude "<prompt>"
    r"|(?:^|\s)-(?:Prompt|Continue)\b|--prompt\b"
    r"|docker\s+(?:exec|run)\b[^\n]*\bclaude\b")
RESUME = re.compile(r"(?i)(?:^|\s)-Continue\b|--continue\b|--resume\b|\bresume\b|再開|続き|続行|継続")
APPROVAL = re.compile(r"承認済み|承認された|承認を得|確認(?:は)?不要|了承済み|許可済み|approved")
_REF = re.compile(r"(?:[A-Za-z]:[\\/]|~[\\/])[^\s'\"`;|&<>(){}]+?\.(?:txt|md|ps1|sh|py|bat|cmd|prompt)\b"
                  r"|\$PSScriptRoot[\\/][\w.\-]+|(?<![\w\\/.\-])[\w.\-]+\.(?:txt|md|prompt)\b")

RUNNING = re.compile(
    r"動いている最中|動いています|実行中|走っています|走っている最中|進行中|回っています|稼働中|計算中|処理中"
    r"|途中から[^。]{0,14}(?:足せ|加え|変え|入れ|渡せ|伝え)(?:られ)?(?:ない|ません)"
    r"|(?:止め|中断し|割り込め)(?:られ)?(?:ない|ません)|まだ終わって(?:いない|いません|ない)|終わるまで待")
RESULT_WORDS = re.compile(r"結果|結論|判定値|終わりました|完了しました|終了しました|push しました|pushしました|報告します|報告です")
STATE_TOOLS = ("TaskOutput", "BashOutput", "Monitor", "ReadNotifications", "ListAgents", "TaskList", "TaskGet")
STATE_CMD = re.compile(
    r"(?i)docker\s+(?:ps|inspect|logs|top|stats)\b|Get-Process|tasklist|\bps\s+(?:aux|-ef)|\.jsonl\b|\.output\b|\.log\b"
    r"|git\s+(?:-C\s+\S+\s+)?(?:fetch|log)\b|LastWriteTime|\bgh\s+run\b")


# ------------------------------------------------------------------ text helpers
def _kw(text, cap=120):
    out = []
    for k in rlg.keywords(text or ""):
        if k in rlg.GENERIC_KW or len(k) < 2:
            continue
        out.append(k)
        if len(out) >= cap:
            break
    return out


def related(kws, text, need=REL_MIN):
    low = (text or "").lower()
    n = 0
    for k in kws:
        if k.lower() in low:
            n += 1
            if n >= need:
                return True
    return False


def _need(kws):
    return min(3, max(1, (len(kws) + 1) // 2))


def carried(item, text):
    """The item's words sit together (one 400-char window) in the text."""
    kws = [k.lower() for k in item["kw"]]
    if not kws or not text:
        return False
    low = text.lower()
    need = _need(kws)
    if len([k for k in kws if rlg._present(k, low)]) < need:
        return False
    step, width = 200, 400
    for i in range(0, max(1, len(low) - step), step):
        w = low[i:i + width]
        if len([k for k in kws if rlg._present(k, w)]) >= need:
            return True
    return False


def dispositioned(item, text):
    """A 「未反映: …」 line (or its next line) names the item."""
    lines = (text or "").splitlines()
    for i, ln in enumerate(lines):
        if not DISP.search(ln):
            continue
        block = [ln]
        for nx in lines[i + 1:i + 16]:      # 「未反映:」 as a heading: the bullets under it, up to a blank line
            if not nx.strip():
                break
            block.append(nx)
        if carried(item, ln + "\n" + block[1] if len(block) > 1 else ln):
            return True
        if len(block) > 2 and re.search(r"[:：]\s*$", ln) and any(carried(item, b) for b in block[1:]):
            return True
    return False


def items_of(prompt):
    """Correction / request sentences of the user's own text (and of a paste the user points at as the spec)."""
    t = rlg.user_text(prompt)
    extra, _h = rlg._spec_pastes(prompt)
    if extra:
        t += "\n" + extra
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    out = []
    for part in re.split(r"(?<=[。！？!?])|\n", t):
        s = part.strip(" \t　-*・>")
        if not s or len(s) > 220 or rlg.NOT_REQ.match(s) or s.startswith(("<", "|", "#")):
            continue
        fb = bool(FEEDBACK.search(s))
        if not (fb or rlg.REQ.search(s)) or EXPLAIN_REQ.search(s) or PREFACE.search(s):
            continue
        if not fb and (rlg._CONFIRM_Q.search(s) or EXPLAIN.search(s)):
            continue
        kw = _kw(s, 12)
        if not kw:
            continue
        out.append({"text": s[:200], "kw": kw, "fb": fb})
        if len(out) >= MAX_ITEMS:
            break
    return out


# ------------------------------------------------------------------ handoffs
def _read_file(path, files=None):
    if files is not None and path in files:
        return files[path]
    try:
        if os.path.getsize(path) > 256 * 1024:
            return ""
        with io.open(path, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _refs(text, base):
    out = []
    for m in _REF.finditer(text or ""):
        r = m.group(0)
        if r.startswith("$PSScriptRoot"):
            r = os.path.join(base or "", r[len("$PSScriptRoot") + 1:])
        elif not re.match(r"^(?:[A-Za-z]:[\\/]|~[\\/])", r):
            r = os.path.join(base or "", r)
        out.append(os.path.normpath(os.path.expanduser(r)))
    return out


def handoff_of(tool, inp, cwd="", files=None):
    """(text, resume, head) when this tool call hands work to another agent / session, else None."""
    inp = inp if isinstance(inp, dict) else {}
    if tool in HANDOFF_FIELDS:
        keys = HANDOFF_FIELDS[tool]
        if keys is None:
            parts = [v for v in _strings(inp)]
        else:
            parts = [inp.get(k) if isinstance(inp.get(k), str) else json.dumps(inp.get(k), ensure_ascii=False)
                     for k in keys if inp.get(k)]
        text = "\n".join(p for p in parts if p)
        if not text.strip():
            return None
        # a brief that says 「<file> を読み、そのとおりに作業して」 carries what that file says
        for ref in _refs(text, cwd)[:6]:
            body = _read_file(ref, files)
            if body:
                text += "\n" + body
        resume = tool in CONTINUE_TOOLS or bool(inp.get("resume")) or bool(RESUME.search(text[:300]))
        return text[:MAX_HANDOFF_TEXT], resume, _head(inp.get("description") or inp.get("prompt") or text)
    if tool not in EXEC:
        return None
    cmd = str(inp.get("command") or "")
    texts = [cmd]
    seen = set()
    frontier = [(p, cwd) for p in _refs(cmd, cwd)]
    for _depth in range(2):
        nxt = []
        for p, _b in frontier:
            if p in seen:
                continue
            seen.add(p)
            body = _read_file(p, files)
            if body:
                texts.append(body)
                nxt += [(q, os.path.dirname(p)) for q in _refs(body, os.path.dirname(p))]
        frontier = nxt
    allt = "\n".join(texts)
    if not LAUNCH.search(allt):
        return None
    inline = re.findall(r"@'(.*?)'@|@\"(.*?)\"@|\$\w+\s*=\s*\"([^\"]{80,})\"", cmd, flags=re.S)
    cands = [x for t in inline for x in t if x] + [x for x in texts[1:] if not LAUNCH.search(x)]
    head = max(cands, key=len) if cands else cmd
    return allt[:MAX_HANDOFF_TEXT], bool(RESUME.search(allt)), _head(head)


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            for s in _strings(v):
                yield s
    elif isinstance(o, list):
        for v in o:
            for s in _strings(v):
                yield s


# ------------------------------------------------------------------ ledger
def new_state():
    return {"prompts": [], "handoffs": [], "blocked": {}}


def _phash(text):
    return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()[:12]


def add_prompt(st, prompt, now, ctx=""):
    """Record a human prompt. Returns the SF items it created (with their related handoff).
    ctx = the assistant's last answer: a terse reply to an answer about the work (「中央値はやめて累積CAGRに」)
    shares few words with the brief itself, so the answer bridges the two."""
    ut = rlg.user_text(prompt)
    if not ut.strip():
        return [], None
    pk = _kw(ut)
    need = REL_MIN if len(pk) > 6 else 2      # a terse correction has few words
    bridge = bool(ctx) and related(pk, ctx, need)
    ck = _kw(ctx, 200) if bridge else []
    rel = [h for h in st["handoffs"] if now - h["ts"] <= SEED_WINDOW and h["ts"] < now
           and (related(pk, h["text"], need) or (bridge and related(ck, h["text"])))]
    items = []
    if rel:
        # in scope: a judgement of the method, or a request whose words appear in the related brief
        briefs = "\n".join(h["text"] for h in rel).lower()
        for it in items_of(prompt):
            if it["fb"] or any(k.lower() in briefs for k in it["kw"]):
                items.append(it)
    rec = {"ts": now, "h": _phash(prompt), "kw": pk, "sf": bool(items),
           "stream": [h["id"] for h in rel], "items": [dict(it, carried=False, disp=False) for it in items]}
    st["prompts"].append(rec)
    return rec["items"], (rel[-1] if rel else None)


def open_items(st, now, text=None, handoff=False):
    """[(prompt, item)] SF items neither carried nor dispositioned, optionally only those related to `text`.
    handoff=True: a 未反映 written only in a chat answer does not count -- the work still lacks the item, so the
    next handoff to it must carry it or say 未反映 itself (the user was told; the worker was not)."""
    out = []
    for p in st["prompts"]:
        if not p.get("sf") or now - p["ts"] > WINDOW:
            continue
        if text is not None and not _rel_prompt(st, p, text):
            continue
        for it in p["items"]:
            if not it.get("carried") and not (it.get("hdisp") if handoff else it.get("disp")):
                out.append((p, it))
    return out


def _rel_prompt(st, p, text):
    if related(p["kw"], text, REL_MIN if len(p["kw"]) > 6 else 2):
        return True
    for h in st["handoffs"]:
        if h["id"] in p.get("stream", []) and related(_kw(h["text"], 200), text):
            return True
    return False


def add_handoff(st, text, resume, now, kind, head="", key=""):
    hid = (st["handoffs"][-1]["id"] + 1) if st["handoffs"] else 1
    st["handoffs"].append({"id": hid, "ts": now, "text": text, "resume": resume, "kind": kind, "head": head,
                           "key": key})
    return hid


def handoff_key(tool, inp):
    """What identifies the same work on a later handoff: the recipient, or the launcher / brief file name."""
    inp = inp if isinstance(inp, dict) else {}
    if tool == "SendMessage":
        return str(inp.get("to") or "")
    if tool in EXEC:
        refs = [os.path.basename(r) for r in _refs(str(inp.get("command") or ""), "")]
        return refs[0] if refs else ""
    return ""


def warn_message(warn):
    return ("【指摘の受け渡し（確認）】この新しい依頼文は、先に渡した作業と語が重なるが、その後の指摘のうち %d 件が入っていない:\n%s\n"
            "同じ作業の続きなら依頼文に入れる。別の作業なら不要（止めない）。" % (len(warn), _list(warn)))


def _continues(st, p, text, resume):
    """The handoff continues the work the prompt was about: a resume / SendMessage, or the same launcher / brief
    file / recipient as a handoff of that work."""
    if resume:
        return True
    low = (text or "").lower()
    for h in st["handoffs"]:
        if h["id"] in p.get("stream", []) and h.get("key") and h["key"].lower() in low:
            return True
    return False


def check_handoff(st, text, resume, now):
    """Mark what this handoff carries. Returns (missing -> deny, warn -> context only, approval cited).
    deny: the handoff continues the work, or names the item's own words (it is about that point);
    warn: any other new handoff that merely shares words with the work (a side task: extraction, a review)."""
    missing, warn = [], []
    th = _phash(text)
    low = (text or "").lower()
    for p, it in open_items(st, now, text, handoff=True):
        if carried(it, text):
            it["carried"] = True
            continue
        if dispositioned(it, text):
            it["disp"] = it["hdisp"] = True
            continue
        kws = [k.lower() for k in it["kw"]]
        about = len([k for k in kws if k in low]) >= min(2, len(kws))
        if not (_continues(st, p, text, resume) or about):
            warn.append((p, it))
            continue
        dh = it.setdefault("denied_h", {})
        if dh.get(th, 0) >= MAX_DENY:
            continue                  # the same text denied twice: let it through, still undelivered for the report
        dh[th] = dh.get(th, 0) + 1
        missing.append((p, it))
    return missing, warn, bool(APPROVAL.search(text or ""))


def _hm(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    except Exception:
        return "?"


def _head(text, n=70):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:n] + ("…" if len(t) > n else "")


def _list(pairs, n=MAX_ITEMS):
    rows = ["  - 「%s」（%s の指示）" % (_head(it["text"], 90), _hm(p["ts"])) for p, it in pairs[:n]]
    if len(pairs) > n:
        rows.append("  - ほか %d 件" % (len(pairs) - n))
    return "\n".join(rows)


def deny_message(missing, approval, resume):
    msg = ("【指摘の受け渡し漏れ】この依頼文（%s）は、先に渡した作業と同じ作業への依頼だが、その後にユーザーが出した指摘・依頼の"
           "うち %d 件が入っていない:\n%s\n"
           "各件を依頼文に書き込む（どう変えるかまで）か、変えないものは依頼文に「未反映: <指摘> — 理由」と書いてから出し直せ。"
           "チャットで答えた・「すでに対応済み」と書いた指摘も、この依頼文に無ければ作業には届かない。"
           "（照合は語の一致で行う。指摘の文言を引いて書けば通る。）"
           % ("再開・続きの指示" if resume else "新しい依頼・出し直し", len(missing), _list(missing)))
    if approval:
        msg += ("\nこの依頼文は「承認済み」等を根拠にしているが、その承認は上の指摘より前のもの。指摘の後の再開・続行は、指摘を入れた"
                "内容でなければ承認の範囲に入らない。")
    return msg


# ------------------------------------------------------------------ stop
def stop_findings(st, answer, tools, notified, now):
    """(missing, report, running_sentence). Marks dispositions written in this answer."""
    rel_open = open_items(st, now, answer)
    report = notified or any(n in ("Agent", "Task", "TaskOutput") for n, _i in tools) or (
        bool(RESULT_WORDS.search(answer or "")) and _state_checked(tools))
    # undelivered = never carried into the work (a disposition in an earlier answer still counts for a report)
    undelivered = []
    for p in st["prompts"]:
        if not p.get("sf") or now - p["ts"] > WINDOW or not _rel_prompt(st, p, answer):
            continue
        for it in p["items"]:
            if not it.get("carried") and not it.get("reported"):
                undelivered.append((p, it))
    missing = []
    for p, it in (undelivered if report else rel_open):
        if dispositioned(it, answer):
            it["disp"] = True
            if report:
                it["reported"] = True
            continue
        missing.append((p, it))
    running = ""
    if rel_open:
        for s in re.split(r"(?<=[。！？\n])", answer or ""):
            if RUNNING.search(s) and not _state_checked(tools):
                running = s.strip()
                break
    return missing, report, running


def _state_checked(tools):
    for n, i in tools:
        i = i if isinstance(i, dict) else {}
        if n in STATE_TOOLS:
            return True
        if n in ("Agent", "Task") or (n in EXEC and i.get("run_in_background")):
            return True        # launched / relaunched this turn
        if n == "Read" and re.search(r"\.(?:jsonl|output|log)$", str(i.get("file_path", ""))):
            return True
        if n in EXEC and STATE_CMD.search(str(i.get("command", ""))):
            return True
    return False


def stop_message(missing, report, running):
    out = []
    if missing:
        if report:
            out.append("【指摘の未反映を報告に書く】この回答は、先に渡した作業の結果・状況を報告しているが、その作業には次の指摘・依頼"
                       "（作業を渡した後にユーザーが出したもの）が渡っていない:\n%s\n"
                       "結果は指摘の前の前提のまま出ている。報告の冒頭近くに各件を「未反映: <指摘> — 結果にどう効くか」と書くか、"
                       "指摘を入れて作業をやり直してから報告せよ。" % _list(missing))
        else:
            out.append("【指摘を作業へ渡す】先に渡した作業と同じ作業について、次の指摘・依頼がまだ作業に渡っていない:\n%s\n"
                       "チャットで答えても作業には届かない（「すでに対応済み」も同じ）。このターンで作業へ渡す（SendMessage・止めて出し"
                       "直す・再開の依頼文に書く）か、回答に「未反映: <指摘> — 理由」と1件ずつ書け。" % _list(missing))
    if running:
        out.append("【作業の状態を確かめずに断定】「%s」と書いたが、このターンに作業の状態（transcript・出力ファイル・docker ps・"
                   "git fetch など）を見ていない。見てから書け。動いていても、指摘は SendMessage や止めて出し直すことで渡せる。"
                   % _head(running, 80))
    return "\n".join(out)


def compact_message(pairs):
    return ("【指摘の受け渡し（圧縮をまたいで引き継ぐ）】先に渡した作業に、次の指摘・依頼がまだ渡っていない（台帳: %s）:\n%s\n"
            "その作業を再開・報告・出し直す前に、各件を依頼文に入れるか「未反映: <指摘> — 理由」と書くこと。"
            % (STATE_DIR, _list(pairs)))


def prompt_message(items, h):
    return ("【指摘の受け渡し】この指示は、%s に渡した作業（%s）と同じ作業への指摘を含む。チャットで答えるだけでは作業に届かない。"
            "作業の状態をツールで確かめ（動いているか・止まって待っているか）、次の各件を作業へ渡す（SendMessage・止めて出し直す・"
            "再開の依頼文に書く）か、回答に「未反映: <指摘> — 理由」と書け:\n%s"
            % (_hm(h["ts"]), h.get("head") or _head(h["text"], 60), "\n".join("  - 「%s」" % _head(it["text"], 90) for it in items[:8])))


# ------------------------------------------------------------------ live I/O
def _sid(ev):
    return re.sub(r"[^\w\-]", "_", str(ev.get("session_id") or "nosession"))[:80]


def _state_path(ev):
    return os.path.join(STATE_DIR, _sid(ev) + ".json")


def load_state(ev):
    try:
        with io.open(_state_path(ev), encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and "prompts" in st:
            return st
    except Exception:
        pass
    return new_state()


def save_state(ev, st):
    now = time.time()
    st["prompts"] = [p for p in st["prompts"] if now - p["ts"] <= 2 * WINDOW][-200:]
    keep = {i for p in st["prompts"] for i in p.get("stream", [])}
    st["handoffs"] = [h for h in st["handoffs"] if now - h["ts"] <= 2 * WINDOW or h["id"] in keep][-200:]
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path(ev) + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, _state_path(ev))
    except Exception:
        pass


def _rows_tail(tp):
    rows = []
    try:
        size = os.path.getsize(tp)
        with io.open(tp, "rb") as f:
            if size > TAIL_BYTES:
                f.seek(size - TAIL_BYTES)
                f.readline()
            for ln in f:
                try:
                    rows.append(json.loads(ln.decode("utf-8", "replace")))
                except Exception:
                    continue
    except Exception:
        pass
    return rows


def prompt_kind(d):
    """'human' / 'notify' / None for a transcript row."""
    if not isinstance(d, dict) or d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(c, str) or not c.strip():
        return None
    s = c.lstrip()
    if s.startswith("<task-notification"):
        return "notify"
    if d.get("isCompactSummary") or s.startswith(("Stop hook feedback", "This session is being continued", "<local-command",
                                                  "<command-name>", "[Your previous response", "Caveat:", "[Request interrupted")):
        return None
    if not rlg.user_text(c).strip():
        return None
    return "human"


def _text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def current_turn(rows):
    """(answer, tools, notified, turn key) of the last turn in the transcript rows."""
    start = None
    for i in range(len(rows) - 1, -1, -1):
        k = prompt_kind(rows[i])
        if k:
            start = i
            break
    if start is None:
        return "", [], False, ""
    tkey = str(rows[start].get("uuid") or rows[start].get("timestamp") or start)
    notified = prompt_kind(rows[start]) == "notify"
    tools, answer = [], ""
    for d in rows[start + 1:]:
        if not isinstance(d, dict) or d.get("isSidechain") or d.get("type") != "assistant":
            continue
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                tools.append((b.get("name") or "", b.get("input") or {}))
            elif b.get("type") == "text" and b.get("text", "").strip():
                answer = (answer + "\n\n" + b["text"]) if answer else b["text"]   # every text of the turn
    return answer, tools, notified, tkey


def _out(obj):
    # bytes, not text: a cp932 console stdout would raise on 「—」 and the hook would fall silent
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    sys.stdout.flush()


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        ev = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    name = ev.get("hook_event_name") or ""
    now = time.time()
    st = load_state(ev)
    if name == "UserPromptSubmit":
        ctx = ""
        if st["handoffs"]:
            rows = _rows_tail(ev.get("transcript_path") or "")
            if rows and prompt_kind(rows[-1]):
                rows = rows[:-1]              # the prompt being submitted, if already written
            ctx, _t, _n, _k = current_turn(rows)
        items, h = add_prompt(st, ev.get("prompt") or "", now, ctx)
        save_state(ev, st)
        if items:
            _record_firing(NAME, ev)
            _out({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                         "additionalContext": prompt_message(items, h)}})
        return 0
    if name == "PreToolUse":
        r = handoff_of(ev.get("tool_name") or "", ev.get("tool_input") or {}, ev.get("cwd") or "")
        if not r:
            return 0
        text, resume, head = r
        missing, warn, approval = check_handoff(st, text, resume, now)
        if missing:
            save_state(ev, st)
            _record_firing(NAME, ev)
            _out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": deny_message(missing, approval, resume)}})
            return 0
        add_handoff(st, text, resume, now, ev.get("tool_name") or "", head,
                    handoff_key(ev.get("tool_name") or "", ev.get("tool_input") or {}))
        save_state(ev, st)
        if warn:
            _out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": warn_message(warn)}})
        return 0
    if name == "SessionStart":
        pairs = open_items(st, now, handoff=True)
        if pairs and (ev.get("source") in ("compact", "resume", None)):
            _record_firing(NAME, ev)
            _out({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": compact_message(pairs)}})
        return 0
    if name == "Stop":
        if ev.get("stop_hook_active"):
            return 0
        if not any(p.get("sf") for p in st["prompts"]):
            return 0
        rows = _rows_tail(ev.get("transcript_path") or "")
        answer, tools, notified, tkey = current_turn(rows)
        if not answer:
            return 0
        missing, report, running = stop_findings(st, answer, tools, notified, now)
        if (missing or running) and not st["blocked"].get(tkey):
            st["blocked"][tkey] = now
            save_state(ev, st)
            _record_firing(NAME, ev)
            _out({"decision": "block", "reason": stop_message(missing, report, running)})
            return 0
        save_state(ev, st)
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
