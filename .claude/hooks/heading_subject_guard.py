# -*- coding: utf-8 -*-
"""PreToolUse hook (Write|Edit): 見出し・タスク名が「何の」を落とした種類の語だけになっていないか。

WHY（2026-11-02 依頼者・逐語）:
  「章のタイトルもなおせ。紹介文みたいに何の、が抜けて略すのはやめろとルールで決めたはずなのに、なぜやってるのか。
   これは、正確に書くなら、メンバーシップの紹介文ドラフトでしょう」
  続けて 2026-11-03「事後の対策が不十分じゃないですか？ 1. 再発防止の手順に則ってやってるんですか？
   2. 全てのリポジトリに展開してますか？ 3. 機械的に防げますか？」
  欠陥の実例: Soulful-Content tasks.md @ 6fce8f1 の見出し「### M2 紹介文ドラフト（2026-10-29 本人原文）」。
  略語の規則（jargon_glossary_guard）は FULL・F5 のような英字の内部記号しか見ておらず、日本語の見出しで
  対象を落とす略し方は、どの機械の検査にも掛からなかった。

不変条件（クラス）:
  .md の見出し（# 〜 ######）と、タスク表（1列目が ID の表）のタスク名で、新しく書いたものは、
  「文書の種類を表す語」（紹介文・ドラフト・テンプレート・メモ・記事 …）を含むなら、それ以外に
  対象を表す語（メンバーシップ・プロフィール・note …）を少なくとも1つ含む。
  ID（M2・S-21）・番号・日付・版の語（初版・更新版）・「本人原文」のような付記は対象に数えない。
  「結論」「背景」「手順」のような節の役割の語だけの見出しは止めない（文書の題で対象が決まっているため）。

判定は語の形で行い、固有の文字列（「紹介文ドラフト」）では塞がない。種類の語・付記の語・節の役割の語を
見出しから取り除き（長い語から順に）、ID・数字・記号・助詞（の・と・や）を消して何も残らなければ違反。

止め方: 新しく増えた違反だけを止める（既存の見出しは触らない限り止めない）。止める・警告の切替は
.claude/report_quality.json の "heading_subject_mode": "deny" | "warn" | "off"（既定 deny）。
例外: 見出し・行の直前の行に <!-- subject-ok: 理由（10字以上） -->。
較正: tests/calibrate_heading_subject_guard.py（全リポの直近30日のコミット）。
CLI: python heading_subject_guard.py --input FILE.md   … 違反があれば exit 1。
Fail-open on any error.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

try:
    from codex_adapter import normalize as _codex_normalize
except Exception:
    def _codex_normalize(d):
        return d

# 語彙は3種。見出しを区切り（記号・助詞）で塊に分け、各塊を語彙の語の連なりに分解する（長い語の部分一致ではなく、
# 塊全体が語彙の語だけで埋まるかを見る＝「案件」は「案」+「件」に分解できないので対象の語として残る）。
# 文書の種類を表す語（これだけでは「何の」が分からない）。
KIND = """
紹介文 説明文 自己紹介文 案内文 告知文 依頼文 返信文 お礼文 謝罪文 投稿文 宣伝文 募集文 挨拶文 概要文 例文集
文章 文面 文案 文書 文 原稿 草稿 下書き 下書 ドラフト 初稿 改稿 素案 試案 たたき台 叩き台 案 テンプレート テンプレ
ひな形 雛形 ひな型 雛型 台本 記事 資料 メモ 覚え書き レポート 報告書 提案書 企画書 計画書 仕様書 手順書 議事録
紹介 告知 案内 draft drafts memo memos article articles text
""".split()
# 付記・版・状態・動作の語、および単独では種類とも対象とも決めにくい語（対象には数えない。単独の見出しは止めない）。
MOD = """
本人原文 本人 原文 初版 更新版 最新版 改訂版 改訂 修正版 確定版 確定 暫定版 暫定 完成版 完成 公開用 投稿用 保存用
コピー用 新版 旧版 新 旧 最新 版 仮 全文 抜粋 前半 後半 続き 追加 追記 更新 作成 作成中 未推敲 推敲 用 一式 等 など
完了 済 済み 未着手 着手 進行中 保留 却下 採用 承認 承認待ち 待ち 要確認 要修正 確認 執筆 レビュー 公開 提出 下記 以下
メール プロンプト キャプション ポスト ツイート 投稿 サンプル コピー スクリプト faq
wip todo done by for from original new old latest final ver version v intro bio post blog newsletter copy
""".split()
# 節の役割の語（これを含む見出しは、文書の題で対象が決まる節として止めない）。
ROLE = """
結論 要点 概要 背景 目的 経緯 前提 対象外 手順 方法 方針 計画 設計 仕様 一覧 表 まとめ 詳細 課題 対策 原因 結果 評価
検証 判定 理由 根拠 注意 注意点 留意点 備考 付録 巻末 参照 出典 参考 参考資料 用語 定義 変更履歴 履歴 次の一手 今後
残課題 状態 説明 要約 本文 例文 返信 提案 修正案 追加案 改善案 対応案 代替案 推奨案 索引 目次
summary template templates overview notes readme usage example examples index contents
""".split()
KIND_SET, MOD_SET, ROLE_SET = set(KIND), set(MOD), set(ROLE)
VOCAB = KIND_SET | MOD_SET | ROLE_SET
MAXLEN = max(len(w) for w in VOCAB)
RE_HEADING = re.compile(r"^ {0,3}(?:>\s*)*(#{1,6})\s+(.*?)\s*#*\s*$")
RE_HTML_H = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.I)
RE_SETEXT = re.compile(r"^ {0,3}(=+|-+)\s*$")
RE_FENCE = re.compile(r"^\s*(?:>\s*)*(```|~~~)")
RE_OK = re.compile(r"<!--\s*subject-ok\s*:\s*([^>]{10,}?)\s*-->")
RE_ZW = re.compile("[​-‍⁠﻿­]")
RE_ID = re.compile(r"(?<![A-Za-z0-9])#?[A-Za-z]{0,4}-?\d+(?:[-.]\d+)*[A-Za-z]?(?![A-Za-z0-9])")
RE_DATE = re.compile(r"\d{4}[-/年.]\d{1,2}(?:[-/月.]\d{1,2}日?)?(?:\s*\d{1,2}:\d{2})?(?:\s*JST)?|\d{8}"
                     r"|\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日")
RE_COUNTER = re.compile(r"第?\d+[本件点つ個枚回章節部号版稿]")
RE_SEP = re.compile(r"(?:および|及び|または|又は|[のとやへをにがはでも]|[^\w]|_)+")
RE_JA_SPACE = re.compile(r"(?<=[^\x00-\x7f])\s+(?=[^\x00-\x7f])")
RE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
RE_ROLE_TAIL = re.compile(r"(?:とは|について|に関して|に関する|とは何か)\s*[?？]?\s*$")
RE_TASK_HEAD = re.compile(r"タスク|やること|作業|todo|task", re.I)


def _plain(s):
    s = unicodedata.normalize("NFKC", RE_ZW.sub("", s))
    s = RE_LINK.sub(r"\1", s)
    s = re.sub(r"<!--.*?-->", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return s.replace("**", " ").replace("__", " ").replace("`", " ")


def _segment(chunk):
    """塊を語彙の語だけで埋め尽くせれば語のリスト、できなければ None（長い語を優先する DP）。"""
    c = chunk.lower()
    best = {0: []}
    for i in range(len(c)):
        if i not in best:
            continue
        for L in range(min(MAXLEN, len(c) - i), 0, -1):
            w = c[i:i + L]
            if w in VOCAB and (i + L) not in best:
                best[i + L] = best[i] + [w]
    return best.get(len(c))


def kind_only(title):
    """種類の語を含み、対象の語も節の役割の語も含まなければ、種類の語のリストを返す。それ以外は None。"""
    s = _plain(title)
    if RE_ROLE_TAIL.search(s):
        return None
    s = RE_COUNTER.sub(" ", RE_ID.sub(" ", RE_DATE.sub(" ", s)))
    s = RE_JA_SPACE.sub("", s)
    words = []
    for chunk in RE_SEP.split(s):
        if not chunk:
            continue
        seg = _segment(chunk)
        if seg is None:
            return None
        words += seg
    if any(w in ROLE_SET for w in words):
        return None
    kinds = [w for w in words if w in KIND_SET]
    return kinds or None


def _task_name(cell):
    """タスク表のタスク名のセルから、目的語の名詞句を取り出す（「〜を投稿する」の「〜」）。"""
    c = cell.strip()
    m = re.match(r"^\*\*(.+?)\*\*", c)
    c = m.group(1) if m else c
    return c.split("を", 1)[0]


def _cells(ln):
    return [c.strip() for c in ln.strip().strip("|").split("|")]


def findings(text):
    """[(行番号 1 始まり, 種類, 見出し・タスク名, [種類の語])]。"""
    out = []
    lines = text.split("\n")
    fence = False
    task_col = None
    for i, ln in enumerate(lines):
        if RE_FENCE.match(ln):
            fence = not fence
            continue
        if fence:
            continue
        prev = lines[i - 1] if i else ""
        if RE_OK.search(prev) or RE_OK.search(ln) or (i > 1 and RE_SETEXT.match(ln) and RE_OK.search(lines[i - 2])):
            continue
        title = None
        m = RE_HEADING.match(ln)
        if m:
            title = m.group(2)
        elif RE_HTML_H.search(ln):
            title = RE_HTML_H.search(ln).group(1)
        elif (i + 1 < len(lines) and RE_SETEXT.match(lines[i + 1]) and ln.strip()
              and not ln.lstrip().startswith(("|", "-", "*", "+", ">")) and not RE_SETEXT.match(ln)
              and not re.match(r"^\s*\d+[.)]\s", ln)):
            title = ln.strip()
        if title is not None:
            task_col = None
            k = kind_only(title)
            if k:
                out.append((i + 1, "見出し", title.strip(), k))
            continue
        if ln.lstrip().startswith("|"):
            cells = _cells(ln)
            if not prev.lstrip().startswith("|"):
                task_col = next((j for j, c in enumerate(cells) if RE_TASK_HEAD.search(c)), None)
                continue
            if task_col is None or all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            if task_col < len(cells) and cells[task_col]:
                name = _task_name(cells[task_col])
                k = kind_only(name)
                if k:
                    out.append((i + 1, "タスク名", name.strip(), k))
        else:
            task_col = None
    return out


def added(before, after):
    """この編集で増えた違反（同じ文言の見出しが既にあっても、件数が増えれば数える）。"""
    import collections
    had = collections.Counter(f[2] for f in findings(before or ""))
    out = []
    for f in findings(after):
        if had[f[2]] > 0:
            had[f[2]] -= 1
        else:
            out.append(f)
    return out


def message(fs):
    items = "\n".join("  - L%d %s「%s」: 種類の語（%s）だけで、何の%sかが書かれていない" % (
        ln, kind, t[:60], "・".join(dict.fromkeys(k)), k[0]) for ln, kind, t, k in fs[:6])
    return ("見出し・タスク名で「何の」を落として略さない（2026-11-02 依頼者「紹介文みたいに何の、が抜けて略すのは"
            "やめろ…正確に書くなら、メンバーシップの紹介文ドラフトでしょう」）。\n" + items +
            "\n直し方: 対象を省かずに書く（例: 「M2 紹介文ドラフト」→「M2 メンバーシップの紹介文ドラフト」）。"
            "ID・日付・「本人原文」などの付記は対象に数えない。版が複数あるなら括弧に初版と更新版の日付を両方書く。"
            "本当に対象が不要なら、直前の行に <!-- subject-ok: 理由（10字以上） -->。")


def _mode():
    try:
        with open(os.path.join(os.getcwd(), ".claude", "report_quality.json"), encoding="utf-8-sig") as f:
            m = json.load(f).get("heading_subject_mode")
        return m if m in ("deny", "warn", "off") else "deny"
    except Exception:
        return "deny"


def _registered_local_copy_exists():
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                                             ".claude", "hooks", base))
        if os.path.normcase(me) == os.path.normcase(local) or not os.path.exists(local):
            return False
        for name in ("settings.json", "settings.local.json"):
            try:
                with open(os.path.join(os.getcwd(), ".claude", name), encoding="utf-8-sig") as f:
                    if base in f.read():
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def main():
    if _registered_local_copy_exists():
        return
    mode = _mode()
    if mode == "off":
        return
    try:
        data = _codex_normalize(json.loads(sys.stdin.buffer.read().decode("utf-8", "replace")))
        tool = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        if not fp.lower().endswith(".md"):
            return
        before = ""
        if os.path.exists(fp):
            with open(fp, encoding="utf-8-sig", errors="replace") as f:
                before = f.read().replace("\r\n", "\n")
        if tool == "Write":
            after = ti.get("content") or ""
        elif tool == "Edit":
            old, new = ti.get("old_string"), ti.get("new_string")
            if old is None or new is None:
                return
            old, new = old.replace("\r\n", "\n"), new.replace("\r\n", "\n")
            after = before.replace(old, new) if ti.get("replace_all") else before.replace(old, new, 1)
        else:
            return
        fs = added(before, after.replace("\r\n", "\n"))
        if not fs:
            return
        _record_firing("heading_subject_guard", data)
        msg = message(fs)
        if mode == "warn":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "additionalContext": "⚠ " + msg}}, ensure_ascii=False))
        else:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": msg}}, ensure_ascii=False))
    except Exception:
        pass


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    a = ap.parse_args(argv)
    with open(a.input, encoding="utf-8-sig", errors="replace") as f:
        fs = findings(f.read().replace("\r\n", "\n"))
    out = sys.stdout.buffer
    out.write(("%s: %s (%d)\n" % ("FAIL" if fs else "PASS", a.input, len(fs))).encode("utf-8"))
    for ln, kind, t, k in fs:
        out.write(("  L%d %s「%s」 %s\n" % (ln, kind, t, "・".join(k))).encode("utf-8"))
    return 1 if fs else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_cli(sys.argv[1:]))
    main()
    sys.exit(0)
