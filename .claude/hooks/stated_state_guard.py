# -*- coding: utf-8 -*-
"""Stop hook: block a reader-dependent branch when the user already stated which side applies.

WHY (2026-10-09)
----------------
Defect class (no proper nouns): 読み手の属性で手順や結論が分かれる成果物を
書くとき、会話・要約・記憶に既にある本人の属性を照合せず、不特定多数向けの
分岐と本人への再質問で書く.

The incident: on 2026-10-07 the user typed 「すべて一般口座で行っているため確定
申告をする予定です」. Two days later, in the same session, a tax-filing
procedure was written for them that opened with 「最初に口座区分を確かめてくだ
さい」, split every step into 特定預りの分／一般預りの分, and closed with 「口座区分
…を確かめ、結果を教えてください」. The fact had NOT been lost: the original
prompt was still in the .jsonl and the compact summary 40 seconds before the
request still said 「一般口座・確定申告」. Claude declared a 前提 line, but
searched only the repo, and two Fable QCs plus review_gate passed it.
The user's words:
    「一般預りと伝えたはず」
    「ユーザーがすでに伝えてないかを確認するようにすべき…全てのリポジトリの
     案件で関わりそう」

delegation_guard does not cover this (measured: decide() returns None on the
defective answer -- 「確かめ」 is not in its verb list -- and even when it fires,
a 「（本人のみ）」 label lets an already-answered question through). Its design
is "ask only for what only the user knows"; this class is "the user already
told you".

WHAT IT DOES
------------
1. Body = this turn's assistant text + the content/new_string of every .md
   Write/Edit. Fenced code is ignored.
2. BRANCH: two or more different option labels with the same suffix
   (〜口座／〜預り／〜の場合／〜の方／〜プラン／〜契約 …) within 800 chars,
   AND a "which applies to you" request (確かめ／どちら／該当／教えて／次第 …)
   within 600 chars.
3. LOOKUP, newest first, first hit wins:
   ① the user's own typed prompts earlier in this transcript (pasted blocks
     stripped): the sentence must contain stem+suffix-family, ASSERT a state
     (です／している／すべて／のみ …) and not REQUEST one (してください …);
   ② ~/.claude/projects/*/memory/*.md, same assert condition;
   ③ compact summaries, only sentences attributed to the user
     (user／ユーザー／述べ／伝え／stated／said／told).
4. A hit blocks the stop ONCE per instruction, quoting the user's words, and
   asks Claude to collapse to that premise and write
   「前提（ユーザー確認済み）: 〜（根拠: YYYY-MM-DD の発言）」.
   Pass label for a genuinely different case: 「（既述とは別件: 理由）」 in the
   same paragraph as the branch. No hit -> silent (no label needed).

CALIBRATION (measured 2026-10-09, tests/calibrate_stated_state_guard.py,
58 real transcripts / 1,995 turns 2026-07..10, 792 turns with .md writes;
this hook's own branches()/lookup() imported):
    v1 naive keywords        fire 20 (1.00%)  true 1  -- 初版/改訂版/自己申告,
                             compact summary quoting Claude's own words
    v2 +ask-hint +assert     fire  6 (0.30%)  true 1  -- その場合／この場合
    v3 +no deictic/1-char    fire  1 (0.05%)  true 1  <-- adopted
    v4 v3 + suffix 「なら」   fire  8 (0.40%)  true 1  -- rejected
The one firing is the incident turn; defective answer alone fires, defective
.md alone fires, the corrected answer+md is silent. The 18 silent branch turns
were about third parties (料金プラン, 妊娠中の人 …), where silence is right.
Known misses (round 2, thresholds NOT lowered): label without suffix
(「特定なら…一般なら…」), English-only branch or summary, a bare question with
no option labels (「口座区分を教えてください」).

fail-open: any exception -> exit 0. stop_hook_active -> return.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import glob
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
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:
    def _codex_transcript(p, *_a, **_k):
        if p:
            sys.stderr.write("[stated_state_guard] codex_transcript.py not found next to this hook; "
                             "Codex transcripts are NOT being read." + chr(10))
        return p
try:
    import turn_classify as _tc
except Exception:
    _tc = None

NAME = "stated_state_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")


def memory_glob():
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "memory", "*.md")


# ---- v3 settings (calibration 2026-10-09). Do not widen without re-running the calibration.
SUFFIX = r"(?:の場合|の分|の方|であれば|預り|預かり|口座|プラン|契約|会員|居住|在住|ユーザーの場合|の人)"
FAMILY = {"預り": "(?:預り|預かり|口座)", "預かり": "(?:預り|預かり|口座)", "口座": "(?:預り|預かり|口座)",
          "の場合": "(?:の場合|なら|で|です|である|を使|にして|になって)", "の分": "(?:預り|預かり|口座|の分)",
          "の方": "(?:の方|です|である|で)", "であれば": "(?:なら|で|です|である)", "の人": "(?:です|である|で)"}
STEM = r"[^\s、。，．（）()「」『』【】\[\]*:：/・|｜#>=<→←]{1,10}"
LABEL = re.compile(r"(?<![^\s、。（）「」【】*:：/・|｜\-■●◆\d]) ?(" + STEM + r")(" + SUFFIX + r")"
                   r"(?=[はがも、：:\s（(]|です|だけ|のみ|なら|の取引|の分)")
STOP = set((
    "その この あの 以下 上記 下記 多く 通常 標準 既存 新規 最新 旧 新 他 別 同 各 全 両 前 後 今 次 先 本 当 該 "
    "上 下 左 右 大 小 多 少 正 負 良 悪 可 不可 必要 不要 最悪 最良 最善 最低 最高 一部 全部 一方 他方 片方 双方 "
    "ほか それ これ あれ どの どちら いずれ 何 なに 失敗 成功 エラー 異常 正常 無 有 なし あり 未 済 空 満 偶数 奇数 "
    "真 偽 OK NG 一般的 具体的 典型的 特別 例外 原則 基本 例 上限 下限 以上 以下 未満 超 以外 同様 違う 異なる 同じ "
    "同一 類似 デフォルト 既定 初期 自動 手動 現在 過去 将来 短期 長期 中期 直近 全体 部分 個別 共通 固有 任意 必須 "
    "推奨 非推奨 有効 無効 停止 実行 開始 終了 完了 継続 中断 利用 使用 不使用 対象 対象外 該当 非該当 一致 不一致 "
    "肯定 否定 賛成 反対 採用 不採用 棄却 多数 少数 最初 最後 上記以外 それ以外 これ以外 そうでない 否 不明 判定不能 "
    "発火 未発火 ブロック 警告 無反応").split())
ASK_HINT = re.compile(r"確かめ|確認し|確認する|確認して|どちら|いずれ|どれに|該当|当たるか|教えて|お知らせ"
                      r"|分からない場合|不明な場合|次第|によって(?:変|異|分)")
ASSERT = re.compile(r"です|でした|である|している|してます|しています|してる|して(?:い)?る|で行って|を使って|使ってい"
                    r"|に住んで|を持って|持ってい|になってい|にしてい|契約して|加入して|開設して|保有して"
                    r"|すべて|全て|全部|のみ|だけ|しかない|しかありません")
REQUEST = re.compile(r"してください|して下さい|してほしい|して欲しい|お願いし|にしてくれ|にして。|になるように")
USER_MARK = re.compile(r"\buser\b|ユーザー|述べ|伝え|stated|said|told|according to the user|user's", re.I)
# pass label: the branch is about a different case than the one the user stated
EXEMPT = re.compile(r"[（(]既述とは別件")


def _ok_stem(s):
    s = s.lstrip("—－-ー ")
    if len(s) < 2 or re.fullmatch(r"[そこあど][のれ]?|そう|こう", s):   # その場合/この場合 are not option labels
        return False
    return (s not in STOP and not re.fullmatch(r"[\dA-Za-z.%,]+", s)
            and bool(re.search(r"[぀-ヿ一-鿿A-Za-z]", s)))


def _paragraph(t, p):
    s = t.rfind("\n\n", 0, p)
    e = t.find("\n\n", p)
    return t[s + 1 if s >= 0 else 0:e if e >= 0 else len(t)]


def branches(text):
    """[(suffix, frozenset(stems), pos)]: >=2 distinct stems with the same suffix within
    800 chars and an ASK_HINT within 600 chars. A group whose paragraph carries
    「（既述とは別件: …）」 is excused."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    hits = [(m.start(), m.group(1), m.group(2)) for m in LABEL.finditer(t)]
    out, seen = [], set()
    for i, (p, s, suf) in enumerate(hits):
        if not _ok_stem(s):
            continue
        stems = {s}
        for q, s2, suf2 in hits[i + 1:]:
            if q - p > 800:
                break
            if suf2 == suf and s2 != s and _ok_stem(s2):
                stems.add(s2)
        if len(stems) < 2:
            continue
        if not ASK_HINT.search(t[max(0, p - 600):p + 800]):
            continue
        if EXEMPT.search(_paragraph(t, p)):
            continue
        key = (suf, frozenset(stems))
        if key not in seen:
            seen.add(key)
            out.append((suf, frozenset(stems), p))
    return out


def _sentences(txt):
    return re.split(r"(?<=[。\n])", txt or "")


def lookup(groups, prior_rows, memory):
    """prior_rows: [(ts, text, kind)] with kind in {"prompt","compact"}, oldest first.
    memory: [(path, text)]. Returns [(label, kind, where, sentence)], one per matched stem."""
    found = []
    for suf, stems, _p in groups:
        fam = FAMILY.get(suf, re.escape(suf))
        for s in sorted(stems):
            pat = re.compile(re.escape(s) + fam)
            hit = None
            for ts, txt, kind in reversed(prior_rows):          # newest first
                if kind != "prompt":
                    continue
                for sent in _sentences(txt):
                    if pat.search(sent) and ASSERT.search(sent) and not REQUEST.search(sent):
                        hit = (s + suf, "prompt", ts, sent.strip()[:160])
                        break
                if hit:
                    break
            if not hit:
                for fn, txt in memory:
                    for sent in _sentences(txt):
                        if pat.search(sent) and ASSERT.search(sent) and not REQUEST.search(sent):
                            hit = (s + suf, "memory", os.path.basename(fn), sent.strip()[:160])
                            break
                    if hit:
                        break
            if not hit:
                for ts, txt, kind in reversed(prior_rows):
                    if kind != "compact":
                        continue
                    for sent in _sentences(txt):
                        if pat.search(sent) and USER_MARK.search(sent):
                            hit = (s + suf, "compact", ts, sent.strip()[:160])
                            break
                    if hit:
                        break
            if hit:
                found.append(hit)
    # newest typed statement first: when both sides match, the latest one is the current state
    by = lambda k: sorted([h for h in found if h[1] == k], key=lambda h: h[2], reverse=(k != "memory"))
    return by("prompt") + by("memory") + by("compact")


def decide(body, prior_rows, memory):
    """Pure decision: list of hits (empty = silent)."""
    groups = branches(body)
    if not groups:
        return []
    return lookup(groups, prior_rows, memory)


# ---------------------------------------------------------------- transcript
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_user_row(d):
    """'prompt' for a human-typed prompt, 'compact' for a compact summary, else None."""
    if d.get("type") != "user" or d.get("isSidechain"):
        return None
    if d.get("isCompactSummary"):
        return "compact"
    if not ("promptSource" in d or "permissionMode" in d):
        return None
    if d.get("promptSource") == "system":
        return None
    if _tc is not None and _tc.is_machine_row(d):
        return None
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return None
    t = _text(d.get("message")).strip()
    if not t or t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:")):
        return None
    return "prompt"


def _clean_prompt(t):
    if _tc is None:
        return t
    return _tc.strip_pasted(_tc.strip_wrappers(t))


def read_turn(tp):
    """(prompt, prompt_ts, body) for the latest human turn, from the transcript tail."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, ans, md = None, "", [], []
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_user_row(d) == "prompt":
            prompt, pts, ans, md = _text(d.get("message")).strip(), d.get("timestamp", ""), [], []
        elif d.get("type") == "assistant" and prompt is not None:
            for b in ((d.get("message") or {}).get("content") or []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    ans.append(b["text"])
                elif b.get("type") == "tool_use" and b.get("name") in ("Write", "Edit", "MultiEdit"):
                    inp = b.get("input") or {}
                    if (inp.get("file_path") or "").lower().endswith(".md"):
                        md.append(inp.get("content") or inp.get("new_string") or "")
                        for e in inp.get("edits") or []:
                            if isinstance(e, dict):
                                md.append(e.get("new_string") or "")
    return prompt, pts, "\n".join(ans) + "\n" + "\n".join(md)


def prior_user_rows(tp, before_ts):
    """[(ts, text, kind)] of human prompts and compact summaries strictly before before_ts.
    Whole file: the statement may be weeks old (the incident's was 2 days / 3,000 rows back).
    Only reached when a branch was found (~1% of turns); 159MB measured at 0.55 s."""
    rows = []
    with io.open(tp, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"user"' not in line or not ("promptSource" in line or "permissionMode" in line
                                            or "isCompactSummary" in line):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            kind = _is_user_row(d)
            if not kind:
                continue
            ts = d.get("timestamp", "")
            if before_ts and ts >= before_ts:
                continue
            txt = _text(d.get("message"))
            rows.append((ts, _clean_prompt(txt) if kind == "prompt" else txt, kind))
    return rows


def load_memory(pattern=None):
    out = []
    for fn in glob.glob(pattern or memory_glob()):
        try:
            with io.open(fn, encoding="utf-8", errors="replace") as f:
                out.append((fn, f.read()))
        except Exception:
            continue
    return out


def reason_text(hits):
    src = {"prompt": "ユーザーの発言", "memory": "記憶ファイル", "compact": "会話要約（ユーザー帰属）"}
    lines = []
    for label, kind, where, sent in hits[:4]:
        lines.append("・「%s」← %s（%s）: 「%s」" % (label, src.get(kind, kind), where[:19], sent))
    both = len({h[0] for h in hits}) >= 2
    return ("【既述状態の照合（1回のみ）】成果物が読み手の属性で分岐し（%s）、本人に確かめさせる形になっているが、"
            "本人はその属性を既に伝えている:\n%s\n"
            "%s"
            "その前提で手順・結論を一本化し、冒頭に「前提（ユーザー確認済み）: 〜（根拠: YYYY-MM-DD の発言）」を書け。"
            "本人への再質問・「どちらか確かめてください」は削る。"
            "分岐が本当に別の対象（第三者・別の口座・将来の変更）についてなら、分岐文と同じ段落に"
            "「（既述とは別件: 理由）」を付けて残してよい。"
            % ("／".join(sorted({h[0] for h in hits})), "\n".join(lines),
               "複数の側が一致した。最も新しい発言を現在の状態とみなし、どちらが現在かを一本化せよ。\n" if both else ""))


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
    prompt, pts, body = read_turn(tp)
    if not prompt or not branches(body):
        return
    hits = decide(body, prior_user_rows(tp, pts), load_memory())
    if not hits:
        return
    key = hashlib.sha1((pts + (prompt or "")).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x")
                                           if ch.isalnum() or ch in "-_") + "_" + key)
    if os.path.exists(mark):
        return          # already blocked once for this instruction
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    # ensure_ascii + bytes: CP932 stdout corrupts kanji ending in 0x5C (see review_gate.py)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason_text(hits)},
                                       ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
