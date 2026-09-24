# -*- coding: utf-8 -*-
"""Chat-answer length guard (UserPromptSubmit + PostToolUse + Stop).

WHY THIS EXISTS (2026-09-24, measured -- not chosen)
----------------------------------------------------
User: 「全体的にチャットの回答が長すぎます … 20〜50%短縮を希望 … 途中回答も
もっと短くしてほしい（後で『間違ってました』となることが結構ある）」.

Replay of 820 real turns (2026-08-24 .. 09-24, all projects):
    final answer        median 1,754 chars, p90 2,928
    intermediate text   13.2 messages/turn; 1.84M chars in total, MORE than
                        all final answers combined (1.38M)
    turns where a later intermediate retracts an earlier one: 68
    Stop-hook re-answers (18% of turns): final median 2,089 vs 1,691 (+24%)

The last row decides the design. Text already shown cannot be withdrawn. A
Stop hook that BLOCKS an over-long answer does not shorten it -- the harness
keeps the long version on screen and the model appends a second one. So:

  * UserPromptSubmit  states the budget BEFORE anything is written, plus last
                      turn's overrun (the feedback loop). User choice
                      2026-09-24: 「次ターンで警告」, not block.
  * PostToolUse       checks the intermediate message written just before the
                      tool call (1 line, <=100 chars, no conclusions/tables)
                      and warns inside the same turn, so the NEXT intermediate
                      is short. It cannot un-show the one already written.
  * Stop              measures the final answer, records it, never blocks.

BUDGET IS KEYED ON WHAT THE TURN DID, NOT ON THE PROMPT
-------------------------------------------------------
turn_classify.py measured that 56% of this user's prompts carry pasted prose,
so prompt keywords misclassify. The turn's tool calls cannot be faked by
pasting:  wrote files / committed -> 作業報告;  web / subagent / >=5 reads ->
調査・設計;  otherwise -> 質問への回答.

What is counted: the answer body with markdown-link URLs removed. The
deliverables table and the 留保/代替案/Next Action tail are measured
separately (user choice: tail <=300 chars, each 1 line; table 説明 <=15 chars),
so the mandatory report format is never what pushes a turn over.

Budgets 600/1,000/1,500 were picked by replaying 576 real turns: implied
cut 46.7% / 29.7% / 22.1% (overall ~30%), inside the user's 20-50% band.
400 for 質問への回答 measured 62.6% -- outside the band, rejected.

Adversarial review (Fable, 2026-09-24) found 10 confirmed holes; each fix
below is tagged "Fable #N" at the line it changed, and each has a RED case
in tests/test_response_length_guard.py.

It never blocks and never exits non-zero. Calibration:
tests/calibrate_response_length_guard.py (replays real transcripts).
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

NAME = "response_length_guard"
BUDGET = {"answer": 600, "work": 1000, "research": 1500}
LABEL = {"answer": u"質問への回答", "work": u"作業報告", "research": u"調査・設計"}
TAIL_MAX = 300
TAIL_WINDOW = 15          # the tail is searched only in the last N non-empty lines
DESC_MAX = 15
ROW_ALLOW = 60            # per deliverables-table row; anything beyond counts as body
INTER_MAX = 100
INTER_TOTAL_MAX = 800     # 30 x 99-char one-liners must not escape (Fable #6)
INTER_WARN_PER_TURN = 2   # each warning costs context; stop after this many
TAIL_BYTES = 2 * 1024 * 1024
MAX_BACK_BYTES = 64 * 1024 * 1024   # Stop: read further back until the turn start
POST_TAIL_BYTES = 256 * 1024        # PostToolUse runs on every tool call
HIST_N = 10
STATE_DIR = os.environ.get("RLG_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state", NAME + "_turns")

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
RESEARCH_TOOLS = {"WebSearch", "WebFetch", "Agent", "Task", "Workflow"}
READ_TOOLS = {"Read", "Grep", "Glob"}
# A throwaway file in temp does not make a turn a 作業報告 (Fable #3).
SCRATCH_RE = re.compile(r"([\\/]te?mp[\\/]|scratchpad|AppData[\\/]Local[\\/]Temp)", re.I)
# Only a git command in command position -- not `echo "git commit"` (Fable #3).
COMMIT_RE = re.compile(
    r"(?:^|&&|;|\|\||\n)\s*(?:cd\s+\S+\s*(?:&&|;)\s*)?git\s+(?:-C\s+\S+\s+)?(?:commit|push)\b")

LINK_RE = re.compile(r"\[([^\]\n]*)\]\([^)\s]*\)")
URL_RE = re.compile(r"https?://[\x21-\x7e]+")      # ASCII only: stops at CJK
FENCE_RE = re.compile(r"^\s*(```|~~~)")
# 推奨 is NOT a tail label: §11 tells the model to write 推奨 mid-body (Fable #8).
TAIL_RE = re.compile(u"^\\s*(?:[-*]\\s*)?\\*{0,2}(留保|代替案|Next Action)\\*{0,2}\\s*[:：]")

# An intermediate message may say WHAT is being done, never WHAT WAS FOUND:
# a finding stated mid-turn is exactly the text that gets retracted later.
# Finding FORMS only -- 「間違いがないか確認します」 is a doing-statement (Fable #7).
CONCLUSION_JA = re.compile(
    u"(原因は|真因は|判明し(?:た|ました)|結論(?:は|として)|確定し(?:た|ました)|"
    u"分かりました|わかりました|分かった|問題ありません|問題なし[。.]|完了しました|"
    u"成功しました|失敗しました|誤りでした|間違(?:い|っ)(?:でした|ていました)|"
    u"訂正します|撤回します|^実は[、,]|でした[。.]?\\s*$)", re.M)
CONCLUSION_EN = re.compile(
    r"\b(root cause|turns out|it was caused by|is caused by|confirmed that|"
    r"the (?:bug|issue|problem|culprit) (?:is|was)|in conclusion|that fixed it|"
    r"now passes|all tests pass)\b", re.I)
PASSFAIL_RE = re.compile(r"\b(PASS|FAIL)(?:ED|ES|S)?\b")


def _visible(text):
    s = LINK_RE.sub(r"\1", text or "")
    s = URL_RE.sub("URL", s)
    return s.replace(u"​", "")


def _count(text):
    """Visible characters, newlines excluded (a blank line is not content)."""
    return len(re.sub(r"[\r\n]+", "", _visible(text).strip()))


def _is_boundary(row):
    """A genuine human prompt (not a tool result, hook feedback or meta row)."""
    if row.get("type") != "user" or row.get("isMeta"):
        return False
    c = (row.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return False
        if any(isinstance(b, dict) and b.get("type") == "image" for b in c):
            return True   # an image-only prompt is still a prompt (Fable #10)
        txt = " ".join(b.get("text", "") for b in c
                       if isinstance(b, dict) and b.get("type") == "text")
    else:
        txt = c if isinstance(c, str) else ""
    t = txt.lstrip()
    if not t or t.startswith("Stop hook feedback") or t.startswith("<local-command"):
        return False
    # Compaction summaries arrive as a user row; auto-compact can land mid-turn.
    if t.startswith("This session is being continued from a previous"):
        return False
    if t.startswith("<task-notification>") or t.startswith("<system-reminder>"):
        return False
    return True


def _parse(data):
    rows = []
    for ln in data.splitlines():
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def read_rows(path, tail_bytes=None, need_boundary=False):
    """Tail of the transcript. With need_boundary, keep doubling the window
    until a turn start is inside it (Fable #9: the biggest turns exceeded 2MB
    and were silently never measured)."""
    n = tail_bytes or TAIL_BYTES
    try:
        size = os.path.getsize(path)
    except Exception:
        return []
    while True:
        try:
            with io.open(path, "rb") as f:
                if size > n:
                    f.seek(size - n)
                    f.readline()
                rows = _parse(f.read().decode("utf-8", "replace"))
        except Exception:
            return []
        if (not need_boundary or size <= n or n >= MAX_BACK_BYTES
                or any(_is_boundary(r) for r in rows)):
            return rows
        n *= 2


def turn_events(rows):
    """Flatten the latest turn into [('text', s) | ('tool', name, input)]."""
    start = None
    for i in range(len(rows) - 1, -1, -1):
        if _is_boundary(rows[i]):
            start = i
            break
    if start is None:
        return None
    ev = []
    for r in rows[start + 1:]:
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and (b.get("text") or "").strip():
                ev.append(("text", b["text"]))
            elif b.get("type") == "tool_use":
                ev.append(("tool", b.get("name") or "", b.get("input") or {}))
    return ev


def classify(ev):
    reads = 0
    kind = "answer"
    for e in ev:
        if e[0] != "tool":
            continue
        name, inp = e[1], e[2]
        if name in WRITE_TOOLS:
            fp = inp.get("file_path") or inp.get("notebook_path") or ""
            if fp and not SCRATCH_RE.search(fp):
                return "work"
            continue
        if name in ("Bash", "PowerShell") and COMMIT_RE.search(inp.get("command") or ""):
            return "work"
        if name in RESEARCH_TOOLS or name.startswith("mcp__"):
            kind = "research"
        elif name in READ_TOOLS or name in ("Bash", "PowerShell"):
            reads += 1
    if kind == "answer" and reads >= 5:
        kind = "research"
    return kind


def split_final(text):
    """-> (body, tail, table_descs, table_excess).

    tail  = from the first 留保/代替案/Next Action label found in the LAST
            TAIL_WINDOW non-empty lines (outside code fences). Text moved far
            below the tail is therefore body again (Fable #8).
    table = the deliverables table. Each row may use ROW_ALLOW visible chars;
            the rest counts as body, whatever column it is stuffed in (#2).
    """
    lines = (text or "").splitlines()
    fenced, in_f = [], False
    for ln in lines:
        if FENCE_RE.match(ln):
            in_f = not in_f
            fenced.append(True)
            continue
        fenced.append(in_f)
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    window = set(nonempty[-TAIL_WINDOW:])
    cut = None
    for i, ln in enumerate(lines):
        if i in window and not fenced[i] and TAIL_RE.match(ln):
            cut = i
            break
    head_lines = lines if cut is None else lines[:cut]
    tail = "" if cut is None else "\n".join(lines[cut:])

    body_lines, descs, excess, in_tbl = [], [], 0, False
    for i, ln in enumerate(head_lines):
        s = ln.strip()
        if (not fenced[i] and s.startswith("|") and u"成果物" in s
                and (u"リンク" in s or u"開く" in s)):
            in_tbl = True
            continue
        if in_tbl and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if len(cells) >= 3:
                descs.append(_visible(cells[1]))
            excess += max(0, _count(s.replace("|", "")) - ROW_ALLOW)
            continue
        in_tbl = False
        body_lines.append(ln)
    return "\n".join(body_lines), tail, descs, excess


def inter_problem(text):
    """None if an intermediate message is fine, else a short reason."""
    v = _visible(text).strip()
    nl = [ln for ln in v.splitlines() if ln.strip()]
    if len(nl) > 1:
        return u"%d行" % len(nl)
    if len(v) > INTER_MAX:
        return u"%d字" % len(v)
    if re.search(r"^\s*(\||#{1,6}\s)", v, re.M):
        return u"表/見出し"
    for rx in (CONCLUSION_JA, CONCLUSION_EN, PASSFAIL_RE):
        m = rx.search(v)
        if m:
            return u"結論語「%s」" % m.group(1)
    return None


def analyze(ev):
    kind = classify(ev)
    last_tool = max([i for i, e in enumerate(ev) if e[0] == "tool"], default=-1)
    final = "\n\n".join(e[1] for e in ev[last_tool + 1:] if e[0] == "text")
    inters = [e[1] for e in ev[:last_tool + 1] if e[0] == "text"]
    body, tail, descs, excess = split_final(final)
    tail_lines = [ln for ln in tail.splitlines() if ln.strip()]
    res = {
        "kind": kind,
        "budget": BUDGET[kind],
        "body": _count(body) + excess,
        "tail": _count(tail),
        "tail_items": sum(1 for ln in tail_lines if TAIL_RE.match(ln)),
        "tail_lines": len(tail_lines),
        "long_descs": [d for d in descs if len(d) > DESC_MAX],
        "inter_n": len(inters),
        "inter_chars": sum(_count(t) for t in inters),
        "inter_bad": [(inter_problem(t), _visible(t).strip()[:40]) for t in inters
                      if inter_problem(t)],
    }
    res["violations"] = violations(res)
    return res


def violations(r):
    """Most severe first: on_prompt shows only the head of this list."""
    out = []
    if r["body"] > r["budget"]:
        out.append(u"本文 %d字／上限 %d字（%s・+%d%%）" % (
            r["body"], r["budget"], LABEL[r["kind"]],
            round(100.0 * (r["body"] - r["budget"]) / r["budget"])))
    if r["inter_chars"] > INTER_TOTAL_MAX:
        out.append(u"途中メッセージ合計 %d字／上限 %d字" % (r["inter_chars"], INTER_TOTAL_MAX))
    if r["inter_bad"]:
        why, ex = r["inter_bad"][0]
        out.append(u"途中メッセージ違反 %d/%d件（例: %s「%s…」）" % (
            len(r["inter_bad"]), r["inter_n"], why, ex))
    if r["tail"] > TAIL_MAX:
        out.append(u"留保・代替案・Next Action 計 %d字／上限 %d字" % (r["tail"], TAIL_MAX))
    if r["tail_items"] and r["tail_lines"] > r["tail_items"]:
        out.append(u"留保等が各1行でない（%d項目で%d行）" % (r["tail_items"], r["tail_lines"]))
    if r["long_descs"]:
        out.append(u"成果物表の説明 %d件が%d字超" % (len(r["long_descs"]), DESC_MAX))
    return out


# The class rule is stated; the classifier's mechanics are not (Fable #3:
# printing "a write makes it 1,000" is a recipe for inflating the budget).
RULES = (u"【回答の長さ上限】本文は 質問への回答600字／作業報告1,000字／調査・設計1,500字 以内"
         u"（区分は実際に行った作業で判定）。留保・代替案・Next Action は各1行・計300字以内、"
         u"成果物表の説明は15字以内。途中メッセージは1行100字以内で「何をしているか」だけ"
         u"（原因・結論・表は最終回答まで書かない）。"
         u"削る順: 自分の作業経緯→確認済みの細部→重複。残す: 結論・判断に効く数値・ユーザーがすること。")


def _state_path(ev, suffix=""):
    sid = ev.get("session_id") or "nosession"
    return os.path.join(STATE_DIR, hashlib.sha256(
        sid.encode("utf-8", "replace")).hexdigest()[:16] + suffix + ".json")


def _hist_path():
    return os.path.join(STATE_DIR, "history.jsonl")


def _load(p):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(p, obj):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".%d.tmp" % os.getpid()
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass


def _trend():
    """Median body/budget over the last HIST_N answers (the goal metric)."""
    try:
        with io.open(_hist_path(), encoding="utf-8") as f:
            recs = [json.loads(ln) for ln in f.readlines()[-HIST_N:] if ln.strip()]
        ratios = [r["body"] / float(r["budget"]) for r in recs if r.get("budget")]
        if len(ratios) >= 3:
            return int(round(100 * statistics.median(ratios))), len(ratios)
    except Exception:
        pass
    return None


def _emit(event_name, text):
    # ensure_ascii + binary write: CP932 kanji ending in 0x5C corrupt text JSON.
    payload = json.dumps({"hookSpecificOutput": {
        "hookEventName": event_name, "additionalContext": text}}, ensure_ascii=True)
    sys.stdout.buffer.write(payload.encode("ascii"))
    sys.stdout.buffer.flush()


def on_prompt(ev):
    st = _load(_state_path(ev))
    msg = RULES
    prev = st.get("violations") or []
    if prev:
        # Worst item + trend only. Listing every item every turn is wallpaper
        # (Fable #1: 93% of historical turns had at least one violation).
        msg += u"\n【前回】" + prev[0]
        if len(prev) > 1:
            msg += u" ほか%d件" % (len(prev) - 1)
        tr = _trend()
        if tr:
            msg += u"。直近%d回の本文は上限の中央値%d%%" % (tr[1], tr[0])
        msg += u"。今回はこの分を削ること。"
        _record_firing(NAME, ev)
    _save(_state_path(ev, "_inter"), {"warned": 0})
    _emit("UserPromptSubmit", msg)


def last_text_before_tool(rows):
    """The assistant text written before the most recent tool call (or batch).

    Parallel tool calls put several tool_use blocks after one text; skipping
    the whole batch is required, or 22.9% of real intermediates are never
    checked (Fable #4). Re-checks of the same text are deduped by the caller.
    """
    blocks = []
    for r in reversed(rows):
        if r.get("type") == "user" and _is_boundary(r):
            break
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        for b in reversed((r.get("message") or {}).get("content") or []):
            if isinstance(b, dict):
                blocks.append(b)
        if len(blocks) > 400:
            break
    seen_tool = False
    for b in blocks:  # newest first
        if b.get("type") == "tool_use":
            seen_tool = True
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            return b["text"] if seen_tool else None
    return None


def on_post_tool(ev):
    text = last_text_before_tool(read_rows(ev.get("transcript_path") or "",
                                           POST_TAIL_BYTES))
    if not text:
        return
    why = inter_problem(text)
    if not why:
        return
    p = _state_path(ev, "_inter")
    st = _load(p)
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]
    if st.get("warned", 0) >= INTER_WARN_PER_TURN or key in (st.get("keys") or []):
        return
    st["warned"] = st.get("warned", 0) + 1
    st["keys"] = (st.get("keys") or [])[-20:] + [key]
    _save(p, st)
    _record_firing(NAME, ev)
    _emit("PostToolUse", u"【途中メッセージ（%s）】途中は1行100字以内で「何をしているか」"
                         u"だけ書く。発見・原因・結論は最終回答にまとめる。" % why)


def on_stop(ev):
    ev_list = turn_events(read_rows(ev.get("transcript_path") or "",
                                    need_boundary=True))
    if ev_list is None:
        return
    r = analyze(ev_list)
    _save(_state_path(ev), {"violations": r["violations"], "kind": r["kind"],
                            "body": r["body"]})
    _save(_state_path(ev, "_inter"), {"warned": 0})
    if ev.get("stop_hook_active"):
        return  # a re-answer forced by another hook: history keeps the first
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(_hist_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": int(time.time()), "kind": r["kind"], "body": r["body"],
                                "budget": r["budget"], "inter": r["inter_chars"]}) + "\n")
    except Exception:
        pass
    if r["violations"]:
        _record_firing(NAME, ev)


def main():
    try:
        me = os.path.normcase(os.path.abspath(__file__))
        local = os.path.normcase(os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__))))
        if me != local and os.path.exists(local):
            return  # a repo-local copy is registered; let it run instead
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    name = ev.get("hook_event_name") or ""
    if name == "UserPromptSubmit":
        on_prompt(ev)
    elif name == "PostToolUse":
        on_post_tool(ev)
    elif name == "Stop":
        on_stop(ev)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
