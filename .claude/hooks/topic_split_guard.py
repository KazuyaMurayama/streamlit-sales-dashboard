# -*- coding: utf-8 -*-
"""1つの依頼で、同じ話題の文書ファイルを2本以上まとめてコミットさせない（PreToolUse: Bash/PowerShell）。

WHY（2026-10-14 依頼者指摘）
    deep-research の commit 014831a で、1つの調査依頼に対し本体レポート
    outputs/NAVAL_HOW_TO_GET_RICH_20261009.md に加えて、同じ話題の Markdown 2本
    （session/NAVAL_CONTEXT_NOTES_20261009.md＝背景ノート、session/NAVAL_COVERAGE_20261009.md
    ＝観点表）を同じコミットで追加した。依頼者:「無駄に3本もレポート作るな。ユーザーのメリットが
    少なく、混乱をもたらす。Claude Code自身が取り違える」。
    near_duplicate_guard（中身がほぼ同じファイルを止める）は、3本の中身が違うので発火しなかった。

不変条件（固有名では塞がない）
    「1つのコミットで新規に追加される文書ファイルのうち、ファイル名から日付・版番号・汎用語
      （NOTES/CONTEXT/COVERAGE/MEMO/DRAFT/SUMMARY/REPORT 等）を除いた話題の語が、片方がもう片方に
      含まれる関係にある組が1つでもあってはならない」
    片方の話題語がもう片方に含まれる＝「その文書は、もう一方の文書の話題の付属物」である。
    シリーズ物（MBA_FINANCE と MBA_ORG_HR のように共通語のほかにそれぞれ固有の主題語を持つ）は
    含まれる関係にならないので通す（較正の結果で決めた。下記）。

対象
    git commit を含む Bash/PowerShell コマンド。新規文書 =
      ① git diff --cached --diff-filter=A（すでにステージ済みの追加）
      ② 同じコマンド内で commit より前に git add があれば、その pathspec に当たる未追跡ファイル
         （git ls-files -o --exclude-standard。`.` `-A` `--all` `-u` 以外のディレクトリ指定は前方一致）
    文書の拡張子: DOC_EXTS。除外: リポのルート直下の .claude/ .codex/（governance の配布物）、
    tests/fixtures/、node_modules 等。

例外（理由必須。黙って通す経路は作らない）
    (a) 正典の工程が要求し、スクリプトが読む台帳（例: Soulful-Content の _meta/book_briefs/<記事ID>.md
        ＝ _meta/prompts/single-book-pipeline.md が作成を指示し scripts/verify_quotes.py 等が読む）は、
        リポの .claude/topic_split_allow.json で宣言する:
          {"allow": [{"glob": "_meta/book_briefs/*.md",
                      "reason": "10字以上の理由",
                      "canon": "その台帳を要求している正典ファイルのリポ内パス"}]}
        reason が10字未満、または canon のファイルがリポに無い宣言は無効（その旨を止めるメッセージに出す）。
        宣言に当たるファイルは突き合わせから外す。
    (b) 依頼者が別々の文書を明示的に求めた1回限りの場合は、コミットメッセージに
        `Topic-Split-Ok: <理由10字以上>` の行を入れる。通すが firing_log に記録する（後で監査できる）。

止め方
    exit 2 + stderr（PreToolUse の拒否。cite_gate と同じ形）。

較正（実測、2026-10-14、tests/calibrate_topic_split_guard.py。判定はフックの find_groups をそのまま使う）
    対象: ~/Desktop/repos 配下 48 リポ（退避用の *_pre20260727_backup を含む）の既定ブランチ直近200コミット
    （merge 除く）＝ 8,092 コミット。新規文書を2本以上含むコミット 138。
      初版（.txt を文書扱い・同名並列と連番を区別しない）  : 発火 76（0.94%）。Soulful の台帳・issue 連番・
        output/<社名>/phaseN.md・requirements.txt・.agents/skills の配布物が誤検知の大半 → 下の4規則を追加
      現行・包含率=1.0・例外宣言あり                      : 発火 26（0.32%）  ← 採用
      現行・包含率≥0.5                                    : 発火 40（0.49%。増えた14件はシリーズ物の誤検知）
      現行・例外宣言なし                                  : 発火 45（Soulful の台帳19件が例外 (a) で消える）
    追加した規則: ①.txt を外す ②ルート直下の .dir/ と archive/・_archived_*/ を外す ③同じファイル名が別の
      ディレクトリにある組は数えない ④両方に番号があって違う組は数えない。汎用語に AGENT(S) を追加。
    発火26件の内訳（全件をリポ×パスで分類）:
      9  本体＋中間メモ・別レポートの同時コミット＝欠陥クラスそのもの（deep-research 7: 014831a・MBA 解説4本・
         ed964be・ea33aa2 / concentration-research-v1 1 / shared-reports 1）
      11 同じ文書の版・派生・分冊の同時コミット＝近縁の欠陥（career_dev の pitch_book と _client 版 7 /
         shopping の v1〜v3 同時取り込み 2（本体と退避 clone）/ report-template と日付版 1 / all_ideas と分冊 1）
      6  誤検知（別物の文書の名前が重なった: Doctor 2・MachineLearning_App 1・add-to-nasdaq 1・
         freelance-compass 1・share-diary 1。いずれも初期セットアップ等の一括追加）
    → deny（拒否）にした。誤検知は 6/8,092 コミット（0.074%）で、(b) の1行で解消でき、拒否のコストは1回の
      書き直し。見逃しのコストは「読み手と AI が正本を取り違える」で、依頼者の指摘はこちら。

終了コード: 0=通過 / 2=拒否
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

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

NAME = "topic_split_guard"
DOC_EXTS = {".md", ".markdown", ".rst", ".adoc", ".org", ".docx"}  # .txt は requirements.txt・生の検索結果などデータが大半のため外す（較正）
EXCLUDED_ANY = {".git", "node_modules", "venv", ".venv", "__pycache__", "site-packages"}
ARCHIVE = re.compile(r"(?:^|/)_?archived?(?:_[^/]*)?/", re.I)  # アーカイブへの移動は生きた文書ではない（較正）
FIXTURE = re.compile(r"(?:^|/)tests?/fixtures/", re.I)
ALLOW_FILE = os.path.join(".claude", "topic_split_allow.json")
MIN_REASON = 10
CONTAIN_THRESHOLD = 1.0  # 較正で決定（docstring 参照）

# 話題を表さない汎用語。ファイル名の「種類」を表す語で、これだけが違う2ファイルは同じ話題。
GENERIC = {
    "NOTES", "NOTE", "CONTEXT", "COVERAGE", "MEMO", "MEMOS", "DRAFT", "DRAFTS", "SUMMARY", "REPORT",
    "REPORTS", "RESEARCH", "ANALYSIS", "PLAN", "FINAL", "OUTLINE", "BRIEF", "SPEC", "REVIEW", "RESULT",
    "RESULTS", "INDEX", "README", "APPENDIX", "CHECKLIST", "TABLE", "TABLES", "LOG", "SESSION", "DATA",
    "RAW", "SOURCE", "SOURCES", "REFS", "REFERENCES", "BACKGROUND", "VERIFY", "VERIFICATION", "AUDIT",
    "TODO", "TASKS", "OVERVIEW", "DETAIL", "DETAILS", "FULL", "MAIN", "BODY", "SCRATCH", "WIP", "TMP",
    "TEMP", "COPY", "OLD", "NEW", "QUOTES", "QUOTE", "SCOPE", "FINDINGS", "EVIDENCE", "THE", "AND",
    "FOR", "WITH", "FROM", "ABOUT", "AGENT", "AGENTS", "メモ", "下書き", "要約", "まとめ", "背景", "観点", "調査", "レポート",
}
_DATE = re.compile(r"(?<!\d)(?:20\d{2}[-_]?\d{2}[-_]?\d{2})(?!\d)")
_VER = re.compile(r"(?:^|[-_ .])v\d+(?=$|[-_ .])", re.I)
_ID = re.compile(r"(?:^|[-_ ])([A-Za-z]{1,4})[-_]?(\d{2,})(?=$|[-_ ])")
_SPLIT = re.compile(r"[^0-9A-Za-z぀-ヿ㐀-鿿]+")
_ASCII_OR_JA = re.compile(r"[A-Za-z]+|\d+|[぀-ヿ㐀-鿿]+")


def _stem(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return _VER.sub(" ", _DATE.sub(" ", stem))


def numbers(path):
    """日付・版番号を除いたファイル名の中の数（issue-010 と issue-011 は別物）。"""
    return set(re.findall(r"\d+", _stem(path)))


def topic_tokens(path):
    """ファイル名から話題の語の集合を返す。"""
    stem = _stem(path)
    toks = set()
    for m in _ID.finditer(stem):  # nt-038 のような記事ID
        toks.add("#" + m.group(1).upper() + m.group(2))
    for part in _SPLIT.split(stem):
        for t in _ASCII_OR_JA.findall(part):
            u = t.upper()
            if u.isdigit():
                continue
            if u.isascii() and len(u) < 3:
                continue
            if not u.isascii() and len(u) < 2:
                continue
            if u in GENERIC:
                continue
            toks.add(u)
    return toks


def same_topic(a, b, threshold=CONTAIN_THRESHOLD):
    if not a or not b:
        return False
    inter = len(a & b)
    return inter > 0 and inter / float(min(len(a), len(b))) >= threshold


def is_doc(rel):
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if len(parts) > 1 and parts[0].startswith("."):  # .claude/.codex/.github/.agents 等: 配布物・道具の設定（較正）
        return False
    if ARCHIVE.search(rel):
        return False
    if any(p in EXCLUDED_ANY for p in parts):
        return False
    if FIXTURE.search(rel):
        return False
    return os.path.splitext(rel)[1].lower() in DOC_EXTS


def find_groups(paths, threshold=CONTAIN_THRESHOLD):
    """同じ話題の新規文書の群（2本以上）を返す。paths はリポ相対パス。"""
    paths = sorted(set(p.replace("\\", "/") for p in paths if is_doc(p)))
    toks = {p: topic_tokens(p) for p in paths}
    parent = {p: p for p in paths}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    nums = {p: numbers(p) for p in paths}
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            # 同じファイル名が別ディレクトリにある＝実体ごとの並列構造（output/<社名>/phase1.md）。
            # 中身の重複は near_duplicate_guard の担当なので、ここでは同じ話題に数えない（較正）
            if os.path.basename(a).lower() == os.path.basename(b).lower():
                continue
            # 両方に番号があって違えば別の対象（連番の issue・分冊）（較正）
            if nums[a] and nums[b] and nums[a] != nums[b]:
                continue
            if same_topic(toks[a], toks[b], threshold):
                parent[find(a)] = find(b)
    groups = {}
    for p in paths:
        groups.setdefault(find(p), []).append(p)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


# ---------- 例外宣言 ----------
def load_allow(root):
    """(有効な glob のリスト, 無効な宣言の説明のリスト)"""
    path = os.path.join(root, ALLOW_FILE)
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [], ["%s が読めない（%s）" % (ALLOW_FILE, e)]
    ok, bad = [], []
    for ent in (data.get("allow") or []):
        g = (ent.get("glob") or "").strip()
        reason = (ent.get("reason") or "").strip()
        canon = (ent.get("canon") or "").strip()
        if not g:
            bad.append("glob が空の宣言")
        elif len(reason) < MIN_REASON:
            bad.append("%s: reason が%d字未満" % (g, MIN_REASON))
        elif not canon or not os.path.isfile(os.path.join(root, canon)):
            bad.append("%s: canon のファイル（%s）がリポに無い" % (g, canon or "未記入"))
        else:
            ok.append(g)
    return ok, bad


def allowed(rel, globs):
    rel = rel.replace("\\", "/")
    return any(fnmatch.fnmatchcase(rel, g) for g in globs)


# ---------- git ----------
def _git(root, args):
    try:
        r = subprocess.run(["git"] + args, cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


_GIT_PREFIX = r"\bgit\b(?P<opts>(?:[\s\\]+(?:-C[\s\\]+(?:\"[^\"]*\"|'[^']*'|\S+)|-[^\s]+|[\w.]+=[^\s]*))*)[\s\\]+"
_COMMIT = re.compile(_GIT_PREFIX + r"commit\b")
_ADD = re.compile(_GIT_PREFIX + r"add\b(?P<args>[^;&|\n]*)")
_DASH_C = re.compile(r"-C[\s\\]+(\"[^\"]*\"|'[^']*'|\S+)")
TRAILER = re.compile(r"Topic-Split-Ok\s*:\s*(?P<r>[^\n\"']{%d,})" % MIN_REASON)


def _unq(s):
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s


def _root_for(cmd, m, base):
    d = base
    dm = _DASH_C.search(m.group("opts") or "")
    if dm:
        d = _unq(dm.group(1))
        if not os.path.isabs(d):
            d = os.path.join(base, d)
    top = _git(d, ["rev-parse", "--show-toplevel"]).strip()
    return top or None


def added_by_git_add(root, cmd, commit_pos, cwd):
    """commit より前の git add の pathspec に当たる未追跡ファイル（リポ相対）。"""
    out = []
    untracked = None
    for m in _ADD.finditer(cmd):
        if m.start() > commit_pos:
            continue
        if untracked is None:
            untracked = [l.strip() for l in _git(root, ["ls-files", "-o", "--exclude-standard"]).splitlines() if l.strip()]
        specs = [_unq(a) for a in m.group("args").split() if a]
        everything = any(s in (".", "-A", "--all", ":/", "*") for s in specs)
        files = [s for s in specs if not s.startswith("-")]
        for u in untracked:
            if everything:
                out.append(u)
                continue
            for s in files:
                full = os.path.normpath(os.path.join(cwd, s))
                rel = os.path.relpath(full, root).replace("\\", "/")
                if rel == u or u.startswith(rel.rstrip("/") + "/") or fnmatch.fnmatchcase(u, rel):
                    out.append(u)
                    break
    return out


def new_docs(root, cmd, commit_pos, cwd):
    staged = [l.strip() for l in _git(root, ["diff", "--cached", "--name-only", "--diff-filter=A"]).splitlines() if l.strip()]
    return sorted(set(staged) | set(added_by_git_add(root, cmd, commit_pos, cwd)))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in (None, "Bash", "PowerShell"):
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    m = _COMMIT.search(cmd)
    if not m:
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    root = _root_for(cmd, m, cwd)
    if not root:
        return 0
    docs = new_docs(root, cmd, m.start(), cwd)
    globs, bad = load_allow(root)
    cand = [p for p in docs if not allowed(p, globs)]
    groups = find_groups(cand)
    if not groups:
        return 0
    t = TRAILER.search(cmd)
    if t:
        _record_fired(NAME, {"allowed_by_trailer": t.group("r").strip(), "groups": groups, "root": root})
        return 0
    _record_fired(NAME, payload)
    lines = ["topic_split_guard: 同じ話題の文書ファイルを、1つのコミットで2本以上新しく追加しようとしています（コミットを止めました）。",
             "読み手と AI が正本を取り違えるため、1つの依頼の文書は本体1本にまとめます。", ""]
    for g in groups:
        lines.append("同じ話題の新規文書:")
        lines += ["  - %s" % p for p in g]
    lines += ["",
              "対処:",
              "  1. 本体1本に統合する（背景ノート・観点表・調査メモ・下書きの中身は本体の節か巻末へ移す）。",
              "  2. 中間メモはリポに置かず OS の一時フォルダへ（PowerShell: $env:TEMP / Git Bash: /tmp）。すでに作ったものは git rm --cached ではなく削除する。",
              "  3. データ（.json/.csv 等）は文書ではないので、このガードの対象外。",
              "",
              "許容する場合（理由必須）:",
              "  (a) 正典の工程が要求し、スクリプトが読む台帳 → リポの %s に" % ALLOW_FILE.replace("\\", "/"),
              '      {"allow": [{"glob": "dir/*.md", "reason": "10字以上の理由", "canon": "その台帳を要求する正典ファイルのパス"}]} を追加する。',
              "  (b) 依頼者が別々の文書を明示的に求めた1回限り → コミットメッセージに `Topic-Split-Ok: <理由10字以上>` の行を入れる（記録される）。"]
    if bad:
        lines += ["", "無効な例外宣言（%s）:" % ALLOW_FILE.replace("\\", "/")] + ["  - " + b for b in bad]
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
