# -*- coding: utf-8 -*-
"""レポートの更新版で、前の版の節・表・表の列を黙って削らせない（PreToolUse: Write/Edit/MultiEdit と git commit）。

WHY（2026-10-19 依頼者指摘）
    NASDAQ_backtest の COVER_BEST_LATEST_20261019.md（commit 69830f1）は、前の版
    COVER_MIN3_BEST_20260824.md（v2）の後継として書かれたが、v2 の H2/H3 見出し 25 本のうち 0.1b
    （分布表）・3.4（感度表）・6.1〜6.4（頑健性）など大半を落とし、7 本だけで書き直した。依頼者:
    「v2 から、勝手に大幅にフォーマット削るな。何かの理由で削るべきものだけ削れ」「レポートの更新版で、
    フォーマットを勝手に削るべきではない。削るべきものがあれば、ユーザーに推奨するべき」。

不変条件（固有名では塞がない）
    「レポートの新しい版は、前の版にあった見出し（H2/H3）・表・表の列を、依頼者の承認なしに落としてはならない」
    前の版 = ①同じファイルの直前の内容（git の HEAD。未追跡ならディスク上の内容）
             ②本文の冒頭 15 行で版の語（前版・旧版・v2・更新版・後継・改訂・置き換え・からの遷移 等）の直後に
               リンクされた .md レポート
             ③同じディレクトリで、日付・-vN を除いたファイル名が同じで、日付（と版番号）が古いレポート
             ④同じディレクトリのレポートで、1 行目の廃盤印の「後継:」がこのファイルを指すもの
    落とした = 前の版の見出しに、新しい版のどの見出しも似ていない（番号・括弧書き・記号を除いた文字の
               2 文字組の Dice 係数 0.5 未満、かつ片方がもう片方を含まない）。
    レポート = .md で、ファイル名に _YYYYMMDD がある・CURRENT_*.md・冒頭 15 行に作成日/最終更新日がある、の
               どれか。README/CLAUDE/AGENTS/tasks/CHANGELOG/FILE_INDEX と .claude/ .codex/ 配下は外す。

発火（較正で決めた。下記）
    見出し: 承認されていない欠落が MIN_HEAD 本以上
    表:     前の版の表が MIN_TABLES 個以上あり、新しい版の表の数が TABLE_RATIO 倍未満に減った
    列:     対応する節の中の表が 2 列以上狭くなった（MIN_NARROW 個以上）

承認（理由だけでは通さない。依頼者の発言の引用が要る）
    本文に `<!-- format-drop: 削る対象（見出し名・列名・「表」）を列挙 承認「依頼者の発言の引用」 -->`
    引用は、このセッションの transcript の依頼者の発言（ハーネスが書いた行・会話の要約を除く）に含まれる
    ことを確かめる。transcript を読めないときは通して記録する。対象に名前のある見出し・列だけが許される
    （古い印が後の別の削除を素通りさせない）。git commit では、コミットメッセージの
    `Format-Drop-Ok: <対象> 承認「引用」` でもよい。

止め方
    exit 2 + stderr。メッセージは「戻す」か「依頼者に削除を推奨して承認を得る」の2択を示す。

較正（実測）
    tests/calibrate_report_format_guard.py の結果を下に記す（未記入のまま配布しない）。
"""
import io
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

NAME = "report_format_guard"
MIN_HEAD = 2          # 較正で決定（docstring）
MIN_TABLES = 3
TABLE_RATIO = 0.7
MIN_SEC_TABLES = 2    # 対応する節の中で減った表の数
MIN_NARROW = 1       # 2 列以上狭くなった表の数
SIM = 0.5
HEAD_LINES = 15

NOT_REPORT = re.compile(r"^(?:readme|claude|agents|tasks|todo|changelog|file_index|memory|license|spec|index)(?:[._-].*)?\.md$", re.I)
EXCLUDED_DIR = re.compile(r"(?:^|/)(?:\.claude|\.codex|\.git|node_modules|tests?/fixtures)/", re.I)
DATE_NAME = re.compile(r"_(20\d{6})(?:-v(\d+))?\.md$", re.I)
STAMP = re.compile(r"^\s*(?:\*\*)?(?:作成日|最終更新日|更新日)")
VERSION_WORD = re.compile(r"(?:前版|旧版|前の版|前回版|前回の|直前の版|更新版|改訂|後継|置き換え|置換|からの遷移|から更新|を更新"
                          r"|\bv\d+\b|第\d+版|previous|supersed|replaces)", re.I)
LINK = re.compile(r"\[[^\]]*\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")
DEPRECATED = re.compile(r"廃盤|deprecated", re.I)
MARK = re.compile(r"<!--\s*format-drop\s*[:：](?P<body>.*?)-->", re.S | re.I)
TRAILER = re.compile(r"Format-Drop-Ok\s*[:：](?P<body>[^\n]*?「[^」]+」[^\n]*)", re.I)
APPROVAL = re.compile(r"承認\s*[「『\"](?P<q>[^」』\"]{4,})[」』\"]")


# ---------------------------------------------------------------- structure

def _strip_code(text):
    return re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$", "", text or "")


def norm(s):
    s = re.sub(r"<!--.*?-->", "", s or "", flags=re.S)
    s = re.sub(r"[（(][^（）()]*[）)]", "", s)                     # 括弧書きは注記
    s = re.sub(r"[*_`~\[\]]|\]\([^)]*\)", "", s)
    s = re.sub(r"^\s*(?:§|第)?\s*[0-9０-９]+(?:[.．\-][0-9０-９a-z]+)*[.．)）章節]?\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*[A-Za-z][.)]\s+", "", s)
    return re.sub(r"[\s\W_]+", "", s).lower()


def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def sim(a, b):
    if not a or not b:
        return 0.0
    if (len(a) >= 2 and a in b) or (len(b) >= 2 and b in a):
        return 1.0
    x, y = _bigrams(a), _bigrams(b)
    return 2.0 * len(x & y) / (len(x) + len(y))


_NUM = re.compile(r"^\s*(?:§|第)?\s*([0-9０-９]+(?:[.．][0-9０-９a-z]+)*)", re.I)
_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def structure(text):
    """(見出し [(level, raw, norm, 番号)], 表 [(属する見出しの添字, 見出しセル)])。H2/H3 のみ。"""
    lines = _strip_code(text).splitlines()
    hs, ts, cur = [], [], -1
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{2,3})\s+(.*?)\s*#*\s*$", ln)
        if m and norm(m.group(2)):
            nm = _NUM.match(m.group(2))
            hs.append((len(m.group(1)), m.group(2).strip(), norm(m.group(2)), nm.group(1) if nm else None))
            cur = len(hs) - 1
            continue
        a = ln.strip()
        if a.startswith("|") and i + 1 < len(lines) and _SEP.match(lines[i + 1].strip()) \
                and not (i > 0 and lines[i - 1].strip().startswith("|")):
            ts.append((cur, [c.strip() for c in a.strip("|").split("|")]))
    return hs, ts


def headings(text):
    return [h[:3] for h in structure(text)[0]]


def tables(text):
    return [t[1] for t in structure(text)[1]]


def match_headings(oh, nh):
    """前の版の見出し → 新しい版の見出し（1対1）。文字の類似で割り当て、残りは同じ番号・同じ階層で割り当てる
    （節の名前を言い換えただけの 「10. QCチェック」→「10. 品質の確認」 を落としたと数えない）。"""
    pairs = []
    for i, o in enumerate(oh):
        for j, n in enumerate(nh):
            v = sim(o[2], n[2])
            if v >= SIM:
                pairs.append((-v, abs(i / max(1, len(oh)) - j / max(1, len(nh))), i, j))
    pairs.sort()
    mo, mn = {}, set()
    for _v, _d, i, j in pairs:
        if i not in mo and j not in mn:
            mo[i] = j
            mn.add(j)
    for i, o in enumerate(oh):
        if i in mo or not o[3]:
            continue
        for j, n in enumerate(nh):
            if j not in mn and n[3] == o[3] and n[0] == o[0]:
                mo[i] = j
                mn.add(j)
                break
    return mo


# ---------------------------------------------------------------- compare

def _marks(text, extra=""):
    """[(対象の文字列, 引用)]"""
    out = []
    for body in [m.group("body") for m in MARK.finditer(text or "")] + [m.group("body") for m in TRAILER.finditer(extra or "")]:
        q = APPROVAL.search(body)
        target = APPROVAL.sub("", body)
        out.append((target, q.group("q").strip() if q else None))
    return out


def _excused(name_norm, marks, approved):
    for target, q in marks:
        if q is None or q not in approved:
            continue
        parts = [norm(p) for p in re.split(r"[、,/／・;；\n]|\s{2,}", target)]
        tn = norm(target)
        if (name_norm and name_norm in tn) or any(sim(name_norm, p) >= SIM for p in parts if p):
            return True
    return False


def compare(old, new, marks=(), approved=()):
    """前の版 old → 新しい版 new で、承認されていない欠落を返す。
    headings: 落ちた見出し / tables: (前の表の数, 新しい表の数)（全体で TABLE_RATIO 倍未満、または対応する節の中で
    MIN_SEC_TABLES 個以上減った） / columns: 対応する節の中で 2 列以上狭くなった表（前の列の見出し）。"""
    approved = set(approved)
    oh, ot = structure(old)
    nh, nt = structure(new)
    mo = match_headings(oh, nh)
    missing = [o[1] for i, o in enumerate(oh) if i not in mo and not _excused(o[2], marks, approved)]
    mo[-1] = -1
    sec_lost, narrowed = 0, []
    for i, j in mo.items():
        ow = sorted((len(c) for s, c in ot if s == i), reverse=True)
        nw = sorted((len(c) for s, c in nt if s == j), reverse=True)
        sec_lost += max(0, len(ow) - len(nw))
        for k, w in enumerate(ow[:len(nw)]):
            if w - nw[k] >= 2:
                cells = next(c for s, c in ot if s == i and len(c) == w)
                narrowed.append(" | ".join(cells))
    tbl = None
    if (len(ot) >= MIN_TABLES and len(nt) < TABLE_RATIO * len(ot)) or sec_lost >= MIN_SEC_TABLES:
        if not _excused(norm("表"), marks, approved):
            tbl = (len(ot), len(nt))
    if narrowed and _excused(norm("列"), marks, approved):
        narrowed = []
    return {"headings": missing, "tables": tbl, "columns": narrowed,
            "fire": len(missing) >= MIN_HEAD or tbl is not None or len(narrowed) >= MIN_NARROW,
            "n_old_headings": len(oh), "sec_tables_lost": sec_lost}


# ---------------------------------------------------------------- reports and predecessors

def is_report(path, text=None):
    p = (path or "").replace("\\", "/")
    base = os.path.basename(p)
    if not base.lower().endswith(".md") or NOT_REPORT.match(base) or EXCLUDED_DIR.search("/" + p):
        return False
    if DATE_NAME.search(base) or base.upper().startswith("CURRENT_"):
        return True
    if text is None:
        text = _read(path) or ""
    return any(STAMP.match(ln) for ln in (text or "").splitlines()[:HEAD_LINES])


def _read(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def _first_line(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return f.readline()
    except Exception:
        return ""


def _key(base):
    m = DATE_NAME.search(base)
    if not m:
        return None, None
    stem = base[:m.start()].lower()
    return stem, (m.group(1), int(m.group(2) or 1))


def predecessors(path, text, exists=os.path.isfile, read=_read, listdir=os.listdir, first_line=None):
    """宣言された・名前から分かる前の版のパス（絶対）。"""
    d = os.path.dirname(os.path.abspath(path))
    me = os.path.normcase(os.path.abspath(path))
    out = []
    for ln in (text or "").splitlines()[:HEAD_LINES]:
        prev_end = 0
        for m in LINK.finditer(ln):
            # 版の語はこのリンクと同じ文の中（前のリンク・句点より後、リンクの直後は次の句読点まで）にあること
            before = re.split(r"[。．!！?？]", ln[prev_end:m.start()])[-1][-40:]
            after = re.split(r"[。．、,!！?？\[]", ln[m.end():])[0][:12]
            prev_end = m.end()
            if not VERSION_WORD.search(before + " " + after) or re.match(r"^[a-z]+:", m.group(1), re.I):
                continue
            cand = os.path.normpath(os.path.join(d, m.group(1)))
            if os.path.normcase(cand) != me and exists(cand) and is_report(cand, read(cand) or ""):
                out.append(cand)
    base = os.path.basename(path)
    stem, ver = _key(base)
    try:
        names = listdir(d)
    except Exception:
        names = []
    best = None
    for nm in names:
        if not nm.lower().endswith(".md") or nm == base:
            continue
        full = os.path.join(d, nm)
        s2, v2 = _key(nm)
        if stem and s2 == stem and v2 < ver and (best is None or v2 > best[0]):
            best = (v2, full)
        first = (first_line or _first_line)(full)
        if DEPRECATED.search(first) and re.search(r"後継[^\n]*" + re.escape(base), first):
            out.append(full)
    if best:
        out.append(best[1])
    seen, res = set(), []
    for p in out:
        k = os.path.normcase(p)
        if k not in seen:
            seen.add(k)
            res.append(p)
    return res


# ---------------------------------------------------------------- approval

def user_texts(transcript_path):
    """依頼者が打った発言（ハーネス行・会話の要約を除く）。読めなければ None。"""
    if not transcript_path:
        return None
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return None
    try:
        import turn_classify as _tc
    except Exception:
        _tc = None
    out = []
    for ln in lines:
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
            continue
        if (r.get("origin") or {}).get("kind") in ("peer", "task-notification"):
            continue
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                continue
            c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
        if not isinstance(c, str):
            continue
        c = re.sub(r"<system-reminder>.*?</system-reminder>", "", c, flags=re.S)
        if _tc is not None:
            c = _tc.strip_wrappers(c)
        out.append(c)
    return out


def approved_quotes(marks, transcript_path):
    qs = [q for _t, q in marks if q]
    if not qs:
        return set()
    texts = user_texts(transcript_path)
    if texts is None:
        return set(qs)               # transcript を読めない: 通して記録する
    flat = re.sub(r"\s+", "", "\n".join(texts))
    return {q for q in qs if re.sub(r"\s+", "", q) in flat}


# ---------------------------------------------------------------- git helpers

def _git(root, args):
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off"] + args, cwd=root, capture_output=True, timeout=20)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
    except Exception:
        return ""


def _toplevel(path):
    d = os.path.dirname(os.path.abspath(path))
    return _git(d, ["rev-parse", "--show-toplevel"]).strip() if os.path.isdir(d) else ""


def head_version(path):
    root = _toplevel(path)
    if not root:
        return None
    rel = os.path.relpath(os.path.abspath(path), root).replace("\\", "/")
    if not _git(root, ["ls-files", "--", rel]).strip():
        return None
    out = _git(root, ["show", "HEAD:" + rel])
    return out or None


# ---------------------------------------------------------------- checks

def check(path, new, transcript_path=None, extra_marks="", baselines=None):
    """path の新しい内容 new を前の版と比べる。[(前の版のラベル, compare の結果)] のうち発火したもの。"""
    if not is_report(path, new):
        return []
    if baselines is None:
        baselines = []
        cur = head_version(path)
        if cur is None:
            cur = _read(path)
        if cur is not None:
            baselines.append(("この文書の直前の版", cur))
        for p in predecessors(path, new):
            t = _read(p)
            if t:
                baselines.append((os.path.basename(p), t))
    marks = _marks(new, extra_marks)
    approved = approved_quotes(marks, transcript_path) if marks else set()
    fired = []
    for label, old in baselines:
        r = compare(old, new, marks, approved)
        if r["fire"]:
            fired.append((label, r))
    return fired


def _apply_edits(cur, edits):
    s = cur
    for e in edits:
        o, n = e.get("old_string", ""), e.get("new_string", "")
        if not o or o not in s:
            return None
        s = s.replace(o, n) if e.get("replace_all") else s.replace(o, n, 1)
    return s


def new_content(payload):
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ""
    tool = payload.get("tool_name")
    if tool == "Write":
        return path, ti.get("content")
    cur = _read(path)
    if cur is None:
        return path, None
    if tool == "Edit":
        return path, _apply_edits(cur, [ti])
    if tool == "MultiEdit":
        return path, _apply_edits(cur, ti.get("edits") or [])
    return path, None


def message(path, fired):
    lines = ["report_format_guard: レポートの新しい版が、前の版の見出し・表・列を承認なしに落としています（書き込みを止めました）。",
             "対象: " + path.replace("\\", "/"), ""]
    for label, r in fired:
        lines.append("前の版: " + label)
        if r["headings"]:
            lines.append("  落ちた見出し（%d/%d）: %s" % (len(r["headings"]), r["n_old_headings"], " / ".join(r["headings"][:20])))
        if r["tables"]:
            lines.append("  表の数: %d → %d" % r["tables"])
        if r["columns"]:
            lines.append("  2列以上狭くなった表（前の版の見出し行）: " + " ／ ".join(r["columns"][:10]))
    lines += ["",
              "対処（どちらか）:",
              "  1. 前の版の節・表・列を残す（数値は今の条件で埋め直す。埋められないものは「未計算」と書いて節は残す）。",
              "  2. 削るべき理由があるものは、依頼者に「何を・なぜ削るか」を推奨として示し、承認を得る。承認後に本文へ",
              "     `<!-- format-drop: 削る見出し名・列名（表ごと減らすなら「表」）承認「依頼者の発言をそのまま引用」 -->` を書く",
              "     （引用は transcript の依頼者の発言と照合する。対象に名前のあるものだけが通る）。"]
    return "\n".join(lines) + "\n"


def on_file_tool(payload):
    path, new = new_content(payload)
    if not path or new is None:
        return 0
    fired = check(path, new, payload.get("transcript_path"))
    if not fired:
        return 0
    _record_fired(NAME, {"session_id": payload.get("session_id"), "path": path,
                         "fired": [(l, r["headings"][:10], r["tables"], r["columns"][:10]) for l, r in fired]})
    sys.stderr.write(message(path, fired))
    return 2


# ---------------------------------------------------------------- git commit

def on_commit(payload):
    try:
        import topic_split_guard as T
    except Exception:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    m = T._COMMIT.search(cmd)
    if not m:
        return 0
    base = payload.get("cwd") or os.getcwd()
    cwd = T.effective_cwd(cmd, m.start(), base)
    root = T._root_for(m, cwd)
    if not root:
        return 0
    seg = cmd[m.start():]
    adds = [a for a in T._ADD.finditer(cmd) if a.start() < m.start()]
    commit_all = re.search(r"(?:^|\s)-(?:[a-zA-Z]*a[a-zA-Z]*)\b|--all\b", seg.split("\n")[0]) is not None
    worktree = set()
    if adds or commit_all:
        mod = T._lines(_git(root, ["diff", "--name-only"]))
        unt = T._lines(_git(root, ["ls-files", "-o", "--exclude-standard"]))
        if commit_all:
            worktree |= set(mod)
        for a in adds:
            here = T.effective_cwd(cmd, a.start(), cwd)
            specs = [T._unq(x) for x in a.group("args").split() if x]
            if any(s in (".", "-A", "--all", ":/", "*", "-u") for s in specs):
                worktree |= set(mod) | set(unt)
                continue
            for s in specs:
                if s.startswith("-"):
                    continue
                rel = os.path.relpath(os.path.normpath(T._abspath(here, s)), root).replace("\\", "/")
                for f in mod + unt:
                    if f == rel or f.startswith(rel.rstrip("/") + "/"):
                        worktree.add(f)
    staged = T._lines(_git(root, ["diff", "--cached", "--name-only", "--diff-filter=AMR"]))
    files = sorted(set(staged) | worktree)
    msg_text = seg
    fm = T._MSGFILE.search(seg)
    if fm:
        msg_text += "\n" + (_read(T._abspath(cwd, fm.group(1))) or "")
    out = []
    for rel in files:
        full = os.path.join(root, rel)
        new = _read(full) if rel in worktree else _git(root, ["show", ":" + rel])
        if not new or not is_report(full, new):
            continue
        baselines = []
        old = _git(root, ["show", "HEAD:" + rel])
        if old:
            baselines.append(("この文書の直前の版（HEAD）", old))
        for p in predecessors(full, new):
            prel = os.path.relpath(p, root).replace("\\", "/")
            t = _git(root, ["show", "HEAD:" + prel]) or _read(p)
            if t:
                baselines.append((os.path.basename(p), t))
        fired = check(full, new, payload.get("transcript_path"), extra_marks=msg_text, baselines=baselines)
        if fired:
            out.append((rel, fired))
    if not out:
        return 0
    _record_fired(NAME, {"session_id": payload.get("session_id"), "root": root,
                         "fired": [(rel, [(l, r["headings"][:10], r["tables"], r["columns"][:10]) for l, r in f]) for rel, f in out]})
    sys.stderr.write("".join(message(rel, f) for rel, f in out)
                     + "（git commit: コミットメッセージに `Format-Drop-Ok: <対象> 承認「引用」` の行を入れてもよい）\n")
    return 2


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--compare":
        old, new = _read(sys.argv[2]) or "", _read(sys.argv[3]) or ""
        r = compare(old, new)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["fire"] else 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        if payload.get("tool_name") in ("Write", "Edit", "MultiEdit"):
            return on_file_tool(payload)
        if payload.get("tool_name") in ("Bash", "PowerShell"):
            return on_commit(payload)
    except Exception:
        return 0                      # 検査の故障で作業を止めない
    return 0


if __name__ == "__main__":
    sys.exit(main())
