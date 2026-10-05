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

WHAT IT DOES (v2, 2026-10-05, after an adversarial review)
----------------------------------------------------------
v1 required the paste word and the sheet word on the SAME line and checked
only the block right below it, in the LAST assistant message. An independent
review (Fable) built 16 realistic failures and 9 legitimate answers: v1
missed 15/16 and blocked 7/9. v2 therefore works on the whole turn and keys
on the shape of the DATA, not on the wording around it:

TRIGGER (turn level): the user prompt or this turn's assistant text has a
sheet word (シート|スプレッドシート|Sheets|spreadsheet|セル|Positions) AND the
assistant text has an offer word (貼|コピペ|ペースト|入力|記入|追加|copy|paste).
"This turn" = every assistant message since the last user prompt, joined:
the paste row may sit in a mid-turn message under a short closing message.

Then EVERY table, code block, inline code span, 4-space-indented line and
column-letter bullet list in the turn is inspected. Only DATA ROWS count:
  - table row  : first cell is a date (YYYY-MM-DD / YYYY/MM/DD). Generic
                 analysis tables (CAGR/MaxDD, 成果物/リンク) are not data rows.
  - code / inline / indented line: split by TAB, or by , ; | ｜ into >= 3
                 fields, and either date-first or a majority of numbers.
                 Fenced blocks tagged js/gs/sh/py/... are skipped; a line
                 that is not date-first is skipped when it looks like code
                 (call syntax, = , trailing ;, function/var/...).
BLOCK when:
  1. a table has a data row as a BODY row (header + >= 1 body row), incl.
     pipe rows with no separator at all and full-width ｜ tables;
  2. a header-only table of column names is followed by a table carrying
     data (column names split off into their own table);
  3. a data row sits in code / inline code / an indented block (only when
     the turn has a paste word proper: 貼|コピペ|ペースト|copy|paste);
  4. the cells are given one by one: a bullet list (- A: 2026-10-05 / - B:
     563 ...) or a vertical table (| A | 入力日 | 2026-10-05 |, 3+ rows).
A header-only table whose header IS the data row passes -- that is the
required format. Blocks ONCE per instruction.

CALIBRATION (measured 2026-10-05, tests/calibrate_paste_row_guard.py: every
real main-agent turn in ~/.claude/projects, rebuilt as the hook sees it, the
hook's own explain() imported; every fire hand-labelled):
    30 days : 376 turns, triggered 57 (15.2%), fired 4 (1.06%)  TP 4 / FP 0
    120 days: 1257 turns, triggered 226 (18.0%), fired 4 (0.32%) TP 4 / FP 0
The 4 fires: the 3 answers corrected on 2026-10-05, and a TAB row on
2026-09-28 (「そのままコピペできるやつ出力して」) -- the same defect, earlier.
The first v2 draft fired 9 times over 120 days with 5 FP: a diff hunk
(1,1368c1,1370), a yen amount (7,730,000円) and 3 sheet LOG rows quoted in
code blocks as evidence in turns that said 入力/追加 but offered no paste.
Hence NOT_A_ROW and the paste-word requirement for code rows.
v1 (a4c742d, same-line trigger) on the same tests: 11/34 -- all 15
adversarial failures and the mid-turn case missed, all 7 legit answers blocked.

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

SHEET = re.compile(r"シート|スプレッドシート|Sheets?\b|spreadsheet|セル|Positions", re.I)
OFFER = re.compile(r"貼|コピペ|ペースト|入力|記入|追加|copy|paste", re.I)
# Code / inline rows need a paste word proper: in calibration, sheet LOG rows
# quoted in code blocks as evidence (「2026-09-09|status|line|ok|...」) fired in
# turns that only said 入力/追加 -- the user was not being handed a row.
PASTE_OFFER = re.compile(r"貼|コピペ|ペースト|copy|paste", re.I)
NOT_A_ROW = re.compile(r"^[+\-−]?[¥$￥]?\d{1,3}(?:,\d{3})+(?:\.\d+)?\S{0,3}$"     # 7,730,000円
                       r"|^\d+(?:,\d+)?[acd]\d+(?:,\d+)?$"                       # diff hunk 1,1368c1,1370
                       r"|^@@ ")
FENCE = re.compile(r"^\s{0,3}(```+|~~~+)\s*([\w+-]*)")
CODE_LANGS = {"js", "gs", "javascript", "ts", "typescript", "sh", "bash", "zsh", "shell", "console",
              "py", "python", "powershell", "ps1", "pwsh", "json", "sql", "yaml", "yml", "html",
              "css", "diff", "mermaid", "java", "go", "rust", "c", "cpp", "ruby"}
PIPE = "|｜"
SEP_CELL = re.compile(r"^\s*:?[-－ー—]{3,}:?\s*$")
DATE = re.compile(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?$")
NUM = re.compile(r"^[+\-−]?[¥$￥]?\d[\d,]*(?:\.\d+)?(?:%|円|万|株|枚|ドル)?$")
CODE_SYNTAX = re.compile(r"\b[A-Za-z_][\w.]*\(.*\)|;\s*$|(?<![<>!=])=(?!=)|\b(?:function|var|let|const|def|import|return)\b|=>")
LETTER_ITEM = re.compile(r"^\s*[-*・]\s*([A-Z]{1,2})(?:列)?\s*[:：=]\s*(.*)$")


def _cells(line):
    s = line.strip()
    if s and s[0] in PIPE:
        s = s[1:]
    if s and s[-1] in PIPE:
        s = s[:-1]
    return [c.strip() for c in re.split(r"[|｜]", s)]


def _is_sep(line):
    cs = _cells(line)
    return bool(cs) and all(SEP_CELL.match(c) for c in cs if c != "") and any(c for c in cs)


def _date_first(cells):
    vals = [c.strip("*` ") for c in cells]
    return bool(vals) and bool(DATE.match(vals[0]))


def _data_fields(fields):
    """>= 3 fields and date-first or mostly numbers."""
    f = [x.strip().strip("\"'") for x in fields]
    if len(f) < 3:
        return False
    if DATE.match(f[0]):
        return True
    nonempty = [x for x in f if x]
    return len(nonempty) >= 3 and sum(1 for x in nonempty if NUM.match(x) or DATE.match(x)) * 2 > len(nonempty)


def _splits(line):
    """Every way of cutting the line into >= 3 fields (TAB, | ｜, comma, semicolon).
    All are tried: a memo field with 「1,425株」 must not hide a ;-separated row."""
    s = line.strip()
    out = []
    for sep in ("\t", r"[|｜]", ",", ";"):
        parts = re.split(sep, s)
        if sep == r"[|｜]":
            parts = [p for i, p in enumerate(parts) if not (p.strip() == "" and i in (0, len(parts) - 1))]
        if len(parts) >= 3:
            out.append(parts)
    return out


def _data_line(line):
    """A code-like line carrying a delimited data row?"""
    s = line.strip()
    if not s or NOT_A_ROW.match(s):
        return False
    cuts = _splits(s)
    if any(DATE.match(f[0].strip().strip("\"'")) for f in cuts):
        return True                     # a date-first row is data even if the memo has (...)
    if CODE_SYNTAX.search(s):
        return False
    return any(_data_fields(f) for f in cuts)


def scan(text):
    """Split the turn's text into tables, code lines and bullet groups."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    tables, code, prose, bullets = [], [], [], []
    i = 0
    cur_b = []
    while i < len(lines):
        ln = lines[i]
        m = FENCE.match(ln)
        if m:
            fence, lang = m.group(1), (m.group(2) or "").lower()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence[:3]):
                body.append(lines[i])
                i += 1
            i += 1
            if lang not in CODE_LANGS:
                code.extend(body)
            continue
        st = ln.strip()
        if st and st[0] in PIPE:
            run = []
            while i < len(lines) and lines[i].strip() and lines[i].strip()[0] in PIPE:
                run.append(lines[i])
                i += 1
            # split the run into tables: a row followed by a separator starts one
            k = 0
            while k < len(run):
                if k + 1 < len(run) and _is_sep(run[k + 1]):
                    header, body = _cells(run[k]), []
                    k += 2
                    while k < len(run) and not (k + 1 < len(run) and _is_sep(run[k + 1])):
                        if not _is_sep(run[k]):
                            body.append(_cells(run[k]))
                        k += 1
                    tables.append((header, body))
                else:               # pipe rows with no separator: every row is a body row
                    body = []
                    while k < len(run) and not (k + 1 < len(run) and _is_sep(run[k + 1])):
                        if not _is_sep(run[k]):
                            body.append(_cells(run[k]))
                        k += 1
                    tables.append((None, body))
            continue
        if re.match(r"^(?: {4,}|\t)\S", ln) and not re.match(r"^\s*(?:[-*+]|\d+\.)\s", ln):
            code.append(ln)
        else:
            prose.append(ln)
        mb = LETTER_ITEM.match(ln)
        if mb:
            cur_b.append(mb.group(2).strip())
        elif st:
            if len(cur_b) >= 3:
                bullets.append(cur_b)
            cur_b = []
        i += 1
    if len(cur_b) >= 3:
        bullets.append(cur_b)
    for ln in prose:
        for span in re.findall(r"`([^`\n]+)`", ln):
            code.append(span)
    return tables, code, bullets


def triggered(text, prompt=""):
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)   # offer words inside code do not count
    return bool((SHEET.search(prompt or "") or SHEET.search(text or "")) and OFFER.search(t))


def explain(text, prompt=""):
    """(description of the broken paste format, the offending row) or (None, None)."""
    if not triggered(text, prompt):
        return None, None
    tables, code, bullets = scan(text)
    for n, (header, body) in enumerate(tables):
        for r in body:
            if _date_first(r):
                return "列名行のある表・複数行の表（データ行が本体行になっている）", " | ".join(r)
        if header is not None and not body and not _date_first(header) and len(header) >= 2:
            nxt = tables[n + 1] if n + 1 < len(tables) else None
            if nxt and ((nxt[0] and _date_first(nxt[0])) or any(_date_first(r) for r in nxt[1])):
                return "列名だけの表とデータの表に分かれた形", " | ".join(header)
        # the cells given one per row: | A | 入力日 | 2026-10-05 | ... (a vertical sheet row)
        rows = [r for r in body if r]
        if len(rows) >= 3 and sum(1 for r in rows if re.match(r"^[A-Z]{1,2}(?:列)?$", r[0])) >= 3                 and any(DATE.match(c) or NUM.match(c) for r in rows for c in r[1:]):
            return "セルを1行ずつ縦に並べた表", " / ".join(" | ".join(r) for r in rows[:3])
    strong = PASTE_OFFER.search(re.sub(r"```.*?```", " ", text or "", flags=re.S))
    for ln in (code if strong else []):
        if _data_line(ln):
            return "コードブロック・インラインコード内の区切り行", ln.strip()
    for b in bullets:
        if sum(1 for v in b if DATE.match(v) or NUM.match(v)) * 2 > len(b):
            return "セルごとの箇条書き", " / ".join(b[:4])
    return None, None


def decide(text, prompt=""):
    """Return a short description of the broken paste format, or None."""
    return explain(text, prompt)[0]


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
    """(last human prompt, its timestamp, ALL assistant text of this turn joined)."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, parts = None, "", []
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            prompt, pts, parts = _text(d.get("message")).strip(), d.get("timestamp", ""), []
        elif d.get("type") == "assistant":
            t = _text(d.get("message")).strip()
            if t:
                parts.append(t)
    return prompt, pts, "\n\n".join(parts)


REASON = ("【貼り付け形式の検査（1回のみ）】シートに貼る内容が%sになっている。"
          "スマホの Google Sheets ではタブ区切りのコードブロックは1セルにまとまり、"
          "列名行のある表は列名まで1行として貼られる（2026-10-05 に2回指摘）。"
          "貼る行は、データそのものを見出し行にした1行だけの Markdown 表にし、その下は区切り行だけにすること"
          "（列名行・本体行・コードブロック・箇条書きは使わない）。例:\n"
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
    prompt, pts, text = read_turn(tp)
    hit = decide(text, prompt) if prompt else None
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
