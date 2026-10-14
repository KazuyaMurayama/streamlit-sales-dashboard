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

較正（実測、2026-10-14 第2版＝Fable 攻撃検証の7件を直した後、tests/calibrate_topic_split_guard.py。
判定はフックの find_groups をそのまま使い、直近24時間の別コミットの追加文書も recent として渡す）
    対象: ~/Desktop/repos 配下 48 リポ（退避用の *_pre20260727_backup を含む）の既定ブランチ直近200コミット
    （merge 除く）＝ 8,186 コミット。新規文書を2本以上含むコミット 137。
      第1版（同一コミットのみ・包含率=1.0）                : 発火 26
      第2版・24時間窓なし                                  : 発火 24（0.29%）
      第2版・24時間窓あり・包含率=1.0・例外宣言あり        : 発火 38（0.46%）  ← 採用
      第2版・包含率≥0.5                                    : 発火 82（1.00%。増分はシリーズ物の誤検知）
      第2版・例外宣言なし                                  : 発火 60（Soulful の台帳が例外 (a) で消える）
    第2版で足した規則（攻撃検証の指摘）: cd/pushd/Set-Location の後の commit で root を解決／種別語（KIND）を
      持つ側は話題語1つの共有で発火／直近24時間の別コミットも比較／同名ファイルの除外は兄弟ディレクトリに
      3つ以上並ぶ・2ディレクトリが同名を3つ以上共有・ディレクトリの番号が違う、のときだけ／core.quotepath=off
      ／Git・git.exe・git "commit"／-F のメッセージファイル内の Topic-Split-Ok。
    較正で足した規則（24時間窓で増えた誤検知を見て）: 日付・-vN・拡張子だけが違う同じディレクトリの組は
      同じ文書の版として数えない（命名規則が許す -v2・日付版・.docx 版。版の扱いは near_duplicate_guard /
      deprecation_guard の担当）／番号違いは種別語があっても別物（nt-062-…-DRAFT と nt-063-…-DRAFT）／
      _reference・vendor・third_party（第三者の文書の保管庫）を外す／ANALYSIS・SUMMARY 等は種別語から外す
      （phase2_industry_analysis が別 phase と結び付いた）。
    発火38件の内訳（全件をリポ×パスで分類）:
      19 欠陥クラスそのもの（本体＋調査メモ・QA 記録・計画/実行記録・別レポートが同じ話題）: deep-research 7・
         同退避 clone 2・book_summary 3・NASDAQ-strategy-gas 2・concentration-research-v1 1・shared-reports 1・
         happiness-system 1・career_dev 1・shopping 退避 clone 1
      9  同じ文書の派生・分冊の同時コミット（career_dev の pitch_book と _client 版 7・all_ideas と分冊 1・
         時刻付き v1 と v2 1）
      10 誤検知（AI-Transformation-Architect 1・Doctor 2・MachineLearning_App 1・Soulful-Content 1・
         add-to-nasdaq 1・enterprise-ai-strategy-advisor 1・freelance-compass 1・happiness-system 1・
         personal-brand-publisher_v1 1。初期セットアップ等の一括追加が中心）
    → deny（拒否）を維持。誤検知は 10/8,186 コミット（0.12%）で、(b) の1行で解消でき、拒否のコストは1回の
      書き直し。見逃しのコストは「読み手と AI が正本を取り違える」で、依頼者の指摘はこちら。
    既知の未対応（攻撃ハーネスで LEAK のまま）: 話題語のない汎用名だけのメモ（CONTEXT_NOTES.md）・両方に別番号
      ・archive/ や .claude/ 配下・.html/.txt 等の拡張子・add -N→commit -am・同コマンド内の mv→add・
      変数展開した commit。

終了コード: 0=通過 / 2=拒否
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
import unicodedata

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
EXCLUDED_ANY = {".git", "node_modules", "venv", ".venv", "__pycache__", "site-packages",
                "_reference", "vendor", "third_party"}  # 第三者の文書の保管庫（較正: 記事アーカイブの【メモ】題）
ARCHIVE = re.compile(r"(?:^|/)_?archived?(?:_[^/]*)?/", re.I)  # アーカイブへの移動は生きた文書ではない（較正）
FIXTURE = re.compile(r"(?:^|/)tests?/fixtures/", re.I)
ALLOW_FILE = os.path.join(".claude", "topic_split_allow.json")
MIN_REASON = 10
CONTAIN_THRESHOLD = 1.0  # 較正で決定（docstring 参照）
RECENT = "24.hours"      # 別コミットに分けた付属メモも比べる窓（Fable 攻撃検証 2026-10-14 #3）
PARALLEL_MIN = 3         # 同名ファイルを「実体ごとの並列構造」とみなす最小の数（#4）

# 「中間メモの種類」を表す語。片方がこれを持ち、話題語を1つでも共有すれば同じ話題（#2）。
# シリーズ物（MBA_FINANCE と MBA_ORG_HR）はこれを持たないので、この規則では止まらない。
KIND = {
    "NOTES", "NOTE", "CONTEXT", "COVERAGE", "MEMO", "MEMOS", "DRAFT", "DRAFTS", "BACKGROUND", "THREAD",
    "DIGEST", "OUTLINE", "RESEARCH", "SCRATCH", "WIP", "FINDINGS", "TWEETS", "TRANSCRIPT",
    "メモ", "下書き", "要約", "まとめ", "背景", "観点", "調査", "ノート", "草稿",
}
# 話題を表さない汎用語（KIND を含む）。
GENERIC = KIND | {
    "REPORT", "REPORTS", "PLAN", "FINAL", "BRIEF", "SPEC", "REVIEW", "RESULT", "RESULTS", "INDEX",
    "README", "APPENDIX", "CHECKLIST", "TABLE", "TABLES", "LOG", "SESSION", "DATA", "RAW", "SOURCE",
    "VERIFY", "VERIFICATION", "AUDIT", "TODO", "TASKS", "OVERVIEW", "DETAIL", "DETAILS", "FULL", "MAIN",
    "BODY", "TMP", "TEMP", "COPY", "OLD", "NEW", "QUOTE", "SCOPE", "THE", "AND", "FOR", "WITH", "FROM",
    "ABOUT", "AGENT", "AGENTS", "レポート", "本文", "SOURCES", "REFS", "REFERENCES", "EVIDENCE", "QUOTES",
    "SUMMARY", "ANALYSIS", "CLAUDE", "CHANGELOG", "CONTRIBUTING", "LICENSE", "SKILL",
}
_DATE = re.compile(r"(?<!\d)(?:20\d{2}[-_]?\d{2}[-_]?\d{2})(?!\d)")
_VER = re.compile(r"(?:^|[-_ .])v\d+(?=$|[-_ .])", re.I)
_ID = re.compile(r"(?:^|[-_ ])([A-Za-z]{1,4})[-_]?(\d{2,})(?=$|[-_ ])")
_SPLIT = re.compile(r"[^0-9A-Za-z\u3040-\u30ff\u3400-\u9fff]+")
# 文字種の切れ目で分ける（ナヴァル背景メモ → ナヴァル / 背景 / メモ）（#2・日本語名）
_RUNS = re.compile(r"[A-Za-z]+|\d+|[\u30a0-\u30ff]+|[\u3400-\u9fff]+|[\u3040-\u309f]+")
_JA_KIND = sorted((k for k in KIND if not k.isascii()), key=len, reverse=True)


def _stem(path):
    stem = unicodedata.normalize("NFKC", os.path.splitext(os.path.basename(path))[0])
    return _VER.sub(" ", _DATE.sub(" ", stem))


def numbers(path):
    """日付・版番号を除いたファイル名の中の数（issue-010 と issue-011 は別物）。"""
    return set(re.findall(r"\d+", _stem(path)))


def _raw_tokens(path):
    stem = _stem(path)
    for k in _JA_KIND:  # 区切りなしの日本語名から種別語を切り出す
        stem = stem.replace(k, " %s " % k)
    toks = set()
    for m in _ID.finditer(stem):  # nt-038 のような記事ID
        toks.add("#" + m.group(1).upper() + m.group(2))
    for part in _SPLIT.split(stem):
        for t in _RUNS.findall(part):
            u = t.upper()
            if u.isdigit():
                continue
            if u.isascii() and len(u) < 3:
                continue
            if not u.isascii() and len(u) < 2:
                continue
            toks.add(u)
    return toks


def topic_tokens(path):
    """ファイル名から話題の語の集合を返す。"""
    return {t for t in _raw_tokens(path) if t not in GENERIC}


def has_kind(path):
    return bool(_raw_tokens(path) & KIND)


def version_key(path):
    """日付・版番号・区切りを除いた (ディレクトリ, 名前)。同じなら同じ文書の版（-v2・日付版・.docx 版）で、
    版の扱いは命名規則と near_duplicate_guard / deprecation_guard の担当（較正）。"""
    return (os.path.dirname(path).lower(), re.sub(r"[\W_]+", "", _stem(path)).lower())


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


def _parallel_pairs(paths):
    """実体ごとの並列構造（output/<社名>/phase1.md）に当たる (a, b) の集合。
    同名ファイルが同じ親の下の兄弟ディレクトリに PARALLEL_MIN 個以上並ぶか、
    2つの兄弟ディレクトリが同名ファイルを PARALLEL_MIN 個以上共有するときだけ（#4）。"""
    by = {}
    for p in paths:
        d = os.path.dirname(p)
        by.setdefault((os.path.dirname(d), os.path.basename(p).lower()), []).append(p)
    shared = {}
    for ps in by.values():
        dirs = sorted(set(os.path.dirname(p) for p in ps))
        for i, x in enumerate(dirs):
            for y in dirs[i + 1:]:
                shared[(x, y)] = shared.get((x, y), 0) + 1
    out = set()
    for ps in by.values():
        if len(ps) < 2:
            continue
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                x, y = sorted((os.path.dirname(a), os.path.dirname(b)))
                if len(ps) >= PARALLEL_MIN or shared.get((x, y), 0) >= PARALLEL_MIN:
                    out.add((a, b))
                    out.add((b, a))
    return out


def find_groups(paths, threshold=CONTAIN_THRESHOLD, recent=()):
    """同じ話題の文書の群（2本以上、かつ paths の新規文書を1本以上含む）を返す。
    paths はこのコミットの新規文書、recent は直近 RECENT に同じリポへ追加された文書（リポ相対パス）。"""
    new = set(p.replace("\\", "/") for p in paths if is_doc(p))
    old = set(p.replace("\\", "/") for p in recent if is_doc(p)) - new
    allp = sorted(new | old)
    toks = {p: topic_tokens(p) for p in allp}
    kind = {p: has_kind(p) for p in allp}
    nums = {p: numbers(p) for p in allp}
    par = _parallel_pairs(allp)
    parent = {p: p for p in allp}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(allp):
        for b in allp[i + 1:]:
            if a in old and b in old:
                continue
            if (a, b) in par:
                continue
            if version_key(a) == version_key(b):
                continue
            if nums[a] and nums[b] and nums[a] != nums[b]:
                continue  # 両方に番号があって違えば別の対象（連番の issue・分冊・記事ID違いの DRAFT）（較正）
            if os.path.basename(a).lower() == os.path.basename(b).lower():
                da, db = numbers(os.path.dirname(a)), numbers(os.path.dirname(b))
                if da and db and da != db:
                    continue  # 同名ファイルが番号違いのディレクトリにある＝記事ごとの並列構造（_posts/nt-037/ と nt-038/）
            if kind[a] or kind[b]:
                # 中間メモの種別語を持つ側があれば、話題語を1つ共有するだけで同じ話題（#2）
                hit = bool(toks[a] & toks[b])
            else:
                hit = same_topic(toks[a], toks[b], threshold)
            if hit:
                parent[find(a)] = find(b)
    groups = {}
    for p in allp:
        groups.setdefault(find(p), []).append(p)
    return [sorted(g) for g in groups.values() if len(g) >= 2 and any(p in new for p in g)]


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
        # core.quotepath=off: 日本語のパスを 8進エスケープにしない（#5）
        r = subprocess.run(["git", "-c", "core.quotepath=off"] + args, cwd=root, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=15)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _lines(s):
    return [l.strip() for l in s.splitlines() if l.strip()]


_Q = r"[\"']?"
_GIT_PREFIX = (r"(?i:\bgit(?:\.exe)?)" + _Q +
               r"(?P<opts>(?:[\s\\`]+(?:-C[\s\\`]+(?:\"[^\"]*\"|'[^']*'|\S+)|-[^\s]+|[\w.]+=[^\s]*))*)[\s\\`]+" + _Q)
_COMMIT = re.compile(_GIT_PREFIX + r"commit\b" + _Q)
_ADD = re.compile(_GIT_PREFIX + r"(?:add|stage)\b" + _Q + r"(?P<args>[^;&|\n]*)")
_DASH_C = re.compile(r"-C[\s\\`]+(\"[^\"]*\"|'[^']*'|\S+)")
# commit より前の cd/pushd/Set-Location（#1）
_CD = re.compile(r"(?:^|[;&|\n(])\s*(?i:cd|pushd|set-location|sl|chdir)(?:\s+/d)?\s+(?:-(?:Path|LiteralPath)\s+)?"
                 r"(\"[^\"]*\"|'[^']*'|[^\s;&|)]+)")
TRAILER = re.compile(r"(?:^|\n|-m\s*[\"']?|\\n)\s*Topic-Split-Ok\s*:\s*(?P<r>[^\n\"'#]{%d,})" % MIN_REASON)
_MSGFILE = re.compile(r"(?:\s-F\s*|\s--file[=\s])(\"[^\"]*\"|'[^']*'|[^\s;&|]+)")


def _unq(s):
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'" else s


def _abspath(base, p):
    p = os.path.expandvars(os.path.expanduser(_unq(p)))
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", p):  # Git Bash の /c/Users/...
        p = p[1] + ":" + p[2:]
    return p if os.path.isabs(p) else os.path.join(base, p)


def effective_cwd(cmd, pos, base):
    """pos より前の cd/pushd/Set-Location を順に当てた作業ディレクトリ。"""
    d = base
    for m in _CD.finditer(cmd[:pos]):
        cand = _abspath(d, m.group(1))
        if os.path.isdir(cand):
            d = cand
    return d


def _root_for(m, cwd):
    d = cwd
    dm = _DASH_C.search(m.group("opts") or "")
    if dm:
        d = _abspath(cwd, dm.group(1))
    top = _git(d, ["rev-parse", "--show-toplevel"]).strip()
    return top or None


def added_by_git_add(root, cmd, commit_pos, cwd):
    """commit より前の git add の pathspec に当たる未追跡ファイル（リポ相対）。"""
    out = []
    untracked = tracked = None
    for m in _ADD.finditer(cmd):
        if m.start() > commit_pos:
            continue
        if untracked is None:
            untracked = _lines(_git(root, ["ls-files", "-o", "--exclude-standard"]))
            tracked = set(_lines(_git(root, ["ls-files"])))
        here = effective_cwd(cmd, m.start(), cwd)
        dm = _DASH_C.search(m.group("opts") or "")
        if dm:
            here = _abspath(here, dm.group(1))
        specs = [_unq(a) for a in m.group("args").split() if a]
        everything = any(s in (".", "-A", "--all", ":/", "*") for s in specs)
        files = [s for s in specs if not s.startswith("-")]
        for s in files:  # git add -f <ignored file> も拾う（明示されたファイル）
            full = os.path.normpath(_abspath(here, s))
            rel = os.path.relpath(full, root).replace("\\", "/")
            if os.path.isfile(full) and rel not in tracked:
                out.append(rel)
        for u in untracked:
            if everything:
                out.append(u)
                continue
            for s in files:
                full = os.path.normpath(_abspath(here, s))
                rel = os.path.relpath(full, root).replace("\\", "/")
                if rel == u or u.startswith(rel.rstrip("/") + "/") or fnmatch.fnmatchcase(u, rel):
                    out.append(u)
                    break
    return out


def new_docs(root, cmd, commit_pos, cwd):
    staged = _lines(_git(root, ["diff", "--cached", "--name-only", "--no-renames", "--diff-filter=A"]))
    return sorted(set(staged) | set(added_by_git_add(root, cmd, commit_pos, cwd)))


def recent_docs(root, since=RECENT):
    """直近に同じリポで新規追加され、今も残っている文書（#3）。"""
    out = _lines(_git(root, ["log", "--since=" + since, "--no-renames", "--diff-filter=A",
                             "--name-only", "--format="]))
    return sorted(set(p for p in out if os.path.isfile(os.path.join(root, p))))


def trailer_reason(cmd, commit_pos, cwd):
    """Topic-Split-Ok の理由（コマンド内の -m、または -F/--file のファイル内）（#7）。"""
    seg = cmd[commit_pos:]
    texts = [seg]
    fm = _MSGFILE.search(seg)
    if fm:
        try:
            with open(_abspath(cwd, fm.group(1)), encoding="utf-8", errors="replace") as f:
                texts.append(f.read())
        except Exception:
            pass
    for t in texts:
        for m in TRAILER.finditer(t):
            r = m.group("r").strip()
            if len(set(r.replace(" ", ""))) >= 5:  # 「xxxxxxxxxx」のような無意味な理由は認めない
                return r
    return None


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
    base = payload.get("cwd") or os.getcwd()
    cwd = effective_cwd(cmd, m.start(), base)
    root = _root_for(m, cwd)
    if not root:
        return 0
    docs = new_docs(root, cmd, m.start(), cwd)
    if not any(is_doc(p) for p in docs):
        return 0
    globs, bad = load_allow(root)
    cand = [p for p in docs if not allowed(p, globs)]
    recent = [p for p in recent_docs(root) if not allowed(p, globs)]
    groups = find_groups(cand, recent=recent)
    if not groups:
        return 0
    reason = trailer_reason(cmd, m.start(), cwd)
    if reason:
        _record_fired(NAME, {"allowed_by_trailer": reason, "groups": groups, "root": root})
        return 0
    _record_fired(NAME, payload)
    lines = ["topic_split_guard: 同じ話題の文書ファイルが、このコミット（と直近24時間のコミット）で2本以上新しく追加されます（コミットを止めました）。",
             "読み手と AI が正本を取り違えるため、1つの依頼の文書は本体1本にまとめます。", ""]
    for g in groups:
        lines.append("同じ話題の新規文書:")
        lines += ["  - %s%s" % (p, "" if p in cand else "（直近のコミットで追加済み）") for p in g]
    lines += ["",
              "対処:",
              "  1. 本体1本に統合する（背景ノート・観点表・調査メモ・下書きの中身は本体の節か巻末へ移す）。",
              "  2. 中間メモはリポに置かず OS の一時フォルダへ（PowerShell: $env:TEMP / Git Bash: /tmp）。すでにコミットしたものは git rm で消す。",
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
