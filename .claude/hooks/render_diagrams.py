# -*- coding: utf-8 -*-
"""Markdown の Mermaid 図を SVG 画像に描き出し、本文に画像を差し込む（印刷・PDF でも図が出るようにする）。

WHY（2026-10-05 依頼者指摘）
  GitHub の Mermaid 図はブラウザで実行時に描かれる。「印刷用」・PDF 化・note・メールでは描かれず、
  空の枠だけが残る（知的生産レポート §3 全体フローで実測）。静的な画像を併記すれば、どこで見ても出る。

使い方
  python .claude/hooks/render_diagrams.py <report.md> [...]      # 図を描いて本文を書き換える
  python .claude/hooks/render_diagrams.py --check <report.md>    # 画像の無い図を数えるだけ（exit 1=あり）

やること（各 ```mermaid ブロックごと）
  1. 同じフォルダの figures/<文書名>_<ソースのハッシュ8桁>.svg に描き出す（ローカルの Edge/Chrome をヘッドレスで使う。
     図の中身は外へ送らない。読み込むのは描画ライブラリ mermaid.js だけ）。
  2. ブロックの直前に ![図N](figures/<文書名>_figN.svg) を置き、ブロックは <details> に畳む
     （GitHub では開けば元の図、印刷では画像だけが出る）。
  既に画像が付いている図は描き直して上書きする（ソースを直したら再実行すればよい）。
"""
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
# Chrome を先に試す（2026-10-05 実測: Chrome は --dump-dom で描画結果を返す。Edge は同じ引数で何も返さなかった）
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
FENCE_RE = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+\.(?:svg|png|jpe?g|gif|webp))(?:\s+\"[^\"]*\")?\)", re.I)
SUMMARY = "図のソース（Mermaid。GitHub では開くと元の図が出る）"


def _browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    return None


def render_svg(src):
    """Mermaid のソース文字列 → SVG 文字列。失敗したら RuntimeError。"""
    b = _browser()
    if not b:
        raise RuntimeError("Edge / Chrome が見つからない（BROWSERS を確認）")
    page = """<!doctype html><html><head><meta charset="utf-8"><script src="%s"></script></head><body>
<textarea id="out"></textarea><script>
mermaid.initialize({startOnLoad:false, theme:"default", securityLevel:"strict", htmlLabels:false,
  flowchart:{htmlLabels:false}, fontFamily:"sans-serif"});
// 画像として開ける SVG にする: HTML ラベル（foreignObject）を使わず、XML として直列化する（<br> のままだと壊れる）
mermaid.render("fig", %s).then(function(r){var d=document.createElement("div"); d.innerHTML=r.svg;
  document.getElementById("out").textContent=new XMLSerializer().serializeToString(d.querySelector("svg"));})
  .catch(function(e){document.getElementById("out").textContent="ERROR:"+e;});
</script></body></html>""" % (MERMAID_JS, _js_str(src))
    fd, path = tempfile.mkstemp(suffix=".html", prefix="mmd_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(page)
    prof = tempfile.mkdtemp(prefix="mmd_prof_")  # 本人が開いているブラウザと混ざらないよう別プロファイル
    try:
        url = "file:///" + path.replace("\\", "/")
        p = subprocess.run([b, "--headless=new", "--disable-gpu", "--no-first-run", "--user-data-dir=" + prof,
                            "--virtual-time-budget=20000", "--dump-dom", url], capture_output=True, timeout=120)
        dom = p.stdout.decode("utf-8", "replace")
    finally:
        os.remove(path)
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'<textarea id="out">(.*?)</textarea>', dom, re.S)
    out = html.unescape(m.group(1)) if m else ""
    if not out.startswith("<svg"):
        raise RuntimeError("描画に失敗: %s" % (out[:200] or "出力なし（mermaid.js を読めなかった可能性。ネットワークを確認）"))
    return out


def _js_str(s):
    import json
    return json.dumps(s, ensure_ascii=False).replace("</", "<\\/")


def blocks(text):
    """[(開始位置, 終了位置, ソース, 直前に有効な画像があるか, その画像パス)]"""
    out = []
    for m in FENCE_RE.finditer(text):
        before = text[:m.start()]
        # 直前（空行・<details>・<summary> を除いて5行以内）の画像
        lines = [ln for ln in before.split("\n")[-12:] if ln.strip()
                 and not re.match(r"\s*</?(details|summary)\b", ln)]
        img = None
        for ln in lines[-5:]:
            im = IMG_RE.search(ln)
            if im:
                img = im.group(1)
        out.append((m.start(), m.end(), m.group(1), img))
    return out


def missing(md_path, text=None):
    """画像の無い（または画像ファイルが実在しない）Mermaid 図の数。"""
    if text is None:
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
    base = os.path.dirname(os.path.abspath(md_path))
    n = 0
    for _s, _e, _src, img in blocks(text):
        if not img or img.startswith(("http://", "https://")) or not os.path.exists(os.path.join(base, img)):
            n += 1
    return n


def process(md_path):
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    base = os.path.dirname(os.path.abspath(md_path))
    stem = os.path.splitext(os.path.basename(md_path))[0]
    found = blocks(text)
    if not found:
        return 0
    os.makedirs(os.path.join(base, "figures"), exist_ok=True)
    pieces, pos = [], 0
    for i, (s, e, src, img) in enumerate(found, 1):
        # 新しい図の名前はソースのハッシュ（順番の番号だと、前に図を足したとき既存の図の画像を上書きする。
        # 2026-10-05 Fable 攻撃検証で実測）
        rel = img if (img and not img.startswith("http")) else "figures/%s_%s.svg" % (
            stem, hashlib.sha1(src.encode("utf-8")).hexdigest()[:8])
        svg = render_svg(src)  # 失敗したら空のファイルを残さずに止まる
        with open(os.path.join(base, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        head = text[pos:s]
        block = text[s:e]
        if img:
            pieces.append(head + block)  # 既存の画像と畳み方はそのまま。SVG だけ描き直す
        else:
            head = head.rstrip("\n")
            if head.endswith("</summary>") and "<details" in head:
                k = head.rindex("<details")  # 既に畳んである図: 画像は <details> の前に置く
                pieces.append(head[:k].rstrip("\n") + "\n\n![図%d](%s)\n\n" % (i, rel) + head[k:] + "\n\n" + block)
            else:
                pieces.append(head + "\n\n![図%d](%s)\n\n<details><summary>%s</summary>\n\n%s\n\n</details>"
                              % (i, rel, SUMMARY, block))
        pos = e
    pieces.append(text[pos:])
    with open(md_path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(pieces))
    return len(found)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--check":
        bad = sum(missing(p) for p in argv[1:])
        print("画像の無い Mermaid 図: %d" % bad)
        return 1 if bad else 0
    for p in argv:
        n = process(p)
        print("%s: %d 図を描き出した（残り画像なし %d）" % (p, n, missing(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
