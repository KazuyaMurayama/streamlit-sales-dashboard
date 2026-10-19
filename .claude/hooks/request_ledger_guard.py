# -*- coding: utf-8 -*-
"""Request ledger (UserPromptSubmit + Stop): every request in a prompt gets an answer.

WHY (2026-10-19, loop action C02 -- reports/CORRECTION_DIGEST_20261019.md)
-------------------------------------------------------------------------
Class C02「依頼の取りこぼし」: 6 corrections in 7 days, 6,410万 context tokens.
Representative: 「購入なしで案1に着手してください。 また、データについてもう少し
探してください。本当に他にないんでしょうか？ なければ、現状のベストである…」 --
one prompt, four requests; the answer did the first and closed. Other cases:
「私が元々の依頼で質問した点に対する回答も、すべて冒頭に載せるべきじゃないですか」
「並行して、下記に回答して」「また、報告してないのでは？」.
scope_coverage_guard (file families) and inbox_guard (scheduled reports) were
adopted for C02 and the class recurred 6 times after each: neither looks at
the REQUESTS of the prompt. Nothing kept the list of what was asked.

WHAT IT DOES
------------
UserPromptSubmit  splits the prompt into request items (sentences that ask
                  for an action or a question) and writes them to a ledger
                  ~/.claude/state/request_ledger/<session>.json (outside every
                  repo). A prompt with fewer than 2 items is not recorded.
Stop              reads the ledger (or re-derives it from the transcript if the
                  ledger is missing) and checks each item against this turn's
                  final answer + the files written in this turn: an item is
                  covered when half of its content words (at least 1, at most
                  2 needed) appear there. If any item is uncovered, the stop is
                  blocked ONCE per prompt with the list; Claude answers each or
                  writes 「未対応: <要求> — 理由」. Never loops: stop_hook_active
                  and a per-prompt mark both end it.

Calibration: tests/calibrate_request_ledger_guard.py (real transcripts).
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
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

NAME = "request_ledger_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.environ.get("RLEDGER_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state", "request_ledger")
MAX_ITEMS = 8
MAX_SENT = 160          # longer sentences are pasted material, not requests

REQ = re.compile(
    r"(?:して|て|で)(?:ください|下さい|ほしい|欲しい|もらいたい|くれ)"
    r"|(?:すすめ|進め|やっ|直し|調べ|探し|教え|まとめ|作っ|書い|出し|確認し|回答し|答え|統合し|修正し|実装し|追加し|削除し|反映し)て(?:$|[。、\s！!])"
    r"|(?:か|ですか|ますか|では|でしょうか|のか|ないの)\s*[？?]"
    r"|[？?]\s*$"
    r"|べき(?:では|じゃ)?"
    r"|(?:しなさい|しろ|せよ|するな|作るな|書くな)")
NOT_REQ = re.compile(r"^(?:OK|ok|はい|了解|ありがとう)")
# Calibration 2026-10-19 (191 real turns): a pointer to material (「添付を確認して」「以下は本当か」
# 「次の検証をしてほしい」「調べてほしいこと：」) and a manner instruction (「簡単にして」) are not
# separate deliverables; their words never show up in the answer, so they fired as misses.
POINTER = re.compile(r"[:：]\s*$|(?:以下|下記|上記|添付|次の|これ|それ)(?:の|を|は|に|について|も)")
MANNER = re.compile(r"(?:簡単|分かりやす|わかりやす|短く|簡潔|丁寧|批判的|日本語|一言|手間が少な)")
_KW = re.compile(r"[一-鿿]{2,}|[゠-ヿー]{3,}|[A-Za-z][A-Za-z0-9_.\-]{1,}|[0-9]+(?:\.[0-9]+)?[%％]?")
KW_STOP = set(
    "ください 下さい 確認 必要 結果 実行 判断 内容 対応 場合 今回 次回 本当 以下 上記 下記 回答 作業 お願い "
    "進め 方法 状態 状況 可能 理由 以上 全体 部分 情報 報告 説明 検討 実施 着手 修正 反映 現状 並行 同様 "
    "また それ これ あなた 自分 ユーザー 全て すべて 本当 他に もう少し".split())


def keywords(s):
    out = []
    for w in _KW.findall(s or ""):
        if w in KW_STOP or len(w) < 2:
            continue
        if w not in out:
            out.append(w)
    return out


def split_items(prompt):
    """Request items of a prompt: [{"text", "kw"}]. Quoted/pasted parts are skipped."""
    t = re.sub(r"```.*?```", " ", prompt or "", flags=re.S)
    t = re.sub(r"(?m)^\s*>.*$", " ", t)
    items = []
    for part in re.split(r"(?<=[。！？!?])|\n", t):
        s = part.strip()
        if not s or len(s) > MAX_SENT or NOT_REQ.match(s):
            continue
        if s.startswith(("<", "[", "|", "#")):
            continue
        if not REQ.search(s):
            continue
        kw = keywords(s)
        if not kw or MANNER.search(s):
            continue
        if POINTER.search(s) and len(kw) <= 2:
            continue
        items.append({"text": s, "kw": kw})
        if len(items) >= MAX_ITEMS:
            break
    return items


def covered(item, text):
    low = (text or "").lower()
    kws = [k.lower() for k in item["kw"]]
    need = min(2, max(1, (len(kws) + 1) // 2))
    return sum(1 for k in kws if k in low) >= need


def uncovered(items, text):
    return [it for it in items if not covered(it, text)]


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def turn_from_events(events):
    """events: [("text", str) | ("tool", name, input dict)] -> evidence text:
    the final answer (texts after the last tool call; earlier texts too) and
    the contents written by Write/Edit in this turn."""
    parts = []
    for e in events:
        if e[0] == "text":
            parts.append(e[1])
        elif e[0] == "tool" and e[1] in WRITE_TOOLS:
            inp = e[2] or {}
            parts.append(str(inp.get("content") or inp.get("new_string") or inp.get("new_source") or ""))
            for ed in inp.get("edits") or []:
                if isinstance(ed, dict):
                    parts.append(str(ed.get("new_string") or ""))
    return "\n".join(parts)


def read_turn(tp):
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
                        events.append(("tool", b.get("name") or "", b.get("input") or {}))
                    elif b.get("type") == "text" and (b.get("text") or "").strip():
                        events.append(("text", b["text"]))
    return prompt, pts, events


def _sid(ev):
    return "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")[:80] or "x"


def _phash(prompt):
    return hashlib.sha1((prompt or "").strip().encode("utf-8", "replace")).hexdigest()[:16]


def _ledger_path(ev):
    return os.path.join(STATE_DIR, _sid(ev) + ".json")


def on_prompt(ev):
    prompt = ev.get("prompt") or ""
    items = split_items(prompt)
    if len(items) < 2:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(_ledger_path(ev), "w", encoding="utf-8") as f:
            json.dump({"prompt_hash": _phash(prompt), "items": items, "blocked": False}, f, ensure_ascii=False)
    except Exception:
        pass


def on_stop(ev):
    if ev.get("stop_hook_active"):
        return
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return
    prompt, pts, events = read_turn(tp)
    if not prompt or not any(e[0] == "text" for e in events):
        return
    path = _ledger_path(ev)
    led = {}
    try:
        with io.open(path, encoding="utf-8") as f:
            led = json.load(f)
    except Exception:
        led = {}
    if led.get("prompt_hash") != _phash(prompt):
        led = {"prompt_hash": _phash(prompt), "items": split_items(prompt), "blocked": False}
    items = led.get("items") or []
    if len(items) < 2 or led.get("blocked"):
        return
    miss = uncovered(items, turn_from_events(events))
    if not miss:
        return
    led["blocked"] = True
    led["uncovered"] = [m["text"] for m in miss]
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
    except Exception:
        pass
    _record_firing(NAME, ev)
    lines = "".join(u"\n  - %s" % m["text"][:100] for m in miss)
    reason = (u"【依頼の台帳照合（1回のみ）】この指示には %d 件の要求があり、うち %d 件に対応する記述が"
              u"最終回答にも今回書いたファイルにも見当たらない:%s\n"
              u"各要求について、今このターンで対応して結果を書くか、対応しない理由を「未対応: <要求> — 理由」の形で"
              u"回答に明記せよ（黙って落とさない）。" % (len(items), len(miss), lines))
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


def main():
    try:
        me = os.path.normcase(os.path.abspath(__file__))
        local = os.path.normcase(os.path.abspath(os.path.join(
            (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__))))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    name = ev.get("hook_event_name") or ""
    if name == "UserPromptSubmit":
        on_prompt(ev)
    elif name == "Stop":
        on_stop(ev)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
