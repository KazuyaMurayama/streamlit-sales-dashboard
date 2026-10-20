# -*- coding: utf-8 -*-
"""レポートの「見る場所によって壊れる」箇所を、悪化したターンで止める（Stop）。

WHY（2026-10-05 依頼者指摘・知的生産レポートで2件同時に実測）
  ① 印刷用（PDF・紙）にすると §3 の図が空の枠になった。GitHub の Mermaid 図はブラウザで実行時に
     描かれるため、印刷・PDF 化・note・メールでは描かれない。
  ② 「採点した全51行動の表」の順位（同点は同じ順位: 3,3,3…）と、下の章の見出し番号（4. 5. 6.）が
     食い違った。読み手はどちらが正しいのか分からない。
  依頼者「修正と、すべてのリポで、レポート作成時の再発防止して」。

不変条件（固有の文書名・図の名前ではなく、形で検査する）
  A. 実行時に描かれる図（```mermaid / geojson / topojson / stl）には、同じリポに実在する静的画像
     （.svg/.png/.jpg）を直前に併記する。画像はこのフォルダの render_diagrams.py で作れる
     （python .claude/hooks/render_diagrams.py <file.md>。Mermaid を SVG にして本文へ差し込む）。
  B. 番号の付いた見出し（### 7. 〇〇）と、順位・番号の列を持つ表の行が同じ対象を指すなら、番号を一致させる
     （対象の対応は near_duplicate_guard と同じ表記揺れ照合。見出しが3件以上表に対応した文書だけを見る）。
  例外: 図・表の直前の行に <!-- render-ok: 理由（10字以上） --> / <!-- numbering-ok: 理由 --> を書く。

  C. 番号列（順位・No.・#）が上から増える（減る）表は連番にする。「順位」の列は重複も飛びも違反。
     「#」「No.」の列は同点を同じ番号にして飛ぶ形（1,2,2,4）だけ違反（1,1,2,2 は行のまとまり、2 の次の 4 は
     本文から参照される行 ID のことがある）。
  E. 1ターンで同じフォルダに同じ日付・同じ接頭辞の新しい .md を2本以上作らない（警告）。
  F. 1ターンで1フォルダに日付で始まる名前のファイルを5本以上作るなら、名前の昇順を新しい順にする（警告）。
  G. 表の最小幅（改行できない並びの幅の列ごとの最大＋余白）を印刷時の本文幅 PRINT_WIDTH（595px）以下にする
     （2026-10-20 追加。詳細は G 節）。例外: 表の直前の行に <!-- width-ok: 理由（10字以上） -->。

止める範囲（2026-10-12 改訂。旧: 「違反の数が HEAD より増えたターンだけ」）:
  比べる相手はターン開始時点の版（ターン内でコミットしても失われない）。止めるのは ①新しい文書 ②違反の数が
  増えた ③このターンで中身が変わった表・図に違反がある。触れていない古い違反は知らせるだけ（形骸化防止）。
  テストの fixture（パスに tests/fixtures/）は見ない。

C05 改訂（2026-10-12, 訂正ダイジェスト C05「表の重複・順序・印刷時の図を成果物全体で機械検査していない」4件）
  クラス: 「読み手の使う順・単位（1表・1文書・新しい順）を崩した成果物を、作ったターンで機械が止めていない」。
  実例ごとの検出（旧版 → 新版。tests/test_c05_report_structure.py、旧版は RRG_HOOK_DIR で当てた）:
    ① deep-research ea33aa2 重複表: 関数は検出するが、ターン内コミットで旧 Stop は知らせるだけ → 新 block
       （near_duplicate_guard の比べる相手を同じく開始時点の版に変更）
    ② 581b50d 「No. ずれ」: 番号 8→8 で増えず旧は知らせるだけ・連番の検査なし → 新 block（触れた表＋連番）
    ③ Soulful-Content aadbcba 2本に分割: 旧は検査なし → 新 警告（E）
    ④ 8669766/7933908 日付名ファイルが古い順: 旧は検査なし → 新 警告（F）
  較正（48リポ・直近30日・各最大50コミット＝2,255コミット。コミット＝ターンの近似）:
    止める 3/2,255（0.13%）＝ 581b50d・ea33aa2・4c4804c の3件とも知的生産レポートの真陽性（旧判定 2件）。
    連番の飛びを全列で数えた初版は 8件で、book_briefs の「#」列（削った主張の行 ID）4件と記事番号 001… の
    飛び1件が灰色→飛びは「順位」列だけにした。E は 2件（運動会カメラの本文＋仕様＝真陽性、NAVAL の作業メモ2本＝灰色）
    で判定不能があるため警告。F は 2件とも狙った実例で警告。日付の列が古い順の表は 3件とも時系列として自然
    （年表・週次の推移・採用日）で不採用。負債（触れたら止める候補）: 画像の無い図 67/2,075、番号の食い違い 13、
    連番崩れ 29、いずれも触れなければ知らせるだけ。
    直近30日の transcript で .md を書いたターン 2,132 のうち 1,064（49.9%）がターン内で git commit していた
    ＝旧判定が半数のターンで「悪化なし」になっていた穴の大きさ。
  Fable 攻撃検証（2026-10-12）で直した点（tests/test_c05_report_structure.py の後半）:
    (1) 時間切れで無言: ファイルごとに git を2〜3回起動し、日付名の新規600本で 74〜94秒（既定 60秒で殺され無出力）。
        → 開始時点の版はリポごとに ls-tree・diff -M・cat-file --batch を各1回（nd.Baseline）、全体に TIME_BUDGET
        （20秒）。超えたら「未検査」を警告と stderr で知らせる。600本の再現で 1.2秒。
    (4) 番号でない行（計・-・16位以下）が1行でもあると列ごと捨てていた → 数として読める行だけで判定、「3位タイ」「=1」は数。
    (5) git mv した古い文書を新規扱いで止めた → diff -M の旧パスの版と比べる。
    (6) 時刻の無い transcript・コミット日付を過去にしたコミットで無言 → 時刻はターン内の最初の行、無ければ直近30分
        （安全側）。開始時点の HEAD は reflog と loose object の更新時刻（環境変数で変えられない）で取る。
    (8) 行をまとめた表（# が 1,1,2,2,3,3）を連番崩れで止めた → # / No. の重複は「同点で飛ぶ形」だけ違反。
  Fable 再検証（2026-10-12）で直した点:
    [高] 開始時点の版と比べるため、ターン内の git pull --rebase --autostash・別セッションのコミット・checkout で
        入った他人の欠陥レポートで止めた（README しか触っていない）→ 止めるのは Claude 自身が書いたファイルだけ
        （transcript の Write/Edit/MultiEdit/NotebookEdit とシェルのコマンドに現れたパス、ターン開始以降に更新した
        未コミットの変更）。それ以外は知らせるだけ。transcript が無ければ何も止めない。
    [中] 上位3＋下位3（1,2,3,49,50,51）の抜粋表、群を削った「#」1,1,2,2,4,4 を止めた → 行数より大きい番号が出る表は
        飛びを見ない（重複だけ）、同じ番号の組が2つ以上ある「#」列は飛びを見ない。
        その代わり、順位の純粋な飛び（1,2,4）は見逃す（行数より大きい番号になるため）。

赤緑: 実物の欠陥版（deep-research 581b50d）で図1件・番号8件を検出、直した版で0件（tests/test_report_render_guard.py）。
攻撃検証（2026-10-05, Fable）: 初版は A 見逃し 14/17・B 見逃し 19/21（同点の多い表で沈黙＝依頼者の元事象そのもの）。
  直した点: 字下げ・4連・引用内のフェンス、コメント/インラインコード内の画像を数えない、空の画像、前の図の画像の流用、
  「1位」「第N位」等の番号の書式、一致率ゲート→順序の一致（8割）ゲート。残る穴: 画像が図の後ろ、参照形式の画像、
  HTML の <table>、章（##）見出しの番号。
較正（2026-10-05, tests/calibrate_report_render_guard.py。48リポ・直近30日・各最大50コミット）:
  止めたコミット 2/2,263（0.09%）＝どちらも狙った実例（知的生産レポート）。HEAD の負債（触っても悪化しなければ
  知らせるだけ）: 画像の無い図 67/2,829本（2.37%）、番号の食い違い 13本（0.46%。freelance-compass の「第1位」見出しと
  表の順位2 など、目視で多くが実際の食い違い）。

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import html
import io
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:  # pragma: no cover
    def _record_firing(*_a, **_k):
        return False
try:
    import near_duplicate_guard as nd
except Exception:  # pragma: no cover
    nd = None

DIAGRAM_LANGS = ("mermaid", "geojson", "topojson", "stl")
IMG = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+\.(?:svg|png|jpe?g|gif|webp))>?(?:\s+\"[^\"]*\")?\s*\)|<img\b[^>]*\bsrc=\"([^\"]+)\"", re.I)
RENDER_OK = re.compile(r"<!--\s*render-ok\s*[:：]\s*(.{10,}?)\s*-->")
NUMBERING_OK = re.compile(r"<!--\s*numbering-ok\s*[:：]\s*(.{10,}?)\s*-->")
_NONWORD = re.compile(r"[\W_]+", re.U)


def _norm(s):
    return _NONWORD.sub("", unicodedata.normalize("NFKC", s).lower())


# ---- A. 実行時に描かれる図 ----
# フェンス: 字下げ0〜3、引用（>）・リストの中、``` か ~~~ の3つ以上。閉じは同じ記号で同じ長さ以上（CommonMark）。
FENCE_OPEN = re.compile(r"^(?:\s*>\s?|\s*(?:[-*+]|\d+[.)])\s+)*\s{0,3}(`{3,}|~{3,})\s*([^\s`]*)")
COMMENT = re.compile(r"<!--.*?-->", re.S)
INLINE_CODE = re.compile(r"`+[^`\n]*`+")


def _code_mask(lines):
    """[(開始行, 終了行, 言語)] と、コードブロックの中の行の集合。"""
    blocks, inside, i, n = [], set(), 0, len(lines)
    while i < n:
        m = FENCE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        mark, lang = m.group(1), m.group(2).lower()
        j = i + 1
        while j < n:
            c = FENCE_OPEN.match(lines[j])
            if c and c.group(1)[0] == mark[0] and len(c.group(1)) >= len(mark) and not c.group(2):
                break
            j += 1
        blocks.append((i, min(j, n - 1), lang))
        inside.update(range(i, min(j, n - 1) + 1))
        i = j + 1
    return blocks, inside


def _visible(text):
    """HTML コメントを空白に置き換える（行番号は保つ）。コメントの中の画像・例外印は数えない。"""
    return COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def diagram_violations(text, base_dir, exists=None):
    """[(行番号, 言語)]：静的画像の無い（または画像ファイルが実在しない・空の）図。
    exists: 文書のフォルダからの相対パスを受けて実在を返す関数（較正で過去のコミットを見るため）。"""
    def _exists(p):
        f = os.path.join(base_dir, p)
        return os.path.isfile(f) and os.path.getsize(f) > 0
    exists = exists or _exists
    raw = text.split("\n")
    vis = _visible(text).split("\n")
    blocks, inside = _code_mask(raw)
    out, last_end = [], -1
    for start, end, lang in blocks:
        if lang in DIAGRAM_LANGS:
            # 直前の図の終わりより後ろ・15行以内で、コードブロックの外・コメントの外の行だけを見る
            lo = max(last_end + 1, start - 15)
            prev = [vis[k] for k in range(lo, start) if k not in inside and vis[k].strip()]
            ok = any(RENDER_OK.search(raw[k]) for k in range(lo, start) if k not in inside)
            if not ok:
                for ln in prev:
                    for im in IMG.finditer(INLINE_CODE.sub("", ln)):
                        src = (im.group(1) or im.group(2) or "").strip()
                        if src.startswith(("http://", "https://")):
                            ok = True  # 外部の画像（GitHub の user-attachments 等）
                        elif src and exists(src.split("#")[0].split("?")[0]):
                            ok = True
            if not ok:
                out.append((start + 1, lang))
            last_end = end
    return out


# ---- B. 見出しの番号と表の順位 ----
RANK_HEAD = re.compile(r"順位|ランク|^rank|^no\.?$|^#$|番号|^位$|^№$", re.I)


def _num(cell):
    """「1」「**1**」「1位」「#1」「1.」「①」「第1位」「No.1」→ 1。番号でなければ None。"""
    s = unicodedata.normalize("NFKC", cell).strip().strip("*_ ")
    m = re.fullmatch(r"(?:第|no\.?\s*|#)?(\d{1,3})\s*(?:位|\.|、|\)|）)?(?:\s*[(（][^)）]*[)）])?", s, re.I)
    return int(m.group(1)) if m else None


def _rank_tables(text):
    if nd is None:
        return []
    out = []
    lines = text.split("\n")
    for start, head, rows, _ok, _sig in nd.md_tables(text):
        if not head:
            continue
        col = next((c for c, h in enumerate(head[:2]) if RANK_HEAD.search(_norm_head(h))), None)
        if col is None:
            continue
        if any(NUMBERING_OK.search(lines[x]) for x in range(max(0, start - 4), start - 1)):
            continue
        ranked = []
        for r in rows:
            if len(r) <= col:
                continue
            n = _num(r[col])
            if n is None:
                continue
            others = [c for x, c in enumerate(r[:col + 4]) if x != col]
            key = next((c for c in others if len(_norm(c)) >= 2 and _num(c) is None
                        and not re.fullmatch(r"[\d.,%\s*]+", c)), None)
            if key:
                ranked.append((n, _keys(key)))
        if len(ranked) >= 3:
            out.append((start, ranked))
    return out


def _norm_head(h):
    return unicodedata.normalize("NFKC", h).strip().strip("*_ ").lower()


def _keys(cell):
    ks = nd._cell_keys(cell)
    if not ks:
        v = _norm(re.sub(r"\*", "", cell))
        if len(v) >= 2:
            ks = {v}
    return ks


HEADING_NUM = re.compile(
    r"^#{1,6}\s+\**(?:第\s*(\d{1,3})\s*位|no\.?\s*(\d{1,3})|【(\d{1,3})】|(\d{1,3})\s*位|(\d{1,3})\s*(?:[.．](?!\d)|[:：)）、]))\**\s*[:：]?\s*(.+?)\s*$",
    re.I)


def numbering_violations(text):
    """[(見出しの行番号, 見出しの番号, 表の行番号, 表の順位, 見出し)]。
    見出しの番号が表の順位を表している文書だけを見る＝対応した見出しを番号順に並べたとき、表の順位も
    ほぼ同じ順に並ぶ（順序の一致が8割以上）。章立て・時系列など別の並びで付けた番号は食い違いとみなさない。
    同点を同じ順位にした表（1,1,1,4）と連番の見出し（1,2,3,4）は、並びは一致して番号が食い違う＝違反。"""
    tables = _rank_tables(text)
    if not tables:
        return []
    heads = []
    _blocks, inside = _code_mask(text.split("\n"))
    for i, ln in enumerate(unicodedata.normalize("NFKC", text).split("\n")):
        if i in inside:
            continue
        m = HEADING_NUM.match(ln)
        # 「## 2. 〇〇」は章の番号であることが多い（2026-10-05 較正: 章見出しが表の行に似て誤検知した 4/18 件）。
        # 順位の見出しとして読むのは ### 以下か、「第N位」「N位」の明示があるときだけ。
        if m and not (ln.startswith("###") or m.group(1) or m.group(4)):
            m = None
        if m:
            num = int(next(g for g in m.groups()[:5] if g))
            title = re.sub(r"[｜|].*$", "", m.group(6))
            title = re.sub(r"[（(](やり方|詳細|解説)[）)]\s*$", "", title)
            heads.append((i + 1, num, title, _keys(title)))
    out = []
    for tstart, ranked in tables:
        matched = []
        for hl, hn, title, hk in heads:
            if not hk:
                continue
            scores = sorted(((nd._match_score(hk, rk), rank) for rank, rk in ranked), key=lambda x: -x[0])
            if scores and scores[0][0] > 0 and (len(scores) < 2 or scores[0][0] > scores[1][0]
                                                 or scores[0][1] == scores[1][1]):
                matched.append((hl, hn, scores[0][1], title))
        if len(matched) < 3:
            continue
        pairs = sorted((hn, rank) for _hl, hn, rank, _t in matched)
        conc = tot = 0
        for a in range(len(pairs)):
            for b in range(a + 1, len(pairs)):
                if pairs[a][0] == pairs[b][0]:
                    continue
                tot += 1
                conc += pairs[a][1] <= pairs[b][1]
        if not tot or conc < 0.8 * tot:
            continue
        for hl, hn, rank, title in matched:
            if hn != rank:
                out.append((hl, hn, tstart, rank, title))
    return out


# ---- C. 番号列の連番（2026-10-12 追加） ----
# WHY: 2026-10-05 依頼者「採点した全51行動の表（太字の15行が上位15）の No. ずれ」。表の順位が 1,2,3,3,3,7,…
#   と同点を同じ順位にしていたため、太字の上位15行の最後が「12」になり、見出しの「15.」と食い違った。
#   見出しが無くても、番号列の重複・飛びはそれだけで読み手を迷わせる（「上位15」の15行目がどれか分からない）。
# 不変条件: 1列目か2列目が番号の列（順位・No.・#・ランク）で、値が上から増える（または減る）並びの表は、
#   隣の行との差がちょうど1（重複も飛びもない連番）。値が並び替わっている列（ID）は見ない。
def _seq_num(cell):
    """番号の列のセル → 数。「3位タイ」「=3」「T3」「3（同点）」も 3。「16位以下」「計」「-」は None（その行は飛ばす）。"""
    n = _num(cell)
    if n is not None:
        return n
    s = unicodedata.normalize("NFKC", cell).strip().strip("*_ ")
    m = re.fullmatch(r"(?:[=T]\s*)?(\d{1,3})\s*位?\s*(?:タイ|tie|同率|同点|=)?\s*(?:[(（][^)）]*[)）])?", s, re.I)
    return int(m.group(1)) if m else None


def sequence_violations(text):
    """[(表の行番号, 列名, [(表内の行, 前の値, この値)], 表の crc32)]：番号列の重複・飛び。
    数として読める行だけで判定する（「計」「-」「16位以下」の行は飛ばす。2026-10-12 Fable 攻撃検証: 1行でも
    数でない行があると列ごと捨てていて、合計行のある表で0件だった）。
    「#」「No.」の列で同じ番号が続くのは行のまとまり（1,1,2,2,3,3）なので違反にしない。違反は
    ①「順位」の列の重複・飛び ②どの列でも、同じ番号が k 行続いた後に k だけ飛ぶ形（1,2,2,4＝同点を同じ順位にした並び）。"""
    if nd is None:
        return []
    lines = text.split("\n")
    out = []
    for start, head, rows, _ok, sig in nd.md_tables(text):
        if not head:
            continue
        col = next((c for c, h in enumerate(head[:2]) if SEQ_HEAD.search(_norm_head(h))), None)
        if col is None:
            continue
        if any(NUMBERING_OK.search(lines[x]) for x in range(max(0, start - 4), start - 1)):
            continue
        cells = [(k + 1, r[col]) for k, r in enumerate(rows) if len(r) > col and r[col].strip()]
        nums = [(k, _seq_num(c)) for k, c in cells]
        nums = [(k, v) for k, v in nums if v is not None]
        if len(nums) < 3 or len(nums) < 0.5 * len(cells):
            continue  # 大半が番号でない列（「1-2」「A」）は連番の列とみなさない
        vals = [v for _k, v in nums]
        up = all(b >= a for a, b in zip(vals, vals[1:]))
        down = all(b <= a for a, b in zip(vals, vals[1:]))
        if not (up or down) or vals[0] == vals[-1]:
            continue  # 並び替えた表の ID 列・全部同じ値の列は見ない
        # 飛び（2 の次が 4）だけを数えるのは「順位」の列だけ。「#」「No.」は行の ID として本文から参照され（「1・6・9行」）、
        # 削った行の番号を詰めないのが正しいことがある（2026-10-12 較正: book_briefs の # 列・記事番号 001… の飛び 5件は灰色）。
        rank_col = bool(RANK_ONLY.search(_norm_head(head[col])))
        # 上位N＋下位N の抜粋表（1,2,3,49,50,51）は、行数より大きい番号が出る＝間を省いた表なので飛びは見ない（重複だけ）。
        excerpt = max(vals) > len(nums) and min(vals) >= 1
        # 「#」で同じ番号が2つ以上の組で出る列は行のまとまり（1,1,2,2,4,4＝群を削った）なので、同点で飛ぶ形も見ない。
        grouped = sum(1 for v in set(vals) if vals.count(v) > 1) >= 2
        bad, run = [], 1
        for i in range(1, len(nums)):
            a, b = vals[i - 1], vals[i]
            if b == a:
                run += 1
                if rank_col:
                    bad.append((nums[i][0], a, b))
                continue
            if abs(b - a) != 1 and not excerpt and (rank_col or (not grouped and run > 1 and abs(b - a) == run)):
                bad.append((nums[i][0], a, b))
            run = 1
        if bad:
            out.append((start, head[col].strip("* "), bad, sig))
    return out

SEQ_HEAD = RANK_HEAD
RANK_ONLY = re.compile(r"順位|ランク|^rank|^位$", re.I)


# ---- G. 印刷で右端の列が切れる表（2026-10-20 追加） ----
# WHY: 2026-10-20 依頼者「生きている原稿の一覧の表で、印刷しようとすると『重要メッセージ』の列が途中から欠けて
#   読めません。列幅が広すぎるという間違いを犯しています…今後も起きないように、すべてのリポジトリで」。
#   Soulful-Content の _meta/REVIEW_REQUIRED_FILES_20260918.md は、見出しに &numsp;（改行できない数字幅の空白）を
#   18・13・30 個足して列幅を広げていた。GitHub の表は display:block・max-width:100% で、画面では横スクロールに
#   なるが、印刷では本文幅（GitHub の印刷用表示で 595px）を超えた分が切り取られる。直した版（4・2・14 個）も
#   実描画で最小幅 604px で、まだ切れた（39ad4e4 で 0・0・8 個＝528px）。
# 不変条件: 表の最小幅（列ごとに「改行できない並び」の最大幅＋左右の余白 26px、を足したもの）が PRINT_WIDTH 以下。
#   改行できない並び: 半角空白で区切った英数字の語・URL・&numsp; や &#8288; でつないだ文字列。全角文字の前後は
#   改行できる（ただし 、。」）・ などの前と 「（ の後は不可）。リンクは表示文字列、<br> は改行として数える。
# 推定の誤差（2026-10-20 較正。GitHub の印刷用表示で表を width:1px にした実描画の幅と比べた 18表）:
#   推定/実描画 = 258/259・537/528・188/189・180/171・119/120・216/213・349/354・332/345・284/287（Soulful-Content 9表）、
#   668/618・657/652・616/592・664/668・1156/1124・886/901・933/906・764/770・815/780（5リポの印刷幅超え候補から抽出 9表）。
#   誤差は −3.8%〜+8.1%。推定 616・実描画 592 の誤検出が1件あるので、迷う表は width-ok で理由を書いて通す。
# 自分が書いたファイルの範囲（2026-10-20 Fable 攻撃検証で確かめた残る穴）:
#   ・サブエージェント（Agent ツール）が生成してコミットしたものは transcript に出ないので知らせるだけ。
#   ・スクリプトで生成してまだコミットしていない .md は知らせるだけ（未コミットの変更を数えると、並行する別セッションの
#     書きかけで止めた。2026-10-20 実運用）。Claude がそのターンで git commit すれば止まる。
#   ・HTML の <table>・引用（>）の中の表は数えない。表の中身が1字でも変われば「触れた表」として止める。
# 発火率（2026-10-20, tests/calibrate_report_render_guard.py。48リポ・直近30日・各最大50コミット＝2,266コミット）:
#   G で止めるコミット 58/2,266（2.56%。fixture を除く）。うち作業台帳（tasks.md・FILE_INDEX.md 等。印刷して
#   読むものではない）だけで止まるものが 11件 → WIDTH_SKIP_NAMES で外し 47/2,266（2.07%）。残りは調査レポート・
#   計画書・要レビュー一覧などで、推定は 595px 超え＝実描画でも切れる側（較正の誤差は最大 +8.1%）。
WIDTH_SKIP_NAMES = ("tasks.md", "file_index.md", "index.md", "changelog.md", "claude.md", "agents.md")
PRINT_WIDTH = float(os.environ.get("REPORT_PRINT_WIDTH", "595"))
WIDTH_OK = re.compile(r"<!--\s*width-ok\s*[:：]\s*(.{10,}?)\s*-->")
_W_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_W_BR = re.compile(r"<br\s*/?>", re.I)
_W_TAG = re.compile(r"</?(?:br|b|i|u|s|em|strong|code|kbd|sub|sup|span|a|img|details|summary|small|mark|del|ins|p|div)\b[^<>]*>", re.I)
_W_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto):[^<>\s]+)>", re.I)
_W_GLUE = "\u2060\u2007\xa0\u202f\ufeff"  # 語結合子・数字幅の空白・改行しない空白（前後で改行させない）
_W_NO_START = "、。」』）】，．・！？"  # この文字の前では改行しない（行頭禁則）
_W_NO_END = "「『（【"  # この文字の後では改行しない（行末禁則）


def _char_w(ch, bold=False):
    """GitHub の表のセル（16px）での1文字の幅の近似（px）。"""
    if ch in ("\u2060", "\u200b", "\ufeff"):
        return 0.0
    if ch == "\u2007":
        return 8.9
    if ch in ("\xa0", "\u202f"):
        return 4.4
    if ch in ("\u2002", "\u2003"):  # &ensp; / &emsp;（2026-10-20 Fable 実測: 100個並べて折れない）
        return 8.0 if ch == "\u2002" else 16.0
    if ch == "\xad":
        return 0.0
    if unicodedata.east_asian_width(ch) == "H":  # 半角カナ
        return 8.0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 16.0
    w = 8.8 if ch.isdigit() else 9.6 if ch.isupper() else 8.2 if ch.isalpha() else 5.0
    return w * (1.06 if bold else 1.0)


def _wide_ch(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F", "H")  # 前後で改行できる文字（全角・半角カナ）


def _unbreakable_runs(cell):
    """セルの中の改行できない並びのリスト。"""
    out = []
    for line in _W_BR.split(cell):
        s = _W_LINK.sub(lambda m: m.group(1), line)
        s = _W_AUTOLINK.sub(lambda m: m.group(1), s)
        s = _W_TAG.sub("", s).replace("**", "").replace("__", "").replace("`", "")
        s = html.unescape(s)
        cur, prev = "", ""
        for i, ch in enumerate(s):
            if ch in (" ", "\t", "\u3000"):
                out.append(cur)
                cur, prev = "", ch
                continue
            if (cur and prev not in _W_GLUE and ch not in _W_GLUE and (_wide_ch(ch) or _wide_ch(prev))
                    and ch not in _W_NO_START and prev not in _W_NO_END):
                out.append(cur)
                cur = ""
            cur += ch
            if ch in "-\u2013\u2014\xad" and i + 1 < len(s):  # ハイフン・ダッシュ・ソフトハイフンの後は改行できる
                out.append(cur)
                cur = ""
            prev = ch
        out.append(cur)
    return [x for x in out if x]


def _show(run):
    """メッセージ用: 不可視の文字を書いたときの形（&numsp;×N 等）に戻す。"""
    run = run.replace("\u2060", "").replace("\ufeff", "").replace("\xad", "")
    for ch, name in (("\u2007", "&numsp;"), ("\xa0", "&nbsp;"), ("\u202f", "&#8239;"), ("\u2002", "&ensp;"),
                     ("\u2003", "&emsp;")):
        run = re.sub(re.escape(ch) + "+", lambda m: "%s×%d" % (name, len(m.group(0))), run)
    return run


def table_min_width(head, rows):
    """(表の最小幅の推定 px, [(列名, 列の最小幅, その列で一番長い改行できない並び)])。"""
    ncol = max([len(head)] + [len(r) for r in rows])
    cols = [(0.0, "")] * ncol
    for bold, row in [(True, head)] + [(False, r) for r in rows]:
        for c, cell in enumerate(row[:ncol]):
            for run in _unbreakable_runs(cell):
                w = sum(_char_w(ch, bold) for ch in run)
                if w > cols[c][0]:
                    cols[c] = (w, run)
    total = sum(w for w, _r in cols) + 26 * ncol + (ncol + 1)  # 左右の余白 13px×2 と罫線 1px
    names = [html.unescape(_W_TAG.sub("", h)).replace("\u2060", "").replace("\u2007", "").strip("* ") for h in head]
    names += [""] * (ncol - len(names))
    return total, [(names[c], w + 26, _show(r)) for c, (w, r) in enumerate(cols)]


def wide_tables(text):
    """[(表の行番号, 最小幅の推定, [(列名, 列幅, 並び)…幅の広い順], 表の crc32)]：印刷幅を超える表。"""
    if nd is None:
        return []
    lines = text.split("\n")
    out = []
    for start, head, rows, _ok, sig in nd.md_tables(text):
        if not head:
            continue
        if any(WIDTH_OK.search(lines[x]) for x in range(max(0, start - 4), start - 1)):
            continue
        total, cols = table_min_width(head, rows)
        if total > PRINT_WIDTH:
            out.append((start, total, sorted(cols, key=lambda x: -x[1]), sig))
    return out


def findings(text, base_dir, exists=None):
    return diagram_violations(text, base_dir, exists), numbering_violations(text)


# ---- D. 「触れた箇所は全数検査」（2026-10-12 改訂） ----
# WHY: 初版は「違反の数が HEAD より増えたターン」だけを止めた。①ターンの中でコミットすると HEAD が今の版になり、
#   比べる相手が自分自身になって絶対に増えない（実例: deep-research ea33aa2・581b50d はどちらもターン内でコミット）。
#   ②表を統合して作り直したターン（581b50d）でも、番号の食い違いが 8→8 で増えないので知らせるだけだった
#   （依頼者はその版を見て「No. ずれ」と指摘した）。
# 不変条件: 比べる相手はターン開始時点の版（nd.base_text）。このターンで中身が変わった表・図（内容の指紋が
#   開始時点の版に無いもの）に違反があれば、数が増えていなくても止める。触れていない古い違反は知らせるだけ。
def _diagram_blocks(text):
    raw = text.split("\n")
    blocks, _inside = _code_mask(raw)
    return {s + 1: "\n".join(x.strip() for x in raw[s:e + 1]).strip() for s, e, lang in blocks if lang in DIAGRAM_LANGS}


def classify(text, base, base_dir, exists=None, base_exists=None, name=""):
    """(止める (dia, num, seq, wide), 知らせるだけ (同))。base は開始時点の版（None＝新しい文書）。
    wide（G. 印刷幅を超える表）は数の増減を見ず、このターンで中身が変わった表だけを止める。"""
    dia, num = findings(text, base_dir, exists)
    seq = sequence_violations(text)
    wide = [] if os.path.basename(name).lower() in WIDTH_SKIP_NAMES else wide_tables(text)
    if base is None:
        return (dia, num, seq, wide), ([], [], [], [])
    base_sigs = {t[4] for t in nd.md_tables(base)}
    wide_blk = [v for v in wide if v[3] not in base_sigs]
    wide_wrn = [v for v in wide if v[3] in base_sigs]
    bd, bn = findings(base, base_dir, base_exists or exists)
    bs = sequence_violations(base)
    if len(dia) > len(bd) or len(num) > len(bn) or len(seq) > len(bs):
        return (dia, num, seq, wide_blk), ([], [], [], wide_wrn)
    sig_at = {t[0]: t[4] for t in nd.md_tables(text)}
    base_dias = set(_diagram_blocks(base).values())
    cur_dias = _diagram_blocks(text)
    base_lines = set(x.strip() for x in unicodedata.normalize("NFKC", base).split("\n"))
    lines = unicodedata.normalize("NFKC", text).split("\n")
    blk, wrn = ([], [], [], wide_blk), ([], [], [], wide_wrn)
    for v in dia:
        (blk if cur_dias.get(v[0]) not in base_dias else wrn)[0].append(v)
    for v in num:
        touched = sig_at.get(v[2]) not in base_sigs or lines[v[0] - 1].strip() not in base_lines
        (blk if touched else wrn)[1].append(v)
    for v in seq:
        (blk if v[3] not in base_sigs else wrn)[2].append(v)
    return blk, wrn


# ---- E. 1つの報告を2本の文書に分けた（2026-10-12 追加） ----
# WHY: 2026-10-06 依頼者「なんでこの2つ分けてんの？どっちを読めばいいの？1つにまとまってる方が助かる」
#   （Soulful-Content aadbcba: PALEO_BENCHMARK_ANALYSIS_20261001.md と PALEO_TITLE_LIST_20261001.md を同じターンで
#   同じフォルダに新規作成。f9924ec で一覧を付録 A に統合）。2026-09-07 にも「2本、わざわざ2つ読まないと
#   分からないのは…1本にして」。
# 不変条件: 1ターンで、同じフォルダに、同じ日付（ファイル名の YYYYMMDD）と同じ主題の接頭辞（最初の区切りまで）を
#   持つ新しい .md を2本以上作らない（付録・一覧は本体の文書の付録にする）。
DATE_TOKEN = re.compile(r"(?<!\d)(20\d{2})-?(\d{2})-?(\d{2})(?!\d)")
DATE_PREFIX = re.compile(r"^(?:\d{1,5}_)?(20\d{2})-?(\d{2})(?:-?(\d{2}))?(?!\d)")


def split_reports(new_rels):
    """[(フォルダ, [ファイル名…])]：同じフォルダ・同じ日付・同じ接頭辞の新しい .md が2本以上。"""
    groups = {}
    for rel in new_rels:
        d, b = os.path.split(rel.replace("\\", "/"))
        stem, ext = os.path.splitext(b)
        if ext.lower() not in (".md", ".markdown") or DATE_PREFIX.match(b):
            continue
        m = DATE_TOKEN.search(stem)
        if not m:
            continue
        prefix = re.split(r"[_\-\s.]", stem, maxsplit=1)[0].lower()
        if not prefix or prefix.isdigit():
            continue
        groups.setdefault((d, "".join(m.groups()), prefix), []).append(b)
    return [(d, sorted(v)) for (d, _dt, _p), v in sorted(groups.items()) if len(v) >= 2]


# ---- F. 日付で始まるファイル名の一覧が古い順に見える（2026-10-12 追加） ----
# WHY: 2026-10-07 依頼者「GitHub のフォルダ内で、古い記事が一番上になっているのは不都合…新しい記事から」
#   （Soulful-Content 8669766 / 7933908: articles/ に「YYYY-MM-DD_<key>_<題>.md」を600本・232本。GitHub は
#   ファイル名の昇順で並べるので、日付で始まる名前は必ず古い順になる。9e1da5f で「0001_<新しい順の番号>_」に改名）。
# 不変条件: 1ターンで1つのフォルダに、日付で始まる名前の新しいファイルを DATE_BATCH 本以上作るなら、
#   名前の昇順＝新しい順になるようにする（新しい順の番号を先頭に付ける、など）。
DATE_BATCH = 5


def oldest_first_batches(new_rels):
    """[(フォルダ, 本数, 先頭に来る名前)]：名前の昇順が古い順になる、日付入りの新しいファイルが DATE_BATCH 本以上。"""
    groups = {}
    for rel in new_rels:
        d, b = os.path.split(rel.replace("\\", "/"))
        m = DATE_PREFIX.match(b)
        if m:
            groups.setdefault(d, []).append((b, "".join(x or "00" for x in m.groups())))
    out = []
    for d, v in sorted(groups.items()):
        if len(v) < DATE_BATCH:
            continue
        v.sort()
        dates = [x[1] for x in v]
        if dates[0] < dates[-1]:  # 名前の昇順の先頭が一番古い＝GitHub で古い順に見える
            out.append((d, len(v), v[0][0]))
    return out


def _fmt(path, dia, num, seq=(), wide=()):
    lines = []
    for ln, lang in dia[:6]:
        lines.append("  - %s:%d  ```%s の図に静的画像が無い（印刷・PDF・note では空の枠になる）" % (path, ln, lang))
    for hl, hn, tl, rank, title in num[:6]:
        lines.append("  - %s:%d  見出し「%d. %s」と %d行目の表の順位 %d が食い違う" % (path, hl, hn, title[:30], tl, rank))
    for tl, col, bad, _sig in list(seq)[:6]:
        lines.append("  - %s:%d  表の「%s」列が連番でない（%s）" % (path, tl, col, "、".join(
            "%d の次が %d" % (a, b) for _k, a, b in bad[:4]) + (" ほか%d箇所" % (len(bad) - 4) if len(bad) > 4 else "")))
    for tl, total, cols, _sig in list(wide)[:6]:
        lines.append("  - %s:%d  表の最小幅が約 %dpx で、印刷の本文幅 %dpx を超える（右端の列が印刷で切れる）。広い列: %s" % (
            path, tl, total, PRINT_WIDTH, "、".join("「%s」%dpx（改行できない並び「%s」）" % (
                n[:12], w, r[:40] + ("…" if len(r) > 40 else "")) for n, w, r in cols[:3])))
    more = len(dia) + len(num) + len(seq) + len(wide) - len(lines)
    if more > 0:
        lines.append("  ほか %d 件" % more)
    return "\n".join(lines)


RESOLVE = (
    "解消法:\n"
    "  図 → python .claude/hooks/render_diagrams.py <文書.md>（グローバルなら ~/.claude/hooks/render_diagrams.py）。"
    "Mermaid を figures/ に SVG で描き出し、図の直前に画像を差し込み、元の図は <details> に畳む。"
    "できた SVG もコミットする。\n"
    "  番号 → 表の順位・No. を上から 1,2,3… の連番にし、見出しの番号と揃える（同点は表の並び順で決め、"
    "その決め方を表の前に1文で書く）。\n"
    "  表の幅 → 見出しの &numsp;・&nbsp;・&#8288; の水増しをやめる、長い URL は [短い表示名](URL) にする、"
    "英語の長い語・型番は <br> や空白で割る、列を減らすか表を2つに分ける。最小幅の推定は印刷の本文幅 595px 以下に。\n"
    "  本当に意図した違いなら、図・表の直前の行に <!-- render-ok: 理由 --> / <!-- numbering-ok: 理由 --> / "
    "<!-- width-ok: 理由 -->（10字以上）。")


TIME_BUDGET = float(os.environ.get("REPORT_RENDER_TIME_BUDGET", "20"))
# 時間の上限（秒）。settings.json の Stop フックは timeout 無し＝既定 60 秒で殺され、殺されると何も出ない
# （2026-10-12 Fable 攻撃検証: 日付名の新規600本をターン内でコミットすると 94秒で無言）。超えたら残りは
# 「未検査」と知らせる（黙って通さない）。


def _key(p):
    return os.path.normcase(os.path.abspath(p))


def _authored(full, authored):
    """このターンで Claude 自身が書いた（と transcript から言える）ファイルか。止めるのはこれだけ。
    transcript が読めないときは空集合＝何も止めず知らせるだけ（安全側の警告）。"""
    return _key(full) in authored


_GIT_COMMIT = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:&\s*)?[\"']?(?:\S*[/\\])?git(?:\.exe)?[\"']?"
                         r"(?:\s+(?:-[Cc]\s+\S+|--?[A-Za-z][\w-]*(?:=\S+)?))*\s+commit(?:\s|$)")


def _runs_git_commit(cmd):
    """シェルのコマンドが git commit を実行するか（区切り ; && || | 改行 ごとに、先頭の語が git でサブコマンドが
    commit のとき）。echo "git commit"・grep "git commit"・git log --grep commit・git commit-tree は数えない
    （2026-10-20 Fable 攻撃検証: 文字列に含むだけで他人のターン内コミットを自分のものにして止めた）。"""
    for seg in re.split(r"[;\n|]|&&|\|\|", cmd):
        if _GIT_COMMIT.match(seg.strip()):
            return True
    return False


def on_stop(ev):
    if ev.get("stop_hook_active") or nd is None:
        return
    deadline = time.time() + TIME_BUDGET
    since, calls = (None, [])
    if ev.get("transcript_path"):
        since, calls = nd.read_turn(ev["transcript_path"])
        since, _how = nd.turn_start(ev["transcript_path"], since)  # 時刻が取れなくても HEAD 比較（無言）に戻さない
    cwd = ev.get("cwd") or os.getcwd()
    try:
        paths = set(nd._touched_files(calls, cwd))
    except Exception:
        paths = set()
    roots = []
    for p in [cwd] + sorted(paths):
        r = nd._git_root(p)
        if r and os.path.normcase(os.path.abspath(r)) not in [os.path.normcase(os.path.abspath(x)) for x in roots]:
            roots.append(r)  # c:\ と C:\ の違いで同じリポを2回検査し、同じ違反を2回出していた（2026-10-20 実運用）
    # 書き込み系ツールの file_path（文字列だけ）とシェルの書き込み先（> >> tee sed -i cp/mv の宛先 等）。読んだだけは含めない
    written = nd.written_paths(calls, cwd)
    authored = {_key(p) for p in written}
    # スクリプトで生成した文書も自分が書いたものに数える（2026-10-20 追加）。WHY: 印刷で列が切れた要レビュー一覧の表は
    #   Claude が build_review_table.py を直して実行し、生成した .md をターン内でコミットしていた。transcript には
    #   .md のパスが出ないので、旧版は「自分で書いていない」として知らせるだけになる（依頼者の元事象を止められない）。
    #   このターンで Claude が git commit を実行したなら、ターン内の手元のコミットで変わったファイルを数える
    #   （git commit を実行していないターン＝定期ジョブ・別セッションのコミットでは使わない）。
    #   「ターン開始以降に更新した未コミットの変更」も数えた初版は、配布直後の実運用で、同じ作業ツリーで並行する
    #   別セッションが書きかけの未追跡ファイル（Soulful-Content の nt-102 の book_brief）で止めた → 外した。
    #   その代わり、スクリプトで生成してまだコミットしていない .md は知らせるだけ（コミットしたターンで止まる）。
    ran_commit = any(n in ("Bash", "PowerShell") and isinstance(i, dict) and isinstance(i.get("command"), str)
                     and _runs_git_commit(i["command"]) for n, i in calls or [])
    block, warn, split, order, unchecked = [], [], [], [], []
    for root in roots:
        if time.time() > deadline:
            unchecked.append((root, "全部"))
            continue
        changed = [r for r in nd.changed_files(root, since) or [] if not nd.is_fixture(r)]  # fixture は欠陥版を置く場所
        if ev.get("transcript_path") and since is not None and ran_commit:
            authored |= nd.local_commit_paths(root, since)
        bl = nd.Baseline(root, since)  # ターン開始時点の版（ls-tree・diff -M・cat-file --batch の各1回）
        if since is not None:
            new = [r for r in changed if bl.is_new(r)]  # git mv したものは旧パスがあるので新規にしない
            split += [(os.path.join(root, d), v) for d, v in split_reports(new)]
            order += [(os.path.join(root, d), n, first) for d, n, first in oldest_first_batches(new)]
        texts = {}
        for rel in changed:
            if os.path.splitext(rel)[1].lower() not in (".md", ".markdown"):
                continue
            try:
                with io.open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except Exception:
                continue
            if "```" in text or "~~~" in text or "|" in text:
                texts[rel] = text
        bases = bl.texts(sorted(texts)) if texts else {}
        left = sorted(texts)
        while left and time.time() <= deadline:
            rel = left.pop(0)
            full = os.path.join(root, rel)
            (bd, bn, bs, bw), (wd, wn, ws, ww) = classify(texts[rel], bases.get(rel), os.path.dirname(full), name=rel)
            if not _authored(full, authored):
                # このターンで Claude 自身が書いていないファイル（git pull・別セッションのコミット・checkout で入った）は
                # 止めない。知らせるだけ（2026-10-12 Fable 再検証: README しか触っていないのに pull で入った欠陥で止めた）。
                wd, wn, ws, ww = wd + bd, wn + bn, ws + bs, ww + bw
                bd, bn, bs, bw = [], [], [], []
            if bd or bn or bs or bw:
                block.append(_fmt(full, bd, bn, bs, bw))
            if wd or wn or ws or ww:
                warn.append(_fmt(full, wd, wn, ws, ww))
        if left:
            unchecked.append((root, "%d本" % len(left)))
    notes = []
    if unchecked:
        msg = ("report_render_guard: %g秒を超えたので一部の文書を検査していない（%s）。図・番号・連番の違反が無いことは"
               "確認できていない。" % (TIME_BUDGET, "、".join("%s 未検査 %s" % u for u in unchecked)))
        sys.stderr.buffer.write((msg + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
        notes.append(msg)
    if split:
        notes.append("このターンで、同じフォルダに同じ日付・同じ主題の新しい文書を2本以上作った。読み手はどちらを読めば"
                     "よいか迷う（2026-10-06 依頼者「なんでこの2つ分けてんの？1つにまとまってる方が助かる」）。"
                     "一覧・付録は本体の文書の付録にして1本にする:\n" + "\n".join(
                         "  - %s: %s" % (d, "、".join(v[:4])) for d, v in split[:6]))
    if order:
        notes.append("このターンで作った、日付で始まる名前のファイルは GitHub では名前の昇順＝古い順に並ぶ"
                     "（2026-10-07 依頼者「古い記事が一番上になっているのは不都合…新しい記事から」）。"
                     "新しい順の番号（0001_ が最新）を先頭に付けるなど、名前の昇順が新しい順になるようにする:\n" + "\n".join(
                         "  - %s: %d本（先頭は %s）" % (d, n, first) for d, n, first in order[:6]))
    if block:
        _record_firing("report_render_guard", ev)
        parts = [
            "【見る場所で壊れるレポート】このターンで作成・変更した図・表に、印刷・PDF で消える図、"
            "見出しと表で食い違う番号、連番になっていない番号の列、または印刷で右端が切れる幅の表がある"
            "（2026-10-05 依頼者指摘: 印刷用で §3 の図が空、全51行動の表の No. ずれ／2026-10-20: 印刷で"
            "「重要メッセージ」の列が途中から欠けて読めない）。\n" + "\n".join(block) + "\n" + RESOLVE]
        if notes:
            parts.append("（あわせて）" + "\n".join(notes))
        _emit({"decision": "block", "reason": "\n".join(parts)})
    elif warn or notes:
        if notes:
            _record_firing("report_render_guard_warn", ev)
        msg = []
        if warn:
            msg.append("このターンで変わった文書に、印刷で消える図・番号の食い違い・連番崩れ・印刷幅を超える表がある。前からある違反か、"
                       "自分で書いていない（pull・別セッションのコミット・checkout で入った）文書なので止めない。\n"
                       + "\n".join(warn))
        msg += notes
        _emit({"systemMessage": "⚠ report_render_guard: " + "\n".join(msg)})



def _emit(obj):
    sys.stdout.buffer.write(json.dumps(obj).encode("utf-8"))
    sys.stdout.buffer.flush()


def main():
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    try:
        on_stop(ev)
    except Exception as e:  # 黙って通さない: 壊れたことは見える形で知らせる
        sys.stderr.buffer.write(("report_render_guard: %r\n" % (e,)).encode("utf-8"))


if __name__ == "__main__":
    main()
