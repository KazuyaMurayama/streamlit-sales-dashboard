# -*- coding: utf-8 -*-
"""Stop hook: block once when a turn reports "updated / fixed N things" without re-measuring them.

WHY (claude-governance CORRECTION_DIGEST_20261026 C04 「検証せず完了報告」, adopted 「採用してすすめて」)
-----------------------------------------------------------------------------------------------
Cause: after a batch update the agent did not re-measure the deliverables and reported the fact
that it edited them as the result. Real complaints (2026-10-22):
  - 「更新したはずの数十本に対して、もう一度確認してほしい…ちゃんと直していない印象です」
    (defect turn 2026-10-22T04:18 Soulful-Content: 「段階1の15本を書き直し、受理して push しました…
     FAIL は0件」; the rewrite itself was done by subagents, the main agent 「本文を読まず」 and never
     measured how hard the sentences were before vs after)
  - 「60％となるべきが、まだ18％など低いままでは？」
    (defect turn 2026-10-22T11:03: changed the ctx-meter denominator and reported
     「これで claude.ai と同じ%が出ます」 without looking at what the display actually showed)
  - 「各記事への更新に以下はちゃんと機能している？なぜ…判定が上がった行が少ないのか？」
    (defect turn 2026-10-22T04:15 evidence re-search: 「5本に反映」 with no before/after distribution)

INVARIANT (no proper nouns)
---------------------------
A turn that changed something (edit/write tool, writing shell command, or an edit delegated to a
subagent) and whose report claims the change is done for several targets (N本/N件/全…/各…) or claims
the visible effect (「これで…出ます／なります」) must show, AFTER the last change,
  (1) a call that measured the targets again (a non-writing read/run/check), and
  (2) in the report, before -> after numbers (「28本→23本」「18%→63%」「822から615px」、変更前/変更後の表), and
  (3) for several targets, which ones did NOT change (「未変更」「変わらなかった」「0件」「残り N 本」).
Otherwise block once per instruction.

Passes when the report says plainly that the change is not verified and does not claim the effect
(「未検証」「まだ確かめていない」… with no 「これで…」), or there is no completion claim.
Not covered: tool calls of subagents (separate transcripts); a measurement that measured the
wrong property (e.g. a FAIL count instead of the target property) -- only the before/after numbers
in the report make that visible to the reader.

CALIBRATED 2026-10-26 (calibrate_batch_verify_guard.py on all main turns in ~/.claude/projects):
  v2 after the Fable review (A1-A5, P1-P3 fixed; noun form, 件/カ所/ヶ所/項目, count and claim in
  different sentences, a ledger edit after the report, echo/clasp push are not measurement, tests N/N
  are before/after only for code, before/after table columns, 「N本（前回 M本）」, measuring Agent):
  30 days : 541 turns, 420 changed something, 101 claimed, 75 blocked (13.9% of turns)
  120 days: 1,621 turns, 1,138 changed, 148 claimed, 109 blocked (6.72% of turns)
  eye review of 40 random blocked turns (120 d): about 31 TP / 9 FP. FP kinds: a re-check stated in
  words or as a test result without before/after (「取得し直して確かめました」「FAIL 0 を確かめました」),
  a diagnosis sentence, a sync report. The 3 real complaint turns all block.

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

NAME = "batch_verify_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
READ_TOOLS = ("Read", "Grep", "Glob")
DOC_EXT = re.compile(r"\.(?:md|txt|html?|csv|tsv|docx?|json)$", re.I)
# shell commands that write files
SHELL_WRITE = re.compile(r"sed\s+-i|perl\s+-[a-z]*i|\.write\(|write_text|write_bytes|Set-Content|Out-File|Add-Content"
                         r"|WriteAllText|WriteAllLines|\btee\s|\brm\s|\bdel\s|Remove-Item|Rename-Item"
                         r"|\bgit\s+(?:apply|checkout\s+--|restore\b(?!\s+--staged))|\bmv\s|\bcp\s|Copy-Item|Move-Item"
                         r"|(?<![0-9&])>>?\s*[\"']?[\w$~./\\:-]+\.(?:md|py|js|json|txt|csv|ya?ml|html|gs|ts)\b"
                         r"|\bcode\s+--install-extension|\bnpm\s+(?:install|run\s+build)|\bvsce\s+package", re.I)
# shell commands that READ or RUN a check (only these count as a measurement; echo / clasp push /
# gh pr create / npm publish are neither -- Fable review A5)
SHELL_MEASURE = re.compile(r"\bpython[0-9.]*\s+(?:-[A-Za-z]+\s+)*(?:-c\b|[^\s;|&]+\.py)|\bnode\s+[^\s;|&]+\.js|\bpytest\b|\bnpm\s+(?:test|run\s+test)"
                           r"|\b(?:grep|rg|cat|wc|ls|head|tail|diff|jq|find|awk|cut|sort|uniq|stat)\b|git\s+(?:diff|show)\b(?!\s+-s)"
                           r"|Select-String|Get-Content|Get-ChildItem|Measure-Object|Compare-Object|Test-Path|curl\b", re.I)
# Agent: a measuring/reviewing delegation is checked first, on description AND prompt (Fable review P2)
CHECK_INTENT = re.compile(r"レビュー|検証|確認|点検|測って|測り|計測|数え|監査|第二意見|反証|査読|review|verify|check|audit|QC|measure", re.I)
EDIT_INTENT = re.compile(r"書き直|書き換え|修正(?!案|点)|直し|直す|更新|反映|改修|置き換え|差し替え|適用して|追記"
                         r"|rewrite|\bedit\b|\bfix\b(?!\s*案)|update|apply", re.I)

_UPD = r"(?:書き直|書き換え|直し|直して|直した|修正|更新|反映|置き換え|差し替え|適用|改修|変更|入れ替え)"
# an update of EXISTING targets reported as done (creating new files is not this class)
DONE = re.compile(_UPD + r"[^。\n？?]{0,30}?(?:ました|済み|済ませ|完了|終え|終わ)")
_UNIT = r"(?:本|行|ファイル|記事|か所|カ所|ヶ所|ケ所|箇所|個所|項目|セル|リポ|冊|件|個|節|関数)"   # Fable A2 (「N点」 is almost always review/instruction points)
_N = r"(?<![\d.,])(?:[2-9]|[1-9]\d+)\s*"
_PAREN = r"(?:（[^）]{0,60}）|\([^)]{0,60}\))?"
# several targets as the OBJECT of the update, in the same sentence as the completion claim
OBJ_COUNT = re.compile(_N + _UNIT + r"(?:分)?" + _PAREN + r"\s*(?:を|とも|すべて|全部|は|も|の(?:記事|ファイル))[^。\n]{0,40}?" + _UPD
                       + r"|" + _N + r"(?:本|行|ファイル|記事|冊|件)" + _PAREN + r"\s*に[^。\n]{0,20}?反映"
                       # 名詞形「15本の書き直しが完了しました」 (Fable A1)
                       + r"|" + _N + _UNIT + _PAREN + r"\s*の" + _UPD + r"[^。\n]{0,20}?(?:完了|済み|終え|終わ)"
                       + r"|(?:全|すべての|全部の)(?:\s*\d+\s*)?(?:記事|ファイル|本|行|リポ|冊|件)[^。\n]{0,20}?(?:を|に)[^。\n]{0,30}?" + _UPD
                       + r"|各(?:記事|ファイル)(?:を|に|の(?:本文|表|判定)を)[^。\n]{0,30}?" + _UPD)
# 「対象は15本です。すべて書き直しました。」: the count and the claim in different sentences (Fable A3)
ALL_CLAIM = re.compile(r"(?:すべて|全て|全部|全件|残り全部|残りすべて)[^。\n]{0,20}?" + _UPD)
ANY_COUNT = re.compile(_N + r"(?:本|行|ファイル|記事|か所|カ所|ヶ所|箇所|リポ|冊)")
SENT = re.compile(r"[^。\n]+")


def _skip(s):
    if re.search(r"(?:し|て)(?:ています|いきます|ます。?$)|予定|次回|これから|解釈し|前提|終わってから|してから行", s):
        return True         # not a completion report
    if re.search(r"しない判断|して(?:い)?ません|しませんでした|直していません|「[^」]*」と書きました", s):
        return True         # negation or a quote of an earlier answer
    if (re.search(r"指摘|レビュー|QC|チェックで|確認で|欠陥|致命|軽微|ご指示|ご依頼|指示の|依頼の|Fable|Opus|Sonnet", s)
            and not re.search(_N + r"(?:本|記事|ファイル|行|リポ|冊)", s)):
        return True         # review findings applied to one deliverable: not a batch of targets
    if re.search(r"(?:更新|反映|変更|修正|適用)され|変更なし|代替案|棄却|未プッシュ|main にあり", s):
        return True         # someone else's change, no change, an option not taken, a presence check
    if re.search(r"配布|配り直|デプロイ|deploy|全\s*\d*\s*リポ[^。\n]{0,20}(?:反映|適用)|グローバル", s, re.I):
        return True         # distribution of code/hooks, verified by deploy checks
    if re.search(r"(?<![\d.])0\s*(?:本|行|ファイル|件)(?:を|は|も)?\s*(?:変更|更新|修正|書き換え)", s):
        return True         # 「全119本中0本を変更しました」 reports that nothing changed
    if (re.search(r"新規|新しく(?:書|作)|新しい(?:記事|単書|ファイル|レポート|下書き)|作成|作り(?!直)|作った|書き上げ|書いた|集約", s)
            and not re.search(r"書き直|書き換え|修正", s)):
        return True         # new files, not an update of existing targets
    return False


def multi_claim(rep):
    """The first sentence that claims an update of several targets is done, or ''."""
    has_count = bool(ANY_COUNT.search(rep or ""))
    for m in SENT.finditer(rep or ""):
        s = m.group(0)
        if not DONE.search(s) or _skip(s):
            continue
        if OBJ_COUNT.search(s) or (has_count and ALL_CLAIM.search(s)):
            return s.strip()
    return ""


EFFECT = re.compile(r"これで[^。\n]{0,60}?(?:出ます|出る|なります|なる|表示され|揃います|そろいます|一致します|直ります|反映され|消えます|動きます)")
_REMEASURE = (r"測り直し(?:た|て|、)|測ったところ|測ると|数え直し(?:た|て|、)|数え直すと|再測定し(?:た|て|、)|再集計し(?:た|て|、)"
              r"|計算し直し(?:た|て|、)|照合し直し(?:た|て|、)|確かめ直し(?:た|て|、)|照合をやり直し")
# before -> after numbers: 「822→615px」「28本から23本」「18% -> 63%」「23本（前回 18本）」「前回 18本、今回 23本」
PRE_POST = re.compile(r"\d[\d,.]*\s*[^\s\d。、→]{0,4}\s*(?:→|->|⇒|➡|=>|から)\s*[約]?\d"
                      r"|(?:変更前|更新前|修正前|直す前|旧)[^\n]{0,40}(?:変更後|更新後|修正後|直した後|新)"
                      r"|(?:" + _REMEASURE + r")[^。\n]{0,60}\d"
                      r"|\d[^。\n]{0,40}(?:" + _REMEASURE + r")"
                      r"|\d+\s*[本件行字個冊か所]{1,2}[^。\n]{0,25}?\d+\s*[本件行字個冊か所]{1,2}に(?:直|変え|改め|増や|減ら)"
                      r"|\d+\s*[本件行]\s*(?:すべて|全て|とも)?\s*(?:一致|照合済)"
                      # 「550万円を530万円に直し」
                      r"|\d[\d,.]*\s*[^\s\d。、]{0,3}を\s*\d[\d,.]*\s*[^\s\d。、]{0,3}に(?:直|変え|改め|訂正)"
                      # Fable P3
                      r"|\d[\d,.]*\s*[^\s\d。、（(]{0,4}\s*[（(]\s*(?:前回|以前|変更前|修正前|更新前|直す前)\s*[:：]?\s*\d"
                      r"|(?:前回|以前|変更前|修正前)\s*[:：]?\s*\d[^。\n]{0,30}?(?:今回|現在|変更後|修正後)\s*[:：]?\s*\d", re.I)
# code changes only: the tests run after the change, with their count (not enough for documents -- Fable A5)
TESTS = re.compile(r"(?:テスト|tests?)[^。\n]{0,30}\d+\s*/\s*\d+|\d+\s*/\s*\d+\s*(?:passed|PASS|件合格|件とも合格)", re.I)
_BEFORE_CELL = re.compile(r"(?:^|[（(\s])(?:前|変更前|修正前|更新前|直す前|旧|before)(?:[）)\s]|$)", re.I)
_AFTER_CELL = re.compile(r"(?:^|[（(\s])(?:後|変更後|修正後|更新後|直した後|新|after)(?:[）)\s]|$)", re.I)
UNCHANGED = re.compile(r"未変更|変わらな|変わって(?:い)?ない|変更なし|変化なし|変化は?なかった|上がらな|下がらな|直って(?:い)?ない"
                       r"|残り\s*\d|残って|残った|未対応|手を付けていない|対象外|(?<![\d.])0\s*(?:本|件|行|か所|箇所)"
                       r"|全\s*\d+\s*(?:本|件|行|ファイル|記事)中\s*\d+\s*(?:本|件|行|ファイル|記事)|unchanged|no change", re.I)
UNVERIFIED = re.compile(r"(?:変更|修正|反映|書き直|書き換え|更新|直した|直し|表示|効果|結果)[^。\n]{0,25}?"
                        r"(?:未検証|未確認|確かめ(?:て|られて)?いません|確認(?:して|でき)?(?:い)?ません|測(?:って|れて)いません)")


def table_prepost(rep):
    """A Markdown table whose header has a before column and an after column and whose body has numbers (Fable P1)."""
    lines = (rep or "").splitlines()
    for k, ln in enumerate(lines):
        if not ln.strip().startswith("|") or k + 2 >= len(lines):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not (any(_BEFORE_CELL.search(c) for c in cells) and any(_AFTER_CELL.search(c) for c in cells)):
            continue
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[k + 1]) and re.search(r"\d", lines[k + 2]):
            return True
    return False


def has_prepost(rep, doc_changed):
    return bool(PRE_POST.search(rep or "")) or table_prepost(rep) or (not doc_changed and bool(TESTS.search(rep or "")))


def _cmd(inp):
    return str((inp or {}).get("command") or "")


def classify(name, inp):
    """'mut' (changes content), 'meas' (measures), or '' (neutral)."""
    if name in EDIT_TOOLS:
        return "mut"
    if name in READ_TOOLS:
        return "meas"
    if name in SHELL_TOOLS:
        c = _cmd(inp)
        if SHELL_WRITE.search(c):
            return "mut"
        return "meas" if SHELL_MEASURE.search(c) else ""
    if name in ("Agent", "Task"):
        p = str((inp or {}).get("prompt") or "") + " " + str((inp or {}).get("description") or "")
        if CHECK_INTENT.search(p):
            return "meas"
        if EDIT_INTENT.search(p):
            return "mut"
        return ""
    if name.startswith("mcp__") and re.search(r"screenshot|snapshot|evaluate|read|get_|query|list", name):
        return "meas"
    if name.startswith("mcp__") and re.search(r"update|create|write|batch|set|fill|type|click", name):
        return "mut"
    return ""


def _is_claim(text):
    return bool(DONE.search(text or "") and (multi_claim(text) or EFFECT.search(text or "")))


def analyse(events):
    """events: [("call", name, input) | ("text", str)] in order.
    Returns dict(mutated, measured_after, report, doc_changed) for the turn.
    report = the text after the last change; when that text has no completion claim (e.g. a ledger
    line edited after the real report, Fable A4), it starts from the last text that has one."""
    last_mut = -1
    doc_changed = False
    for k, e in enumerate(events):
        if e[0] == "call" and classify(e[1], e[2]) == "mut":
            last_mut = k
            path = str((e[2] or {}).get("file_path") or (e[2] or {}).get("notebook_path") or "")
            if e[1] not in EDIT_TOOLS or DOC_EXT.search(path):
                doc_changed = True
    if last_mut < 0:
        return {"mutated": False, "measured_after": False, "report": "", "doc_changed": False}
    after = events[last_mut + 1:]
    measured = any(e[0] == "call" and classify(e[1], e[2]) == "meas" for e in after)
    report = "\n".join(e[1] for e in after if e[0] == "text")
    if not _is_claim(report):
        idx = [k for k, e in enumerate(events) if e[0] == "text" and _is_claim(e[1])]
        if idx:
            report = "\n".join(e[1] for e in events[idx[-1]:] if e[0] == "text")
    if not report.strip():
        texts = [e[1] for e in events if e[0] == "text"]
        report = texts[-1] if texts else ""
    return {"mutated": True, "measured_after": measured, "report": report, "doc_changed": doc_changed}


def decide(events, prompt=""):
    """Returns None (pass) or a list of missing items."""
    a = analyse(events)
    if not a["mutated"]:
        return None
    rep = a["report"]
    if not DONE.search(rep):
        return None
    multi = bool(multi_claim(rep))
    effect = bool(EFFECT.search(rep))
    if not (multi or effect):
        return None
    prepost = has_prepost(rep, a["doc_changed"])
    if not effect and UNVERIFIED.search(rep) and not prepost:
        return None          # says plainly it is not verified and claims no effect
    missing = []
    if not a["measured_after"]:
        missing.append("measure")
    if not prepost:
        missing.append("prepost")
    if multi and not UNCHANGED.search(rep):
        missing.append("unchanged")
    return missing or None


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
    """Yield (prompt, timestamp, events) for each main-agent turn in the transcript lines."""
    prompt, pts, events, seen = None, "", [], set()
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            if prompt is not None:
                yield prompt, pts, events
            prompt, pts, events, seen = _text(d.get("message")).strip(), d.get("timestamp", ""), [], set()
        elif d.get("type") == "assistant":
            c = (d.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    bid = b.get("id") or ""
                    if bid and bid in seen:
                        continue
                    seen.add(bid)
                    events.append(("call", b.get("name", ""), b.get("input") or {}))
                elif b.get("type") == "text" and (b.get("text") or "").strip():
                    events.append(("text", b["text"].strip()))
    if prompt is not None:
        yield prompt, pts, events


def read_turn(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    last = None
    for t in turns(data):
        last = t
    return last


REASON = ("【検証せず完了報告（1回のみ）】このターンは内容を変更し、最終回答で「%s」と完了を報告しているが、"
          "変更した対象を測り直した結果が報告に無い（不足: %s）。依頼者の指摘（2026-10-22）:"
          "「更新したはずの数十本に対して、もう一度確認してほしい…ちゃんと直していない印象です」"
          "「60％となるべきが、まだ18％など低いままでは？」。編集した事実は成果ではない。報告の前に次を行うこと。"
          "(1) 最後の変更の後に、変更した対象（全ファイル・実際の表示・実際の出力）を、変えたかった性質そのもので測り直す"
          "（例: 各記事の判定の分布・平均文長・表示される%%・検査スクリプトの出力。合否の件数だけで代えない）。"
          "(2) 最終回答に、測った前後の数値を書く（例:「判定が上がった行 3→11行」「表示 18%%→63%%」、または変更前/変更後の表）。"
          "(3) 対象が複数なら、変わらなかった対象を一覧で書く（無ければ「変わらなかった対象: 0件」と書く）。"
          "測れない場合（画面を読めない等）は、「これで〜になります」と効果を言い切らず、何が未検証で誰が何を見れば確かめられるかを1文で書く。")
MISSING = {"measure": "最後の変更の後の測り直し", "prepost": "前後の数値", "unchanged": "変わらなかった対象の一覧"}


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
    prompt, pts, events = t
    missing = decide(events, prompt)
    if not missing:
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
    rep = analyse(events)["report"]
    m = DONE.search(rep)
    claim = m.group(0)[:40] if m else "完了"
    reason = REASON % (claim, "・".join(MISSING[x] for x in missing))
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
