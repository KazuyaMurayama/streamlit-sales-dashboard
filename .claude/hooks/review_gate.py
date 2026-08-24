# -*- coding: utf-8 -*-
"""Stop hook: force a critical self-review of the answer before the turn ends.

THE PROBLEM THIS SOLVES
-----------------------
The user's standing rules already require covering every ask (要件対応表), a
留保 line, and a Next Action. A survey of this machine (2026-08-24) found those
conventions defined in exactly one place — prose in ~/.claude/CLAUDE.md — and
enforced by nothing: no hook or script parses for them. That is the same shape
as the stale-date defect, whose lesson was recorded as:

    "a wrong answer looks correct to its author"

An author who believes the answer is complete will not re-read it looking for a
missing ask. So the review cannot be something the author opts into.

WHY A Stop HOOK AND NOT A SUBAGENT
----------------------------------
A judge subagent has no conversation context. It sees (request, answer) and can
check surface coverage, but cannot tell whether a claim is supported by what was
actually done in the session — and it costs a cold spawn (~5-15k tokens, 10-30s)
on every qualifying turn. The main model already holds the full context CACHED,
so an in-context review turn costs a few hundred tokens.

The hook's three jobs are the ones a model cannot do for itself:
  1. decide WHEN review is due (deterministic, cannot be rationalised away)
  2. FORCE it (decision:block — cannot be forgotten)
  3. ANCHOR it to the user's literal words, re-extracted from the transcript,
     rather than to the author's recollection of them. This is the actual
     counter to "a wrong answer looks correct to its author": the review is
     performed against external text, not memory.

COST — replayed over 1,274 real turns (2026-08-24), not estimated:
    Tier 0  52.4%  -> 0 tokens
    Tier 1  12.3%  -> ~400 tokens on already-cached context
    Tier 2  35.2%  -> ~1200 tokens on already-cached context
    weighted ~472 tokens/turn (~47k per 100 turns). No subagent is ever
    spawned by this hook, so there is no cold-start or latency cost.

LOOP SAFETY: `stop_hook_active` is set once the harness has already blocked;
returning early there means at most ONE forced review turn per answer. This is
the pattern session_guard.py has used in production.

FAIL-OPEN: any exception -> exit 0. A guard bug must never strand a turn.
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE_DIR = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".",
                         "claude_review_gate")

# Latent expectations are NOT inferred per turn — that would need an LLM. They
# are pre-compiled from the user's own recorded feedback, and only the entries
# whose trigger fired this turn are injected, so the prompt never nags about
# irrelevant dimensions. Each entry: (trigger, reminder).
LATENT = (
    ("report", "レポートは自己完結（他版参照で中核を省略しない）／結論が単体でミスリードしない／"
               "数値には成立前提を併記／表示値は有効数字4桁"),
    ("push", "成果物3列表（成果物・説明・リンク）とURL存在確認（git ls-tree で blob 確認）"),
    ("numbers", "パラメータのbare表記禁止（初出時に「何が・どの条件で・どうなる」を1文添える）"),
    ("git", "完了＝main へマージ済み＆push済み。ブランチに成果物を残さない"),
)


def _sid(ev):
    s = ev.get("session_id") or "nosession"
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:16]


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(p, obj):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, p)
    except Exception:
        pass


def _read_turn(transcript_path):
    """Return (user_request, files_written, answer_text) for the latest turn.

    Reads only the tail: transcripts reach 677KB+ and this runs on every answer.
    """
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-4000:]
    except Exception:
        return None, [], ""

    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue

    # Walk backwards to the last genuine user turn (not a tool_result).
    #
    # Two positions matter and they are NOT the same one:
    #   `start`  — where THIS turn's work begins (files/answer are collected
    #              from here forward)
    #   `req`    — the text the review is anchored to
    # When the user replies "はい、そのようにすすめて", that phrase begins the
    # turn but carries no requirements. Anchoring the review to it would review
    # the answer against the word "proceed" — measured on a real transcript
    # before this fix. So `req` keeps walking back past continuation-only
    # utterances to the last turn that actually stated something.
    import turn_classify as _tc

    def _text(r):
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                return None
            return next((b.get("text") for b in c
                         if isinstance(b, dict) and b.get("type") == "text"), None)
        return c if isinstance(c, str) else None

    user_idx = [i for i, r in enumerate(rows)
                if r.get("type") == "user" and _text(r)]
    if not user_idx:
        return None, [], ""
    start = user_idx[-1]

    req = None
    for i in reversed(user_idx):
        t = _text(rows[i])
        if not _tc.strip_wrappers(t).strip():
            continue
        if _tc.is_continuation(t):
            continue          # "proceed" — keep looking further back
        req = t
        break
    if req is None:
        req = _text(rows[start])

    files, answer = [], []
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in (
                    "Write", "Edit", "NotebookEdit"):
                fp = (b.get("input") or {}).get("file_path")
                if fp:
                    files.append(os.path.basename(fp.replace("\\", "/")))
            elif b.get("type") == "text":
                answer.append(b.get("text") or "")
    return req, files, "\n".join(answer)


def _triggers(files, answer):
    out = []
    low = " ".join(files).lower()
    if any(f.lower().endswith(".md") for f in files):
        out.append("report")
    if re.search(r"git push|pushed|push 完了", answer or ""):
        out.append("push")
    if re.search(r"\d+\.\d{3,}|\d{2,}%", answer or ""):
        out.append("numbers")
    if re.search(r"commit|branch|merge|ブランチ", answer or "") or low:
        out.append("git")
    return out


def _prompt(tier, request, files, answer):
    """Build the review instruction. Kept short: it is paid on every fire."""
    req = (request or "").strip()
    req = re.sub(r"<[^>]+>.*?</[^>]+>", "", req, flags=re.S).strip()
    if len(req) > 700:
        req = req[:700] + " …(略)"

    if tier == 1:
        return ("【自動レビュー（1回のみ）】以下のユーザー依頼に対し、回答が"
                "①依頼どおりの動作を実際に確認したか ②未確認事項を「未確認」と"
                "明示したか ③意図的に省いた項目を明示したか を点検せよ。"
                "問題なければ1行で述べて終えてよい。\n---\n" + req)

    fired = _triggers(files, answer)
    notes = [t for k, t in LATENT if k in fired]
    body = ("【自動レビュー（1回のみ・Tier2）】下記はユーザーの依頼原文である。"
            "回答がこれを満たしているか、以下の順で自己点検せよ。\n"
            "1. 明示依頼の対応表: 依頼を逐語で引用し、回答のどこで応じたか、"
            "充足/部分/未回答 を判定する（引用は必須。要約で代用しない）\n"
            "2. 派生依頼: 各依頼の成功条件と、当然含まれるはずの兄弟要求"
            "（例「Xを直して」→ 同種の欠陥を他所でも探したか）\n"
            "3. 潜在的期待: 下記の該当項目\n"
            "4. この回答を受けてユーザーが次に何をするか。追加質問なしで動けるか\n"
            "不足があればこのターンで補え。確認できないものは「未確認」と明記し、"
            "閾値を下げて充足扱いにしない。"
            "意図的な部分回答（計画の承認待ち等）ならその旨と残項目を1行で述べてよい。")
    if notes:
        body += "\n【該当する潜在期待】\n" + "\n".join("・" + n for n in notes)
    return body + "\n---\n【依頼原文】\n" + req


def main():
    # Defer to a registered repo-local copy, matching the existing convention.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        raw = sys.stdin.buffer.read()
        ev = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return  # already forced one review; never loop

    try:
        import turn_classify as tc
    except Exception:
        return

    tp = ev.get("transcript_path")
    if not tp:
        return
    request, files, answer = _read_turn(tp)
    if request is None:
        return  # could not parse: fail open rather than nag blindly

    tier, reasons = tc.classify(request, files_written=files, answer=answer)
    if tier == 0:
        return

    # Dedupe: do not re-review the same request unless new files appeared.
    path = os.path.join(STATE_DIR, _sid(ev) + ".json")
    st = _load(path)
    key = hashlib.sha1((tc.strip_wrappers(request) or "").encode(
        "utf-8", "replace")).hexdigest()[:16]
    if st.get("key") == key and st.get("files", 0) >= len(files):
        return
    _save(path, {"key": key, "files": len(files)})

    # ensure_ascii=True, and write BYTES.
    #
    # ⚠️ Windows CP932 hazard, hit for real while building this: several common
    # kanji end in byte 0x5C — 「表」 is 0x95 0x5C, also 「十」「ソ」「构」. If the
    # JSON is emitted as text through a CP932 stdout, that trailing 0x5C is read
    # back as a backslash and the payload dies with "Invalid \escape", so the
    # hook silently stops working. ensure_ascii escapes every non-ASCII char to
    # \uXXXX, and writing to the binary buffer bypasses the locale codec
    # entirely. Do not "simplify" this to print(..., ensure_ascii=False).
    payload = json.dumps({
        "decision": "block",
        "reason": _prompt(tier, request, files, answer),
    }, ensure_ascii=True)
    sys.stdout.buffer.write(payload.encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
