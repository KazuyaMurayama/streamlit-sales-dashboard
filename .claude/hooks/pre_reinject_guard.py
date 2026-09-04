# -*- coding: utf-8 -*-
"""Context re-injection guard (context-hygiene C7).

実測に基づく設計:
  直近6セッション 44,860,172 字のうち、file attachment の 87.8% が
  「2回目以降の再注入」だった。445 ファイルが計 1,335 回注入され、
  最悪は同一ファイル 33 回。単発 40,000 字超の tool_result は 6 セッションで
  わずか 1 件しかない。つまりコンテキストを埋めているのは
  「1回が大きい」ことではなく「同じものが何度も入る」ことである。

  そのため本 hook はサイズではなく **反復** を止める。
  pre_read_guard.py（C2・サイズ上限）とは対象クラスが異なり、両立する。

判定（不変条件で書く。固有ファイル名に依存しない）:
  同一セッション内で、同一パス・同一内容(mtime+size)の Read を
  2 回目以降に行おうとした場合に deny する。
  「内容が変わっていない同じファイルを読み直しても新情報はゼロだが、
    コンテキスト消費は満額かかる」——これが不変条件。
  ファイルが更新されていれば(mtime か size が変化)再 Read は許可する。

fail-open:
  あらゆる例外は exit 0（Read を止めない）。deny は上記条件が
  明確に成立したときのみ。
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

# 1セッション内の Read 台帳。session_id ごとに1ファイル。
STATE_DIR = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".",
                         "claude_reinject_guard")

# 除外: 読み直しに意味がある/小さくて害がないもの
EXEMPT_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb")
# 読み直す正当性が高い状態ファイル（進行中に外部が書き換える）
EXEMPT_BASENAME = ("tasks.md", "STATE.md", "MEMORY.md", "CURRENT_BEST_STRATEGY.md")

# この字数未満のファイルは再 Read を許す（節約効果が小さく、誤 deny の害が上回る）
MIN_BYTES = 2000


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    ev = json.loads(raw)

    if (ev.get("tool_name") or "") != "Read":
        return 0

    ti = ev.get("tool_input") or {}
    fp = ti.get("file_path")
    if not fp:
        return 0

    # 部分 Read は再取得の正当性がある（別の範囲を見ている）
    if ti.get("offset") is not None or ti.get("limit") is not None:
        return 0

    low = fp.lower()
    if low.endswith(EXEMPT_SUFFIX):
        return 0
    if os.path.basename(fp) in EXEMPT_BASENAME:
        return 0

    try:
        stt = os.stat(fp)
    except OSError:
        return 0
    if stt.st_size < MIN_BYTES:
        return 0

    sid = ev.get("session_id") or "nosession"
    # session_id は外部由来。パスに使う前に英数字へ正規化する。
    sid = hashlib.sha256(sid.encode("utf-8", "replace")).hexdigest()[:16]

    os.makedirs(STATE_DIR, exist_ok=True)
    ledger_path = os.path.join(STATE_DIR, sid + ".json")
    ledger = load(ledger_path)

    key = hashlib.sha256(os.path.abspath(fp).lower().encode("utf-8", "replace")).hexdigest()[:24]
    fingerprint = "%d:%d" % (int(stt.st_mtime), stt.st_size)

    prev = ledger.get(key)
    if prev and prev.get("fp") == fingerprint:
        n = prev.get("n", 1)
        msg = (
            u"[C7 再注入ガード] このファイルは本セッションで既に全文 Read 済みで、"
            u"その後 変更されていません（前回から mtime・サイズとも同一 / 既に %d 回）。\n"
            u"同一内容の再 Read は新情報ゼロでコンテキストのみ消費します"
            u"（実測: file attachment の 87.8%% が再注入の重複でした）。\n"
            u"対処のいずれかを選んでください:\n"
            u"  1. 既にコンテキスト内にある内容をそのまま使う（推奨）\n"
            u"  2. 特定箇所だけ必要なら offset/limit 付きで Read する\n"
            u"  3. 検索なら Grep を使う\n"
            u"対象: %s"
        ) % (n, fp)
        ledger[key] = {"fp": fingerprint, "n": n + 1, "t": int(time.time())}
        save(ledger_path, ledger)
        # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
        _record_firing("pre_reinject_guard", ev)
        sys.stderr.write(msg)
        return 2

    ledger[key] = {"fp": fingerprint, "n": 1, "t": int(time.time())}
    save(ledger_path, ledger)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # fail-open: ガードの不具合で作業を止めない
        sys.exit(0)
