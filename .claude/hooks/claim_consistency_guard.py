# -*- coding: utf-8 -*-
"""Stop hook: 今回の回答が、同じ会話で自分が出した推奨・Next Action を黙って覆していないか／
ユーザーが言っていない意向を前提にしていないかを検査する。

WHY (2026-10-12・訂正ダイジェスト C07「論理・判断の誤り」)
------------------------------------------------------------
Defect class (固有名詞なし):
    自分が同じ会話で先に出した推奨・Next Action の前提を、後の回答の所見が崩しているのに、
    「前回の推奨は撤回する」と書かずに新しい結論だけを出す（または、ユーザーが述べていない
    意向・方針を本人のものとして結論の前提に置く）。

最重要の実例（2026-10-08、個人の税務相談セッション）:
    直前の回答の Next Action:
        「BTC を売るなら、株やくりっく株365の利益が少ない年を選んでください。
          そうすれば基礎控除が残り、18%前後に収まります。」
    次の回答（表で答えたターン）:
        「株・くりっく株365の利益は分離課税なので、BTC に掛かる税率は上がりません。」
        「1,500万円までは基礎控除が変わらないので、BTC の税金は3つとも同じです。」
    → 後の所見は前の推奨（利益の少ない年を選べ）を事実上不要にしたが、撤回の一文がない。
    ユーザー原文: 「あなたが言った、下記と矛盾するのでは？」

2件目（2026-10-06、調査レポート）: ユーザーが一言も述べていない「従量課金に寄せる案」を
結論で退け、ユーザー原文「従量課金に寄せるつもりは全くないし、言ってない」。
→ 本フックの P2（意向の帰属）は「あなたは〜したい／〜とのことなので」の明示的な帰属文だけを
見る。この実例は帰属の言い回しを持たない（案を退けただけ）ため**検出しない**（既知の穴、下記）。

既存フックとの境界（重複実装しない）:
    stated_state_guard      … ユーザーが既に述べた属性で分岐する成果物（属性の照合）
    pre_report_quality_guard の state 検査 … 立ち上げ前の現状値を判断理由にする
    premise_recommendation_guard … 1つの .md の中で分析と結論が逆を向く
    本フック                … **会話をまたいだ**自分の推奨との食い違い（P1）と、意向の帰属（P2）

INVARIANTS
----------
P1 自己矛盾（未撤回の推奨反転）:
    同じ transcript の直近 PRIOR_WINDOW 回の回答のうち「推奨文」（Next Action / 推奨 / 結論 行、
    または 〜してください・〜すべき・〜がおすすめ で終わる否定のない文）と、今回の回答の
    「無効化文」（変わらない・同じ・影響しない・上がりません・不要・しなくて大丈夫 等）が、
    汎用語を除いた内容語を MIN_SHARED 個以上共有し、
    かつ今回の回答に撤回・訂正の明示（訂正・撤回・取り下げ・前回の〜は不要 等）がない。
P2 意向の帰属:
    今回の回答（チャット＋このターンの .md 書き込み）が「あなたは／ユーザーは …したい・方針・
    重視・つもり・希望」「ご希望の」「とのことなので」等でユーザーの意向を前提にしているのに、
    その帰属節の内容語がセッション内のユーザー発言・会話要約・記憶のどこにも 1 つも無い。
P3 ユーザー申告の数値: 採用しない（既知の穴の節）。

OUTPUT
------
P1: 1 指示につき 1 回だけ block（decision=block）。同じ指示の 2 回目以降の Stop は systemMessage の警告。
    BLOCK_P1=False で全て警告に落とせる（再較正で偽陽性が増えたときのスイッチ）。
P2: 警告（systemMessage）のみ。判定不能を閾値の引き下げで黙らせず、警告で人間に戻す。

CALIBRATION (実測 2026-10-12 v2・tests/calibrate_claim_consistency_guard.py が本フックの decide() を import)
    コーパス: ~/.claude/projects/*/*.jsonl の主スレッド。再開で重複した prompt 行は ts で除去
    （除去しないと 30 日 616 ターン、除去後 352 ターン）。
      v1 (初版)                 30日 1 / 352 (0.28%)  60日 1 / 806  真陽性 1・偽陽性 0
      v1 MIN_SHARED=2 (棄却)    60日 4 / 806 (0.50%)  真陽性 1・偽陽性 3（「変わらず」の状況報告、
                                同じ原因の再説明、表の列名の言及）
      v2 (採用)                 30日 P1 1 / 352 (0.28%)  P2 0
                                60日 P1 1 / 805 (0.12%)  P2 1 (0.12%)
                                P1: 真陽性 1（2026-10-08 の実例）・偽陽性 0
                                P2: 偽陽性 1（ユーザー「自動車: なし」→回答「車両なしとのことなので」の言い換え）
      PRIOR_WINDOW 3→8          発火数は不変（実例は直前ターン）。古い推奨ほど前提が変わるため 3 を採用
    v2 の変更（Fable の攻撃的検証 2026-10-12 への修正）:
      (2) 撤回語は回答全体ではなく「覆された推奨と内容語を 2 語以上共有する文」にだけ効く。
          撤回文自身が共有しない場合は、撤回文か直前の文が 前回／先ほど／Next Action を名指しして
          いるときに限り隣の文と合わせて数える。「矛盾しません」「食い違いはありません」の否定形は
          撤回とみなさない。v1 では「表記の訂正: 3桁に丸めた」1 行で欠陥版が通り、実データの回答の
          約 2 割に撤回語があって検査が実質的に消えていた。
      (3) ターン内の assistant text を全部つないで判定（今回・過去とも）。v1 は最後のブロックだけを
          見ていたため、欠陥文の後に「以上です。保存しました。」が続くと無言、push 報告の前に書いた
          Next Action は推奨として見えなかった。
      (7) 偽陽性の除外: 無効化文の前に「〜ても／〜でも」（条件の説明）、無効化文か直前 3 文に状況変化の
          明示（状況が変わ／前提が変わ／新しい情報 …）、今回のユーザー発言が推奨の内容語を 2 語以上
          含み かつ 方針変更語（やめ／不要／中止／変更 …）を含む。
      (9) 表のセルも文として扱う（無効化文のみ）。
      ほか: NULLIFY から「変わらず」を外した（「現状は前回から変わらず…操作待ちです」の状態報告が
          v2 の全文連結で 60 日に 1 件出たため）。P2 の「ご要望の〜」は引用「」の中身だけを見る
          （「ご要望どおり用意しました」の後ろは自分の行動で、意向ではない）。
    v3 の変更（Fable 再検証 2026-10-12・除外が広すぎて実例の言い換えが素通りした）:
      条件句の除外は「仮定の操作説明」（を／に〜しても・変えても 等）に限り、しかも比較語を主節に
      絞るだけ（主節が推奨を覆していれば検出）。「利益が増えても」は除外しない。
      状況変化は否定形（新しい情報はありません／状況は変わっていません）を数えない。「ご指示どおり」
      はその文が推奨の内容語を 2 語以上含むときだけ。ユーザーの方針変更は、同じ文に推奨の内容語
      2 語以上と取消語（やめ／不要／中止／変更／しない …）が共起するときだけ（「長くしないで」
      「列を変更」「課税方針」では外さない）。撤回語の否定は直後 6 字以内の ません／ない／なし 全般
      （食い違っていません／矛盾してはいません／矛盾は生じません）。表記・丸め・桁・列の訂正は撤回
      ではない。推奨文の末尾に「のがよい」「を勧めます」を追加。
      較正 v3: 30日 P1 1 / 352・P2 0、60日 P1 1 / 804・P2 1（v2 と同じ 2 件。新しい発火なし）。
    判定: P1 は block（全ターン比 1% 未満・偽陽性 0）。ただし 1 指示 1 回だけで、2 回目以降の
    Stop は警告に落とす。P2 は真陽性を実データで確認できておらず偽陽性 1 のため警告止まり。
赤緑: 欠陥版（2026-10-08 10:54 UTC 直前で切った実 transcript と抜粋 fixture）で block、
    撤回の一文を足した是正版で無音。Fable の回避入力 4 種（否定形・無関係な訂正）を前後どちらに
    足しても block、複数ブロックのターンでも block（tests/test_claim_consistency_guard.py）。
既知の穴（閾値は下げない）:
    - 内容語の共有が 2 語以下の言い換え（tests の P1_KNOWN_MISSES、xfail strict）
    - 数値だけが変わる自己矛盾（「約261万円」→「約283万円」）。再計算の正当な更新と区別できない
    - 推奨の対象を言わずに覆す（「それは不要です」）。指示語の解決はしない
    - P2: 帰属の言い回しを使わない意向の捏造（2026-10-06「従量課金に寄せる案は…」）は対象外
    - P3（ユーザー申告の数値との不一致）は不採用: 唯一の候補例 2026-10-05「80株…1345に足され」は
      回答側が 1,425株[1,345+80] と正しく計算しており、陽性例が 1 件も無く較正できない

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
import time

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
            sys.stderr.write("[claim_consistency_guard] codex_transcript.py not found next to this hook; "
                             "Codex transcripts are NOT being read." + chr(10))
        return p
try:
    import turn_classify as _tc
except Exception:
    _tc = None

NAME = "claim_consistency_guard"
TAIL_BYTES = 6 * 1024 * 1024   # 最初に読む末尾の量。足りなければ倍々に広げる（read_turns）
TIME_BUDGET = 4.0               # 読み広げに使う秒数の上限
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")
PRIOR_WINDOW = 3        # 直近何回分の回答の推奨と照合するか
MIN_SHARED = 3          # 共有する内容語の最小数（P1）
BLOCK_P1 = True         # 較正 2026-10-12: 60日 0.12%・偽陽性 0（docstring）。1 指示 1 回だけ止める

FENCE = re.compile(r"```.*?```", re.S)
SENT_SPLIT = re.compile(r"(?<=[。！？!?])|\n")
TOKEN = re.compile(r"[一-龥々〆ヵヶァ-ヴーA-Za-z0-9][一-龥々〆ヵヶァ-ヴーA-Za-z0-9+#._-]*")
GENERIC = set("""
場合 前提 確認 計算 結果 必要 今回 前回 以下 以上 方法 対応 実行 判断 表示 部分 全体 理由 問題 状態 内容
記載 本文 成果物 説明 リンク 留保 推奨 結論 Next Action main push GitHub ファイル リポ リポジトリ 回答
作業 指示 ユーザー 本人 自分 次 今 後 前 値 件 回 数 点 円 万円 % 年 月 日 時 分 秒 時間 期間 程度 約
可能 可能性 影響 変更 確定 完了 開始 終了 手順 設定 記録 情報 データ 資料 一次資料 実測 検証 確認済み
同じ 同様 最新 現在 現行 既存 新規 通常 一部 全部 合計 以降 以前 まで から ため 使用 利用 選択
OK NG md txt json py
""".split())

DIRECTIVE_LINE = re.compile(r"^\s*(?:[-*>]\s*)?(?:\*\*)?\s*(?:Next Action|推奨|結論|おすすめ)\s*(?:\*\*)?\s*[:：]\s*(?:\*\*)?")
DIRECTIVE_END = re.compile(r"(してください|選んでください|ください|すべきです|すべき|がおすすめです|をおすすめします"
                           r"|推奨します|しましょう|が有利です|のがよいです|のがよい|のが良いです|のが良い"
                           r"|を勧めます|をお勧めします|を推奨します)[。．]?\s*$")
NEG_ANY = re.compile(r"((?<![少危汚幼切])ない|ません|不要|せず|なし|やめ|見送|不利)")
NULLIFY = re.compile(r"(変わらない|変わりません|変化しません|変化しない|影響を受けません|影響を受けない|とも同じ|影響しない|影響しません|影響はありません"
                     r"|関係ない|関係ありません|上がりません|上がらない|下がりません|下がらない|増えません|減りません"
                     r"|不要です|必要ありません|必要はありません|しなくて(?:大丈夫|よい|いい|構いません)"
                     r"|意味がない|意味はありません|効果がない|効果はありません|差は(?:ない|ありません|出ません))")
RETRACT = re.compile(r"(訂正|撤回|取り下げ|取り消|前回の(?:回答|推奨|Next Action|説明|計算)?[^。\n]{0,40}"
                     r"(?:誤り|誤っ|間違|不要|違い|食い違|矛盾|当てはまりません|成り立ちません)"
                     r"|先ほど[^。\n]{0,40}(?:誤り|誤っ|間違|不要|食い違|矛盾)|矛盾し|食い違"
                     r"|(?:前回|先ほど)の(?:推奨|Next Action|回答)は維持"
                     r"|(?:前回|先ほど)の(?:推奨|Next Action)[^。\n]{0,60}(?:場合に限|条件で|ときだけ|場合だけ))")

# 撤回語の直後 6 字以内の否定（矛盾しません／食い違っていません／矛盾してはいません／矛盾は生じません …）
RETRACT_NEG = re.compile(r"^[^。\n]{0,6}?(?:ません|ない|なし)")
# 表記・丸め・列などの訂正は推奨の撤回ではない
RETRACT_NOTATION = re.compile(r"(表記|丸め|桁に|桁で|列名|列の|書式|誤字|誤記|脱字|フォーマット|表示形式|typo)")
REFERS_BACK = re.compile(r"(前回|先ほど|さきほど|Next Action|前の推奨|前の回答)")
# 仮定の操作説明（〜にしても／〜を変えても）。「利益が増えても」のような事実の条件は含めない
HYPO_OP = re.compile(r"[をに][^、。\n]{0,10}?(?:し|変え|上げ|下げ|増やし|減らし|設定し|切り替え|入れ|外し)ても")
STATE_CHANGE = re.compile(r"(状況が変わ|前提が変わ|条件が変わ|事情が変わ|状況の変化|前提の変化|新しい情報|新たに分かった"
                          r"|方針を変え|方針が変わ)")
STATE_NEG = re.compile(r"^[^。\n]{0,6}?(?:ません|ない|なし)")
INSTRUCTED = re.compile(r"(ご指示により|ご指示どおり|ご指示通り|ご指示のとおり|ご指示の通り)")
USER_CANCEL = re.compile(r"(やめ|止め|しない|不要|いらない|要らない|中止|やらない|取りやめ|見送|変更)")

ATTR = re.compile(
    r"(?:(?:あなた|ユーザー|ご本人|本人|貴方|ご自身)(?:は|が|として)(?P<c1>[^。\n]{2,40}?)"
    r"(?:したい|たい(?:と|との|ので|という|意向)|方針|意向|つもり|重視して|優先して|を望ん|をご希望|を希望して|と考えておられ)"
    r"|(?P<c2>[^。\n、（）()「」`*]{2,30}?)(?:とのことなので|とのことですので|とのご希望|というご希望|というご要望|というご意向)"
    # 「ご要望どおり用意しました」の後ろは自分の行動であって意向ではない -> 引用された中身だけを見る
    r"|(?:ご希望|ご要望|ご意向|ご方針)の「(?P<c3>[^」\n]{2,30})」)")


def _tokens(s):
    out = set()
    for t in TOKEN.findall(s or ""):
        t = t.strip("._-")
        if len(t) < 2 or t.isdigit() or re.fullmatch(r"[\d,.]+", t):
            continue
        if t in GENERIC:
            continue
        out.add(t)
    return out


def _sentences(text):
    text = FENCE.sub(" ", text or "")
    return [s.strip() for s in SENT_SPLIT.split(text) if s and s.strip()]


def directives(answer):
    """推奨文: Next Action/推奨/結論 行、または否定を含まない 〜してください 等で終わる文。"""
    out = []
    in_na = False
    for raw in (FENCE.sub(" ", answer or "")).splitlines():
        line = raw.strip()
        if not line:
            in_na = False
            continue
        if line.startswith("|"):
            continue
        is_head = bool(DIRECTIVE_LINE.match(line))
        for s in _sentences(line):
            core = re.sub(r"^\W*(?:Next Action|推奨|結論|おすすめ)\W*", "", s)
            if (is_head or in_na or DIRECTIVE_END.search(s)) and not NEG_ANY.search(core):
                if len(_tokens(core)) >= MIN_SHARED:
                    out.append(core)
        in_na = is_head
    return out


def _units(answer):
    """Sentences, with Markdown table rows split into cells (a nullifier may sit in a cell)."""
    out = []
    for s in _sentences(answer):
        if s.lstrip().startswith("|"):
            out.extend(c.strip() for c in s.strip().strip("|").split("|")
                       if c.strip() and not re.fullmatch(r"[-:\s]+", c))
        else:
            out.append(s)
    return out


def _state_changed(unit):
    """「状況が変わりました」等の明示。「新しい情報はありません」のような否定は数えない。"""
    for m in STATE_CHANGE.finditer(unit):
        if not STATE_NEG.match(unit[m.end():m.end() + 10]):
            return True
    return False


def nullifiers(answer):
    """[(sentence, tokens_to_compare, index)]。
    - 状況変化の明示（無効化文か直前 3 文、否定形は除く）があれば除外。
    - 仮定の操作説明（「SCALE を 1.875 にしても INJECT の判定は変わりません」）は、比較に使う語を
      主節（最後の「ても」より後ろ）に限る。主節だけで推奨の内容語を覆していれば検出は残る。"""
    units = _units(answer)
    out = []
    for i, s in enumerate(units):
        m = NULLIFY.search(s)
        if not m:
            continue
        if any(_state_changed(u) for u in units[max(0, i - 3):i + 1]):
            continue
        toks = _tokens(s)
        hyp = list(HYPO_OP.finditer(s[:m.start()]))
        if hyp:
            toks = _tokens(s[hyp[-1].end():])
        out.append((s, toks, i))
    return out


def _instructed_near(units, i, directive_tokens):
    """「ご指示どおり…」が無効化文か直前 3 文にあり、その文が推奨の内容語を 2 語以上含む。"""
    return any(INSTRUCTED.search(u) and len(_tokens(u) & directive_tokens) >= 2
               for u in units[max(0, i - 3):i + 1])


def user_cancelled(prompt, directive_tokens):
    """ユーザー発言の同じ文の中に、推奨の内容語 2 語以上と取消語（やめ／不要／中止／変更／しない …）が共起する。"""
    for sent in _sentences(prompt or ""):
        if USER_CANCEL.search(sent) and len(_tokens(sent) & directive_tokens) >= 2:
            return True
    return False


def _is_retraction(sent):
    """RETRACT を含み、その語が否定されていない（「矛盾しません」「食い違いはありません」は撤回ではない）。"""
    if RETRACT_NOTATION.search(sent):
        return False                       # 「表記の訂正: 3桁に丸めました」は推奨の撤回ではない
    for m in RETRACT.finditer(sent):
        if not RETRACT_NEG.match(sent[m.end():m.end() + 10]):
            return True
    return False


def retracted(answer, directive_tokens):
    """覆された推奨と内容語を2語以上共有する撤回文があるか。撤回文自身が共有しないときは、
    撤回文か直前の文が「前回／先ほど／Next Action」を名指ししている場合に限り隣の文と合わせて数える。
    回答のどこかに撤回語があるだけでは通さない（Fable 検証 2026-10-12: 「表記の訂正: 3桁に丸めた」
    1行で欠陥版が通り、実データ 616 ターン中 120 の回答に撤回語があって検査が消えていた）。"""
    units = _units(answer)
    for i, s in enumerate(units):
        if not _is_retraction(s):
            continue
        if len(_tokens(s) & directive_tokens) >= 2:
            return True
        prev = units[i - 1] if i else ""
        if REFERS_BACK.search(s):            # 「前回の推奨は撤回します。〜は…」: 前後1文で対象を名指し
            window = " ".join(units[max(0, i - 1):i + 2])
        elif REFERS_BACK.search(prev):       # 「前回の Next Action『〜』は不要でした。撤回します。」
            window = prev + " " + s
        else:
            continue
        if len(_tokens(window) & directive_tokens) >= 2:
            return True
    return False


def p1(answer, prior_answers, prompt=""):
    """[(prior_directive, current_sentence, shared_tokens)]"""
    if not answer:
        return []
    nulls = nullifiers(answer)
    if not nulls:
        return []
    units = _units(answer)
    hits, seen = [], set()
    for prev in prior_answers[-PRIOR_WINDOW:]:
        for d in directives(prev):
            dt = _tokens(d)
            if retracted(answer, dt):
                continue
            if user_cancelled(prompt, dt):
                continue                   # 直前のユーザー発言がその推奨の対象について方針を変えた
            for s, st, i in nulls:
                if _instructed_near(units, i, dt):
                    continue
                shared = dt & st
                if len(shared) >= MIN_SHARED and (d, s) not in seen:
                    seen.add((d, s))
                    hits.append((d, s, sorted(shared)))
    return hits


def p2(body, user_corpus):
    """[(attribution_sentence, missing_tokens)] — 帰属節の内容語がユーザー側に1つも無いもの。"""
    hits = []
    uc = user_corpus or ""
    for m in ATTR.finditer(FENCE.sub(" ", body or "")):
        clause = m.group("c1") or m.group("c2") or m.group("c3") or ""
        toks = _tokens(clause)
        if not toks:
            continue
        if any(t in uc for t in toks):
            continue
        a, b = m.start(), m.end()
        hits.append((body[max(0, a - 20):b + 10].replace("\n", " "), sorted(toks)))
    return hits


def decide(answer, md_body, prior_answers, user_corpus, prompt=""):
    """Pure decision. {'p1': [...], 'p2': [...]}"""
    return {"p1": p1(answer, prior_answers, prompt), "p2": p2((answer or "") + "\n" + (md_body or ""), user_corpus)}


# ---------------------------------------------------------------- transcript
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_user_row(d):
    if d.get("type") != "user" or d.get("isSidechain"):
        return None
    if d.get("isCompactSummary"):
        return "compact"
    if not ("promptSource" in d or "permissionMode" in d):
        # Codex rollouts converted by codex_transcript.to_claude_rows carry neither key nor a uuid;
        # every Claude Code row has a uuid. Without this, the hook would be silent on Codex.
        if "uuid" in d or "sessionId" in d:
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


def iter_turns(lines):
    """Yield dicts {ts, prompt, answer, md, compact} per human turn (compact summaries reset nothing
    but are yielded as kind 'compact' so the caller can add them to the user corpus)."""
    cur = None
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        k = _is_user_row(d)
        if k == "prompt":
            if cur:
                yield cur
            cur = {"ts": d.get("timestamp", ""), "prompt": _text(d.get("message")), "texts": [], "md": [],
                   "compact": False}
        elif k == "compact":
            if cur:
                yield cur
            cur = None
            yield {"ts": d.get("timestamp", ""), "prompt": _text(d.get("message")), "texts": [], "md": [],
                   "compact": True}
        elif d.get("type") == "assistant" and cur is not None:
            for b in ((d.get("message") or {}).get("content") or []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    cur["texts"].append(b["text"])
                elif b.get("type") == "tool_use" and b.get("name") in ("Write", "Edit", "MultiEdit"):
                    inp = b.get("input") or {}
                    if (inp.get("file_path") or "").lower().endswith(".md"):
                        cur["md"].append(inp.get("content") or inp.get("new_string") or "")
                        for e in inp.get("edits") or []:
                            if isinstance(e, dict):
                                cur["md"].append(e.get("new_string") or "")
    if cur:
        yield cur


def read_turns(tp, start_bytes=None, grow=True, time_budget=None):
    """末尾から読み、今回のユーザー行と照合に要る直前 PRIOR_WINDOW 回が揃うまで読む量を倍にする。
    (turns, ok)。ok=False は上限（ファイル全体か時間予算）まで読んでも今回のユーザー行が無いこと。
    WHY: 現ターン内に 7MB の tool_result があると、固定 6MB の末尾読みではユーザー行が切れ、
    iter_turns が今回の回答を拾えず無言になった（Fable 第3回検証 2026-10-12・再現済）。"""
    size = os.path.getsize(tp)
    budget = start_bytes or TAIL_BYTES
    t0 = time.time()
    limit = TIME_BUDGET if time_budget is None else time_budget
    while True:
        start = max(0, size - budget)
        with open(tp, "rb") as f:
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()
        if start:
            lines = lines[1:]           # 途中から読んだ最初の行は壊れている
        turns = list(iter_turns(lines))
        real = [t for t in turns if not t["compact"]]
        have_current = bool(turns) and not turns[-1]["compact"]
        if start == 0 or (have_current and len(real) > PRIOR_WINDOW):
            return turns, have_current or (bool(turns) and turns[-1]["compact"])
        if not grow or time.time() - t0 > limit:
            return turns, have_current
        budget *= 2


def final_answer(turn):
    """ターン内（ユーザー発言から次のユーザー発言まで）の assistant text を全部つないだもの。
    最後のブロックだけだと、欠陥文の後に「以上です。保存しました。」が続く回答や、push 報告の前に
    書いた Next Action を見落とす（Fable 検証 2026-10-12: 複数ブロックのターンが 445/616）。"""
    return "\n\n".join(turn.get("texts") or [])


def clean_prompt(t):
    if _tc is None:
        return t
    try:
        return _tc.strip_wrappers(t)
    except Exception:
        return t


def load_memory(pattern=None):
    pat = pattern or os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "memory", "*.md")
    out = []
    for fn in glob.glob(pat):
        try:
            with io.open(fn, encoding="utf-8", errors="replace") as f:
                out.append(f.read())
        except Exception:
            continue
    return "\n".join(out)


def build_context(turns, memory_text=""):
    """turns: list from iter_turns (oldest first, last = current). -> (answer, md, prior_answers, user_corpus)"""
    cur = turns[-1]
    prior = [final_answer(t) for t in turns[:-1] if not t["compact"] and t.get("texts")]
    corpus = "\n".join(clean_prompt(t["prompt"]) for t in turns) + "\n" + memory_text
    return final_answer(cur), "\n".join(cur["md"]), prior, corpus, clean_prompt(cur["prompt"])


def reason_text(res):
    lines = []
    if res["p1"]:
        lines.append("【推奨との食い違い（P1）】今回の回答の所見が、この会話で先に出した推奨を無効にしているのに、撤回の一文がない:")
        for d, s, sh in res["p1"][:3]:
            lines.append("・前の推奨「%s」\n  今回「%s」（共通語: %s）" % (d[:120], s[:120], "・".join(sh[:6])))
        lines.append("前の推奨がもう成り立たないなら、回答の冒頭に「前回の『〜』は撤回します（理由: 〜）」と書け。"
                     "両立するなら「前回の推奨は〜の場合に限り有効」と条件を1文で書け（このどちらかで通る）。")
    if res["p2"]:
        lines.append("【意向の帰属（P2）】ユーザーの意向として書いた内容が、この会話のユーザー発言・要約・記憶のどこにも無い:")
        for s, toks in res["p2"][:3]:
            lines.append("・「%s」（ユーザー側に無い語: %s）" % (s[:140], "・".join(toks[:6])))
        lines.append("本人が言っていない意向なら「前提: 〜と解釈した。違えば言ってくれ」に書き換えるか、その前提を外して結論を立て直せ。")
    return "\n".join(lines)


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
    turns, ok = read_turns(tp)
    if not ok:
        sys.stderr.write("[claim_consistency_guard] 検査できなかった: transcript の末尾から今回のユーザー発言を"
                         "見つけられない（巨大な tool_result か時間予算切れ）。この回答の推奨との食い違いは未検査。\n")
        return
    if not turns or turns[-1]["compact"]:
        return
    answer, md, prior, corpus, prompt = build_context(turns, "")
    res = decide(answer, md, prior, corpus, prompt)
    if res["p2"]:      # memory is read only when needed (the attributed intent may be stated there)
        res["p2"] = p2(answer + "\n" + md, corpus + "\n" + load_memory())
    if not (res["p1"] or res["p2"]):
        return
    _record_firing(NAME, ev)
    text = reason_text(res)
    if BLOCK_P1 and res["p1"]:
        key = hashlib.sha1((turns[-1]["ts"] + turns[-1]["prompt"]).encode("utf-8", "replace")).hexdigest()[:16]
        mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x")
                                               if ch.isalnum() or ch in "-_") + "_" + key)
        if not os.path.exists(mark):
            try:
                os.makedirs(STATE_DIR, exist_ok=True)
                open(mark, "w").close()
            except Exception:
                pass
            sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": text},
                                               ensure_ascii=True).encode("ascii"))
            sys.stdout.buffer.flush()
            return
    # ensure_ascii + bytes: CP932 stdout corrupts kanji ending in 0x5C (see review_gate.py)
    sys.stdout.buffer.write(json.dumps({"systemMessage": "[claim_consistency_guard] " + text},
                                       ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
