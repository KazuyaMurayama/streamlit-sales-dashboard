# -*- coding: utf-8 -*-
"""Markdown 内の ```mermaid ブロックを PNG 画像図に変換する（GitHub の操作パネル回避・2026-09-05）。

背景: GitHub は Mermaid を iframe で描画し、右上・右下に固定ピクセルの操作パネルを重ねる。
スマホではパネルが図の幅の約43%を占めるため（実測）、コンパクトな図は右側のノードが必ず隠れる。
画像（PNG）にはパネルが重ならないので、同じ mermaid.js でこちら側で描画して埋め込む。

変換後の形式（ソースは保持され、編集可能）:
    ![図N](figures/<stem>_figN.png)

    <details><summary>図N Mermaid ソース（sha256:XXXXXXXXXXXX）</summary>

    ```mermaid-src
    <元の Mermaid コード>
    ```

    </details>

`mermaid-src` は GitHub が図として描画しない言語名なので、二重描画にならない。
sidecar `figures/<stem>_figN.png.sha256` にソースの hash を書き、検査器（mermaid_overlay_check.py）が
「ソースを編集したのに画像を再描画していない」状態を検出する。

使い方:
    python .claude/hooks/mermaid_to_image.py FILE.md            # ```mermaid ブロックを全て画像図へ変換
    python .claude/hooks/mermaid_to_image.py FILE.md --refresh  # 画像図のソースが変わっていたら再描画
終了コード: 失敗が1件でもあれば 1。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mermaid_overlay_check import FENCE_RE, IMG_FIG_RE, RENDER_JS, NODE, PANEL, code_hash, norm_code  # noqa: E402


def render_pngs(blocks, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    payload = {"blocks": blocks, "viewports": [], "panel": PANEL, "export_dir": out_dir}
    p = subprocess.run([NODE, RENDER_JS], input=json.dumps(payload), capture_output=True, text=True, timeout=300)
    data = json.loads(p.stdout)
    if data.get("fatal"):
        raise RuntimeError(data["fatal"][:400])
    return {r["id"]: r for r in data["results"]}


def figure_block(n, rel_png, code, h):
    return (f"![図{n}]({rel_png})\n\n"
            f"<details><summary>図{n} Mermaid ソース（sha256:{h[:12]}）</summary>\n\n"
            f"```mermaid-src\n{norm_code(code)}```\n\n</details>")


def convert(md_path):
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    stem = os.path.splitext(os.path.basename(md_path))[0]
    md_dir = os.path.dirname(os.path.abspath(md_path))
    fig_dir = os.path.join(md_dir, "figures")
    # 既存の画像図の番号を数えて連番を続ける
    n0 = len(IMG_FIG_RE.findall(text))
    fences = list(FENCE_RE.finditer(text))
    if not fences:
        print(f"{md_path}: 変換対象の ```mermaid ブロックなし")
        return 0
    blocks = []
    for i, m in enumerate(fences, n0 + 1):
        blocks.append({"id": f"{stem}_fig{i}", "code": m.group(1), "n": i})
    res = render_pngs(blocks, fig_dir)
    fails = 0
    new = text
    for m, b in zip(reversed(fences), reversed(blocks)):
        r = res.get(b["id"])
        if not r or r.get("error"):
            print(f"[FAIL] {md_path} 図{b['n']}: {r.get('error') if r else 'no result'}")
            fails += 1
            continue
        h = code_hash(b["code"])
        with open(r["png"] + ".sha256", "w", encoding="utf-8") as f:
            f.write(h + "\n")
        rel = f"figures/{os.path.basename(r['png'])}"
        new = new[:m.start()] + figure_block(b["n"], rel, b["code"], h) + new[m.end():]
        print(f"[OK] {md_path} 図{b['n']} → {rel} ({r['svg_w']:.0f}x{r['svg_h']:.0f})")
    if new != text:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new)
    return fails


def refresh(md_path):
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    md_dir = os.path.dirname(os.path.abspath(md_path))
    stale, fails = [], 0
    for m in IMG_FIG_RE.finditer(text):
        png = os.path.join(md_dir, m.group("png"))
        h = code_hash(m.group("code"))
        side = png + ".sha256"
        h_side = open(side, encoding="utf-8").read().strip() if os.path.isfile(side) else ""
        if h_side != h or not os.path.isfile(png):
            stale.append((m, png, h))
    if not stale:
        print(f"{md_path}: 再描画不要（全画像図がソースと整合）")
        return 0
    blocks = [{"id": os.path.splitext(os.path.basename(png))[0], "code": m.group("code")} for m, png, h in stale]
    res = render_pngs(blocks, os.path.dirname(stale[0][1]))
    new = text
    for m, png, h in reversed(stale):
        r = res.get(os.path.splitext(os.path.basename(png))[0])
        if not r or r.get("error"):
            print(f"[FAIL] {md_path}:{m.group('png')}: {r.get('error') if r else 'no result'}")
            fails += 1
            continue
        with open(png + ".sha256", "w", encoding="utf-8") as f:
            f.write(h + "\n")
        # summary 内の短縮 hash を更新
        seg = new[m.start():m.end()]
        seg = re.sub(r"sha256:[0-9a-f]{12,64}", f"sha256:{h[:12]}", seg, count=1)
        new = new[:m.start()] + seg + new[m.end():]
        print(f"[OK] 再描画 {m.group('png')}")
    if new != text:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new)
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    fails = 0
    for p in a.files:
        fails += refresh(p) if a.refresh else convert(p)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
