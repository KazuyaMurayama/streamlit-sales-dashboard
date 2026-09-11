# -*- coding: utf-8 -*-
"""Stop hook: 前提を本文に取り込みながら、結論・推奨を更新し忘れた文書を検出する。

WHY THIS EXISTS (2026-09-11)
----------------------------
2026-09-07、ユーザーは逐語でこう述べた——「ファイルインデックスがすでに自動で
各ファイルの概要を把握しているため、ファイルを問い合わせたらすぐ見つかると
思います」。OBSIDIAN_VS_VSCODE_GITHUB_20260905.md はこの前提を §4-1 の表と
感度分析に**正しく取り込み**、スコア差が +26/+23/+11 → +13/+9/+3 に縮むことまで
示した。そして「3 用途とも判定できない範囲に入る」と自分で書いた。

**それでも §0 の推奨は「2 週間試すべき」のまま据え置かれた。**

分析は更新されたのに結論だけ古いまま残る——これがこの欠陥のクラスである。
ユーザーは +13 を見て「まだ高い、かなりメリットがある」と読んだ。実際には
感度分析で下げ切れていない軸（G 取り込み）が残っており、実績で是正すると
+1/−3/+3、つまり「同等かやや劣る」だった。**推奨を据え置いたことに加えて、
下げるべき軸を下げ残していた。**

WHY A HOOK AND NOT A RULE
-------------------------
この欠陥は書いた本人には見えない。分析本文を更新した時点で「反映した」という
達成感が生じ、結論セクションを読み返す動機が消えるからである。CLAUDE.md に
「結論も更新せよ」と書いても、本人は更新したつもりでいるので読み直さない。
2026-09-07 の実例では、同じセッション内で 2 度「メリットが分からない」「ちゃんと
示しなさい」と指摘されながら、説明不足と解釈して結論は触らなかった。

WHAT IS CHECKED
  P1 WARN  文書が「前提を反映して評価が下がった」ことを示す語（感度分析・
           加点すると・縮む・差は N 点・判定できない 等）を含むのに、
           結論/推奨セクションが依然として肯定的な推奨語（試す・導入・推奨・
           採用）だけで構成されている場合に報告する。

NON-GOALS (deliberate)
  - 正しい結論が何かは判定しない。機械には決められない。報告するのは
    「分析と結論が逆を向いている可能性」だけで、判断は人に戻す。
  - スコアの再計算はしない。ルーブリックの妥当性は別問題である。
  - 閾値を下げて検出率を上げない。誤検知が増えれば読まれなくなる。

CALIBRATION (実測 2026-09-11・独立QC後の再設計版)
  46 リポ / 1,869 の .md で発火 27 件（1.44%）。過去に「35.9% は形骸化確実、
  除外して 1.8% で妥当」と較正した前例と同程度の水準である。
  実際の欠陥版 3 版（83119be / 65db661 / 98484cb）すべてを検出し、是正後の
  origin/main は無音。selftest の変種 19 件は 19 件検出（100%）。
  発火を目視した例: 真陽性 = HAPPY_MEN_40S_FINAL_20260728.md（判定文の後ろに
  だけ「d=0.31 だが…d=−0.03＝差なしまで縮む」がある）。偽陽性 =
  HAPPINESS_PURSUITS_EVIDENCE_20260721.md（引用文献の記述に反応）。
  **偽陽性は残っている**。1 行の warn でありブロックしないため許容した。
  再測は --calibrate <repos の親ディレクトリ>。

初版の失敗（独立QCが実測で破った。記録として残す）
  初版は「結論の判定文に肯定語があるか」を語彙辞書で判定し、発火 0.00% を
  「静かで良い」と自己申告した。QC の実測で死んだ検査と判明:
    - CONCL_HEAD が結論系見出し 308 本の **31.2% しか拾えなかった**
      （「## 0. エグゼクティブサマリー」26 本・「## 0. いきなり結論」21 本 等）
    - 実在する判定文 213 本のうち推奨語を含むのは **5 本 (2.3%)**。この作者の
      レポートの結論は採否ではなく所見であり、語彙で向きを読む設計が原理的に
      成立しない
    - 同クラスの変種 31 件中 26 件を取りこぼし（83.9%）
  → 語彙判定を捨て、**下方修正の記述が判定文より後ろにしか無いこと**を
    位置関係で見る設計に作り直した。これが欠陥の本質（読者は冒頭の判定文で
    理解を作るので、留保が後段にあると古い判定のまま読む）に対応する。

SELFTEST
  python premise_recommendation_guard.py --selftest
  (a) 欠陥版（感度分析で差が縮んだと書きつつ推奨は「試す」のまま）→ 検出
  (b) 修正版（推奨も「不要」に更新済み）→ 無音
  (c) 感度分析を含まない通常の文書 → 無音
  (a) が本体である。直した版で PASS しても何も証明しない。
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

# 「前提を反映した結果、評価が下がった」ことを示す語。
# 単独では出にくく、組み合わせで初めて意味を持つため 2 群に分けて両方を要求する。
DOWNGRADE = re.compile(
    r"感度分析|加点すると|加点する（|正しく加点|縮(み|む|まる)|"
    r"判定できない範囲|誤差の範囲|差は(消|無)|意義は小さい|上回らない|"
    r"前提を(反映|織り込|踏まえ)|再評価すると|優劣が付かない")
# 数値で縮小を示す形。**必須条件にしてはいけない**——2026-09-11 の実測で、
# 「再評価すると優劣が付かない」のように言葉だけで下方修正する版が
# 段階1で落ちていた（変種 19 件中 8 件が取りこぼし）。
GAP_SHRANK = re.compile(r"[+＋]\s*\d+\s*[／/]\s*[+＋]?\s*\d+|差\s*[はが]\s*[+＋]?\s*\d+")
# 言葉だけで下方修正を述べる形。数値が無くても段階1を通す。
VERBAL_SHRANK = re.compile(
    r"優劣が付かない|判定できない|同等|差は(?:小さ|無|ほぼ)|"
    r"意義は小さい|上回らない|誤差の範囲")

# 結論・推奨セクションの見出し。
# 2026-09-11 の独立QC(Fable)が実測: 初版の `(0\.\s*)?(結論|推奨|サマリー|…)` は
# 日付付きレポート 460 本のうち結論系見出しを持つ 308 本の **31.2% しか拾えなかった**。
# 取りこぼしの上位は「## 0. エグゼクティブサマリー」26本・「## 0. いきなり結論」21本・
# 「## §0 結論」7本。カタカナ表記と §/番号の揺れを実コーパスから帰納して作り直した。
CONCL_HEAD = re.compile(
    r"^#{1,4}\s*(?:§\s*)?(?:\d+[.\-]?\s*)?(?:\d+秒)?\s*"
    r"(?:結論|判定|方針|総括|まとめ|サマリ[ー]?|エグゼクティブ\s*サマリ[ー]?|"
    r"いきなり結論|Executive\s*Summary|Summary|TL;?DR)", re.M | re.I)

# 「前提を反映して差が縮んだ」ことを述べている文そのもの。
# 初版は POSITIVE/NEGATIVE の語彙辞書で判定文の向きを読もうとしたが、独立QCの
# 実測で破綻した: 実在する判定文 213 本のうち推奨語を含むのは **5 本 (2.3%)** しか
# なく、大半は「note で月30万円は…届かない」のような所見であって採否ではない。
# 語彙で採否を読む設計は、この作者のレポートでは原理的に機能しない。
#
# そこで**語彙を捨て、位置関係で判定する**。この欠陥の本質は
# 「下方修正の事実が、判定文より後ろにしか無い」ことである。読者は冒頭の判定文で
# 理解を作るので、留保が後段にあっても判定が古いままなら誤読する——ユーザーが
# 「+13 はまだ高い」と読んだのは、まさにこの構造による。
DOWNGRADE_SENT = re.compile(
    r"[^。\n]*(?:感度分析|正しく加点|加点すると|前提を(?:反映|織り込|踏まえ)|"
    r"再評価|縮(?:み|む|まる)|判定できない|誤差の範囲|優劣が付かない|"
    r"意義は小さい|上回らない)[^。\n]*[。\n]")

EXCLUDE_DIRS = (".claude/", ".github/", "node_modules/", "_archive", "_archived",
                ".venv/", "vendor/", "session/", "logs/", "tmp/", "docs/superpowers/")
MAX_REPORTED = 3


def _git_bytes(*args, **kw):
    try:
        p = subprocess.run(["git"] + list(args), capture_output=True,
                           timeout=20, cwd=kw.get("cwd"))
        return p.stdout if p.returncode == 0 else b""
    except Exception:
        return b""


def _repo_root(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10, cwd=cwd)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def changed_md(root):
    """作業ツリーで変更された .md（session_guard と同じ方式）。"""
    out = set()
    raw = _git_bytes("status", "--porcelain", "-z", "-uall", cwd=root)
    fields = [f for f in (raw or b"").split(b"\x00") if f]
    i = 0
    while i < len(fields):
        f = fields[i].decode("utf-8", "replace")
        status, name = f[:2], f[3:]
        i += 1
        if status and status[0] in ("R", "C"):
            i += 1
        if status.strip() == "D":
            continue
        if name.lower().endswith(".md"):
            n = name.replace("\\", "/")
            if not any(d in "/" + n for d in EXCLUDE_DIRS):
                out.add(n)
    return out


def conclusion_block(text):
    """最初の結論/推奨セクションの本文を返す。無ければ ''。"""
    m = CONCL_HEAD.search(text)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^#{1,3}\s+", text[start:], re.M)
    return text[start:start + (nxt.start() if nxt else 4000)]


def verdict_span(text):
    """判定文の終端オフセット。結論セクション冒頭の強調文、無ければ最初の文。

    読者が最初に受け取る一文がどこで終わるかを返す。ここより後ろにしか
    下方修正が無ければ、読者は古い判定のまま理解を作る。
    """
    m = CONCL_HEAD.search(text)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"^#{1,4}\s+", text[start:], re.M)
    blk_end = start + (nxt.start() if nxt else min(4000, len(text) - start))
    blk = text[start:blk_end]
    # 強調が「ラベル」の場合は判定文ではない。ラベルは名詞句で終止し、直後に
    # コロン等が続く（例: 「**採点の是正（2026-09-11）**: 感度分析の…」）。
    # ラベルを判定文と誤認すると、その直後にある本文が「判定文より後ろ」に
    # 分類され、更新済みの文書まで検出してしまう（2026-09-11 実測）。
    for b in re.finditer(r"\*\*(.+?)\*\*", blk, re.S):
        inner = b.group(1).strip()
        if len(inner) <= 6:
            continue
        after = blk[b.end():b.end() + 2]
        if re.match(r"\s*[:：]", after):       # ラベル → 次の強調へ
            continue
        if not re.search(r"[。．.！？]|です|ます|である|しない|ない$", inner):
            continue                          # 終止しない断片はラベル扱い
        return start + b.end()
    for mm in re.finditer(r"[^\n]+", blk):
        s = mm.group(0).strip().lstrip("->*| ").strip()
        if len(s) > 6 and not s.startswith(("|", "---")):
            return start + mm.end()
    return None


def analyze(text):
    """(検出したか, 理由) を返す。

    語彙で採否を読まない（実コーパス 213 本中 5 本しか推奨語を含まない）。
    **下方修正の記述が、判定文より後ろにしか存在しないこと**を位置で判定する。
    """
    if not DOWNGRADE.search(text):
        return False, ""
    if not (GAP_SHRANK.search(text) or VERBAL_SHRANK.search(text)):
        return False, ""
    end = verdict_span(text)
    if end is None:
        return False, ""
    # 判定文そのもの（およびその直前＝見出し〜判定文）に下方修正が書かれていれば、
    # 読者は最初の一文で下方修正を受け取れる。欠陥ではない。
    head = CONCL_HEAD.search(text)
    lead = text[head.start():end]
    if DOWNGRADE_SENT.search(lead):
        return False, ""
    # 判定文が下方修正を**結論として言い切っている**場合も更新済みとみなす。
    # 例:「導入しない。現行構成と同等で、追加の手間だけが残る。」
    # ここだけは語彙を使うが、対象は判定文 1 文に限る（文書全体の語彙辞書が
    # 破綻したのは 213 本中 5 本しか一致しなかったためで、判定文が下方修正を
    # 述べているかは別の問題である）。
    if VERBAL_SHRANK.search(lead):
        return False, ""
    # 判定文より後ろに下方修正の文があるか。無ければそもそも対象外。
    if not DOWNGRADE_SENT.search(text[end:]):
        return False, ""
    return True, ("差が縮んだ・判定できないという記述が、冒頭の判定文より"
                  "後ろにしかありません。読者は古い判定のまま読みます")


def _scan(root, rels):
    hits = []
    for rel in sorted(rels):
        ap = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(ap):
            continue
        try:
            with open(ap, encoding="utf-8-sig") as f:
                t = f.read()
        except Exception:
            continue
        ok, why = analyze(t)
        if ok:
            hits.append((rel, why))
    return hits


def _selftest():
    import io
    import shutil
    import tempfile
    results = []
    tmp = tempfile.mkdtemp(prefix="prg_selftest_")
    try:
        # (a) 欠陥版: 分析は下げたが推奨は据え置き
        broken = (
            "# 評価\n\n## 0. 結論\n\n"
            "**入れる価値はある。2 週間試すことを推奨する。**\n\n"
            "## 4. 採点\n\n"
            "感度分析: 現行構成に問い合わせを正しく加点すると、"
            "差は +13／+9／+3 に縮み、3 用途とも判定できない範囲に入る。\n")
        ok, why = analyze(broken)
        results.append(("(a) 欠陥版を検出", ok))
        print("selftest 1/3 %s" % ("PASS" if ok else "FAIL"))

        # (b) 修正版: 推奨も更新済み
        fixed = broken.replace(
            "**入れる価値はある。2 週間試すことを推奨する。**",
            "**導入しない。現行構成と同等で、追加の手間だけが残る。**")
        ok2, _ = analyze(fixed)
        results.append(("(b) 修正版は無音", not ok2))
        print("selftest 2/3 %s" % ("PASS" if not ok2 else "FAIL"))

        # (d) 撤退容易さの言及を「不採用の判定」と誤読しないこと。
        # これが 2026-09-11 に本物の欠陥版を見逃した実際の原因である。
        trap = broken.replace(
            "**入れる価値はある。2 週間試すことを推奨する。**",
            "**入れる価値はある。2 週間試すことを推奨する。**"
            "やめるときもファイルは何も変わらない。")
        ok4, _ = analyze(trap)
        results.append(("(d) 撤退容易さの記述に騙されない", ok4))
        print("selftest 4/5 %s" % ("PASS" if ok4 else "FAIL"))

        # (e) 留保が結論セクション内にあっても、判定文が肯定なら検出する。
        # これが本物の欠陥版の構造であり、(a) の合成版では再現できていなかった。
        caveat = (
            "# 評価\n\n## 0. 結論\n\n"
            "**入れる価値はある。2 週間試すことを推奨する。**\n\n"
            "> 注: 正しく加点すると差は +13／+9／+3 に縮み、"
            "3 用途とも判定できない範囲に入る。\n\n"
            "## 4. 採点\n\n感度分析の詳細。\n")
        ok5, _ = analyze(caveat)
        results.append(("(e) 留保が同セクションにあっても検出", ok5))
        print("selftest 5/5 %s" % ("PASS" if ok5 else "FAIL"))

        # (c) 感度分析を含まない通常文書
        plain = ("# 手順書\n\n## 0. 結論\n\n"
                 "この手順を採用する。\n\n## 1. 詳細\n\n通常の説明。\n")
        ok3, _ = analyze(plain)
        results.append(("(c) 通常文書は無音", not ok3))
        print("selftest 3/5 %s" % ("PASS" if not ok3 else "FAIL"))

        # (f) 変種への汎用性。独立QC(2026-09-11)が初版を 31 変種中 26 件
        # 取りこぼし(83.9%)で破ったため、QC が使った軸を回帰テストにする:
        # 見出しの揺れ・推奨語の揺れ・下方修正の言い回しの揺れ。
        heads = ["## 0. エグゼクティブサマリー", "## 0. いきなり結論",
                 "## §0 結論", "## 判定", "#### 結論", "## TL;DR",
                 "## 方針", "## 総括", "## Executive Summary"]
        verdicts = ["**導入を進める。**", "**限定的に可とする。**",
                    "**GO とする。**", "**価値があると判断する。**",
                    "**トライアルを開始する。**", "**おすすめできる。**"]
        downs = ["前提を織り込むと差は +13／+9／+3 に縮む。",
                 "再評価すると優劣が付かない。",
                 "正しく加点すると判定できない範囲に入る。",
                 "感度分析では差は +2／+1／+0 まで縮まる。"]
        variants = []
        for h in heads:
            variants.append("# X\n\n%s\n\n**採用する。**\n\n## 2. 詳細\n\n%s\n"
                            % (h, downs[0]))
        for v in verdicts:
            variants.append("# X\n\n## 0. 結論\n\n%s\n\n## 2. 詳細\n\n%s\n"
                            % (v, downs[1]))
        for dwn in downs:
            variants.append("# X\n\n## 0. 結論\n\n**採用する。**\n\n"
                            "## 2. 詳細\n\n%s\n" % dwn)
        det = sum(1 for v in variants if analyze(v)[0])
        rate = 100.0 * det / len(variants)
        ok6 = rate >= 90.0
        results.append(("(f) 変種 %d 件中 %d 件検出 (%.1f%%)"
                        % (len(variants), det, rate), ok6))
        print("selftest 6/6 %s: 変種 %d 件中 %d 件検出 (%.1f%%)"
              % ("PASS" if ok6 else "FAIL", len(variants), det, rate))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, o in results if o)
    print("\n%d/%d passed" % (passed, len(results)))
    for n, o in results:
        if not o:
            print("  FAILED: %s" % n)
    if passed == len(results):
        print("SELFTEST OK")
    return 0 if passed == len(results) else 1


def _calibrate(parent):
    """全リポの .md に当てて発火率を実測する（自作テストの合格は較正ではない）。"""
    total = fired = repos = 0
    hits = []
    for d in sorted(os.listdir(parent)):
        rp = os.path.join(parent, d)
        if not os.path.isdir(os.path.join(rp, ".git")):
            continue
        repos += 1
        raw = _git_bytes("ls-files", "-z", "*.md", cwd=rp)
        for rel in (raw or b"").decode("utf-8", "replace").split("\0"):
            rel = rel.strip()
            if not rel or any(x in "/" + rel for x in EXCLUDE_DIRS):
                continue
            ap = os.path.join(rp, rel.replace("/", os.sep))
            try:
                with open(ap, encoding="utf-8-sig") as f:
                    t = f.read()
            except Exception:
                continue
            total += 1
            ok, _ = analyze(t)
            if ok:
                fired += 1
                hits.append("%s/%s" % (d, rel))
    print("対象リポ: %d / 検査した .md: %d / 発火: %d (%.2f%%)"
          % (repos, total, fired, (100.0 * fired / total) if total else 0.0))
    for h in hits[:20]:
        print("   " + h)
    return 0


def main():
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return
    try:
        if data.get("stop_hook_active"):
            return
        root = _repo_root(os.getcwd())
        if not root:
            return
        hits = _scan(root, changed_md(root))
        if not hits:
            return
        _record_firing("premise_recommendation_guard", data)
        lines = ["・%s: %s" % (r, w) for r, w in hits[:MAX_REPORTED]]
        sys.stderr.write(
            "⚠ 前提を反映したのに結論を更新していない可能性があります:\n"
            + "\n".join(lines) +
            "\n分析本文を書き換えた時点で「反映した」と感じ、結論セクションを"
            "読み返さないのがこの欠陥の起き方です。結論・推奨が、更新後の"
            "分析と同じ向きを指しているか確認してください。\n")
    except Exception:
        pass


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            if not _s.isatty():
                _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--calibrate" in sys.argv:
        i = sys.argv.index("--calibrate")
        parent = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.getcwd()
        sys.exit(_calibrate(parent))
    main()
    sys.exit(0)
