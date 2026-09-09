# -*- coding: utf-8 -*-
"""Mermaid 図が GitHub の操作パネル（右上の2ボタン／右下のパン・ズーム）に隠れないかを
実レンダリングで検査する（CLAUDE.md §3「図解」の保存前チェック / 再発防止 2026-09-05）。

原理:
  headless Chromium で Mermaid を描画し、GitHub と同じく「コンテナ幅に max-width:100% で縮小」
  したうえで、パネルと同寸の矩形をコンテナの右上・右下に置き、ノード／エッジラベル／サブグラフ
  ラベルの表示座標が矩形と交差したら FAIL。目視・推測ではなく座標で判定する。

較正（PANEL 定数）:
  2026-09-05 にユーザー提供のスマホ実スクリーンショット（画像幅 1170px ＝ CSS 390px の 3 倍）から
  実測した値。GitHub の実装値ではない。表示幅は「スマホ(367px)」と「デスクトップ(1000px)」の
  2条件で検査し、どちらか一方でも交差すれば FAIL（スマホのほうが厳しい）。

使い方:
  python .claude/hooks/mermaid_overlay_check.py FILE.md [...]      # 指定ファイル
  python .claude/hooks/mermaid_overlay_check.py --all              # presentations/ reports/ 配下の全 .md
  python .claude/hooks/mermaid_overlay_check.py FILE.md --preview  # パネルを赤で重ねた PNG を出力
  python .claude/hooks/mermaid_overlay_check.py FILE.md --json     # 機械可読
終了コード: FAIL が1件でもあれば 1。レンダラーが動かない場合は 3（未検証。合格扱いにしない）。

除外: ラベルが空のノード、または classDef で `spacer` クラスを付けたノードは「隠れてよい余白」として
      判定対象外にする（回避策の余白ノードに使う）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER_JS = os.path.join(HERE, "mermaid_render.js")
NODE = os.environ.get("NODE_BIN", "node")

# --- 較正定数（CSS px）。出所: 2026-09-05 スマホ実スクリーンショット1枚の実測。GitHub 実装値ではない。
PANEL = {
    "container_pad": 8,
    "tr": {"top": 12, "right": 33, "w": 85, "h": 35},     # 右上: ↔ / ⧉ の2ボタン
    "br": {"bottom": 12, "right": 38, "w": 112, "h": 98}, # 右下: パン4方向＋リセット＋拡大縮小
}
VIEWPORTS = [
    {"name": "mobile", "width": 367},    # iPhone 縦向きの本文幅（実測）
    {"name": "desktop", "width": 1000},  # PC のファイル表示の本文幅（概算・未実測）
]

FENCE_RE = re.compile(r"^```mermaid[ \t]*\n(.*?)^```", re.M | re.S)
# 画像図の形式（mermaid_to_image.py が生成）:
#   ![alt](figures/X.png)
#   <details><summary>... sha256:XXXXXXXXXXXX ...</summary>
#   ```mermaid-src
#   <code>
#   ```
#   </details>
IMG_FIG_RE = re.compile(
    r"!\[[^\]]*\]\((?P<png>[^)\s]+\.png)\)\s*\n\s*<details>.*?sha256:(?P<hash>[0-9a-f]{12,64}).*?"
    r"```mermaid-src[ \t]*\n(?P<code>.*?)^```\s*</details>", re.M | re.S)


def norm_code(code):
    return "\n".join(l.rstrip() for l in code.strip("\n").splitlines()).strip() + "\n"


def code_hash(code):
    return hashlib.sha256(norm_code(code).encode("utf-8")).hexdigest()


def check_image_figures(md_path):
    """画像図の整合: PNG 実在／summary の hash == ソース hash == sidecar hash。戻り値: 問題文字列のリスト"""
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    problems, n = [], 0
    for m in IMG_FIG_RE.finditer(text):
        n += 1
        png = os.path.join(os.path.dirname(os.path.abspath(md_path)), m.group("png"))
        h_src = code_hash(m.group("code"))
        h_sum = m.group("hash")
        line = text.count("\n", 0, m.start()) + 1
        if not os.path.isfile(png):
            problems.append(f"{md_path}:{line} 画像 {m.group('png')} が存在しない → `python .claude/hooks/mermaid_to_image.py {md_path} --refresh`")
            continue
        side = png + ".sha256"
        h_side = open(side, encoding="utf-8").read().strip() if os.path.isfile(side) else ""
        if not h_src.startswith(h_sum) or h_side != h_src:
            problems.append(f"{md_path}:{line} 画像 {m.group('png')} がソースと不整合（ソース変更後に未再描画）→ `python .claude/hooks/mermaid_to_image.py {md_path} --refresh`")
    return n, problems


def extract_blocks(md_path):
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    blocks = []
    for i, m in enumerate(FENCE_RE.finditer(text), 1):
        line = text.count("\n", 0, m.start()) + 1
        blocks.append({"id": f"{os.path.basename(md_path)}__fig{i}", "code": m.group(1), "line": line})
    return blocks


def render(blocks, preview_dir=None):
    payload = {"blocks": blocks, "viewports": VIEWPORTS, "panel": PANEL, "preview_dir": preview_dir}
    try:
        # encoding/errors are REQUIRED, not cosmetic: text=True decodes with
        # the locale codec (cp932 here). The renderer's error message is
        # Japanese UTF-8, so cp932 raised UnicodeDecodeError inside
        # subprocess's reader THREAD -- which surfaces as stderr="" rather
        # than an exception. The diagnostic silently vanished and a missing
        # playwright looked like a code bug (measured 2026-09-09).
        p = subprocess.run([NODE, RENDER_JS], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"renderer unavailable: {e}"
    if p.returncode != 0 or not p.stdout.strip():
        return None, f"renderer failed: rc={p.returncode} stderr={p.stderr[-400:]}"
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None, f"renderer output not JSON: {p.stdout[:200]}"
    if data.get("fatal"):
        return None, f"renderer fatal: {data['fatal'][:400]}"
    return data["results"], None


def check_files(paths, preview=False):
    """戻り値: (report dict, exit_code)"""
    report = {"files": [], "fail": 0, "pass": 0, "unverified": 0, "image_problems": []}
    all_blocks, owner = [], {}
    for path in paths:
        bl = extract_blocks(path)
        n_img, probs = check_image_figures(path)
        report["files"].append({"path": path, "blocks": len(bl), "image_figures": n_img})
        report["image_problems"] += probs
        report["pass"] += n_img - len([p for p in probs if p.startswith(path)])
        report["fail"] += len(probs)
        for b in bl:
            owner[b["id"]] = (path, b["line"])
            all_blocks.append(b)
    if not all_blocks:
        return report, (1 if report["fail"] else 0)
    preview_dir = None
    if preview:
        preview_dir = os.path.join(tempfile.gettempdir(), "mermaid_overlay_preview")
        os.makedirs(preview_dir, exist_ok=True)
        report["preview_dir"] = preview_dir
    results, err = render(all_blocks, preview_dir)
    if err:
        report["error"] = err
        report["unverified"] = len(all_blocks)
        return report, 3
    by_block = {}
    for r in results:
        by_block.setdefault(r["id"], []).append(r)
    report["blocks"] = []
    for bid, rs in by_block.items():
        path, line = owner[bid]
        entry = {"id": bid, "path": path, "line": line, "viewports": [], "status": "PASS"}
        for r in rs:
            v = {"viewport": r["viewport"], "svg_w": r["svg_w"], "svg_h": r["svg_h"], "scale": r["scale"],
                 "hits": r["hits"], "error": r["error"], "preview": r.get("preview")}
            entry["viewports"].append(v)
            if r["error"]:
                entry["status"] = "UNVERIFIED"
            elif r["hits"] and entry["status"] != "UNVERIFIED":
                entry["status"] = "FAIL"
        report["blocks"].append(entry)
        if entry["status"] == "FAIL":
            report["fail"] += 1
        elif entry["status"] == "PASS":
            report["pass"] += 1
        else:
            report["unverified"] += 1
    code = 1 if report["fail"] else (3 if report["unverified"] else 0)
    return report, code


def format_report(report):
    lines = []
    for p in report.get("image_problems", []):
        lines.append(f"[FAIL] {p}")
    if report.get("error"):
        lines.append(f"[UNVERIFIED] レンダラーが動作せず検証できない: {report['error']}")
        return "\n".join(lines)
    for b in report.get("blocks", []):
        lines.append(f"[{b['status']}] {b['path']}:{b['line']}  ({b['id']})")
        for v in b["viewports"]:
            if v["error"]:
                lines.append(f"    {v['viewport']:8s} render error: {v['error']}")
                continue
            sc = f"scale={v['scale']}" if v["scale"] is not None else ""
            lines.append(f"    {v['viewport']:8s} svg={v['svg_w']:.0f}x{v['svg_h']:.0f} {sc} hits={len(v['hits'])}")
            for h in v["hits"]:
                lines.append(f"      - {h['kind']} 「{h['label']}」 が {'/'.join(h['hit'])} パネルと交差 (x={h['x']},y={h['y']},w={h['w']},h={h['h']})")
            if v.get("preview"):
                lines.append(f"    preview: {v['preview']}")
    lines.append(f"---- PASS {report['pass']} / FAIL {report['fail']} / UNVERIFIED {report['unverified']} ----")
    if report.get("blocks") and any(b["status"] == "FAIL" for b in report["blocks"]):
        lines.append("回避策（2026-09-05 実測: スマホではパネルが幅の43%を占めるため、Mermaid ブロックのままでは"
                     "コンパクトな図は回避不能）: `python .claude/hooks/mermaid_to_image.py FILE.md` で PNG 画像図に変換する"
                     "（同じ mermaid.js で描画・ソースは <details> 内に保持・パネルは画像には重ならない）。"
                     "変換後に本スクリプトで再検査する。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    paths = list(a.files)
    if a.all:
        for pat in ("presentations/*.md", "reports/*.md"):
            paths += sorted(glob.glob(pat))
    paths = [p for p in dict.fromkeys(paths) if p.endswith(".md") and os.path.isfile(p)]
    if not paths:
        print("対象ファイルなし", file=sys.stderr)
        return 0
    report, code = check_files(paths, preview=a.preview)
    print(json.dumps(report, ensure_ascii=False, indent=1) if a.json else format_report(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
