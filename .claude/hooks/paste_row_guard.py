# -*- coding: utf-8 -*-
"""Stop hook: block a spreadsheet paste row in a format that breaks one-shot paste.

WHY (2026-10-05, the user corrected it twice in one turn sequence)
------------------------------------------------------------------
The user asked for a row to paste into the Positions sheet (Google Sheets,
on a phone). Two answers in a row broke the one-shot paste:

  (a) a TAB-separated row inside a ``` code block. The tabs did not survive
      the copy -- Sheets put the whole row into ONE cell
      (「貼り付け、一セルになるぞ」).
  (b) a Markdown table with a column-name header row (| A 入力日 | B くりっく
      枚数 | ... |), the separator, then the data row. Copying the table
      pasted the header as an extra row (「列名がいらねーよ」).

In between, a third answer offered a semicolon row + 「テキストを列に分割」 and a
7-row 列/項目/値 table -- the same class: anything that is not one row of
cells needs extra steps.

The format that pastes in one shot is a ONE-ROW Markdown table whose header
row IS the data, followed only by the separator line:

    | 2026-10-05 | 563 | 14032666 | 18210541 |  | 9560 | memo |
    |---|---|---|---|---|---|---|

WHAT IT DOES
------------
Only when a prose line of the final answer offers sheet paste content -- a
paste word (貼|コピペ|ペースト|paste) and a sheet word (シート|スプレッドシート|
Sheets|セル|列|N行) on the SAME line -- the table or code block next to that
line (the first one below it, at most 3 prose lines away and not past a
heading) is checked for:
  1. a code block with a delimited row: an inner TAB, or 3+ separators of
     「;」「,」 or 2+ spaces on a line that is not code;
  2. a Markdown table with >= 1 body row (rows after the separator).
Either one blocks the stop ONCE per instruction with the required format.
Blocks ABOVE the line are not checked: a closing 「上の1行を貼って」 sits next
to the 成果物 table, and the paste block itself is always introduced by a
line above it.

CALIBRATION (measured 2026-10-05, tests/calibrate_paste_row_guard.py, real
transcripts in ~/.claude/projects, the hook's own decide() imported):
    last 30 days : 376 answers, paste-offer lines in 5, fired 3 (0.80%)
    last 120 days: 1257 answers, fired 3 (0.24%)
All 3 firings are the 3 answers the user corrected on 2026-10-05 (recall
3/3, 0 false positives). The first version also fired on 「309行」 (a file's
line count) and 「文字列」 -- the sheet words were narrowed to remove both.

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

NAME = "paste_row_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

PASTE = re.compile(r"貼|コピペ|ペースト|paste", re.I)
# 「行」 alone would match 実行/行う/銀行 and 「列」 alone 配列/行列/文字列 -- both
# are restricted to their sheet senses. In calibration 「309行」 (a file's line
# count) and 「文字列」 fired, so only 1行/一行/N行目 count, and 字列 is excluded.
SHEET = re.compile(r"シート|スプレッドシート|Sheets?\b|セル"
                   r"|(?<![配行並系序直羅字])列(?!挙)"
                   r"|(?<![0-9０-９])[1１一]行(?!数)|[0-9０-９一二三]行目"
                   r"|(?:上の|下の|次の|同じ|空い(?:てい)?る|最終|新しい|各|値の)行")
FENCE = re.compile(r"^\s{0,3}(```+|~~~+)\s*([\w+-]*)")
SEP_ROW = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
CODE_LINE = re.compile(r"[={}]|=>|\b(?:function|var|let|const|return|def|import|if|for)\b")
GAP = 3          # prose lines allowed between the paste line and its block


def _blocks(answer):
    """Split the answer into ('prose', line) / ('code', lines) / ('table', rows)
    items, in order."""
    lines = (answer or "").replace("\r\n", "\n").split("\n")
    items, i = [], 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m:
            fence, body, i = m.group(1), [], i + 1
            while i < len(lines) and not lines[i].strip().startswith(fence[:3]):
                body.append(lines[i])
                i += 1
            items.append(("code", body))
            i += 1
            continue
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and SEP_ROW.match(lines[i + 1]):
            rows = [lines[i]]
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            items.append(("table", rows))
            continue
        items.append(("prose", lines[i]))
        i += 1
    return items


def _is_paste_line(line):
    s = re.sub(r"「[^」]{0,200}」|`[^`]*`", " ", line)   # quoted / inline code is not an offer
    return bool(PASTE.search(s) and SHEET.search(s))


def _code_problem(body):
    for ln in body:
        s = ln.strip()
        if not s or "|" in s:
            continue
        if re.search(r"\S\t", ln):
            return "コードブロック内のタブ区切り行"
        if CODE_LINE.search(s):
            continue
        for sep, label in ((";", "セミコロン"), (",", "カンマ"), (r" {2,}", "空白")):
            if len(re.findall(sep, s)) >= 3:
                return "コードブロック内の%s区切り行" % label
    return None


def decide(answer):
    """Return a short description of the broken paste format, or None."""
    items = _blocks(answer)
    for i, (kind, val) in enumerate(items):
        if kind != "prose" or not _is_paste_line(val):
            continue
        cands = []
        gap = 0                                   # the block below the line
        for k in range(i + 1, len(items)):
            kk, vv = items[k]
            if kk != "prose":
                cands.append(items[k])
                break
            if vv.lstrip().startswith("#"):
                break
            if vv.strip():
                gap += 1
                if gap > GAP:
                    break
        for kk, vv in cands:
            if kk == "code":
                p = _code_problem(vv)
                if p:
                    return p
            elif kk == "table" and len(vv) > 1:
                return "列名行や複数行のある表（本体 %d 行）" % (len(vv) - 1)
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
    if d.get("promptSource") == "system":
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


REASON = ("【貼り付け形式の検査（1回のみ）】シートに貼る内容が%sになっている。"
          "スマホの Google Sheets ではタブ区切りのコードブロックは1セルにまとまり、"
          "列名行のある表は列名まで1行として貼られる（2026-10-05 に2回指摘）。"
          "貼る行は、データそのものを見出し行にした1行だけの Markdown 表にし、その下は区切り行だけにすること"
          "（列名行・本体行・コードブロックは使わない）。例:\n"
          "| 2026-10-05 | 563 | 14032666 | 18210541 |  | 9560 | メモ |\n"
          "|---|---|---|---|---|---|---|\n"
          "空欄の列は「|  |」で残す。列の説明が必要なら表の外に文章で書く。この形式で回答し直せ。")


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
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": REASON % hit}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
