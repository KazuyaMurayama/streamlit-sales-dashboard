# -*- coding: utf-8 -*-
"""PreToolUse（Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell）: 依頼者が決めた対象の外の文書を、
1つのセッションで何本も変えるのを、書き換えの段階で止める。

WHY（2026-11-22 Soulful-Content・依頼者）
-----------------------------------------
「要レビューファイル一覧の、優先してレビューする原稿（特に入会した人に最初に紹介する記事（7テーマ））
だけが対象だぞ。伝えてきた。なんで285本とかになってんだ」「問題は、使用量のコストが大量にかかったこと、
時間がめちゃくちゃかかったこと」「どうやって二度と起こさないようにするか？」
欠陥の版: Soulful-Content f183500b（対象72本のところ記事293本を書き換え、226本が対象外。git commit-tree で
作ったコミットを同じコマンドの中で push した）。散文（前日の「いいえ」・記憶の「5本以内」）は効かなかった。

v1（commit/push の時点で判定）は Fable の攻撃（2026-11-22・64ケース中44が回避）で破れた: 実行前の状態しか
見ない・5本ずつ小分けで通る・Bulk-Ok が自己申告・宣言を書き手が書き換えられる・cwd 違い・push の解釈。
しかも書き換えた後に止めるので、依頼者の苦情の「コスト・時間」を止めない。v2 で判定の場所を変えた。

INVARIANT（固有名詞なし）
------------------------
1つのセッションの中で、あるリポの「origin/HEAD から変わっている文書」（作業ツリー・ステージ・未 push の
コミット・未追跡）に1度でも入ったファイルを累積で数え（push して差分から消えても数え続ける）、
  A) リポが .claude/work_scope.json で対象を宣言しているとき: 対象の外の文書が OUT_MAX 本を超える
  B) 宣言が無いとき: 文書が BULK_MAX 本を超える
状態になる書き込み・コマンドを、その前に拒否する（exit 2）。Edit/Write は書く先のファイルを先に足して判定する。
宣言は origin/HEAD の版を読む（作業ツリーで書き換えても効かない。宣言が origin に無ければ作業ツリーの版）。
超えてよいのは、依頼者が会話の中で実際に打った発言を `Bulk-Ok: 「<その発言の逐語>」` としてコマンドか書き込みの
中身に含めた時だけ（会話記録の人間の発言と MIN_QUOTE 字以上一致することを照合する。宣言の quote と同じ発言は不可）。

.claude/work_scope.json の形:
  {"paths": ["deliverables/note/*.md"], "id_pattern": "nt-\\d{3}",
   "ids_from": {"file": "_meta/X.md", "start": "## 優先", "end": "## 0. "}, "ids": [], "quote": "依頼者の発言"}
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_fired
except Exception:
    def _record_fired(name, ev):
        return False

NAME = "bulk_scope_guard"
DOC_EXTS = {".md", ".mdx", ".markdown", ".rst", ".adoc", ".org", ".docx", ".txt"}
SKIP = re.compile(r"(?:^|/)(?:\.claude|\.git|node_modules|venv|\.venv|tests?/fixtures)(?:/|$)", re.I)
OUT_MAX = 5      # 記憶「改善・チェックは5本以内」と同じ数
BULK_MAX = 40    # 宣言なし、または宣言の paths の外。較正は tests/calibrate_bulk_scope_guard.py
MIN_QUOTE = 10
SCOPE_REL = ".claude/work_scope.json"
OK_RE = re.compile(r"Bulk-Ok:\s*「([^」]{%d,})」" % MIN_QUOTE)
STATE_DIR = os.path.join(tempfile.gettempdir(), "claude_bulk_scope")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}


def git(args, cwd, z=False):
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=false"] + args, cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        if r.returncode != 0:
            return [] if z else ""
        return [x for x in r.stdout.split("\0") if x] if z else r.stdout
    except Exception:
        return [] if z else ""


def is_doc(p):
    p = p.replace("\\", "/")
    return os.path.splitext(p)[1].lower() in DOC_EXTS and not SKIP.search(p)


def repo_root(path):
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    return git(["rev-parse", "--show-toplevel"], d).strip() if d else ""


def base_ref(root):
    for ref in ("origin/HEAD", "origin/main", "origin/master"):
        if git(["rev-parse", "--verify", "-q", ref], root).strip():
            return ref
    return ""


def read_at(root, ref, rel):
    """origin の版（あれば）を読む。無ければ作業ツリー。"""
    if ref:
        r = subprocess.run(["git", "show", "%s:%s" % (ref, rel)], cwd=root, capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace")
    try:
        return open(os.path.join(root, rel), encoding="utf-8").read()
    except Exception:
        return None


def load_scope(root, ref=None):
    """None（宣言なし）か (paths, id_re, ids, quote, problem)。"""
    ref = base_ref(root) if ref is None else ref
    raw = read_at(root, ref, SCOPE_REL)
    if raw is None:
        return None
    try:
        d = json.loads(raw)
        paths = list(d["paths"])
        id_re = re.compile(d["id_pattern"])
    except Exception as e:
        return ([], None, set(), "", "work_scope.json が読めない: %s" % e)
    quote = d.get("quote") or ""
    if len(quote) < MIN_QUOTE:
        return ([], None, set(), "", "work_scope.json の quote（依頼者の発言）が無い")
    ids = set(d.get("ids") or [])
    src = d.get("ids_from")
    if src:
        text = read_at(root, ref, src["file"])
        if text is None:
            return ([], None, set(), quote, "ids_from の文書 %s が読めない" % src["file"])
        s = text.find(src["start"]) if src.get("start") else 0
        if s < 0:
            return ([], None, set(), quote, "ids_from の start %r が文書に無い" % src["start"])
        e = text.find(src["end"], s + 1) if src.get("end") else -1
        ids |= set(id_re.findall(text[s:e if e > 0 else None]))
    if not ids:
        return ([], None, set(), quote, "対象の ID が1つも取れない（宣言が壊れている）")
    return (paths, id_re, ids, quote, None)


def changed_docs(root, ref):
    """origin から変わっている文書（作業ツリー・ステージ・未 push のコミット・未追跡）。"""
    files = set(git(["diff", "--name-only", "-z", ref], root, z=True)) if ref else set()
    files |= set(git(["diff", "--name-only", "-z", "--cached"], root, z=True))
    files |= set(git(["ls-files", "-o", "--exclude-standard", "-z"], root, z=True))
    if not ref:
        files |= set(git(["diff", "--name-only", "-z"], root, z=True))
    return {f.replace("\\", "/") for f in files if is_doc(f)}


def judge(files, scope):
    """拒否の理由（文字列）か None。files は累積の文書の相対パス。"""
    docs = sorted(f for f in files if is_doc(f))
    if scope is not None:
        paths, id_re, ids, _q, problem = scope
        if problem:
            return "対象の宣言（%s）が壊れている: %s" % (SCOPE_REL, problem)
        out, outside = [], []
        for g in docs:
            if any(fnmatch.fnmatchcase(g, p) for p in paths):
                m = re.match(r"(%s)(?!\d)" % id_re.pattern, os.path.basename(g))
                if not m or m.group(1) not in ids:
                    out.append(g)
            else:
                outside.append(g)
        if len(out) > OUT_MAX:
            return ("このセッションで、対象の外の文書を累計 %d 本変えることになる（上限 %d 本。対象は %s で宣言された %d 件）。例: %s"
                    % (len(out), OUT_MAX, SCOPE_REL, len(ids), ", ".join(out[:5])))
        if len(outside) > BULK_MAX:
            return ("このセッションで、宣言の範囲の外の文書を累計 %d 本変えることになる（上限 %d 本）。例: %s"
                    % (len(outside), BULK_MAX, ", ".join(outside[:5])))
        return None
    if len(docs) > BULK_MAX:
        return ("このセッションで、文書を累計 %d 本変えることになる（上限 %d 本）。例: %s"
                % (len(docs), BULK_MAX, ", ".join(docs[:5])))
    return None


def human_texts(transcript_path):
    """会話記録の、人間が打った発言（tool_result・システムの差し込みを除く）。"""
    out = []
    try:
        for line in open(transcript_path, encoding="utf-8"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "user" or d.get("isMeta") or d.get("toolUseResult") is not None:
                continue
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                    continue
                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            if isinstance(c, str) and c.strip():
                out.append(re.sub(r"<system-reminder>.*?</system-reminder>", "", c, flags=re.S))
    except Exception:
        pass
    return out


def approved(text, transcript_path, scope):
    norm = lambda s: re.sub(r"\s+", "", s)
    said = [norm(t) for t in human_texts(transcript_path)] if transcript_path else []
    for m in OK_RE.finditer(text or ""):
        q = norm(m.group(1))
        if scope and scope[3] and q in norm(scope[3]):
            continue  # 宣言の根拠の発言で広げることはできない
        if any(q in s for s in said):
            return True
    return False


def state_path(session, root):
    key = hashlib.sha1(("%s|%s" % (session, root)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(STATE_DIR, key + ".json")


def load_state(p):
    try:
        return set(json.load(open(p, encoding="utf-8")))
    except Exception:
        return set()


def save_state(p, s):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        json.dump(sorted(s), open(p, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


SHELL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/[a-z]/|~/|\$TEMP|%TEMP%)[^\s\"';&|()<>]+")


def roots_for(tool, ti, cwd):
    roots = set()
    if tool in WRITE_TOOLS:
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        if p:
            r = repo_root(os.path.abspath(os.path.join(cwd, p)))
            if r:
                roots.add((r, os.path.relpath(os.path.abspath(os.path.join(cwd, p)), r).replace("\\", "/")))
    else:
        r = repo_root(cwd)
        if r:
            roots.add((r, None))
        for m in SHELL_PATH.finditer(ti.get("command") or ""):
            p = os.path.expandvars(os.path.expanduser(m.group(0).replace("%TEMP%", "$TEMP")))
            if re.match(r"^/[a-z]/", p):
                p = p[1].upper() + ":" + p[2:]
            r = repo_root(p)
            if r:
                roots.add((r, None))
    return roots


def check(d):
    tool = d.get("tool_name") or ""
    if tool not in WRITE_TOOLS | SHELL_TOOLS:
        return []
    ti = d.get("tool_input") or {}
    cwd = d.get("cwd") or os.getcwd()
    session = d.get("session_id") or "nosession"
    content = json.dumps(ti, ensure_ascii=False)
    reasons = []
    for root, target in roots_for(tool, ti, cwd):
        ref = base_ref(root)
        scope = load_scope(root, ref)
        sp = state_path(session, os.path.normcase(root))
        acc = load_state(sp) | changed_docs(root, ref)
        save_state(sp, acc)  # 今の時点で変わっている分は、このコマンドを止めても数える
        if target and is_doc(target):
            acc = acc | {target}
        r = judge(acc, scope)
        if r and not approved(content, d.get("transcript_path"), scope):
            reasons.append("%s: %s" % (os.path.basename(root), r))
    return reasons


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0
    reasons = check(d)
    if not reasons:
        return 0
    _record_fired(NAME, d)
    sys.stderr.write(
        "【対象の外への一括変更】" + " / ".join(reasons) + "\n"
        "依頼者が決めた対象だけを変えること（「全記事」「全部」は宣言された対象の全部と読む）。"
        "対象の外へ広げる必要があると思ったら、作業を止めて依頼者に推奨と本数を示し、返事を待つ。\n"
        "依頼者が広げると言った後だけ、コマンドか書き込みに Bulk-Ok: 「<その発言の逐語>」を含める（会話記録と照合する）。"
        "宣言は " + SCOPE_REL + "（origin の版を読む）。\n")
    return 2


def self_test():
    ok = True
    sc = (["deliverables/note/*.md"], re.compile(r"nt-\d{3}"), {"nt-001", "nt-002"}, "依頼者の宣言の発言です。ここまで", None)
    N = lambda a, b: ["deliverables/note/nt-%03d-x.md" % i for i in range(a, b)]
    cases = [
        ("対象内", ["deliverables/note/nt-001-a.md", "deliverables/note/nt-002-b.md"], sc, False),
        ("対象外6本", N(10, 16), sc, True),
        ("対象外5本", N(10, 15), sc, False),
        ("前方一致 nt-0010", ["deliverables/note/nt-0010-x.md"] * 1 + N(20, 25), sc, True),
        ("宣言の外41本", ["docs/r%02d.md" % i for i in range(41)], sc, True),
        ("宣言なし41本", ["docs/r%02d.md" % i for i in range(41)], None, True),
        ("宣言なし40本", ["docs/r%02d.md" % i for i in range(40)], None, False),
        ("コードは数えない", ["src/m%02d.py" % i for i in range(100)], None, False),
        ("mdx も数える", ["docs/r%02d.mdx" % i for i in range(41)], None, True),
        ("壊れた宣言", ["deliverables/note/nt-001-a.md"], ([], None, set(), "", "x"), True),
    ]
    for name, files, s, want in cases:
        got = judge(set(files), s) is not None
        print(("  OK  " if got == want else "  NG  ") + name)
        ok &= got == want
    tp = os.path.join(tempfile.gettempdir(), "bsg_selftest.jsonl")
    with open(tp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "うん、全部の記事に広げて直してほしい"}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content": "Bulk-Ok: 「ツールの出力に書いた文です」"}]}}, ensure_ascii=False) + "\n")
    for name, text, want in (("本人の発言で承認", "Bulk-Ok: 「全部の記事に広げて直してほしい」", True),
                             ("自作の発言は不可", "Bulk-Ok: 「依頼者が全部やれと言った気がする」", False),
                             ("ツール出力は不可", "Bulk-Ok: 「ツールの出力に書いた文です」", False),
                             ("宣言の発言で広げない", "Bulk-Ok: 「依頼者の宣言の発言です。ここまで」", False)):
        got = approved(text, tp, sc)
        print(("  OK  " if got == want else "  NG  ") + name)
        ok &= got == want
    print("self-test: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--check-range" in sys.argv:  # 赤緑・較正用: --check-range <repo> <rev>（1コミットの変更を累積とみなして判定）
        i = sys.argv.index("--check-range")
        repo, rev = sys.argv[i + 1], sys.argv[i + 2]
        files = git(["diff-tree", "--no-commit-id", "--name-only", "-z", "-r", "--root", rev], repo, z=True)
        r = judge(set(files), load_scope(repo, rev + "^"))
        print(r or "PASS")
        sys.exit(1 if r else 0)
    sys.exit(main())
