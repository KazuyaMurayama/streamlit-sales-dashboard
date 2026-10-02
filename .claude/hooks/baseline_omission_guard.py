# -*- coding: utf-8 -*-
"""Stop hook: 差（ポイント差）を、比較の基準値なしで読者に渡すのを止める。

THE DEFECT CLASS (2026-10-02)
-----------------------------
固有名詞なしで言うと: 「2つの率の差（○ポイント・pt・pp）を書いたのに、その差が
乗っている基準の率（プラセボ群・対照群・ベースラインが何%か）を同じ場所に書かない」。

実例: アゼライン酸とニキビ治療薬の比較で、ネットワークメタ解析の値を
「プラセボより面皰が何ポイント多く減ったか: アゼライン酸14.4、配合剤25.3」
とだけ報告した。ユーザーの指摘（逐語）:「ベースは何％？1％と50％では？＋２５Ptの
意味がぜんぜんちがうだろが。」——基準が1%なら26%対15%で約1.7倍、50%なら75%対
64%で約1.2倍。差だけでは、読者は効果の大きさを判断できない。

この回答は、別モデル（Fable）の独立レビューを2回通っていた。レビューは
「数値が原典と一致するか」を照合したが、「読者が数値を解釈するのに必要な
基準が書かれているか」は誰も見ていなかった。数値が正しいほど、この欠落は
目視を通過する。だから機械で見る。

WHAT IS CHECKED (invariant, not strings)
  対象: このターンの最終回答テキスト、およびこのターンに Write/Edit で書いた
        .md の新しい本文（既存ファイルの負債は見ない）。
  検出: 「数値＋ポイント/pt/pp/percentage points」という差の表現。
  合格条件（同じ文・表の行・箇条書きの1項目の中に、次のどれかがある）:
    (a) 差以外の「率（%）」が2つ以上ある（例: 48.1% 対 23.2%）
    (b) 基準を表す語（基準・ベース・プラセボ・基剤・対照・比較群・から・→ 等）
        と、率（%）が1つ以上ある
  濃度（20%クリーム・2%ゲル等）は率として数えない。

ACTION: 1回だけ block（stop_hook_active で再入しない）。該当箇所を最大8件示す。

NON-GOALS
  - 基準値が正しいかは判定しない（それは evidence_table_guard / 人の仕事）。
  - 「倍」「%増」等の相対表現は対象外。相対表現は基準を含意するため。
  - 閾値を下げて検出率を上げない。

CALIBRATION（実測 2026-10-02・ローカル51トランスクリプト・最終回答3,894件）
  初版 5.86% → 閾値・許容幅の除外 5.47% → 数値の遷移(a→b) 5.14% →
  独立QC（Fable）指摘を反映: 率の文脈に限定・NFKC 正規化・前後1文/表見出しまで
  基準を探す・同じ回答に同じ指標の水準(%)があれば合格・小数の確率(P=0.9990)を
  水準として扱う・「−2pp世界」等のシナリオ除外 → 2.88%（112件・12/51セッション）。
  残る発火の大半は CAGR/MaxDD の pp 差を水準なしで書いた回答で、クラスどおりの
  真陽性と判断した（定量セッション1本で 13.3%）。閾値は下げていない。
  欠陥版（14f72f2 版レポート）で 11件 FAIL、直した版で 0件を tests/ が確認する。

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import glob
import io
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:  # pragma: no cover
    def _record_firing(*_a, **_k):
        return False
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:
    def _codex_transcript(p, *_a, **_k):
        if p:
            sys.stderr.write("[baseline_omission_guard] codex_transcript.py not found; "
                             "Codex transcripts are NOT being read.\n")
        return p

MAX_REPORTED = 8

# Matched after NFKC normalisation (full-width digits/letters, ㌽ -> ASCII/ポイント).
DIFF = re.compile(
    r"(?<![\d.])[+]?\d+(?:\.\d+)?\s*%?\s*"
    r"(?:ポイント|pts?|pp|percentage[- ]points?|points?)"
    r"(?![A-Za-z])", re.I)
# Only differences between RATES are in scope. "日経平均250ポイント下落", "12pt
# font", "3ポイントシュート" are not (adversarial QC 2026-10-02).
RATE_CTX = re.compile(r"(%|率|確率|割合|シェア|減少|増加|改善|悪化|上乗せ|差|CAGR|MaxDD|p_zero|rate|share|probability|difference)", re.I)
# Loyalty/reward points and scoring rubrics are not rate differences.
NOT_RATE = re.compile(r"(楽天|dポイント|Ponta|PayPay|Vポイント|還元|付与|貯ま|獲得|マイル|点満点|日経平均|ダウ|指数|売気配|買気配|指値|pips|フォント|font|シュート|点差)", re.I)
# A probability written as a decimal ("P=0.9990") is also a level.
PROB = re.compile(r"(?<![\d.])0\.\d{2,}")
PCT = re.compile(r"(?<![\d.])\d+(?:\.\d+)?\s*[%％](?!\s*(?:クリーム|ゲル|配合|濃度|液|ローション|溶液|含有))")
# Thresholds, tolerances and stress shifts are rules, not observed differences:
# "≤3pp", "±1pp", "−2ppストレス", "閾値0.5pp". Calibration 2026-10-02: these were
# the largest false-positive group (NASDAQ guardrail wording).
THRESHOLD = re.compile(r"([≤≥<>±]|以内|以上|以下|未満|閾値|しきい値|上限|下限|許容|ガードレール|ストレス|世界|シナリオ|ショック|tolerance|threshold|scenario)")
PAIR = re.compile(r"\d+(?:\.\d+)?\s*[%％]?\s*(?:→|⇒|->|から|対|vs\.?)\s*[+−\-]?\d+(?:\.\d+)?")
BASE = re.compile(r"(基準|ベース|ベースライン|プラセボ|基剤|対照|比較群|母数|分母|baseline|placebo|control|vehicle)", re.I)


def _units(text):
    """Split into sentence-like units: table rows, list items, sentences."""
    return [u for u, _b in _units_with_block(text)]


def _units_with_block(text):
    """Yield (unit, block_text). A block is a run of non-blank lines plus the
    line just before it, so a table row sees its header and the sentence that
    introduces the table (where "減少率" etc. usually lives)."""
    lines = (text or "").splitlines()
    out = []
    i = 0
    prev_line = ""
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip():
            j += 1
        block = "\n".join([prev_line] + lines[i:j])
        for line in lines[i:j]:
            s = line.strip()
            if s.startswith("|"):
                out.append((s, block))
                continue
            for part in re.split(r"(?<=[。！？!?])\s*", s):
                if part.strip():
                    out.append((part.strip(), block))
        prev_line = lines[j - 1].strip()
        i = j
    return out


# Answer-level fallback (adversarial QC 2026-10-02): "CAGR +1.44pp" is fine when the
# same answer already states "CAGR 29.1%" elsewhere (typically in a table).
METRIC = re.compile(r"(CAGR|MaxDD|p_zero\w*|Sharpe|[一-龥ァ-ヶー]{1,8}率)", re.I)


def _metric_has_level(unit, full):
    full = DIFF.sub(" ", full)          # the difference itself is not a level
    for m in METRIC.finditer(DIFF.sub(" ", unit)):
        name = re.escape(m.group(1))
        if re.search(name + r"[^\n]{0,24}?\d+(?:\.\d+)?\s*%", full):
            return True
    return False


def _anchored(ctx):
    rest = DIFF.sub(" ", ctx)
    pcts = PCT.findall(rest) + PROB.findall(rest)
    if len(pcts) >= 2:
        return True
    if pcts and BASE.search(rest):
        return True
    # both levels written as a transition / comparison ("0.9983→0.9957", "29.1 対 30.5")
    return bool(PAIR.search(rest))


def analyze(text):
    """Return list of offending units (strings)."""
    hits = []
    full = unicodedata.normalize("NFKC", text or "")
    pairs = _units_with_block(full)
    units = [p[0] for p in pairs]
    for i, (u, block) in enumerate(pairs):
        diffs = [m for m in DIFF.finditer(u)]
        if not diffs:
            continue
        if NOT_RATE.search(u) or not RATE_CTX.search(DIFF.sub(" ", u + "\n" + block)):
            continue
        # every diff in the unit is a threshold/tolerance -> not a reported difference
        if all(THRESHOLD.search(u[max(0, m.start() - 6):m.end() + 8]) for m in diffs):
            continue
        # the base may sit in the same unit or the adjacent sentence/row
        ctx = " ".join(units[max(0, i - 1):i + 2]) if not u.startswith("|") else u
        if _anchored(u) or _anchored(ctx) or _metric_has_level(u, full):
            continue
        hits.append(u)
    return hits


def _read_turn(transcript_path):
    """Return (answer_text, md_texts) for the latest genuine user turn."""
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-4000:]
    except Exception:
        return "", []
    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    try:
        import turn_classify as _tc
        strip = _tc.strip_wrappers
    except Exception:
        def strip(t):
            return t or ""

    def _text(r):
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                return None
            return next((b.get("text") for b in c
                         if isinstance(b, dict) and b.get("type") == "text"), None)
        return c if isinstance(c, str) else None

    try:
        is_machine = _tc.is_machine_row
    except Exception:
        def is_machine(_r):
            return False
    idx = [i for i, r in enumerate(rows)
           if r.get("type") == "user" and _text(r) and not is_machine(r)
           and strip(_text(r)).strip()]
    start = idx[-1] if idx else -1
    answer, mds = [], []
    last_text = ""
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                last_text = b.get("text") or ""
                answer.append(last_text)
            elif b.get("type") == "tool_use" and b.get("name") in ("Write", "Edit", "MultiEdit"):
                inp = b.get("input") or {}
                fp = str(inp.get("file_path") or "")
                if not fp.lower().endswith(".md"):
                    continue
                for k in ("content", "new_string"):
                    v = inp.get(k)
                    if isinstance(v, str):
                        mds.append(v)
                for e in inp.get("edits") or []:
                    if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                        mds.append(e["new_string"])
    # Only the final message is what the user reads as the answer.
    return last_text, mds


REASON = (
    "⛔【baseline_omission】差（ポイント差）だけを書いて、基準の率を書いていない箇所があります（%d件）。\n"
    "基準が1%%なら+25ポイントは26倍、50%%なら1.5倍で、意味がまったく違います。\n"
    "同じ文・表の行に、基準側の率（プラセボ群・対照群・ベースラインが何%%か）か、"
    "両群の率（例: 48.1%% 対 23.2%%）を添えてください。基準が原典に無いなら"
    "「基準の率は原典に記載なし」と明記してください。\n%s")


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            (os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks",
            os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        return
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return
    tp = _codex_transcript(ev.get("transcript_path"))
    if not tp:
        return
    answer, mds = _read_turn(tp)
    hits = analyze(answer)
    for m in mds:
        hits.extend(analyze(m))
    if not hits:
        return
    seen, uniq = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    shown = ["  - " + (h if len(h) <= 160 else h[:160] + "…") for h in uniq[:MAX_REPORTED]]
    if len(uniq) > MAX_REPORTED:
        shown.append("  ... 他 %d 件" % (len(uniq) - MAX_REPORTED))
    _record_firing("baseline_omission_guard", ev)
    out = {"decision": "block", "reason": REASON % (len(uniq), "\n".join(shown))}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


# --- self-test: defective version must FAIL, fixed version must PASS -------
DEFECTIVE = [
    # 2026-10-02 の実際の回答（当時の欠陥版・抜粋）
    "| 薬 | プラセボとの差 |\n|---|---|\n| アゼライン酸 | 14.4ポイント |",
    "| 薬 | プラセボとの差 |\n|---|---|\n| アダパレン＋BPO配合剤（エピデュオなど） | 25.3ポイント |",
    "配合剤との差は約11ポイントで、こちらは値の幅が重なりません。",
    "20%クリームはクリンダマイシン＋BPO配合剤より、12週で18.5ポイント低い減り方でした（221人）。",
    "The combination improved the clearance rate by 12 percentage points.",
    "改善率の差は２５．３Ｐｔだった。",
    "面皰の減少率は25.3%ptの差がついた。",
]
FIXED = [
    "| **アゼライン酸** | **14.4ポイント（8.44〜20.3）** | **37.6%減** | **52.5%減** |",
    "（アゼライン酸14.4・配合剤25.3ポイント）を、大規模試験でプラセボ（基剤）を塗った群の減少率23〜38%に足した目安である。",
    "| BPO 3%＋クリンダマイシン1% | Schaller 2016 | 面皰の平均減少率でアゼライン酸が18.5ポイント低い。総病変は中央値で53.9%減 対 69.0%減 | 41.9% 対 55.9% | 低 |",
    "ガードレール（p_zero_cover悪化≤3pp・枯渇確率悪化≤1pp）は全セル充足。",
    "ただし基剤だけを塗った側も45.6%減っており、上乗せは約14ポイントと控えめである。",
    "楽天ポイントが100ポイント貯まる。",
    "日経平均は250ポイント下落した。",
    "見出しは12ptのフォントにした。",
    "プラセボ群は23%減少した。アゼライン酸は14.4ポイント上乗せした。",
]


def _selftest():
    bad = 0
    for t in DEFECTIVE:
        if not analyze(t):
            print("MISS (should FAIL):", t)
            bad += 1
    for t in FIXED:
        h = analyze(t)
        if h:
            print("FALSE POSITIVE (should PASS):", t)
            bad += 1
    print("selftest: %d defective / %d fixed, failures=%d" % (len(DEFECTIVE), len(FIXED), bad))
    return 1 if bad else 0


def _iter_final_answers(path):
    """Yield the final assistant text of each user turn in a transcript."""
    try:
        rows = [json.loads(l) for l in io.open(path, encoding="utf-8", errors="replace") if l.strip()]
    except Exception:
        return
    last = None
    for r in rows:
        t = r.get("type")
        if t == "user":
            c = (r.get("message") or {}).get("content")
            is_tool = isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
            if not is_tool:
                if last:
                    yield last
                last = None
        elif t == "assistant":
            for b in ((r.get("message") or {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "text" and (b.get("text") or "").strip():
                    last = b.get("text")
    if last:
        yield last


def _calibrate(parent):
    files = glob.glob(os.path.join(parent, "*", "*.jsonl"))
    n = fired = 0
    samples = []
    for f in files:
        for ans in _iter_final_answers(f):
            n += 1
            h = analyze(ans)
            if h:
                fired += 1
                if len(samples) < 40:
                    samples.append((os.path.basename(f)[:8], h[0][:140]))
    print("transcripts=%d answers=%d fired=%d rate=%.2f%%" % (len(files), n, fired, 100.0 * fired / max(n, 1)))
    for s in samples:
        print(" ", s[0], "|", s[1])
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--calibrate" in sys.argv:
        i = sys.argv.index("--calibrate")
        sys.exit(_calibrate(sys.argv[i + 1] if len(sys.argv) > i + 1 else
                            os.path.join(os.path.expanduser("~"), ".claude", "projects")))
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
