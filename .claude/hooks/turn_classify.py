# -*- coding: utf-8 -*-
"""Shared turn classifier for the requirements gate and the answer review.

WHY THIS MODULE EXISTS SEPARATELY
---------------------------------
Two mechanisms need the same judgement ("how much ceremony does this turn
deserve?"): the UserPromptSubmit requirements gate and the Stop answer review.
If each carried its own copy they would drift and disagree — the gate would
demand a REQSPEC on turns the reviewer then ignored. One classifier, two callers.

CALIBRATION — every constant here was MEASURED, not chosen
----------------------------------------------------------
Replayed against 1,270 real user turns from 12 sessions (2026-08-24).

Round 1. Two independently-produced designs both proposed character-count
thresholds. Both measured wrong, the same way:

    design assumed Tier2 ~8%     measured 74.6%   (len>=400 fired on 67%)
    design assumed Tier2 "rare"  measured 71.3%   (len>=300 fired on 82%)

Root cause: this user routinely PASTES long material (competitor tables, prior
answers, quoted rules) into an otherwise short instruction. Typed-prompt length
is bimodal — p25=277 chars, median=8,055 — so length measures "did they paste
something", not "is this complex". Length of the PROMPT is therefore never used
as a trigger. Do not re-add a len>= rule without re-running the replay.

Round 2. Stripping pastes by markup was not enough either. After removing
fences, quotes, tables and rules, the median remaining prompt was still 5,092
chars and 56% still carried >=2,000 chars of *bare pasted prose* with no markup
to key on. Every keyword list scanning the prompt therefore hit quoted text
rather than intent: "repo delete" fired 272x, "push --force" 227x, "force push"
172x — all inspected, essentially all were quoted RULES about force-pushing,
not requests to force-push. Tier2 stuck at 59%.

THE FIX — gate on OUTCOME, not on prose
---------------------------------------
What a turn PRODUCED cannot be faked by pasting. Same 1,270 turns:

    keyword scan of prompt   Tier2 59.1%   ~843 tok/turn
    outcome-based            Tier2 27.2%   ~375 tok/turn   <-- adopted

Prompt text is still used for exactly two things, both robust to pasting:
continuation detection (exact match on a short utterance) and the explicit user
override (!req / !noreq). Enumerated-ask counting is retained only to escalate
a turn that ALREADY wrote files, never to escalate on its own.
"""
import re

# Harness-injected wrappers. Not the user's words; must never feed a signal.
_WRAP = (
    r"<system-reminder>.*?</system-reminder>",
    r"<local-command[^>]*>.*?</local-command[^>]*>",
    r"<command-name>.*?</command-name>",
    r"<command-message>.*?</command-message>",
    r"<command-args>.*?</command-args>",
    r"<ide_selection>.*?</ide_selection>",
    r"<user-prompt-submit-hook>.*?</user-prompt-submit-hook>",
)

# Continuation utterances: carry no new requirements, must not re-trigger.
CONTINUATION = {
    "続き", "続けて", "すすめて", "進めて", "再開", "再開して", "そのまま",
    "はい", "うん", "ok", "OK", "よろしく", "お願い", "いいよ", "了解", "次",
    "continue", "go on", "proceed", "yes", "sure", "next", "resume",
}

# Markers that an answer asserts a judgement rather than merely reporting.
_RECOMMEND = re.compile(
    r"推奨|おすすめ|結論|判断|採用|棄却|比較|トレードオフ|べきです|方がよい"
    r"|recommend|conclusion|trade-?off|verdict")

REPORT_NAME = re.compile(r"_\d{8}(?:-v\d+)?\.md$", re.I)


def strip_wrappers(text):
    """Remove harness-injected blocks. Returns the user's own words."""
    s = text or ""
    for w in _WRAP:
        s = re.sub(w, "", s, flags=re.S)
    return s.strip()


def strip_pasted(text):
    """Remove quoted/pasted material so enumeration counts reflect ASKS.

    Note this is necessary but NOT sufficient — see module docstring round 2.
    It is why enumeration alone never escalates to Tier 2.
    """
    s = text or ""
    s = re.sub(r"```.*?```", "", s, flags=re.S)       # fenced code
    s = re.sub(r"^\s*[>|].*$", "", s, flags=re.M)      # quoted / table rows
    s = re.sub(r"^\s*-{3,}\s*$", "", s, flags=re.M)    # horizontal rules
    s = re.sub(r"^\s*\|.*\|\s*$", "", s, flags=re.M)   # markdown tables
    return s.strip()


def is_continuation(text):
    """True if the utterance only says 'carry on' and states no requirement.

    Exact-set matching is not enough: real replies compose the tokens, e.g.
    「はい、そのようにすすめて」 = はい + そのように + すすめて. Measured on a
    live transcript, exact matching failed on that exact string and the review
    then anchored itself to the word "proceed" instead of the actual request.

    Rule: short utterance, and every comma-separated fragment is either a
    continuation token or a filler like 「そのように」. Length-capped so a real
    instruction that merely starts with 「はい、」 is not swallowed.
    """
    body = strip_pasted(strip_wrappers(text)).strip().rstrip("。.!！ 　")
    if not body or len(body) > 40:
        return False
    low = body.lower()
    if low in {c.lower() for c in CONTINUATION}:
        return True
    fillers = ("そのように", "それで", "その方向", "この方針", "for now", "please",
               "と", "で", "ね", "よ", "、", ",")
    frags = [f.strip() for f in re.split(r"[、,。\s]+", body) if f.strip()]
    if not frags:
        return False
    cont = {c.lower() for c in CONTINUATION}
    for f in frags:
        fl = f.lower()
        if fl in cont or f in fillers:
            continue
        if any(f.startswith(c) or c in f for c in CONTINUATION if len(c) >= 3):
            continue
        return False
    return True


def count_asks(text):
    """Enumerated asks in the instruction head.

    Restricted to the first 1200 chars: a genuine multi-part request states its
    parts up front, while enumerations further down are usually quoted material
    that survived stripping.
    """
    head = (text or "")[:1200]
    items = re.findall(r"^\s*(?:\d+[.):：]|[①-⑩]|[-・]\s)\s*(.+)$", head, re.M)
    return len([i for i in items if len(i.strip()) > 4])


def classify(prompt, files_written=None, report_written=False, answer=None):
    """Return (tier, reasons).

    tier 0 = no ceremony; 1 = light; 2 = full review.

    Gating is OUTCOME-based: the decisive inputs are what the turn wrote, not
    what the prompt says, because 56% of this user's prompts contain bare pasted
    prose that defeats any keyword scan of the request.

    `files_written` / `report_written` / `answer` are known only at Stop time.
    The UserPromptSubmit caller passes none of them and classifies on the
    prompt alone, which can only yield tier 0 or an explicit override — that
    asymmetry is intentional and documented in the gate hook.
    """
    files_written = list(files_written or [])
    raw = strip_wrappers(prompt)
    body = strip_pasted(raw)

    # Explicit user override always wins over our inference.
    if re.search(r"!req\b|要件定義して", raw, re.I):
        return 2, ["ユーザーが要件定義を明示要求"]
    if re.search(r"!noreq\b|そのままやって|すぐやって", raw, re.I):
        return 0, ["ユーザーが要件定義の省略を明示指示"]

    # Continuation: exact match on a short utterance. Robust to pasting,
    # because a pasted block never reduces to one of these strings.
    if is_continuation(raw) and not files_written:
        return 0, ["継続指示（新規要件なし）"]

    reasons = []
    md_files = [w for w in files_written if w.lower().endswith(".md")]
    if report_written or any(REPORT_NAME.search(w) for w in files_written):
        reasons.append("レポート.mdを生成")
    if len(files_written) >= 5:
        reasons.append("%dファイルを変更" % len(files_written))
    if len(md_files) >= 2:
        reasons.append("ドキュメント%d件を変更" % len(md_files))
    if reasons:
        return 2, reasons

    if files_written:
        n = count_asks(body)
        if n >= 2:
            return 2, ["列挙された依頼が%d件かつ変更を伴う" % n]
        return 1, ["ファイル変更を伴う依頼"]

    # No files written. Most such turns are questions and need nothing. But a
    # long ANALYTICAL answer (a recommendation, comparison, design) is a
    # deliverable even though it touched no file — and it is exactly the kind
    # of answer that can be confidently wrong. Measured on the source session:
    # the design turn wrote zero files yet produced the primary work product.
    #
    # Answer length is safe here where prompt length was not: the answer is OUR
    # OWN text, so it cannot be inflated by the user pasting material.
    # 3000 chars, not 1500: measured on the same corpus, >=1500 escalated 17%
    # of all turns (Tier2 would hit 44%), while >=3000 adds 8.1% and reaches
    # Tier2 ~35%. Below 3000 the "answer" is usually a status report, not an
    # analysis someone will act on.
    if answer:
        a = answer.strip()
        if len(a) >= 3000 and _RECOMMEND.search(a):
            return 2, ["ファイル変更なしだが判断・推奨を含む長文回答"]
    return 0, ["成果物なし"]
