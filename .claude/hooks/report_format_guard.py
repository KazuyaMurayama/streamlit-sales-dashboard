# -*- coding: utf-8 -*-
"""レポートの更新版で、前の版の節・表・表の列を黙って削らせない（PreToolUse: Write/Edit/MultiEdit と git commit）。

WHY（2026-10-19 依頼者指摘）
    NASDAQ_backtest の COVER_BEST_LATEST_20261019.md（commit 69830f1）は、前の版
    COVER_MIN3_BEST_20260824.md（v2）の後継として書かれたが、v2 の H2/H3 見出し 24 本のうち 0.1b
    （分布表）・3.4（感度表）・6.1〜6.4（頑健性）など大半を落とし、7 本だけで書き直した。依頼者:
    「v2 から、勝手に大幅にフォーマット削るな。何かの理由で削るべきものだけ削れ」「レポートの更新版で、
    フォーマットを勝手に削るべきではない。削るべきものがあれば、ユーザーに推奨するべき」。

不変条件（固有名では塞がない）
    「レポートの新しい版は、前の版にあった見出し（H2〜H4）・その中身・表・表の列を、依頼者の承認なしに落としてはならない」
    前の版 = ①同じファイルのディスク上の内容と、このセッションで最初に見た内容（1本ずつ削る Edit の累積を見る）
             ②git commit 時は HEAD の版・24時間前の版・7日前の版（導入日 2026-10-19 以降のコミットだけ）・改名前のパス・
               同じコミットで消した同じディレクトリのレポート（名前の先頭語が同じか、見出しの3割以上が対応するもの）
             ③本文の冒頭 30 行で、版の語（前版・旧版・v2・更新版・後継・改訂・置き換え・からの遷移・をベースに 等）と
               同じ文にあるリンク／ファイル名の .md レポート
             ④同じディレクトリのレポートで、1 行目の廃盤印の「後継:」がこのファイルを指すもの
             ⑤（①〜④の宣言が無いとき）同じディレクトリで、日付・-vN を除いたファイル名が同じで日付が古いレポートの
               うち、見出しの3割以上が新しい版と対応するもの（RETRO_日付 のような別件の定期レポートを前の版にしない）
    落とした = 前の版の見出しに対応する新しい版の見出しが無い（番号・括弧書き・記号を除いた文字の 2 文字組の
               Dice 係数 0.5 以上か包含、で 1 対 1 に対応づけ。残りは同じ番号・同じ階層で対応づけるが、その数は
               max(2, 前の版の見出しの2割) まで＝番号だけ残して中身を全部差し替える書き換えを通さない）、
               または対応する見出しの中身（表の見出し行を除く本文行）が 3 行以上 → 0 行、10 行以上 → 1/5 未満になった
               （下位見出しへ移したものは除く）。
    レポート = .md で、ファイル名に _YYYYMMDD / _YYYY-MM-DD / _vN がある・CURRENT_*.md・冒頭 15 行に作成日/最終更新日が
               ある、のどれか。README/CLAUDE/AGENTS/tasks/CHANGELOG/FILE_INDEX と .claude/ .codex/ 配下は外す。

発火（較正で決めた。下記）
    見出し: 承認されていない欠落（中身を空にした見出しを含む）が MIN_HEAD 本以上
    表:     前の版の表が MIN_TABLES 個以上あり新しい版で TABLE_RATIO 倍未満、または対応する節の中で減った表
            （ただし全体で減った数まで＝表を付録へ移しただけは数えない）が MIN_SEC_TABLES 個以上
    列:     対応する節の表が 2 列以上狭くなった、全体で 3 列以上狭くなった、または列名が 2 本以上入れ替わった
            （幅を広げた表・全列の改名は書き直しとして数えない）
    行:     データ行が 6 行以上の表が 1 行以下になった（表を残して中身を空にする）

承認（理由だけでは通さない。依頼者の発言の引用が要る）
    本文に `<!-- format-drop: 削る対象（見出し名・番号、表・列・行を減らすなら「表」「列」、全部なら「全部」）承認「依頼者の発言の引用」 -->`
    引用は ①空白を除いて 6 字以上 ②削除の語（削・消・不要・要らない・外す・省く・カット・落とす・捨てる・取り除く・廃止 等。
    「書き直して」「作り直して」「変えていい」は事故当時の指示そのもので削除の承認ではない）を含む ③このセッションの
    transcript の依頼者の発言1件の中にそのまま含まれる（ハーネスの行・会話の要約・サブエージェントの行を除く。
    サブエージェントの transcript では承認を一切通さない）④引用の後 30 字に「却下・だめ・しないで・いや・本当に・？」等が無い。
    落とした見出しごとに、印の対象と引用の「削除の語を含み、残す・否定の語（残・維持・ないで・ずに・せず 等）を含まない句」
    （読点・句点で区切る）の両方がその見出しの番号（点の無い番号は「6章」「§6」「6.」の形だけ。「0.1〜0.3」の範囲も可）か
    名前を指すときだけ許す（対象は Claude が書くので、対象だけでは許さない）。「6章は丸ごと削って」は 6 章の小節も含む。
    「全部」は、引用の句が構成の名詞と助詞だけを前に置いた「全部＋削除の語」で始まり、引用のどこにも残す・否定の語が
    無いときだけ（「6章の小節は全部削って」は全部の承認ではない）。「表」「列」は対象で単独の語（「表記ゆれ」の表は
    数えない）、かつ引用の削除の句にあるとき。表の列名が消えても、同じ値の列が新しい表にあれば改名とみなす。
    確かめた承認は文書ごとに ~/.claude/state/report_format_guard/approved.json に残し（「全部」の承認は残さない）、
    その文書の後の Edit・コミット（24 時間前・7 日前の版との比較）で同じ削除を再び止めない。別の文書には効かない。
    transcript を読めないときは通し、
    firing_log に unverified として記録する。git commit では、コミットメッセージの
    `Format-Drop-Ok: <対象> 承認「引用」` でもよい（同じく文書ごとに残る）。
    セッションの起点: このセッションで最初に見た内容。Claude が最後に書いた内容とディスクが違えば（依頼者の手・git pull）
    今の内容で取り直す。

止め方
    exit 2 + stderr。メッセージは「戻す」か「依頼者に削除を推奨して承認を得る」の2択を示す。

較正（実測）
    tests/calibrate_report_format_guard.py で 50 リポ（governance 配下 49＋NASDAQ_backtest）の git 履歴から、
    レポートの版の組 1,277 組（同じファイルの直前の版 1,222・宣言された前の版 55）を再生した（2026-10-19）。
    発火 155 組 = 12.1%（見出しの規則だけなら 15 % 前後、行の規則を 1/3 未満にすると 14.2%）。
    見出しで発火した組の無作為 12 件を目で分類: 9 件は節の削除（book_summary の「批判的に読むなら」
    「誰が読むべきか」の削除＝今回の事故と同じ型、WFA レポートの v2 が 10 見出し中 8 本を落とした 等）、
    3 件は中身の入れ替え（買い物比較の順位の見出し・生活ビジョンの見出しの言い換え）。実物の事故
    （NASDAQ 69830f1・ce93e8e）はどちらも発火し、正しい復元版（302e3c3）は通る。
    閾値: MIN_HEAD を 1 にすると 16.4%、3 にすると 10.6%（事故の型は 2 本以上で落とすので 2）。

既知の未対応（Fable 攻撃・独立 QC 2026-10-19 の残り。tests の KNOWN_LEAKS と同じ）
    取りこぼし: 表1個だけの削除・太字への格下げ1本＋表→箇条書き1個（各閾値の下）／先頭の | が無い表／
      前の版を一切宣言せず、名前も日付も違い、見出しの対応が3割未満の新しいファイルへの書き直し
      （commit で同じディレクトリのレポートを消していれば②で拾う）／Bash（sed・python）で書いたファイルは
      commit まで見ない／見出し1本だけの未承認の削除（MIN_HEAD の下）／transcript を読めないときの引用は検証せず通す
      （firing_log に記録）／承認の記録は機械ごと（別の機械では 7 日前の版との比較で再び止まりうる）／
      空行を挟まず続く2つの表は1つと数える（GFM の描画と同じ）。
    止めすぎ（承認の印で通す）: 番号の無い見出しの言い換え2本以上・節の統合・列の統合・節内の2表の統合／
      別テーマのレポートを版の語と同じ文でリンク／「章立ては全部作り直していい」だけの指示（削除の語での確認が要る）。
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_fired
except Exception:  # firing_log 未配備でも本体は動く
    def _record_fired(name, ev):
        return False

NAME = "report_format_guard"
MIN_HEAD = 2          # 較正で決定（docstring）
MIN_TABLES = 3
TABLE_RATIO = 0.7
MIN_SEC_TABLES = 2    # 対応する節の中で減った表の数
SIM = 0.5
GUT_LINES = 10        # 本文がこの行数以上の節が
GUT_RATIO = 5         # 1/5 未満に縮んだら「中身が空」と同じに扱う（QC E1）
MIN_ROWS = 6          # データ行がこの数以上の表が
ROW_KEEP = 1          # この行数以下に減ったら発火（QC E2。1/3 未満では発火率が 12.1% → 14.2% に上がり、
                      # ダイジェストの更新・一覧の絞り込みなど中身の更新まで止めた。較正 2026-10-19）
INSTALLED = "2026-10-19"   # 7 日前の版を比べるのはこの日以降のコミットだけ（導入前の履歴で止めない）
HEAD_LINES = 15       # 作成日/最終更新日を探す行数
DECL_LINES = 30       # 前の版の宣言を探す行数
STEM_MATCH = 0.3      # ⑤ 名前だけで前の版とみなす見出しの対応率
STATE = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME)

NOT_REPORT = re.compile(r"^(?:readme|claude|agents|tasks|todo|changelog|file_index|memory|license|spec|index)(?:[._-].*)?\.md$", re.I)
EXCLUDED_DIR = re.compile(r"(?:^|/)(?:\.claude|\.codex|\.git|node_modules|tests?/fixtures)/", re.I)
DATE_NAME = re.compile(r"[_-](20\d{2}-?\d{2}-?\d{2})(?:[-_]v(\d+))?\.md$", re.I)
VER_NAME = re.compile(r"[_-]v(\d+)\.md$", re.I)
STAMP = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*)?(?:作成日|最終更新日|更新日)")
# 較正（2026-10-19）: 単独の「改訂」「新版」、大文字の V1〜V11（検証項目の番号）は前の版の宣言ではなかった
# （MBA 科目シリーズの索引、比較 README、検証番号 V3 が誤って前の版を作った）。版番号は小文字の v と全角ｖ だけ
VERSION_WORD = re.compile(r"(?:前版|旧版|前の版|前回版|前回の|直前の版|更新版|改訂版|後継|置き換え|置換|からの遷移|から更新|を更新"
                          r"|をベースに|を基に|をもとに|に代わる|を引き継|の続き|の後継"
                          r"|(?<![A-Za-z0-9])[vｖ][0-9０-９]+(?![A-Za-z0-9])|第\d+版|(?i:previous|supersed|replaces|based on))")
MDREF = re.compile(r"\[[^\]]*\]\(([^)\s#]+\.md)(?:#[^)]*)?\)|(?<![\w./(\-])([\w.\-ぁ-んァ-ヶー一-鿿]+\.md)\b")
DEPRECATED = re.compile(r"廃盤|deprecated", re.I)
MARK = re.compile(r"<!--\s*format-drop\s*[:：](?P<body>.*?)-->", re.S | re.I)
TRAILER = re.compile(r"Format-Drop-Ok\s*[:：](?P<body>[^\n]*?「[^」]+」[^\n]*)", re.I)
APPROVAL = re.compile(r"承認\s*(?:「(?P<q>.+)」|『(?P<q2>.+)』|\"(?P<q3>[^\"]+)\")", re.S)   # 引用の中の「」を許す（Fable FP11）
# 削除の語。「書き直して」「作り直して」「変えていい」は事故当時の指示そのもので、削除の承認ではない（Fable QC A1b）
DROP_WORD = re.compile(r"削|消|不要|要らな|いらな|外し|外す|省|なくして|無くして|カット|やめて|止めて|落と|捨て|取り除|除い|抜い|廃止"
                       r"|drop|remove|delete|cut", re.I)
ALL_WORD = re.compile(r"全部|すべて|全て|全体|全節|丸ごと")
_STRUCT = r"(?:章立て|節|章|見出し|セクション|表|列|項目|構成|フォーマット)"
# 「全部」の承認: 全部の語のすぐ後に削除の語（間は助詞か構成の名詞だけ）。「全ての数値を…、不要な注記は削って」を通さない（A2）
ALL_DROP = re.compile(r"(?:全部|すべて|全て|全体|全節|丸ごと)(?:の" + _STRUCT + r")?(?:は|を|も|とも)?(?:" + DROP_WORD.pattern + r")", re.I)
# 残す・否定の語。句の中にあれば、その句は削除の承認ではない（「6.1は残して」「削らないで」「変えずに」。QC3-1）
KEEP_WORD = re.compile(r"残|維持|そのまま|keep|ないで|ずに|せず|しない|しなく|な[いく]て|not\b|don'?t", re.I)
# 引用の後（同じ発言の 30 字以内）にあれば承認ではない（疑問・撤回。QC A5・QC3-4）
REJECT_AFTER = re.compile(r"却下|だめ|ダメ|駄目|不可|しないで|するな|ないで|ではなく|じゃなくて|言ってない|言っていない|NG"
                          r"|いや|待って|まって|本当に|ほんとに|[?？]|か[。．]")
SENT = re.compile(r"[。．!！?？\n]")
PHRASE = re.compile(r"[、,，;；。．!！?？\n]")
KIND_IN_QUOTE = {"表": re.compile(r"(?<![図年代発公辞一])表(?![記現示明情彰紙題面すさしせそ])"),
                 "列": re.compile(r"(?<![系配行序並羅陳数整直])列(?![挙島車強])")}


# ---------------------------------------------------------------- structure

def _strip_code(text):
    """コードブロックを、行数を保った無害な行に置き換える（中の ## を見出しにしない。中身は本文行として数える。QC3-10）。
    行頭の空白は [ \\t]*（\\s* は改行をまたいで後戻りする。D2）。"""
    return re.sub(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$",
                  lambda m: "\n".join("·" for _ in m.group(0).split("\n")), text or "")


def norm(s):
    s = re.sub(r"<!--.*?-->", "", s or "", flags=re.S)
    s = re.sub(r"[（(][^（）()]*[）)]", "", s)                     # 括弧書きは注記
    s = re.sub(r"[*_`~\[\]]|\]\([^)]*\)", "", s)
    s = re.sub(r"^\s*(?:§|第)?\s*[0-9０-９]+(?:[.．\-][0-9０-９a-z]+)*[.．)）章節]?\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*[A-Za-z][.)]\s+", "", s)
    return re.sub(r"[\s\W_]+", "", s).lower()


def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def sim(a, b):
    if not a or not b:
        return 0.0
    if (len(a) >= 2 and a in b) or (len(b) >= 2 and b in a):
        return 1.0
    x, y = _bigrams(a), _bigrams(b)
    return 2.0 * len(x & y) / (len(x) + len(y))


_NUM = re.compile(r"^\s*(?:§|第)?\s*([0-9０-９]+(?:[.．][0-9０-９a-z]+)*)", re.I)
_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def structure(text):
    """(見出し [(level, raw, norm, 番号, 本文行数)], 表 [(属する見出しの添字, 見出しセル, データ行数, データ行のセル)])。H2〜H4。
    本文行数 = 次の見出しまでの空でない行（表の見出し行・区切り行を除く。表のデータ行は数える）。"""
    lines = _strip_code(text).splitlines()
    hs, ts, cur = [], [], -1
    body = {}
    skip = set()
    in_table = False
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,4})\s+(.*?)\s*#*\s*$", ln)
        if m and norm(m.group(2)):
            nm = _NUM.match(m.group(2))
            hs.append([len(m.group(1)), m.group(2).strip(), norm(m.group(2)), nm.group(1) if nm else None, 0])
            cur = len(hs) - 1
            in_table = False
            continue
        a = ln.strip()
        if a.startswith("|") and i + 1 < len(lines) and _SEP.match(lines[i + 1].strip()) \
                and not (i > 0 and lines[i - 1].strip().startswith("|")):
            ts.append([cur, [c.strip() for c in a.strip("|").split("|")], 0, []])
            skip.update((i, i + 1))
            in_table = True
        elif in_table and a.startswith("|") and i not in skip:
            ts[-1][2] += 1
            ts[-1][3].append([c.strip() for c in a.strip("|").split("|")])
        elif not a.startswith("|"):
            in_table = False
        if a and i not in skip and not a.startswith("#") and cur >= 0:
            body[cur] = body.get(cur, 0) + 1
    for k, v in body.items():
        hs[k][4] = v
    return [tuple(h) for h in hs], [tuple(t) for t in ts]


def headings(text):
    return [h[:3] for h in structure(text)[0]]


def tables(text):
    return [t[1] for t in structure(text)[1]]


def _has_child(hs, j):
    return j + 1 < len(hs) and hs[j + 1][0] > hs[j][0]


def match_headings(oh, nh):
    """前の版の見出し → 新しい版の見出し（1対1）。文字の類似で割り当て、残りは同じ番号・同じ階層で割り当てる
    （「10. QCチェック」→「10. 品質の確認」 の言い換えを落としたと数えない）。番号だけの割り当ては
    max(2, 前の版の見出しの2割) まで（番号を残して見出しを全部差し替える書き換えを通さない。Fable FN03）。"""
    pairs = []
    exact_only = len(oh) * len(nh) > 250000          # 見出し 500 本級は完全一致だけ（D1: 2文字組の総当たりが秒単位になる）
    for i, o in enumerate(oh):
        for j, n in enumerate(nh):
            v = (1.0 if o[2] == n[2] else 0.0) if exact_only else sim(o[2], n[2])
            if v >= SIM:
                pairs.append((-v, abs(i / max(1, len(oh)) - j / max(1, len(nh))), i, j))
    pairs.sort()
    mo, mn = {}, set()
    for _v, _d, i, j in pairs:
        if i not in mo and j not in mn:
            mo[i] = j
            mn.add(j)
    cap = max(2, int(0.2 * len(oh)))
    for i, o in enumerate(oh):
        if i in mo or not o[3] or cap <= 0:
            continue
        for j, n in enumerate(nh):
            if j not in mn and n[3] == o[3] and n[0] == o[0]:
                mo[i] = j
                mn.add(j)
                cap -= 1
                break
    return mo


# ---------------------------------------------------------------- approval marks

def _marks(text, extra=""):
    """[(対象の文字列, 引用)]"""
    out = []
    for body in [m.group("body") for m in MARK.finditer(text or "")] + [m.group("body") for m in TRAILER.finditer(extra or "")]:
        q = APPROVAL.search(body)
        target = APPROVAL.sub("", body)
        out.append((target, (q.group("q") or q.group("q2") or q.group("q3")).strip() if q else None))
    return out


def _squash(s):
    return re.sub(r"\s+", "", s or "").lower()


def quote_shape_ok(target, q):
    """引用の形の条件（①②）。何を削ってよいかは、落とした見出しごとに引用の中身で確かめる（_quote_names）。
    対象（target）は Claude が書くので、形の判定に使わない（Fable QC A1/A7）。"""
    sq = _squash(q)
    return len(sq) >= 6 and bool(DROP_WORD.search(sq))


def _all_ok(q):
    """文書全体の削除の承認: 引用のどれかの句が、構成の名詞と助詞だけを前に置いた「全部＋削除の語」で始まり
    （「6章の小節は全部削って」は 6 章だけの承認。QC3-2）、引用のどこにも残す・否定の語が無い
    （「全部削っていい、0章だけ残して」「全部は消さないで」。QC3-2）。"""
    if KEEP_WORD.search(q or ""):
        return False
    head = re.compile(r"^\s*(?:" + _STRUCT + r"(?:は|を|も)?)?\s*" + ALL_DROP.pattern, re.I)
    return any(head.search(ph) for ph in PHRASE.split(q or ""))


def _ascii_num(s):
    return (s or "").translate(str.maketrans("０１２３４５６７８９．", "0123456789."))


def _num_in(num, text):
    """番号 num（6 / 6.1）が text に見出しの番号として現れる。6.1 は 6.10・16.1 と区別し、点の無い番号（6）は
    「6章」「6節」「§6」「第6」「6.」のときだけ（「表の1行目」「2026-10-19」の数字を見出しと取らない。QC3-3）。"""
    t = _ascii_num(text)
    n = re.escape(_ascii_num(num))
    if "." in num:
        return re.search(r"(?<![0-9.])" + n + r"(?![0-9]|\.[0-9])", t) is not None
    return re.search(r"(?:§\s*|第\s*)" + n + r"(?![0-9])|(?<![0-9.\-/])" + n + r"(?:\s*[章節]|\.(?![0-9]))", t) is not None


def _range_has(o, text):
    """「0.1〜0.3」「6.1-6.4」の範囲に見出し o の番号が入る（QC3-8）。"""
    if not o[3] or "." not in o[3]:
        return False
    num = _ascii_num(o[3])
    for m in re.finditer(r"(\d+)\.(\d+)\s*[〜~～\-－–]\s*(?:(\d+)\.)?(\d+)", _ascii_num(text)):
        a, b1, c, b2 = m.group(1), int(m.group(2)), m.group(3) or m.group(1), int(m.group(4))
        parts = num.split(".")
        minor = re.match(r"\d+", parts[1]) if len(parts) == 2 else None      # 0.1b は 0.1 の枝として範囲に入れる
        if a == c and parts[0] == a and minor and b1 <= int(minor.group(0)) <= b2:
            return True
    return False


def _has_num(o, text):
    return bool(o[3]) and (_num_in(o[3], text) or _range_has(o, text))


def _parent_nums(num):
    parts = _ascii_num(num or "").split(".")
    return [".".join(parts[:k]) for k in range(1, len(parts))]


def _quote_names(o, q):
    """引用の、削除の語を含み残す・否定の語を含まない句（読点・句点で区切る。QC3-1）が、見出し o（番号か名前、
    または「6章は丸ごと」のように親の番号＋全部・丸ごと）を指す。"""
    for ph in PHRASE.split(q or ""):
        if not DROP_WORD.search(ph) or KEEP_WORD.search(ph):
            continue
        if _has_num(o, ph):
            return True
        if ALL_WORD.search(ph) or "ごと" in ph:
            if any(_num_in(pn, ph) for pn in _parent_nums(o[3])):
                return True
        hn, sn = o[2], re.sub(r"[\s\W_]+", "", ph).lower()
        if len(hn) >= 2 and hn in sn:
            return True
        b = _bigrams(hn)
        if len(hn) >= 4 and len(b & _bigrams(sn)) >= 0.6 * len(b):
            return True
    return False


def _target_names(o, target):
    if _has_num(o, target) or any(_num_in(pn, target) for pn in _parent_nums(o[3])):
        return True
    parts = [norm(p) for p in re.split(r"[、,/／・;；\n]|\s{2,}", target)]
    tn, name_norm = norm(target), o[2]
    return bool(name_norm) and (name_norm in tn or any(sim(name_norm, p) >= SIM for p in parts if p))


def _excused(o, marks, approved):
    """見出し o の欠落が承認されている: 印の対象と引用の両方が o を指す（引用の削除の文に o の番号か名前）、
    または対象が「全部」で引用が「全部＋削除の語」。"""
    for target, q in marks:
        if q is None or q not in approved:
            continue
        if ALL_WORD.search(target) and _all_ok(q):
            return True
        if _target_names(o, target) and _quote_names(o, q):
            return True
    return False


def _excused_kind(kind, marks, approved):
    """表の数・表の列の減少（kind = 表 / 列）の承認: 対象に「表」「列」が単独の語であり（「表記ゆれ」の表は数えない。A8）、
    引用の削除の語を含む文にも表・列がある。または「全部」の承認。"""
    for target, q in marks:
        if q is None or q not in approved:
            continue
        if ALL_WORD.search(target) and _all_ok(q):
            return True
        if not re.search(r"(?:^|[\s、,/／・;；:：「」『』（）()])" + kind + r"(?:ごと|の数|全体)?(?=$|[\s、,/／・;；:：「」『』（）()])", target.strip()):
            continue
        if any(DROP_WORD.search(ph) and not KEEP_WORD.search(ph) and KIND_IN_QUOTE[kind].search(ph) for ph in PHRASE.split(q)):
            return True
    return False


# ---------------------------------------------------------------- compare

def compare(old, new, marks=(), approved=()):
    """前の版 old → 新しい版 new で、承認されていない欠落を返す。"""
    approved = set(approved)
    oh, ot = structure(old)
    nh, nt = structure(new)
    mo = match_headings(oh, nh)
    missing = []
    for i, o in enumerate(oh):
        if i not in mo:
            label = o[1]
        elif not _has_child(nh, mo[i]) and ((o[4] >= 3 and nh[mo[i]][4] == 0) or
                                             (o[4] >= GUT_LINES and nh[mo[i]][4] * GUT_RATIO < o[4])):
            # 見出しだけ残して中身を消す・1 行に縮める（Fable FN01・QC E1）。下位見出しへ移したのは除く（較正）
            label = o[1] + "（中身が空）"
        else:
            continue
        if not _excused(o, marks, approved):
            missing.append(label)
    mo[-1] = -1
    sec_lost, narrowed, col_loss, shrunk = 0, [], 0, []
    for i, j in mo.items():
        ots = [(c, r, d) for s, c, r, d in ot if s == i]
        nts = [(c, r, d) for s, c, r, d in nt if s == j]
        sec_lost += max(0, len(ots) - len(nts))
        for (oc, orows, odata), (nc, nrows, ndata) in _match_tables(ots, nts):
            w = len(oc) - len(nc)
            lost = [k for k, c in enumerate(oc) if norm(c) and not any(sim(norm(c), norm(d)) >= SIM for d in nc)]
            col_loss += max(0, w)
            # 列を減らして別の列を足す（Fable FN07）。列名が消えても、同じ値の列が新しい表にあれば改名とみなす
            # （英略号 → 日本語の改名を止めない。QC3-9）。広げた表・全列の改名は書き直しの範囲として数えない
            # （較正: NASDAQ 302e3c3 の正しい復元版が4表で止まった）
            gone = [k for k in lost if not _renamed(odata, k, ndata)]
            swapped = len(gone) >= 2 and len(nc) <= len(oc) and len(lost) < len(oc)
            if w >= 2 or swapped:
                narrowed.append(" | ".join(oc))
            if orows >= MIN_ROWS and nrows <= ROW_KEEP:
                shrunk.append("%s（%d → %d 行）" % (" | ".join(oc), orows, nrows))   # データ行の削減（QC E2）
    sec_lost = min(sec_lost, max(0, len(ot) - len(nt)))     # 付録へ移しただけは数えない（Fable FP04）
    tbl = None
    if (len(ot) >= MIN_TABLES and len(nt) < TABLE_RATIO * len(ot)) or sec_lost >= MIN_SEC_TABLES:
        if not _excused_kind("表", marks, approved):
            tbl = (len(ot), len(nt))
    if col_loss >= 3 and not narrowed:
        narrowed = ["全体で %d 列狭くなった" % col_loss]          # 全表から1列ずつ（Fable FN06）
    if narrowed and _excused_kind("列", marks, approved):
        narrowed = []
    if shrunk and _excused_kind("表", marks, approved):
        shrunk = []
    return {"headings": missing, "tables": tbl, "columns": narrowed, "rows": shrunk,
            "fire": len(missing) >= MIN_HEAD or tbl is not None or bool(narrowed) or bool(shrunk),
            "n_old_headings": len(oh), "sec_tables_lost": sec_lost, "col_loss": col_loss}


def _col(data, k):
    return [r[k] for r in data if k < len(r) and r[k] not in ("", "-", "—")]


def _renamed(odata, k, ndata):
    """前の版の k 列目の値の半分以上が、新しい版のどれかの列にそのままある（列名だけ変えた）。値が無ければ判定不能＝改名扱い。"""
    ov = _col(odata, k)
    if not ov:
        return True
    width = max((len(r) for r in ndata), default=0)
    return any(sum(1 for v in ov if v in set(_col(ndata, m))) * 2 >= len(ov) for m in range(width))


def _match_tables(ots, nts):
    """同じ節の表を1対1に対応づける（列名の重なりが大きい順、同点は並び順）。"""
    cand = []
    for a, (oc, _r, _d) in enumerate(ots):
        os_ = {norm(c) for c in oc if norm(c)}
        for b, (nc, _r2, _d2) in enumerate(nts):
            ns = {norm(c) for c in nc if norm(c)}
            cand.append((-len(os_ & ns) / max(1, len(os_ | ns)), abs(a - b), a, b))
    cand.sort()
    ua, ub, out = set(), set(), []
    for _j, _d, a, b in cand:
        if a not in ua and b not in ub:
            ua.add(a)
            ub.add(b)
            out.append((ots[a], nts[b]))
    return out


# ---------------------------------------------------------------- reports and predecessors

def is_report(path, text=None):
    p = (path or "").replace("\\", "/")
    base = os.path.basename(p)
    if not base.lower().endswith(".md") or NOT_REPORT.match(base) or EXCLUDED_DIR.search("/" + p):
        return False
    if DATE_NAME.search(base) or VER_NAME.search(base) or base.upper().startswith("CURRENT_"):
        return True
    if text is None:
        text = _read(path) or ""
    return any(STAMP.match(ln) for ln in (text or "").splitlines()[:HEAD_LINES])


def _read(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _first_line(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.readline()
    except Exception:
        return ""


def _key(base):
    m = DATE_NAME.search(base)
    if m:
        return base[:m.start()].lower(), (m.group(1).replace("-", ""), int(m.group(2) or 1))
    m = VER_NAME.search(base)
    if m:
        return base[:m.start()].lower(), ("", int(m.group(1)))
    return None, None


def declared(text):
    """本文の冒頭で、版の語と同じ文にある .md の参照（リンク先またはファイル名）。"""
    out = []
    for ln in (text or "").splitlines()[:DECL_LINES]:
        refs = list(MDREF.finditer(ln))
        for k, m in enumerate(refs):
            ref = m.group(1) or m.group(2)
            if re.match(r"^[a-z]+:", ref, re.I):
                continue
            start = refs[k - 1].end() if k else 0
            end = refs[k + 1].start() if k + 1 < len(refs) else len(ln)
            before = re.split(r"[。．!！?？]", ln[start:m.start()])[-1][-40:]
            after = re.split(r"[。．!！?？]", ln[m.end():end])[0][:30]
            if VERSION_WORD.search(before + " " + after):
                out.append(ref)
    return out


def predecessors(path, text, exists=os.path.isfile, read=_read, listdir=os.listdir, first_line=None):
    """宣言された・名前から分かる前の版のパス（絶対）。"""
    d = os.path.dirname(os.path.abspath(path))
    me = os.path.normcase(os.path.abspath(path))
    out = []
    for ref in declared(text):
        cand = os.path.normpath(os.path.join(d, ref))
        if os.path.normcase(cand) != me and exists(cand) and is_report(cand, read(cand) or ""):
            out.append(cand)
    base = os.path.basename(path)
    stem, ver = _key(base)
    try:
        names = listdir(d)
    except Exception:
        names = []
    same_stem = []
    for nm in names:
        if not nm.lower().endswith(".md") or nm == base:
            continue
        full = os.path.join(d, nm)
        s2, v2 = _key(nm)
        if stem and s2 == stem and v2 < ver:
            same_stem.append((v2, full))
        first = (first_line or _first_line)(full)
        if DEPRECATED.search(first) and re.search(r"後継[^\n]*" + re.escape(base), first):
            out.append(full)
    if not out and same_stem:
        # ⑤ 名前だけが手掛かり: 同じ日付の -vN は同じ文書の改訂（命名規則）。日付が違えば、見出しが3割以上
        # 対応するときだけ（RETRO_日付 のような別件の定期レポートを除く。Fable FP12）
        v2, full = max(same_stem)
        oh = structure(read(full) or "")[0]
        nh = structure(text)[0]
        if v2[0] == ver[0] or (oh and len(match_headings(oh, nh)) >= STEM_MATCH * len(oh)):
            out.append(full)
    seen, res = set(), []
    for p in out:
        k = os.path.normcase(p)
        if k not in seen:
            seen.add(k)
            res.append(p)
    return res


# ---------------------------------------------------------------- approval

def user_texts(transcript_path):
    """依頼者が打った発言（ハーネス行・会話の要約・サブエージェントの行を除く）。読めなければ None。"""
    r = _user_rows(transcript_path)
    return None if r is None else r[0]


def _user_rows(transcript_path):
    """(依頼者の発言, サブエージェントの transcript か)。読めなければ None。"""
    if not transcript_path:
        return None
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return None
    try:
        import turn_classify as _tc
    except Exception:
        _tc = None
    out = []
    side = False
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if not isinstance(r, dict):
            continue
        if r.get("isSidechain") or r.get("agentId"):
            side = True                       # サブエージェントの user 行は親エージェントの指示文（Fable QC A4）
            continue
        if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
            continue
        if (r.get("origin") or {}).get("kind") in ("peer", "task-notification"):
            continue
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        if not isinstance(c, str):
            continue
        c = re.sub(r"<system-reminder>.*?</system-reminder>", "", c, flags=re.S)
        if _tc is not None:
            c = _tc.strip_wrappers(c)
        out.append(c)
    return out, side


def _pathkey(path):
    return os.path.normcase(os.path.abspath(path or "")).replace("\\", "/")


def _approved_store():
    """{パス|引用: {"t", "target", "q"}}。壊れていたら .bak に退避して記録する（QC D6）。"""
    p = os.path.join(STATE, "approved.json")
    if not os.path.isfile(p):
        return {}
    try:
        with io.open(p, encoding="utf-8") as f:
            v = json.load(f)
        if not isinstance(v, dict):
            raise ValueError("not a dict")
        return {k: e for k, e in v.items() if isinstance(e, dict) and e.get("q")}
    except Exception as ex:
        try:
            os.replace(p, p + ".bak")
            _record_fired(NAME, {"approved_store_corrupt": repr(ex)[:200]})
        except Exception:
            pass
        return {}


def _save_approved(path, pairs):
    if not pairs or not path:
        return
    try:
        cur = _approved_store()
        for t, q in pairs:
            if ALL_WORD.search(t or ""):
                continue                      # 「全部」の承認は残さない（同じパスの別の文書に効く。QC3-6）
            cur.setdefault(_pathkey(path) + "|" + _squash(q), {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "target": t, "q": q})
        os.makedirs(STATE, exist_ok=True)
        with io.open(os.path.join(STATE, "approved.json"), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def standing_marks(path):
    """この文書で前に確かめた承認 [(対象, 引用)]。本文から印を消した後・コミットメッセージだけで承認した後の
    Edit／後のコミット（24 時間前・7 日前の版との比較）で、同じ削除を再び止めない（QC B1/B2）。文書ごと（QC A3）。"""
    if not path:
        return []
    k = _pathkey(path) + "|"
    return [(e.get("target") or "", e["q"]) for key, e in _approved_store().items() if key.startswith(k)]


def approved_quotes(marks, transcript_path, session_id=None, path=None):
    qs = [(t, q) for t, q in marks if q and quote_shape_ok(t, q)]
    if not qs:
        return set()
    rows = _user_rows(transcript_path)
    if rows is None:
        # transcript を読めない: 通すが記録する（Fable FN12）
        _record_fired(NAME, {"session_id": session_id, "unverified_quotes": [q for _t, q in qs]})
        return {q for _t, q in qs}
    texts, side = rows
    if side:
        # サブエージェントの中では承認を通さない（親セッションで依頼者の承認を得る。QC A4）
        _record_fired(NAME, {"session_id": session_id, "sidechain_quotes": [q for _t, q in qs]})
        return set()
    stored = {_squash(q) for _t, q in standing_marks(path)}
    msgs = [_squash(t) for t in texts]
    ok, new = set(), []
    for t, q in qs:
        sq = _squash(q)
        if sq in stored:
            ok.add(q)
            continue
        for m in msgs:                                # 発言1件の中に、そのまま（発言をまたがない。Fable FN11）
            k = m.find(sq)
            if k >= 0 and not REJECT_AFTER.search(m[k + len(sq):k + len(sq) + 30]):   # 疑問・撤回が続かない（QC A5・QC3-4）
                ok.add(q)
                new.append((t, q))
                break
    _save_approved(path, new)
    return ok


# ---------------------------------------------------------------- git helpers

def _git(root, args):
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off"] + args, cwd=root, capture_output=True, timeout=20)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------- session snapshot

def _snap(kind, path, session_id):
    key = hashlib.sha1((str(session_id) + "|" + os.path.normcase(os.path.abspath(path))).encode("utf-8")).hexdigest()[:20]
    return os.path.join(STATE, kind, key + ".md")


def _write_snap(p, text):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except Exception:
        pass


def _cleanup(days=7):
    """first/ last/ の 7 日より古い写しを消す（QC C3）。"""
    lim = time.time() - days * 86400
    for kind in ("first", "last"):
        d = os.path.join(STATE, kind)
        try:
            for nm in os.listdir(d):
                fp = os.path.join(d, nm)
                if os.path.getmtime(fp) < lim:
                    os.remove(fp)
        except Exception:
            pass


def session_first(path, session_id, current):
    """このセッションで最初に見た内容（無ければ current を記録して返す）。1本ずつ削る Edit の累積を見る（Fable FN19/20）。
    Claude が最後に書いた内容とディスクが違う（依頼者の手・git pull で変わった）ときは、今の内容を起点に取り直す（QC C1）。
    session_id が無ければ使わない（QC C2）。"""
    if current is None or not session_id:
        return None
    p = _snap("first", path, session_id)
    got = _read(p)
    last = _read(_snap("last", path, session_id))
    if got is None or (last is not None and last != current):
        if got is None:
            _cleanup()
        _write_snap(p, current)
        return current
    return got


def remember_written(path, session_id, content):
    if session_id and content is not None:
        _write_snap(_snap("last", path, session_id), content)


# ---------------------------------------------------------------- checks

def check(path, new, transcript_path=None, extra_marks="", baselines=None, session_id=None):
    """path の新しい内容 new を前の版と比べる。[(前の版のラベル, compare の結果)] のうち発火したもの。"""
    if not is_report(path, new):
        return []
    if baselines is None:
        baselines = []
        cur = _read(path)
        if cur is not None:
            baselines.append(("この文書の今の内容", cur))
            first = session_first(path, session_id, cur)
            if first is not None and first != cur:
                baselines.append(("この文書のセッション開始時の内容", first))
        for p in predecessors(path, new):
            t = _read(p)
            if t:
                baselines.append((os.path.basename(p), t))
    standing = standing_marks(path)
    marks = _marks(new, extra_marks)
    approved = approved_quotes(marks, transcript_path, session_id, path) if marks else set()
    marks = marks + standing
    approved |= {q for _t, q in standing}
    fired = []
    for label, old in baselines:
        r = compare(old, new, marks, approved)
        if r["fire"]:
            fired.append((label, r))
    return fired


def _apply_edits(cur, edits):
    s = cur
    for e in edits:
        o, n = e.get("old_string", ""), e.get("new_string", "")
        if not o or o not in s:
            return None
        s = s.replace(o, n) if e.get("replace_all") else s.replace(o, n, 1)
    return s


def new_content(payload):
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ""
    tool = payload.get("tool_name")
    if tool == "Write":
        return path, ti.get("content")
    cur = _read(path)
    if cur is None:
        return path, None
    if tool == "Edit":
        return path, _apply_edits(cur, [ti])
    if tool == "MultiEdit":
        return path, _apply_edits(cur, ti.get("edits") or [])
    return path, None


def message(path, fired):
    lines = ["report_format_guard: レポートの新しい版が、前の版の見出し・中身・表・列を承認なしに落としています（止めました）。",
             "対象: " + path.replace("\\", "/"), ""]
    for label, r in fired:
        lines.append("前の版: " + label)
        if r["headings"]:
            lines.append("  落ちた見出し（%d/%d）: %s" % (len(r["headings"]), r["n_old_headings"], " / ".join(r["headings"][:20])))
        if r["tables"]:
            lines.append("  表の数: %d → %d" % r["tables"])
        if r["columns"]:
            lines.append("  狭くなった・列が入れ替わった表（前の版の見出し行）: " + " ／ ".join(r["columns"][:10]))
        if r.get("rows"):
            lines.append("  データ行が減った表: " + " ／ ".join(r["rows"][:10]))
    lines += ["",
              "対処（どちらか）:",
              "  1. 前の版の節・表・列・行を残す（数値は今の条件で埋め直す。埋められないものは「未計算」と書いて節は残す）。",
              "     H5 以下への格下げ・1 行への要約も欠落とみなす。",
              "  2. 削るべき理由があるものは、依頼者に「何を・なぜ削るか」を推奨として示し、承認を得る。承認後に本文へ",
              "     `<!-- format-drop: 削る見出し名（表・列・行を減らすなら「表」「列」）承認「依頼者の発言をそのまま引用」 -->` を書く。",
              "     引用は依頼者の発言1件の中にそのまま含まれ、削除の語（削・消・不要・外す・省く・落とす 等）と同じ文に、",
              "     削る見出しの番号か名前があること（「書き直して」「最新にして」は削除の承認ではない）。",
              "     サブエージェントの中では承認は通らない（親セッションで承認を得る）。",
              "     依頼者が自分で消した後に止まったなら、依頼者に「○○は私が消した、削ってよい」と書いてもらい、その文を引用する。"]
    return "\n".join(lines) + "\n"


def on_file_tool(payload):
    path, new = new_content(payload)
    if not path or new is None:
        return 0
    # session_id の無い呼び出しは日付ごとに分ける（別の日の内容を起点にしない。QC C2）
    sid = payload.get("session_id") or ("nosession-" + time.strftime("%Y%m%d"))
    fired = check(path, new, payload.get("transcript_path"), session_id=sid)
    if not fired:
        remember_written(path, sid, new)
        return 0
    _record_fired(NAME, {"session_id": payload.get("session_id"), "path": path,
                         "fired": [(l, r["headings"][:10], r["tables"], r["columns"][:10], r["rows"][:5]) for l, r in fired]})
    sys.stderr.write(message(path, fired))
    return 2


# ---------------------------------------------------------------- git commit

def on_commit(payload):
    try:
        import topic_split_guard as T
    except Exception:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    m = T._COMMIT.search(cmd)
    if not m:
        return 0
    base = payload.get("cwd") or os.getcwd()
    cwd = T.effective_cwd(cmd, m.start(), base)
    root = T._root_for(m, cwd)
    if not root:
        return 0
    seg = cmd[m.start():]
    adds = [a for a in T._ADD.finditer(cmd) if a.start() < m.start()]
    commit_all = re.search(r"(?:^|\s)-(?:[a-zA-Z]*a[a-zA-Z]*)\b|--all\b", seg.split("\n")[0]) is not None
    worktree = set()
    mod = T._lines(_git(root, ["diff", "--name-only"]))
    gone = set(T._lines(_git(root, ["ls-files", "--deleted"])))
    if adds or commit_all:
        unt = T._lines(_git(root, ["ls-files", "-o", "--exclude-standard"]))
        if commit_all:
            worktree |= set(mod)
        for a in adds:
            here = T.effective_cwd(cmd, a.start(), cwd)
            specs = [T._unq(x) for x in a.group("args").split() if x]
            if any(s in (".", "-A", "--all", ":/", "*", "-u") for s in specs):
                worktree |= set(mod) | set(unt)
                continue
            for s in specs:
                if s.startswith("-"):
                    continue
                rel = os.path.relpath(os.path.normpath(T._abspath(here, s)), root).replace("\\", "/")
                for f in mod + unt:
                    if f == rel or f.startswith(rel.rstrip("/") + "/"):
                        worktree.add(f)
    status = {}
    old_name = {}
    for ln in _git(root, ["diff", "--cached", "--name-status", "-M"]).splitlines():
        f = ln.split("\t")
        if len(f) >= 2 and f[0]:
            status[f[-1]] = f[0][0]
            if f[0][0] == "R" and len(f) >= 3:
                old_name[f[2]] = f[1]
    deleted = [p for p, s in status.items() if s == "D"] + ([g for g in gone] if (adds or commit_all) else [])
    files = sorted({p for p, s in status.items() if s in "AMR"} | (worktree - gone))
    msg_text = seg
    fm = T._MSGFILE.search(seg)
    if fm:
        msg_text += "\n" + (_read(T._abspath(cwd, fm.group(1))) or "")
    day_ago = _git(root, ["rev-list", "-1", "--before=24.hours.ago", "HEAD"]).strip()
    week_ago = _git(root, ["rev-list", "-1", "--before=7.days.ago", "--after=" + INSTALLED, "HEAD"]).strip()
    out = []
    for rel in files:
        full = os.path.join(root, rel)
        new = _read(full) if rel in worktree else _git(root, ["show", ":" + rel])
        if not new or not is_report(full, new):
            continue
        baselines = []
        prev = old_name.get(rel, rel)
        old = _git(root, ["show", "HEAD:" + prev])
        if old:
            baselines.append(("この文書の直前の版（HEAD）", old))
        if day_ago:
            o24 = _git(root, ["show", "%s:%s" % (day_ago, prev)])
            if o24 and o24 != old:
                baselines.append(("この文書の24時間前の版", o24))
        if week_ago and week_ago != day_ago:
            o7 = _git(root, ["show", "%s:%s" % (week_ago, prev)])
            if o7 and o7 != old:
                baselines.append(("この文書の7日前の版", o7))   # 日をまたいで1本ずつ削る（QC B4）
        if not old:
            nh_new = structure(new)[0]
            for dp in deleted:                       # 同じコミットで消した同じディレクトリのレポート（Fable FN22）
                if os.path.dirname(dp) == os.path.dirname(rel):
                    t = _git(root, ["show", "HEAD:" + dp])
                    if not t or not is_report(dp, t):
                        continue
                    s1, s2 = _key(os.path.basename(dp))[0], _key(os.path.basename(rel))[0]
                    w1 = {w for w in re.split(r"[_\-]", (s1 or "").lower()) if w}
                    w2 = {w for w in re.split(r"[_\-]", (s2 or "").lower()) if w}
                    oh = structure(t)[0]
                    # 名前の語が2つ以上共通（COVER_MIN3_BEST → COVER_BEST_LATEST）か見出しが3割以上対応するときだけ
                    # （無関係なレポートの削除と新規追加 RETRO → PRICING・COVER_RETRO → COVER_PRICING を止めない。QC B3・QC3-12）
                    if (w1 and w1 == w2) or len(w1 & w2) >= 2 \
                            or (oh and len(match_headings(oh, nh_new)) >= STEM_MATCH * len(oh)):
                        baselines.append((dp + "（このコミットで削除）", t))
        for p in predecessors(full, new):
            prel = os.path.relpath(p, root).replace("\\", "/")
            t = _git(root, ["show", "HEAD:" + prel]) or _read(p)
            if t:
                baselines.append((os.path.basename(p), t))
        fired = check(full, new, payload.get("transcript_path"), extra_marks=msg_text, baselines=baselines,
                      session_id=payload.get("session_id"))
        if fired:
            out.append((rel, fired))
    if not out:
        return 0
    _record_fired(NAME, {"session_id": payload.get("session_id"), "root": root,
                         "fired": [(rel, [(l, r["headings"][:10], r["tables"], r["columns"][:10], r["rows"][:5]) for l, r in f])
                                   for rel, f in out]})
    sys.stderr.write("".join(message(rel, f) for rel, f in out)
                     + "（git commit: コミットメッセージに `Format-Drop-Ok: <対象> 承認「引用」` の行を入れてもよい）\n")
    return 2


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--compare":
        old, new = _read(sys.argv[2]) or "", _read(sys.argv[3]) or ""
        r = compare(old, new)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["fire"] else 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        if payload.get("tool_name") in ("Write", "Edit", "MultiEdit"):
            return on_file_tool(payload)
        if payload.get("tool_name") in ("Bash", "PowerShell"):
            return on_commit(payload)
    except Exception:
        return 0                      # 検査の故障で作業を止めない
    return 0


if __name__ == "__main__":
    sys.exit(main())
