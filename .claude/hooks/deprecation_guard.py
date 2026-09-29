# -*- coding: utf-8 -*-
"""使わないと言われたファイルを、ファイル自体に「廃盤」と書かせ、その後の取り違えを止める。

WHY（2026-09-29 依頼者指摘）
    依頼者が「ドラフト1は不要」と言ったのに、ファイル（nt-037）には何の印も付けず、
    口頭で「今後は手を入れません」と答えただけだった。印の無いファイルは、次のセッションや
    別のエージェントから見ると現役のファイルと区別がつかず、取り違えの元になる。
    依頼者の言葉: 「ユーザーが使わないと言ったものは毎回いつも使わないようにファイル自体を
    変えなさい。口頭で答えるだけじゃなくて、ファイル自体を加工するのを毎回必ずやるように」。

2つの場面で動く（settings.json の Stop と PreToolUse の両方に登録する）:
    Stop        依頼者の最新の発言が「〇〇は不要／使わない／廃盤」の形なのに、そのターンで
                触ったファイル（Write/Edit の対象と、Bash/PowerShell のコマンドに現れたパス）の
                どれにも、実ファイルとして廃盤の印が無ければ止める（1回だけ）。
                文字列「廃盤」を書いたかではなく、実ファイルの先頭を読んで判定する
                （grep の検索語やコミットメッセージに書くだけで通った欠陥＝Fable 検証 2026-09-29）。
    PreToolUse  廃盤の印があるファイルを Read したら知らせる。Edit/Write/MultiEdit/NotebookEdit と、
                そのファイルを書き換える Bash/PowerShell は拒否する。
                印の行だけを変える Edit は通す（依頼者が復活させると言ったとき）。

廃盤の印（ファイルの先頭40行・行頭にあること。説明文中の引用で自分をロックしないため行頭に限る）:
    ⛔ 廃盤（年-月-日）: <理由>。後継: <後継ファイル>      ← 日付は数字で書く
    または front matter の行  status: deprecated

較正（実測 2026-09-29, tests/calibrate_deprecation_guard.py）:
    直近60日の依頼者発言 1,692件に宣言判定をかけ、発火10件（0.59%）。該当は「ドラフト1は不要」
    「ドラフト1は使わない」「〜実装計画書も同様に不要」「_posts/INDEX.mdはいらない」
    「計画や検証のレポートはいらない」。後2つは消す／作らない指示で、Stop は1回止めた後
    「その旨を1行書いて終える」で抜けられる。見逃しの型（nt-037 のような ID・「については」・
    指示語）は Fable 検証で見つけ、テストに入れた。
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:  # pragma: no cover
    def _record_firing(*_a, **_k):
        return False

HEAD_LINES = 40
MARK_LINE_RE = re.compile(r"^\s*(?:⛔\s*廃盤[（(]\d{4}-\d{2}-\d{2}[）)]|status:\s*(?:deprecated|廃盤)\s*$)",
                          re.M | re.I)

# ── 依頼者の「使わない」宣言 ──
# 対象語（成果物を指す語・ファイル名・記事ID・指示語）の直後に否定語が来る形だけを拾う。
_OBJ = (r"(?:ドラフト|draft|下書き|ファイル|記事|レポート|資料|原稿|版|案|シート|スライド|"
        r"プラン|バージョン|v\d|第\d稿|旧稿|旧版|テンプレ(?:ート)?|ノート|メモ|"
        r"計画書|報告書|仕様書|設計書|企画書|提案書|"
        r"(?:前|最初|1つ目|一つ目|古い|旧)の(?:やつ|もの|方)|"
        r"(?<![A-Za-z])[A-Za-z]{1,6}-\d{2,4}(?!\d)|"   # nt-037 のような ID（\b は「は」の前で効かない）
        r"[\w\-]+\.(?:md|py|json|txt|csv|html|pptx|docx|xlsx|gs|js|ts))")
# 「削除して」「捨てて」は入れない: 消すよう求められたものは消せば済み、印は要らない。
_NEG = r"(?:不要|要らない|いらない|使わない|使いません|廃盤|ボツ|没|破棄|お蔵入り|却下|採用しない|不採用)"
# 対象語と否定語の間は「番号・閉じ括弧・助詞・もう/今後/一切」だけ。間に別の名詞が入る
# 「ファイル操作に Agent は使わないで」（道具の指示）を拾わない。
DEPRECATE_RE = re.compile(
    _OBJ + r"\s?[0-9０-９一二三四五六七八九十A-Za-zＡ-Ｚ]{0,3}[」』\"')）\s]{0,2}"
    r"(?:の方)?(?:については|は|を|も|、)?\s*(?:同様に|もう|今後|一切|もはや)?\s*" + _NEG)
# 疑問・仮定・否定の否定、および「作らないで／チャットで答えて」型（存在しない物の指示）は対象外
NOT_A_DECISION = re.compile(
    r"(?:不要|使わない|廃盤|いらない)(?:ですか|でしょうか|か[?？]|なら|ならば|ではない|じゃない)"
    r"|(?:不要|いらない)[。、\s]*(?:です[。、\s]*)?(?:チャット|口頭|すぐ|直接|そのまま|画面)")

_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_SHELL_TOOLS = ("Bash", "PowerShell")
_PATH_TOKEN = re.compile(r"[\w.~:/\\\-]+\.(?:md|py|json|txt|csv|html|pptx|docx|xlsx|gs|js|ts|ipynb)")
# シェルで対象を書き換える形（読むだけの grep/cat/head は通す。rm/git rm＝消すのは通す）
_SHELL_WRITE = re.compile(
    r"sed\s+-i|perl\s+-[a-z]*i|>\s*[\"']?[\w.~/\\]|\btee\b|Set-Content|Out-File|Add-Content|"
    r"\.write\(|write_text|open\([^)]*['\"][wa]|\bmv\b|Move-Item|\bcp\b|Copy-Item")


def _emit(obj):
    # CP932 の 0x5C 問題を避けるため ASCII で書く（review_gate.py と同じ）
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


def mark_line(path):
    """先頭 HEAD_LINES 行の行頭に廃盤の印があれば、その行を返す。無ければ None。"""
    try:
        if not os.path.isfile(path):
            return None
        with io.open(path, encoding="utf-8", errors="replace") as f:
            head = "".join(f.readline() for _ in range(HEAD_LINES))
    except Exception:
        return None
    m = MARK_LINE_RE.search(head)
    if not m:
        return None
    # status 行しか無いときは、本文の ⛔ 行があればそちらを示す（後継が書いてある）
    for ln in head.split("\n"):
        if re.match(r"^\s*⛔\s*廃盤", ln):
            return ln.strip()
    return head[m.start():].split("\n", 1)[0].strip()


def is_deprecation_request(text):
    if not text:
        return False
    t = re.sub(r"<([A-Za-z_-]+)[^>]*>[\s\S]*?</\1>", " ", text)  # 貼り付け・システム挿入のタグ内は見ない
    for m in DEPRECATE_RE.finditer(t):
        tail = t[m.start():m.end() + 16]
        if not NOT_A_DECISION.search(tail):
            return True
    return False


def _text_of(r):
    c = (r.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        return next((b.get("text") for b in c if isinstance(b, dict) and b.get("type") == "text"), None)
    return c if isinstance(c, str) else None


def _genuine_user_text(r):
    """依頼者本人の発言だけを返す。スキル注入（isMeta）・/コマンドの出力・要約の続き文は除く
    （除かずに最後の user 行と見なすと、宣言があっても黙った＝30日で18.4%のターン。Fable 検証）。"""
    if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
        return None
    t = _text_of(r)
    if not t:
        return None
    s = t.lstrip()
    if s.startswith("<local-command") or s.startswith("<command-") or s.startswith("Base directory for this skill") \
            or s.startswith("This session is being continued") or s.startswith("[Request interrupted"):
        return None
    return t


def read_turn(transcript_path):
    """(最新の依頼者の発言, そのターンのツール呼び出し [(name, input)]) を返す。"""
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            rows = []
            for ln in f.readlines()[-6000:]:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        return None, []
    idx = [i for i, r in enumerate(rows) if _genuine_user_text(r)]
    if not idx:
        return None, []
    start = idx[-1]
    calls = []
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_use":
                calls.append((b.get("name"), b.get("input") or {}))
    return _genuine_user_text(rows[start]), calls


def _shell_paths(cmd, cwd):
    """コマンド文字列に現れるファイルパスを、cwd と cmd 内の cd 先で解決した実在パスの集合にする。"""
    bases = [cwd or os.getcwd()]
    for m in re.finditer(r"(?:^|[;&|\s])(?:cd|Set-Location|pushd)\s+([\"']?)([^\"';&|\n]+)\1", cmd):
        d = m.group(2).strip()
        if re.match(r"^/[a-zA-Z]/", d):  # Git Bash の /c/Users → C:/Users
            d = d[1] + ":" + d[2:]
        bases.append(d if os.path.isabs(d) else os.path.join(bases[0], d))
    out = set()
    for tok in _PATH_TOKEN.findall(cmd):
        tok = tok.strip("\"'")
        if re.match(r"^/[a-zA-Z]/", tok):
            tok = tok[1] + ":" + tok[2:]
        tok = os.path.expanduser(tok)
        for p in ([tok] if os.path.isabs(tok) else [os.path.join(b, tok) for b in bases]):
            if os.path.isfile(p):
                out.add(os.path.abspath(p))
    return out


def touched_files(calls, cwd):
    files = set()
    for name, inp in calls:
        if name in _WRITE_TOOLS:
            fp = inp.get("file_path") or inp.get("notebook_path")
            if fp:
                files.add(fp if os.path.isabs(fp) else os.path.join(cwd or os.getcwd(), fp))
        elif name in _SHELL_TOOLS:
            files |= _shell_paths(inp.get("command") or "", cwd)
    return files


def on_stop(ev):
    if ev.get("stop_hook_active"):
        return
    tp = ev.get("transcript_path")
    if not tp:
        return
    req, calls = read_turn(tp)
    if not is_deprecation_request(req):
        return
    if any(mark_line(f) for f in touched_files(calls, ev.get("cwd"))):
        return
    _record_firing("deprecation_guard", ev)
    _emit({"decision": "block", "reason": (
        "【廃盤の印】依頼者が成果物を「不要／使わない／廃盤」と言ったのに、このターンで触ったファイルの"
        "どれにも廃盤の印が付いていない。口頭の返事や別の文書に書くだけでは、次のセッションや別の"
        "エージェントが取り違える（2026-09-29 依頼者指示「ファイル自体を加工するのを毎回必ずやる」）。\n"
        "対象ファイル自体の本文1行目（front matter があればその直後）の行頭に、日付を数字で次を書き、"
        "front matter があれば status: deprecated にする:\n"
        "  ⛔ 廃盤（2026-01-31 の形の日付）: <理由>。後継: <後継ファイル>\n"
        "build や一覧の対象からも外す。消すよう言われたもの・まだ存在しない物（「レポートは作らないで」）"
        "なら、その旨を1行書いて終えてよい。")})


def _strip_marks(s):
    return "\n".join(ln for ln in (s or "").split("\n") if not MARK_LINE_RE.match(ln))


def _only_mark_changes(old, new):
    """印の行を取り除けば old と new が同じ＝印の行だけを変える編集。"""
    return MARK_LINE_RE.search(old or "") is not None and _strip_marks(old) == _strip_marks(new)


def _deny(line):
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
           "permissionDecisionReason": (
               "⛔ 廃盤のファイルは変更しない（%s）。後継ファイルを使うこと。"
               "依頼者が復活させると言った場合だけ、先に印の行だけを Edit で消す（本文は同時に変えない）。" % line)}})


def on_pre_tool(ev):
    tool = ev.get("tool_name") or ""
    ti = ev.get("tool_input") or {}
    if tool in _SHELL_TOOLS:
        cmd = ti.get("command") or ""
        if not _SHELL_WRITE.search(cmd):
            return
        for p in sorted(_shell_paths(cmd, ev.get("cwd"))):
            line = mark_line(p)
            if line:
                _record_firing("deprecation_guard", ev)
                _deny(line)
                return
        return
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fp:
        return
    if not os.path.isabs(fp):
        fp = os.path.join(ev.get("cwd") or os.getcwd(), fp)
    line = mark_line(fp)
    if not line:
        return
    _record_firing("deprecation_guard", ev)
    if tool == "Read":
        _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": (
            "⛔ このファイルは廃盤です（%s）。依頼者が使わないと決めたもの。"
            "作業対象を取り違えていないか確認し、後継ファイルを使うこと。" % line)}})
        return
    if tool == "Edit" and _only_mark_changes(ti.get("old_string"), ti.get("new_string")):
        return  # 印の行だけを直す編集（依頼者が復活させると言ったとき）は通す
    if tool in _WRITE_TOOLS:
        _deny(line)


def _registered_local_copy_exists():
    """別のリポ内コピーが存在し、かつそのリポの settings に登録されているときだけ True
    （存在だけで黙ると、44リポで層ごと無効化した 2026-07-14 の事故と同じになる）。"""
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", base))
        if me == local or not os.path.exists(local):
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
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    try:
        name = ev.get("hook_event_name")
        if name == "Stop" or (name is None and "stop_hook_active" in ev and "tool_name" not in ev):
            on_stop(ev)
        elif name in ("PreToolUse", None) and ev.get("tool_name"):
            on_pre_tool(ev)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
