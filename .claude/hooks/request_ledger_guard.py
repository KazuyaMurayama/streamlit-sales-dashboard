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

2026-10-19 (Fable QC I2/I3, tests/test_hook_qc_20261019.py): any verb noun + 〜して / しといて at a
sentence end, and English imperatives, are requests; the kanji of the request's verb (探して→探) is a
keyword, a generic word alone (データ) does not cover, and synonyms / kanji bigrams do (計算→算出,
必要入金額→必要な入金). Pasted material is skipped (<pasted_content> when the prompt has other text,
everything after 「以下のメール…」, 「ユーザー: …」 lines), and an answer that ends by asking which
one is meant is left to delegation_guard. 7 days / 197 turns: firing 11.6% -> 9.6%; C02 recall stays
1/3 (one miss is about an earlier prompt, the other answered with the asked-for word).
Second Fable QC (2026-10-19): 「以下の指摘を直して。」 no longer cuts the listed requests; English lines
in a Japanese prompt are pasted material; an English request answered in Japanese is judged on the
words that can be looked up (EN_JA, identifiers) instead of passing; 「〜に関して。」 is no request.
7 days / 200 turns: firing 9.5%, C02 recall 1/3.

2026-10-26 (C02 again, CORRECTION_DIGEST_20261026: 4 corrections in 7 days). Invariant: the requirements
live in what the prompt POINTS AT (a pasted hand-off, 「下記に回答して」, a GitHub URL / a path given as the
spec), and that material was neither itemised nor read. Two additions:
 (a) SPEC PASTE -- a <pasted_content> block is now itemised when the user's own text points at it as the
     spec (「下記に回答して」「以下の指示どおりに進めて」「添付の要望に対応して」), and a paste-only prompt (a
     hand-off) also counts its bullet directives in dictionary form (「- 結果は X の冒頭から更新する」).
     A paste introduced as material (「以下のメールに返信して」, RLG-FP6) is still skipped.
 (b) SPEC REFS -- a GitHub blob/tree URL in the user's text, or a file path on a line that names it as the
     spec (必読・手本・参照・正典・下記に定めた・に従って・を元に・読んで), must be touched by a tool call this
     turn (Read / git show / Contents API / WebFetch / Grep ... : its basename in the tool input).
     Otherwise the stop is blocked once (shared with the item check: one block per prompt).
     A ref is touched when its basename (or its stem: the user's task.md finds tasks.md) is in a tool input; a
     spec word must sit within NEAR chars of the path (or the line is a label 「- 必読: …」); more than MAX_URLS
     GitHub URLs or a prompt over MAX_REF_TEXT chars is a quoted list / batch job, not a pointer.
 Also: an item whose only word is the go verb (「2本を順に進めて。」「再開して。」) is no deliverable (GO_VERBS).
Real C02 of the week: 0/4 caught -- in all four the pointed files WERE read and the paste items covered; what was
dropped lived in a source the prompt did not name (the predecessor report -> report_format_guard, the book behind an
article, the obvious RCT row of a rating scale, two task sets deferred as one 「未対応」).
Calibration (tests/calibrate_request_ledger_guard.py --compare <old>): 30 days / 823 turns 14.3% -> 14.5% (+1, TP);
120 days / 2,222 turns 14.0% -> 13.8% (+2 TP, -6 rows = 2 distinct 「再開して。」 turns); unread-ref firings 1 in 120 days.
Tests: tests/test_request_ledger_guard_c02_20261026.py (21; the 7 BLOCK/once checks fail on the pre-extension version).
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
    r"|(?:しなさい|しろ|せよ|するな|作るな|書くな)"
    # any verb in the 〜て imperative at the end of a sentence (Fable QC 2026-10-19 I2: 「実行して。」「push して。」
    # 「更新しといて。」 were outside the 20-verb list). Not 「〜について」「〜として」「〜なので」.
    # Only after a verb noun (実行・push・更新): 「〜ようにして」「最小限にして」「〜でやって」 are manner, not deliverables
    # (calibration 2026-10-19: the bare 〜て ending raised firing 11.6% -> 17.3%, all manner instructions).
    # 「〜に関して。」「〜に対して」 are not verbs (QC2 R12)
    r"|(?:(?![関対際即反])[一-鿿]|[ァ-ヶー]|[A-Za-z])\s*し(?:て|てね|ておいて|といて|といてね)\s*[。！!]?\s*$"
    # English requests (RLG-FN4)
    r"|(?i:^\s*(?:please\s+)?(?:fix|update|add|remove|delete|push|run|write|create|check|make|change|implement|test|commit|merge"
    r"|deploy|rename|move|investigate|explain|tell|show|find|search|review|summari[sz]e|compare|list|send|draft|translate"
    r"|refactor|clean|build|install|set|use|keep|stop|start|continue|finish)\b|\bplease\b|\b(?:could|can|would)\s+you\b)")
NOT_REQ = re.compile(r"^(?:OK|ok|はい|了解|ありがとう)")
# Calibration 2026-10-19 (191 real turns): a pointer to material (「添付を確認して」「以下は本当か」
# 「次の検証をしてほしい」「調べてほしいこと：」) and a manner instruction (「簡単にして」) are not
# separate deliverables; their words never show up in the answer, so they fired as misses.
POINTER = re.compile(r"[:：]\s*$|(?:以下|下記|上記|添付|次の)(?:の|を|は|に|について|も)|(?:これ|それ)(?:を|について)")
# 「また、それは適切ですか？」 is a question about the answer's own claim, not a pointer (C02 2026-10-13 miss)
MANNER = re.compile(r"(?:簡単|分かりやす|わかりやす|短く|簡潔|丁寧|批判的|日本語|一言|手間が少な|必要に応じて|できるだけ|なるべく|最小限|ようにし)")
_KW = re.compile(r"[一-鿿]{2,}|[゠-ヿー]{3,}|[A-Za-z][A-Za-z0-9_.\-]{1,}|[0-9]+(?:\.[0-9]+)?[%％]?")
KW_STOP = set(
    "ください 下さい 確認 必要 結果 実行 判断 内容 対応 場合 今回 次回 本当 以下 上記 下記 回答 作業 お願い "
    "進め 方法 状態 状況 可能 理由 以上 全体 部分 情報 報告 説明 検討 実施 着手 修正 反映 現状 並行 同様 "
    "また それ これ あなた 自分 ユーザー 全て すべて 本当 他に もう少し "
    "the to of and for in on at with is it be this that please".split())


def keywords(s):
    out = []
    for w in _KW.findall(s or ""):
        if w in KW_STOP or w.lower() in KW_STOP or len(w) < 2:
            continue
        if w not in out:
            out.append(w)
    return out


# 2026-10-19 (first real run): a subagent hand-back arrives inside
# <system-reminder id=...>...</system-reminder id=...> in the user turn; its indented
# "  - ..." lines were recorded as the user's requests. Injected blocks are not the user's words.
_INJECTED = re.compile(
    r"<(system-reminder|task-notification|agent-message|local-command-[\w-]+|command-[\w-]+)\b[^>]*>"
    r".*?(?:</\1\b[^>]*>|\Z)", re.S)      # an unclosed block runs to the end (Fable QC RLG-FP7)


_PASTED = re.compile(r"<pasted_content\b[^>]*>(.*?)(?:</pasted_content\b[^>]*>|\Z)", re.S)
# a line that introduces pasted material: everything after it is the material, not the user's requests
# (Fable QC RLG-FP6: a pasted mail's 「納期はいつですか？」 was recorded as the user's question)
# 「以下の指摘を直して。\n1. …」 lists the user's own requests (Fable QC2 I-2), and 「次の章である…この記事」 is no intro
MATERIAL_INTRO = re.compile(r"(?:以下|下記|次)の(?!章|節|回|段階|手順|ステップ|点|項目|指摘|作業|タスク)[^。\n、]{0,10}"
                            r"(?:メール|文面|文章|本文|記事|メッセージ|ログ|会話|やり取り|やりとり"
                            r"|テキスト|コメント|引用|資料|議事録|チャット|ダイジェスト|返信|出力)")
# a pasted conversation or digest line (「ユーザー: 最後までやって。」)
SPEAKER = re.compile(r"^\s*[-*・]?\s*(?:ユーザー|利用者|依頼者|User|Claude|assistant|AI|Assistant|Human)\s*[:：]")


def user_text(prompt):
    t = _INJECTED.sub(" ", prompt or "")
    # pasted blocks are material -- unless the prompt is nothing but the paste (then it is the request)
    outside = _PASTED.sub(" ", t).strip()
    if outside:
        t = outside
    else:
        t = _PASTED.sub(lambda m: m.group(1), t)
    lines = t.splitlines()
    for i, ln in enumerate(lines):
        if MATERIAL_INTRO.search(ln):
            lines = lines[:i + 1]
            break
    return "\n".join(ln for ln in lines if not SPEAKER.match(ln)).strip()


# (a) the user's own text points at the paste as the spec: 「下記に回答して」「以下の指示どおりに」「添付の要望に対応して」
SPEC_POINTER = re.compile(r"(?:下記|以下|上記|添付|貼り付け|貼付|引き継ぎ|引継ぎ)(?:に|で|の|を|は|も)?[^。\n]{0,12}?"
                          r"(?:定め|決め|指示|依頼|要望|要件|仕様|タスク|手順|引き継|引継|回答|答え|対応|従|沿|とおり|通り"
                          r"|進め|実施|反映|やっ|質問|指摘|修正|直し)")
# a hand-off bullet in dictionary form: 「- 結果は X の冒頭から更新する（同じ日なら…）」「②M2 の例外を直す」
_BULLET = re.compile(r"^\s*(?:[-*・■□●◆▶]|[①-⑳]|\d+[.)．、]|[（(]\d+[)）])")
_DICT_END = re.compile(r"(?:する|しない|し直す|直す|探す|作る|書く|読む|使う|残す|守る|消す|削る|足す|置く|送る|測る"
                       r"|進める|始める|止める|確かめる|調べる|載せる|入れる|まとめる|揃える|そろえる|分ける|変える|替える"
                       r"|測り直す|探し直す|作り直す|書き直す|やり直す)$")


MAX_POINTER_TEXT = 600   # 「下記に回答して」 is short; a 3,000-char classification prompt quoting pastes is not a pointer


def _spec_pastes(prompt):
    """(text of pasted blocks the user points at as the spec, True when the prompt is a paste-only hand-off)."""
    t = _INJECTED.sub(" ", prompt or "")
    outside = _PASTED.sub(" ", t).strip()
    blocks = [m.group(1) for m in _PASTED.finditer(t)]
    if not blocks:
        return "", False
    if not outside:
        return "", True             # user_text() already returns the paste itself
    if len(outside) > MAX_POINTER_TEXT or MATERIAL_INTRO.search(outside) or not SPEC_POINTER.search(outside):
        return "", False            # material (a mail to answer) or no pointer: the paste stays skipped
    return "\n".join(blocks), False


def _dict_directive(line):
    s = re.sub(r"[（(][^（）()]*[）)]\s*[。．]?\s*$", "", line.strip())
    s = re.sub(r"[。．]\s*$", "", s).strip()
    return bool(_BULLET.match(line)) and bool(_DICT_END.search(s))


def split_items(prompt):
    """Request items of a prompt: [{"text", "kw"}]. Quoted/material pastes are skipped; a paste the user points
    at as the spec (and a paste-only hand-off) is itemised, bullet directives in dictionary form included."""
    extra, handoff = _spec_pastes(prompt)
    items = _items_from(user_text(prompt), handoff)
    if extra and len(items) < MAX_ITEMS:
        for it in _items_from(extra, True):
            if it["text"] not in [x["text"] for x in items]:
                items.append(it)
            if len(items) >= MAX_ITEMS:
                break
    return items


def _items_from(t, spec):
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"(?m)^\s*>.*$", " ", t)
    items = []
    parts = []
    if spec:
        rest = []
        for ln in t.splitlines():
            if _dict_directive(ln) and len(ln.strip()) <= MAX_SENT and len(items) < MAX_ITEMS:
                s = _BULLET.sub("", ln, count=1).strip()
                kw = keywords(s)
                if kw and not MANNER.search(s):
                    items.append({"text": s, "kw": kw})
                    continue
            rest.append(ln)
        t = "\n".join(rest)
    # English lines in a Japanese prompt are pasted material (a README's 「Set the env var FOO.」, QC2 R11)
    pj = sum(1 for ch in t if ord(ch) > 0x3000) >= 3
    for part in re.split(r"(?<=[。！？!?])|(?<=\.)\s+(?=[A-Z])|\n", t):
        sub = re.split(r"(?<=[^につとし]て)、|(?<=んで)、", part)
        parts += sub if len(sub) > 1 and REQ.search(sub[-1]) else [part]
    for part in parts:
        s = part.strip()
        if not s or len(s) > MAX_SENT or NOT_REQ.match(s):
            continue
        if s.startswith(("<", "[", "|", "#")):
            continue
        if not REQ.search(s) or (pj and _ja_ratio(s) < 0.05 and not re.search(r"[\\/]", s)):
            continue
        kw = keywords(s)
        vs = verb_stem(s)
        if vs and vs not in kw:
            kw.append(vs)
        if not kw or MANNER.search(s):
            continue
        if kw == [vs] and vs in GO_VERBS:
            continue
        if POINTER.search(s) and len(kw) <= 2:
            continue
        items.append({"text": s, "kw": kw})
        if len(items) >= MAX_ITEMS:
            break
    return items


# the kanji of the verb that carries the request: 「探して」→探, 「計算してください」→計算 (RLG-FN3: 「データについて
# もう少し探してください」 was covered by 「データ」 alone in an answer that never searched)
_VERB = re.compile(r"([一-鿿]+)(?:し|[っいべめせけれきえみびちりにぎ])?(?:て|んで|しといて|といて)(?:ください|下さい|ほしい|欲しい|もらいたい|くれ|ね|よ|おいて)?\s*[。！!？?]?\s*$")
# 「進めて」「着手して」 alone: the go signal of the prompt, answered by doing the other items (2026-10-26)
GO_VERBS = set("進 着手 始 続 開始 再開 継続".split())
# a word that alone says nothing about which request was answered
GENERIC_KW = set("データ ファイル スクリプト コード レポート 資料 記事 テスト シート 結果 一覧 内容 文書 数値 ドキュメント".split())
# answers use other words for the same act (Fable QC RLG-FP3: 計算→算出, シート→スプレッドシート)
SYNONYMS = [set(g.split()) for g in (
    "計算 算出 試算 算定 集計 求め 計上", "確認 照合 検証 確か チェック 点検", "調 調査 検索 探 探索 確認",
    "探 探索 検索 調 調査 捜", "直 修正 訂正 修復 fix", "書 記載 追記 作成 記述 執筆", "作 作成 追加 新規 生成",
    "消 削除 除去 撤去", "送 送信 共有 送付", "更新 反映 アップデート update 書き換", "追加 足 加え add",
    "実行 走ら 回し 実施 run", "反映 更新 適用 取り込", "統合 まとめ 併合 マージ merge", "教 回答 説明 答")]


def verb_stem(s):
    m = _VERB.search(s or "")
    return m.group(1)[-2:] if m else ""


# an English request answered in Japanese (this environment's answers are always Japanese): its words are
# looked up in Japanese. Fable QC2 I-4: the old fail-open let 「Update the README. Push to main.」 pass.
EN_JA = {k: v.split() for k, v in {
    "fix": "直 修正 fix", "bug": "バグ 不具合 bug", "parser": "パーサ parse", "update": "更新 反映 update",
    "add": "追加 加え add", "test": "テスト test", "tests": "テスト test", "push": "プッシュ push", "run": "実行 走ら run",
    "remove": "削除 消 remove", "delete": "削除 消 delete", "build": "ビルド build", "fail": "失敗 fail",
    "fails": "失敗 fail", "error": "エラー error", "check": "確認 チェック check", "write": "書 作成 write",
    "create": "作成 作 create", "commit": "コミット commit", "merge": "マージ 統合 merge", "deploy": "デプロイ 配布 deploy",
    "report": "レポート 報告 report", "script": "スクリプト script", "unit": "単体 unit", "search": "検索 探 search",
    "find": "探 検索 見つ find", "rename": "名前 リネーム rename", "refactor": "リファクタ 整理 refactor",
    "explain": "説明 explain", "why": "原因 理由 なぜ why", "review": "レビュー 確認 review", "install": "インストール install",
    "docs": "文書 ドキュメント docs", "doc": "文書 ドキュメント doc", "readme": "readme"}.items()}


def _checkable(k):
    """A word that can be looked for in a Japanese answer: Japanese, an identifier (parse_date, README, v2), or in EN_JA."""
    return (not re.match(r"^[a-z]+$", k)) or k in EN_JA


def _present(k, low):
    if k in low:
        return True
    if k in EN_JA:
        return any(w in low for w in EN_JA[k])
    for g in SYNONYMS:
        if k in g and any(w in low for w in g):
            return True
    if len(k) >= 4 and re.match(r"^[一-鿿]+$", k):    # 必要入金額 → 必要・入金・金額
        bi = [k[i:i + 2] for i in range(len(k) - 1)]
        return sum(1 for b in bi if b in low) * 2 >= len(bi)
    return False


def _ja_ratio(t):
    t = re.sub(r"\s", "", t or "")
    return sum(1 for ch in t if ord(ch) > 0x3000) / float(len(t) or 1)


def covered(item, text):
    low = (text or "").lower()
    kws = [k.lower() for k in item["kw"]]
    if _ja_ratio(item["text"]) < 0.1 and _ja_ratio(text) > 0.3:
        # English (or path-only) request answered in Japanese: judge on the words that can be looked up;
        # if none can, words cannot decide (fail-open, RLG-FP2)
        kws = [k for k in kws if _checkable(k)]
        if not kws:
            return True
    hits = [k for k in kws if _present(k, low)]
    need = min(2, max(1, (len(kws) + 1) // 2))
    if len(hits) < need:
        return False
    # hits made only of generic words cover nothing when the item has a specific word (RLG-FN3)
    specific = [k for k in kws if k not in {g.lower() for g in GENERIC_KW}]
    return not specific or any(k in specific for k in hits)


def uncovered(items, text):
    return [it for it in items if not covered(it, text)]


# (b) spec references: a GitHub file URL anywhere in the user's text, or a path on a line naming it as the spec
_GH_URL = re.compile(r"https?://(?:github\.com/[\w.\-]+/[\w.\-]+/(?:blob|tree|raw)/[^\s/)>\]]+/|raw\.githubusercontent\.com/"
                     r"[\w.\-]+/[\w.\-]+/[^\s/)>\]]+/)([A-Za-z0-9_.\-/%~+]+)")
_PATH = re.compile(r"(?<![\w/.\-])((?:[A-Za-z]:[\\/]|~[\\/]|\.{1,2}[\\/])?(?:[\w.\-ぁ-んァ-ヶー一-鿿・]+[\\/])*"
                   r"[\w\-ぁ-んァ-ヶー一-鿿・][\w.\-ぁ-んァ-ヶー一-鿿・]*\.(?:md|py|json|jsonl|gs|js|ts|txt|csv|ya?ml|toml|html|ipynb|sh|ps1))(?![\w])")
SPEC_REF = re.compile(r"必読|手本|を参照|参照して|参照し|定め|に従|沿って|とおり|通りに|をもとに|を元に|を基に|読んで|読み込んで|目を通")
# a label line 「- 必読: a.md と b.md」 points at every path on it
SPEC_LABEL = re.compile(r"^\s*(?:[-*・■]\s*)?(?:必読|手本|参照|正典|仕様|参考)[^:：\n]{0,8}[:：]")
NEAR = 15            # a spec word must be this close to the path (「X.md、下記に定めた」 yes; 「X.md が良いか。…参照すべき」 no)
MAX_URLS = 3         # more GitHub URLs than this = a pasted list (a digest of past prompts), not a pointer
MAX_REF_TEXT = 2500  # a longer prompt is a batch job quoting other prompts (correction digest, 2026-09-29), not a pointer


def _base(p):
    try:
        from urllib.parse import unquote
        p = unquote(p)
    except Exception:
        pass
    b = re.split(r"[\\/]", p.rstrip("/\\"))[-1]
    return re.sub(r"^.*[ぁ-ん](?=[A-Za-z0-9_])", "", b)


def spec_refs(prompt):
    """[(shown, basename)] that the user points at as the spec. Material pastes, code and quotes are skipped."""
    extra, _h = _spec_pastes(prompt)
    t = user_text(prompt) + ("\n" + extra if extra else "")
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"(?m)^\s*>.*$", " ", t)
    out, seen = [], set()
    if len(t) > MAX_REF_TEXT:
        return out
    urls = list(_GH_URL.finditer(t))
    for m in (urls if len({u.group(1) for u in urls}) <= MAX_URLS else []):
        b = _base(m.group(1))
        if b and b not in seen:
            seen.add(b)
            out.append((m.group(0), b))
    for ln in t.splitlines():
        label = bool(SPEC_LABEL.match(ln))
        if not label and not SPEC_REF.search(ln):
            continue
        ln2 = _GH_URL.sub(" ", ln)
        for m in _PATH.finditer(ln2):
            if not label and not SPEC_REF.search(ln2[max(0, m.start() - NEAR):m.end() + NEAR]):
                continue
            b = _base(m.group(1))
            if b and b not in seen and len(b) >= 5:
                seen.add(b)
                out.append((m.group(1), b))
    return out[:MAX_ITEMS]


def unread_refs(refs, events):
    """refs whose basename appears in no tool input of this turn (Read / Bash git show / Grep / WebFetch / MCP ...)."""
    blob = []
    for e in events:
        if e[0] == "tool":
            try:
                blob.append(json.dumps(e[2], ensure_ascii=False))
            except Exception:
                blob.append(str(e[2]))
    s = "\n".join(blob)
    try:
        from urllib.parse import unquote
        s = s + "\n" + unquote(s)
    except Exception:
        pass
    s = s.replace("\\\\", "/").replace("\\", "/").lower()
    def seen(b):
        b = b.lower()
        stem = b.rsplit(".", 1)[0]
        return b in s or (len(stem) >= 4 and stem in s)
    return [r for r in refs if not seen(r[1])]


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
    t = user_text(_text(d.get("message")))
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# 「口座Aは3つあります。どれを指しますか？」: asking what the request means is answering it, not dropping it
CLARIFY = re.compile(r"(?:どれ|どちら|どの|いずれ|何を|どこ)[^。？?]{0,30}(?:指しますか|ですか|でしょうか|ますか)\s*[？?]\s*$")


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
    return hashlib.sha1(user_text(prompt).encode("utf-8", "replace")).hexdigest()[:16]


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
    if led.get("blocked"):
        return
    items = led.get("items") or []
    miss, unread = decide(prompt, items, events)
    if not miss and not unread:
        return
    led["blocked"] = True
    led["uncovered"] = [m["text"] for m in miss]
    led["unread"] = [r[0] for r in unread]
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False)
    except Exception:
        pass
    _record_firing(NAME, ev)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": block_reason(items, miss, unread)},
                                       ensure_ascii=True).encode("ascii"))


def decide(prompt, items, events):
    """(uncovered items, unread spec refs) of one turn -- the calibration script calls this too."""
    last = next((e[1] for e in reversed(events) if e[0] == "text"), "")
    if CLARIFY.search(last.strip()[-200:]):
        return [], []   # the answer ends by asking which one is meant; delegation_guard checks that question
    evidence = turn_from_events(events)
    miss = uncovered(items, evidence) if len(items) >= 2 else []
    unread = [r for r in unread_refs(spec_refs(prompt), events)
              if not re.search(u"(?:未読|読めな|開けな|取得できな)[^\n]{0,80}" + re.escape(r[1]), evidence)
              and not re.search(re.escape(r[1]) + u"[^\n]{0,80}(?:未読|読めな|開けな|取得できな)", evidence)]
    return miss, unread


def block_reason(items, miss, unread):
    out = [u"【依頼の台帳照合（1回のみ）】"]
    if miss:
        out.append(u"この指示（貼り付けた引き継ぎ・「下記」で指した本文を含む）には %d 件の要求があり、うち %d 件に対応する"
                   u"記述が最終回答にも今回書いたファイルにも見当たらない:%s\n"
                   u"各要求について、今このターンで対応して結果を書くか、対応しない理由を「未対応: <要求> — 理由」の形で"
                   u"回答に明記せよ（黙って落とさない）。"
                   % (len(items), len(miss), "".join(u"\n  - %s" % m["text"][:100] for m in miss)))
    if unread:
        out.append(u"指示が仕様として指したファイル・URL を、このターンのツール呼び出しで1度も開いていない:%s\n"
                   u"Read（ローカルの clone）・git show origin/main:<パス>・GitHub Contents API のどれかで中身を読み、"
                   u"そこに定められた節・表・列・要求を成果物と1件ずつ突き合わせて結果を回答に書け。"
                   u"読めない場合は「未読: <ファイル名> — 理由」と書け。"
                   % "".join(u"\n  - %s" % r[0][:140] for r in unread))
    return "\n".join(out)


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
