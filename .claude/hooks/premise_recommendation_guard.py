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

CALIBRATION (実測 2026-09-11)
  46 リポ / 1,869 の .md に当てて発火 0 件（0.00%）。当時の欠陥版
  (deep-research 65db661) には発火する。ノイズを出さずに標的を捉える幅である。
  再測は --calibrate <repos の親ディレクトリ>。

KNOWN LIMITATION (実測 2026-09-11)
  判定文が見出し（「推奨事項（…を反映）」等）の版 (98484cb) は無音になる。
  verdict_sentence が最初の強調文を取るため、見出し直後に別の強調がある構成
  では判定文を取り違える。閾値は下げない——下げれば 0.00% の静かさを失い、
  読まれない警告になる。取りこぼしは人のレビューに残す。

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
    r"判定できない範囲|誤差の範囲|差は(消|無)|意義は小さい|上回らない")
GAP_SHRANK = re.compile(r"[+＋]\s*\d+\s*[／/]\s*[+＋]?\s*\d+|差\s*[はが]\s*[+＋]?\s*\d+")

# 結論・推奨セクションの見出し
CONCL_HEAD = re.compile(r"^#{1,3}\s*(0\.\s*)?(結論|推奨|サマリー|Executive|まとめ)", re.M)
# 肯定的な推奨語
POSITIVE = re.compile(r"試す|試行|導入(する|を推奨|に値)|推奨する|採用(する|を推奨)|"
                      r"入れる価値|やってみる|始める")
# 否定・保留の「判定」。単語の出現ではなく**判定文の形**で照合する。
# 2026-09-11 の実測: 単語 `やめる` で照合したところ、欠陥版の結論にあった
# 「やめるときもファイルは何も変わらない」（撤退が容易という安心材料）を
# 「採用しないという判定」と誤読し、本物の欠陥版を見逃した。
# 語の出現は判定ではない。判定を表す述語の形に限定する。
NEGATIVE = re.compile(
    r"(導入|採用|移行)し(ない|ません)|"
    r"(入れ|やめ|見送)(ない|る)こと(を推奨|に決|とする)|"
    r"(不要|中止|棄却|見送り)(である|です|と(判断|結論|する)|。|\*\*)|"
    r"推奨し(ない|ません)|"
    r"(同等|差は(小さ|無|ほぼ無)|判定できない)(である|です|。|\*\*|範囲)")

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


def verdict_sentence(concl):
    """結論セクションの「判定文」＝最初の強調文（**…**）または最初の文。

    セクション全体を見てはいけない。2026-09-11 の実測: 欠陥版の結論には
    留保として「3 用途とも判定できない範囲に入る」が**含まれていた**。
    セクション全体で照合すると、この留保の存在を「判定を更新済み」と誤読し、
    本物の欠陥を見逃す。読者が最初に受け取るのは冒頭の太字の判定文であり、
    留保が後段にあっても判定が肯定なら、読者は肯定と理解する——これが
    ユーザーが「+13 はまだ高い、かなりメリットがある」と読んだ経路である。
    """
    m = re.search(r"\*\*(.+?)\*\*", concl, re.S)
    if m:
        return m.group(1)
    for line in concl.splitlines():
        if line.strip():
            return line.strip()
    return ""


def analyze(text):
    """(検出したか, 理由) を返す。"""
    if not (DOWNGRADE.search(text) and GAP_SHRANK.search(text)):
        return False, ""
    concl = conclusion_block(text)
    if not concl:
        return False, ""
    v = verdict_sentence(concl)
    if not v:
        return False, ""
    if NEGATIVE.search(v):
        return False, ""          # 判定文そのものが更新されている
    if not POSITIVE.search(v):
        return False, ""          # 判定文が推奨していない
    return True, ("本文は「前提を反映して差が縮んだ」と述べているのに、"
                  "冒頭の判定文は肯定のままです")


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
