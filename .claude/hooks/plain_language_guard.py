# -*- coding: utf-8 -*-
"""Stop hook: a plain-language rewrite must keep the original verdict labels and their judge.

WHY (2026-11-09 correction digest, class C06 「用語・表現のミスリード」, adopted)
-----------------------------------------------------------------------------
Defect class (no proper nouns): 平易化・言い換えを求められたとき、元の文にあった
判定ラベル・判定の主体・指示語の係り先を自作の語へ置き換え、読者が原義を復元
できない.

The incident (nasdaq-rebuild-v2, 2026-11-08T10:35Z). The user pasted
    「832 を採用しないのは妥当か → Fable の判定は『妥当』。 …」
and asked 「この意味をもっと分かりやすく説明して」. The rewrite was a 1,500-char
analogy (過去問・練習問題・本番の試験) that never said 「妥当」 and never named
Fable: the question the pasted text answered (is NOT adopting 832 right?) and
who answered it were both gone. Siblings in the same week: 「部分的に支持」 rendered
as 「研究の裏づけがあります」 in 9 articles (2026-11-04), 「合言葉」 coined for a
password (2026-11-05), 「割り引きの規則」「合図の倍率」 coined for a haircut rule and a
signal leverage (2026-11-08), 「ですよね」「ますよ」 in report-style article text
(2026-11-02).

jargon_glossary_guard (PreToolUse Write|Edit) checks only the SHAPE of internal
identifiers in .md reports (FULL, F5, P09_STR). It never sees chat answers,
never sees Japanese verdict words, and never compares a rewrite with its
source. This hook owns exactly that comparison; it does not look at
identifier shapes at all.

INVARIANT
---------
When the user asks for a plainer / re-worded explanation, every verdict label
of the source (a dictionary word -- 妥当／採用／棄却／PASS／FAIL／部分的に支持 … --
standing in a verdict position: quoted, bold, after 判定は／結論：／→) and the judge
named for it (「Fable の判定」) must still appear in the rewrite, verbatim or as
「原語（＝説明）」.

WHAT IT DOES
------------
Trigger: the user's own words in the latest prompt (pasted blocks removed)
ask for a re-wording (分かりやすく／平易に／噛み砕いて／言い換え／意味が分からない／
意味不明／どういう意味 …; RE_ASK). Other turns are never checked.
Source: the material the user pointed at -- the pasted block / quoted text in
the prompt when it has >= SRC_MIN_CHARS of it, otherwise the previous turn's
final answer.
  L  (block, once per instruction)  verdict labels or the judge missing from
     the final answer.
  R  (REVIEW, systemMessage only)   signals a machine cannot judge reliably:
     R1 the answer's opening sentence starts with a demonstrative (これは／その〜):
        nothing precedes it, so its referent is outside the answer;
     R2 mean prose sentence length > MEAN_SENT_MAX chars;
     R3 colloquial sentence endings (〜よね／〜ですよ／〜だね …) >= COLLOQ_MAX of
        sentences;
     R4 an analogy (例え話／〜と考えてほしい) introduces quoted names that are not
        in the source, without mapping them back.
  R items never block: the measured precision is below what a block needs
  (see CALIBRATION). They are returned to the human with the numbers.

CALIBRATION: see tests/calibrate_plain_language_guard.py (this hook's own
analyze() imported, ~/.claude/projects/*/*.jsonl, 14 days). Numbers are in
that script's output and in the C06 countermeasure report.

CLI: python plain_language_guard.py --source SRC.txt --answer ANS.txt [--prompt P.txt]
     exit 1 when L fires.
fail-open: any exception -> exit 0. stop_hook_active -> return.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:
    def _codex_transcript(p, *_a, **_k):
        return p
try:
    import turn_classify as _tc
except Exception:
    _tc = None

NAME = "plain_language_guard"
TAIL_BYTES = 6 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

# ---------------------------------------------------------------- dictionary
# Verdict vocabulary. Each group is one scale; a label is matched only in a
# verdict position (VERDICT_POS), so the everyday 「採用する」 in prose is ignored.
# Longest first inside the alternation so 「部分的に支持」 wins over 「支持」.
LABELS = sorted(set("""
妥当 妥当ではない 妥当でない 不当 適切 不適切
採用 不採用 採用しない 採用見送り 見送り 棄却 却下 保留 撤回 撤回・再設計 再設計 観察中 継続 中止 差し戻し 承認
合格 不合格 通過 不通過 未達 達成
支持 部分的に支持 支持されない 不支持 反証 根拠なし 根拠不十分 検証対象外 一部支持 限定的に支持
有意 有意でない 非有意 成立 不成立 一致 不一致 誤り 正しい 正確 不正確
確認済み 未確認 未検証 検証済み 推奨 非推奨 条件付き 要注意 問題なし 問題あり 可 不可 該当 非該当
PASS FAIL REVIEW WARN NG ADOPT REJECT HOLD KEEP DROP GO NO-GO CONFIRMED PLAUSIBLE REFUTED
""".split()), key=len, reverse=True)
_LAB = "|".join(re.escape(x) for x in LABELS)
_CUE = r"(?:判定|結論|評価|判断|審査|結果|答え|扱い|ステータス|状態|見立て|verdict|Verdict|VERDICT)"
VERDICT_POS = [
    re.compile(r"[「『\"“](" + _LAB + r")[」』\"”]"),                       # 「妥当」
    re.compile(r"\*\*(" + _LAB + r")\*\*"),                                  # **PASS**
    re.compile(_CUE + r"\s*(?:は|が|も|=|＝|:|：|→)\s*[「『\"*]{0,2}(" + _LAB + r")(?![一-龥ァ-ヶA-Za-z])"),
    re.compile(r"(?:→|⇒)\s*[「『\"*]{0,2}(" + _LAB + r")(?![一-龥ァ-ヶA-Za-z])"),
    re.compile(r"^\s*\|?\s*(" + _LAB + r")\s*\|", re.M),                     # | FAIL | table cell
]
# User-approved plain wordings that count as keeping the label (the 正規化辞書).
# Only add an entry the user approved in words; quote the approval.
#   部分的に支持: 2026-11-04 「『部分的に支持』の判定を『研究の裏づけが一定あります』と示すのが妥当。
#                 前の『部分的にのみ』『支持されない』は妥当ではない」
PLAIN_EQUIV = {
    "部分的に支持": ["研究の裏づけが一定あります", "研究の裏づけが一定ある"],
}
# The judge of a verdict: 「Fable の判定」「独立QCの結論」「ユーザーが判断」.
# Kanji-only judges must be a role noun (審査員・依頼者・監査役): calibration
# 2026-11-09 found 「実務の判断」「総説の評価」 matched as judges otherwise.
RE_JUDGE = re.compile(
    r"([A-Za-z][A-Za-z0-9.\-]{1,24}|[ァ-ヶー]{2,12}|[一-龥]{1,6}(?:者|員|官|役|会|局|庁|社|部|班|チーム))"
    r"\s*(?:の|が)\s*(?:判定|評価|結論|判断|審査|レビュー)")
JUDGE_STOP = {"この", "その", "今回", "前回", "最終", "全体", "結果", "本", "同じ", "今", "次", "私", "自分",
              "機械", "検査", "自動", "事前", "一次", "二次"}

# The user's own words asking for a re-wording.
# 「分かりやすく」 alone is not an ask: calibration 2026-11-09 matched
# 「初学者でも分かりやすく適用できるように」 in a report request. It must govern
# an explaining verb within a few characters.
_EXPL = r"(?:説明|言い|言っ|言え|書い|書き|書け|直し|直せ|整理|まとめ|伝え|して|教え|示し|示せ|回答|答え)"
RE_ASK = re.compile(
    r"(?:分かりやすく|わかりやすく|分かり易く|解りやすく|平易に|噛み砕|かみ砕|かみくだ|噛みくだ|"
    r"易しく|やさしく|簡単に|かんたんに|シンプルに)[^。\n]{0,3}" + _EXPL + r"|"
    r"(?:分かりやすく|わかりやすく|分かり易く)[^。\n]{0,40}(?:説明|提示|整理|書き直|言い直|示)(?:して|しなさい|せよ)|"
    r"平易化|言い換え|言いかえ|"
    r"意味(?:が|は)?(?:分から|わから|分かりません|わかりません|通じ|不明)|意味不明|どういう意味|何を意味|"
    r"ピンとこない|理解できな|読んでも分からな|専門用語.{0,10}(?:減ら|使わな|平易|なくし)")
# The ask points at the previous answer (Fable B1/B1c/B2, 2026-11-09: 「このリポの
# フォルダ構成を簡単に説明して」「_norm 関数の意味が分からない」 name another object;
# demanding the previous answer's PASS/採用 there blocked legitimate work).
RE_PREV_REF = re.compile(
    r"前の|上の|上記|さっきの|先ほどの|先程の|前回の|直前の|今の(?:回答|説明|話|報告)|"
    r"(?:この|その|あなたの|今回の)(?:回答|説明|報告|意味|結論|文章|文|内容|話|Next ?Action)|"
    r"(?:回答|報告|説明)(?:が|は|を)(?!.{0,3}して)|^(?:それ|これ)(?:は|って|が|の意味)|意味不明です?$")
SRC_MIN_CHARS = 2    # any quoted term counts: 「『本書／通説』では意味が分から」 points at the term, not the whole previous answer (2026-11-09 calibration); 「『コンテナの窓に合言葉…』は意味不明」 quotes 18 chars

# REVIEW thresholds (calibrated; see CALIBRATION).
MEAN_SENT_MAX = 60
COLLOQ_MAX = 0.20
COLLOQ_MIN_SENTS = 5
RE_COLLOQ = re.compile(r"(?:よね|ですよ|ますよ|だよ|だね|ですね|ますね|かな|じゃない|でしょ|っす|けどね|んだ|よ)[!！?？]*$")
RE_DEMO_OPEN = re.compile(r"^(?:これ|それ|あれ|こちら|そちら)(?:は|が|を|も|で|に)")
RE_DEMO_FIRST = re.compile(r"^(?:この|その|あの|当該|上記の|前述の)(?!ため|とき|場合|まま|後|うえ|上で|ように)[一-龥ァ-ヶー]")
# R4: an analogy introduces new quoted names (「過去問」「練習問題」) not in the source.
RE_ANALOGY = re.compile(r"例え話|たとえ話|例えると|たとえると|と考えてほしい|と考えてください|のようなもの")


def _fold(s):
    return unicodedata.normalize("NFKC", s or "")


def _strip_md(text):
    t = re.sub(r"```.*?```", "\n", text or "", flags=re.S)
    t = re.sub(r"<[^>\n]{1,80}>", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    return t


# ---------------------------------------------------------------- analysis
def is_ask(prompt_own):
    return bool(RE_ASK.search(_fold(prompt_own or "")))


def verdict_labels(source):
    s = _fold(_strip_md(source))
    found = []
    for rx in VERDICT_POS:
        for m in rx.finditer(s):
            lab = m.group(1)
            if lab not in found:
                found.append(lab)
    return found


def judges(source):
    s = _fold(_strip_md(source))
    out = []
    for m in RE_JUDGE.finditer(s):
        j = m.group(1).strip()
        if j in JUDGE_STOP or any(j.endswith(x) for x in ("この", "その")) or len(j) < 2:
            continue
        if j not in out:
            out.append(j)
    return out


def missing_labels(source, answer, check_judges=True):
    a = _fold(answer)
    miss_l = [x for x in verdict_labels(source)
              if x not in a and not any(e in a for e in PLAIN_EQUIV.get(x, ()))]
    miss_j = [x for x in judges(source) if x not in a] if check_judges else []
    return miss_l, miss_j


def prose_sentences(text):
    out = []
    for ln in _strip_md(text).splitlines():
        s = ln.strip()
        if not s or s.startswith(("|", "#", ">")) or re.match(r"^[-=*_]{3,}$", s):
            continue
        s = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", s)
        s = re.sub(r"\*\*|__|`", "", s)
        for part in re.split(r"(?<=[。！？!?])", s):
            p = part.strip()
            if len(re.findall(r"[ぁ-んァ-ヶ一-龥]", p)) >= 4:
                out.append(p)
    return out


def review_items(answer, source=None):
    items = []
    body = _fold(_strip_md(answer))
    sents = prose_sentences(answer)
    first = next((ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith(("#", "|"))), "")
    first = re.sub(r"^(?:[-*+]|\d+[.)])\s+|\*\*", "", first)
    # R1 only at the opening sentence: nothing precedes it in the answer, so a
    # demonstrative there necessarily points outside the answer. A mid-answer
    # 「その＋名詞」 noun scan was tried and dropped (2026-11-09 calibration: 5 of 5
    # REVIEWs on re-wording turns were normal anaphora such as 「元の依頼と、その達成状況」).
    if RE_DEMO_OPEN.match(first) or RE_DEMO_FIRST.match(first):
        items.append(("R1", "回答の書き出し「%s」の指示語の係り先が回答内に無い" % first[:20]))
    if source is not None and RE_ANALOGY.search(body):
        coined = []
        for m in re.finditer(r"「([^「」]{2,10})」", body):
            q = m.group(1)
            if q not in _fold(source) and q not in coined:
                coined.append(q)
        if coined:
            items.append(("R4", "例え話の新しい呼び名 %s が元の語との対応なしに出てくる"
                          % "・".join("「%s」" % x for x in coined[:4])))
    if sents:
        mean = sum(len(x) for x in sents) / float(len(sents))
        if mean > MEAN_SENT_MAX:
            items.append(("R2", "平均文長 %.0f 字（目安 %d 字以下）" % (mean, MEAN_SENT_MAX)))
        if len(sents) >= COLLOQ_MIN_SENTS:
            col = [x for x in sents if RE_COLLOQ.search(re.sub(r"[。]+$", "", x))]
            rate = len(col) / float(len(sents))
            if rate >= COLLOQ_MAX:
                items.append(("R3", "話し言葉の文末 %d/%d 文（%.0f%%・目安 %.0f%% 未満）例:「%s」"
                              % (len(col), len(sents), rate * 100, COLLOQ_MAX * 100, col[0][-20:])))
    return items


def source_of(prompt_raw, prev_answer):
    """The material the user pointed at: pasted/quoted text in the prompt, else the previous answer."""
    p = prompt_raw or ""
    pasted = re.findall(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", p, flags=re.S)
    own = re.sub(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", " ", p, flags=re.S)
    quoted = re.findall(r"「([^「」]{6,})」", own)
    block = re.findall(r"^\s*>.*$", own, flags=re.M)
    # Lines around the ask: 「以下も意味不明\n\n<the text>」 and, since Fable B4
    # (2026-11-09), a short paste FOLLOWED by the ask on the last line.
    lines = [ln for ln in own.splitlines() if ln.strip()]
    around = []
    if any(RE_ASK.search(_fold(ln)) for ln in lines):
        around = [ln for ln in lines if not RE_ASK.search(_fold(ln))]
    material = "\n".join(pasted + quoted + block + around)
    if len(re.sub(r"\s", "", material)) >= SRC_MIN_CHARS:
        return material, "prompt"
    return prev_answer or "", "previous_answer"


def own_words(prompt_raw):
    p = re.sub(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", " ", prompt_raw or "", flags=re.S)
    if _tc is not None:
        try:
            p = _tc.strip_wrappers(p)
        except Exception:
            pass
    # The ask sits at the start or the end; the middle is material. Fable B4
    # (2026-11-09): first-3-lines only missed 「<3 pasted lines>\nこの意味を分かりやすく説明して」.
    ls = p.strip().splitlines()
    keep = ls if len(ls) <= 6 else ls[:3] + ls[-3:]
    return "\n".join(keep)


def analyze(prompt_raw, prev_answer, answer):
    """{'ask': bool, 'source_kind', 'missing_labels', 'missing_judges', 'review': [...]}"""
    res = {"ask": False, "source_kind": None, "missing_labels": [], "missing_judges": [], "review": []}
    if not is_ask(own_words(prompt_raw)) or not (answer or "").strip():
        return res
    res["ask"] = True
    src, kind = source_of(prompt_raw, prev_answer)
    res["source_kind"] = kind
    # The judge is checked only against text the user pointed at. A whole previous
    # answer names many actors (スクリプト・フック) that a re-explanation need not repeat.
    ml, mj = missing_labels(src, answer, kind == "prompt")
    res["review"] = review_items(answer, src)
    if kind == "previous_answer" and not RE_PREV_REF.search(_fold(own_words(prompt_raw))):
        # Not clearly about the previous answer: return it to the human, never block.
        if ml:
            res["review"].insert(0, ("R5", "依頼の対象が直前の回答か不明だが、直前の回答の判定ラベル %s が回答に無い"
                                     % "・".join("「%s」" % x for x in ml[:4])))
        ml, mj = [], []
    res["missing_labels"], res["missing_judges"] = ml, mj
    return res


# ---------------------------------------------------------------- transcript
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_prompt_row(d):
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
        return False
    if _tc is not None and _tc.is_machine_row(d):
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    if not t or t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:",
                              "Stop hook feedback", "This session is being continued", "<system-reminder>")):
        return False
    return True


def turns(rows):
    """[(prompt_text, prompt_ts, final_answer)] -- final = text written after the turn's last tool call."""
    out = []
    cur = None
    for d in rows:
        if d.get("isSidechain"):
            continue
        if is_prompt_row(d):
            if cur:
                out.append(cur)
            cur = {"prompt": _text(d.get("message")), "ts": d.get("timestamp", ""), "final": []}
            continue
        if cur is None or d.get("type") != "assistant" or d.get("isApiErrorMessage"):
            continue
        for b in ((d.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                cur["final"] = []
            elif b.get("type") == "text" and (b.get("text") or "").strip():
                cur["final"].append(b["text"])
    if cur:
        out.append(cur)
    return [(t["prompt"], t["ts"], "\n".join(t["final"])) for t in out]


def read_rows(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        if size > TAIL_BYTES:
            f.readline()
        data = f.read().decode("utf-8", "replace").splitlines()
    rows = []
    for ln in data:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    return rows


def reason_text(res):
    parts = []
    if res["missing_labels"]:
        parts.append("判定ラベル: " + "、".join("「%s」" % x for x in res["missing_labels"][:8]))
    if res["missing_judges"]:
        parts.append("判定の主体: " + "、".join("「%s」" % x for x in res["missing_judges"][:4]))
    src = "貼り付けられた元の文" if res["source_kind"] == "prompt" else "直前の回答"
    return ("【平易化での原語の保持（1回のみ）】言い換えを求められた回答から、%sにあった次の語が消えている: %s。\n"
            "読者は言い換え後の文から元の判定を復元できない（2026-11-08「この意味をもっと分かりやすく説明して」に"
            "「Fable の判定は『妥当』」を含まない例え話で答えた事例）。\n"
            "各語を原語のまま残すか「原語（＝平易な説明）」の形で併記し、冒頭の1文で元の問いへの答えを原語で言え"
            "（例:「Fable の判定は『妥当』＝832 を採用しないのは正しい、という意味だ」）。"
            "言い換えのための新しい呼び名（例え話の語）を作るなら、元の語との対応を1回書く。"
            % (src, "／".join(parts)))


def review_text(items):
    return ("[plain_language_guard] REVIEW（止めない・人が判断）: 言い換えの回答に、機械では正否を決められない"
            "読みにくさの兆候がある: " + "／".join(x[1] for x in items[:4]))


def _emit(obj):
    # ensure_ascii + bytes: CP932 stdout corrupts kanji ending in 0x5C (see review_gate.py)
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                                             ".claude", "hooks", os.path.basename(__file__)))
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
    tp = _codex_transcript(ev.get("transcript_path") or "")
    if not tp or not os.path.isfile(tp):
        return
    ts = turns(read_rows(tp))
    if not ts:
        return
    prompt, pts, answer = ts[-1]
    prev = ts[-2][2] if len(ts) >= 2 else ""
    res = analyze(prompt, prev, answer)
    if not res["ask"]:
        return
    key = hashlib.sha1((pts + prompt).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x")
                                           if ch.isalnum() or ch in "-_") + "_" + key)

    def _touch(path):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            open(path, "w").close()
        except Exception:
            pass
    if res["missing_labels"] or res["missing_judges"]:
        if not os.path.exists(mark):
            _touch(mark)
            _record_firing(NAME, ev)
            _emit({"decision": "block", "reason": reason_text(res)})
        return
    # REVIEW: once per instruction, and never after this instruction was blocked
    # (Fable B8, 2026-11-09: every re-answer after the block carried the notice).
    if res["review"] and not os.path.exists(mark) and not os.path.exists(mark + "_r"):
        _touch(mark + "_r")
        _record_firing(NAME + "_review", ev)
        _emit({"systemMessage": review_text(res["review"])})


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--answer", required=True)
    a = ap.parse_args(argv)

    def rd(p):
        if not p:
            return ""
        with io.open(p, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    prompt = rd(a.prompt) or "この意味をもっと分かりやすく説明して。"
    src = rd(a.source)
    if src:
        prompt = prompt + "\n<pasted_content id=\"cli\">" + src + "</pasted_content id=\"cli\">"
    res = analyze(prompt, "", rd(a.answer))
    sys.stdout.buffer.write((json.dumps(res, ensure_ascii=False) + "\n").encode("utf-8"))
    return 1 if (res["missing_labels"] or res["missing_judges"]) else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_cli(sys.argv[1:]))
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
