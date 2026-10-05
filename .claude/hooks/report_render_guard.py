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

止めるのは悪化したターンだけ: ①新しい文書 ②違反の数が HEAD より増えた。前からある違反は知らせるだけ
（古い文書を1行直すたびに全図の描き直しを強いると形骸化する）。

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


def findings(text, base_dir, exists=None):
    return diagram_violations(text, base_dir, exists), numbering_violations(text)


def _fmt(path, dia, num):
    lines = []
    for ln, lang in dia[:6]:
        lines.append("  - %s:%d  ```%s の図に静的画像が無い（印刷・PDF・note では空の枠になる）" % (path, ln, lang))
    for hl, hn, tl, rank, title in num[:6]:
        lines.append("  - %s:%d  見出し「%d. %s」と %d行目の表の順位 %d が食い違う" % (path, hl, hn, title[:30], tl, rank))
    more = len(dia) + len(num) - len(lines)
    if more > 0:
        lines.append("  ほか %d 件" % more)
    return "\n".join(lines)


RESOLVE = (
    "解消法:\n"
    "  図 → python .claude/hooks/render_diagrams.py <文書.md>（グローバルなら ~/.claude/hooks/render_diagrams.py）。"
    "Mermaid を figures/ に SVG で描き出し、図の直前に画像を差し込み、元の図は <details> に畳む。"
    "できた SVG もコミットする。\n"
    "  番号 → 表の順位を連番にして見出しと揃える（同点は表の並び順で決め、その決め方を表の前に1文で書く）。\n"
    "  本当に意図した違いなら、図・表の直前の行に <!-- render-ok: 理由 --> / <!-- numbering-ok: 理由 -->（10字以上）。")


def on_stop(ev):
    if ev.get("stop_hook_active") or nd is None:
        return
    since, calls = (None, [])
    if ev.get("transcript_path"):
        since, calls = nd.read_turn(ev["transcript_path"])
    cwd = ev.get("cwd") or os.getcwd()
    try:
        paths = set(nd._touched_files(calls, cwd))
    except Exception:
        paths = set()
    roots = []
    for p in [cwd] + sorted(paths):
        r = nd._git_root(p)
        if r and r not in roots:
            roots.append(r)
    block, warn = [], []
    for root in roots:
        for rel in nd.changed_files(root, since) or []:
            if os.path.splitext(rel)[1].lower() not in (".md", ".markdown"):
                continue
            full = os.path.join(root, rel)
            try:
                with io.open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except Exception:
                continue
            if "```" not in text and "~~~" not in text and "|" not in text:
                continue
            dia, num = findings(text, os.path.dirname(full))
            if not dia and not num:
                continue
            head = nd._git(root, ["show", "HEAD:" + rel.replace("\\", "/")])
            if head is None:
                worse = True
            else:
                hd, hn = findings(head, os.path.dirname(full))
                worse = len(dia) > len(hd) or len(num) > len(hn)
            (block if worse else warn).append(_fmt(full, dia, num))
    if block:
        _record_firing("report_render_guard", ev)
        _emit({"decision": "block", "reason": (
            "【見る場所で壊れるレポート】このターンで作成・変更した文書に、印刷・PDF で消える図、"
            "または見出しと表で食い違う番号がある（2026-10-05 依頼者指摘: 印刷用で §3 の図が空、"
            "表の順位と見出しの No. がずれた）。\n" + "\n".join(block) + "\n" + RESOLVE)})
    elif warn:
        _emit({"systemMessage": "⚠ report_render_guard: このターンで触った文書に、前からある印刷で消える図・番号の"
               "食い違いがある（このターンでは悪化していないので止めない）。\n" + "\n".join(warn)})


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
