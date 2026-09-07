"""Mermaid 図ガード（PostToolUse: Write|Edit|Bash|PowerShell ／ Stop）。

目的: Markdown に Mermaid 図を書いた／変えた時点で必ず発火し、GitHub の操作パネル（右上2ボタン・
右下パン/ズーム）にノードが隠れないかを **実レンダリング** で検査する（2026-09-05 再発防止）。
画像図（mermaid_to_image.py で変換済み）については「ソースと画像の整合」を検査する。

発火条件:
  - PostToolUse Write|Edit       : 対象が .md で ```mermaid（-src 含む）を含む
  - PostToolUse Bash|PowerShell  : 直近3分以内に更新された .md（git 追跡外含む）で同上（heredoc 書き込み対策）
  - Stop                         : HEAD と差分のある .md（未コミット・未追跡）で同上（バックストップ）
判定:
  - FAIL       → block（理由と回避策を提示）
  - UNVERIFIED → block（レンダラー不在。無反応を正常と解釈しない: CLAUDE.md F2）。Stop では1回だけ
  - PASS       → 何もしない
検査本体: 同ディレクトリの mermaid_overlay_check.py（無ければ cwd の _meta/）。環境変数 MERMAID_CHECKER で上書き可。
キャッシュ: ファイル内容の sha256 ごとに直近結果を OS temp に保存し、未変更ファイルは再描画しない。
Fail-open: 本フック自身の例外は exit 0（ただし検査不能は UNVERIFIED として block する）。

Dedup rule: グローバル copy は、リポ側に登録済み copy がある場合だけ退く（他フックと同じ規約）。
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-05, not chosen)
---------------------------------------------
- 欠陥版に当てて FAIL することを確認: 問題のスクリーンショット（スマホ）と同じ図を検査器にかけ、
  同じノード「快楽の友愛」が右下パネルと交差する判定（x=253.7,y=131.3 / scale 0.459）を得た。
  既存コーパス 35 図中 **33 図がスマホ幅で FAIL、14 図が PC 幅でも FAIL**（実レンダリングで計測）。
- 直した版で PASS: 画像図に変換後 PASS 2/2。ソースだけ改変して未再描画にすると FAIL（整合検査）。
- フック本体: PASS ファイルの Write イベントで沈黙、FAIL ファイルで decision=block（実イベントを流して確認）。
- 発火頻度: 対象は「Mermaid を含む .md の更新時」に限られる。本セッション（約 60 回のツール呼出）で
  レンダリングが走ったのは 5 回、block は 2 回（いずれも真陽性）。誤検知は観測していない。
- 未計測: PC 幅 1000px は概算（実スクリーンショットはスマホのみ）。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(tempfile.gettempdir(), "mermaid_figure_guard_cache.json")
RECENT_SEC = 180


def _registered_local_copy_exists():
    """グローバル copy が退く条件: 別のリポ側 copy が存在し、かつ settings に登録されている。"""
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
            except OSError:
                continue
        return False
    except Exception:
        return False


def _checker():
    env = os.environ.get("MERMAID_CHECKER")
    if env:
        return env
    for c in (os.path.join(HERE, "mermaid_overlay_check.py"),
              os.path.join(os.getcwd(), ".claude", "hooks", "mermaid_overlay_check.py"),
              os.path.join(os.getcwd(), "_meta", "mermaid_overlay_check.py")):
        if os.path.isfile(c):
            return c
    return None


def _has_figure(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "```mermaid" in f.read()
    except OSError:
        return False


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(c):
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f)
    except Exception:
        pass


def _changed_md_files():
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    files = []
    for line in out.splitlines():
        p = line[3:].strip()
        if " -> " in p:
            p = p.split(" -> ")[-1]
        p = p.strip('"')
        if p.endswith(".md") and os.path.isfile(p):
            files.append(p)
    return files


def _recent_md_files():
    now = time.time()
    return [p for p in _changed_md_files() if now - os.path.getmtime(p) <= RECENT_SEC]


def _candidates(ev):
    if ev.get("hook_event_name") == "Stop":
        files = _changed_md_files()
    else:
        tool = ev.get("tool_name") or ""
        if tool in ("Write", "Edit"):
            fp = (ev.get("tool_input") or {}).get("file_path") or ""
            files = [fp] if fp.endswith(".md") and os.path.isfile(fp) else []
        else:
            files = _recent_md_files()
    return [f for f in files if _has_figure(f)]


def run_check(files):
    """戻り値: (status, text)  status ∈ PASS/FAIL/UNVERIFIED"""
    chk = _checker()
    if not chk:
        return "UNVERIFIED", "mermaid_overlay_check.py が見つからない（.claude/hooks/ か _meta/ に配置すること）"
    try:
        p = subprocess.run([sys.executable, chk] + files, capture_output=True, text=True, timeout=400)
    except Exception as e:
        return "UNVERIFIED", "検査器の起動に失敗: %s" % e
    text = (p.stdout or "") + (("\n" + p.stderr[-400:]) if p.returncode not in (0, 1) and p.stderr else "")
    return {0: "PASS", 1: "FAIL"}.get(p.returncode, "UNVERIFIED"), text.strip()


def main():
    try:
        raw = sys.stdin.buffer.read()
        ev = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return
    try:
        if _registered_local_copy_exists():
            return
        files = _candidates(ev)
        if not files:
            return
        cache = _load_cache()
        todo, statuses, texts = [], {}, []
        for f in files:
            h = _sha(f)
            hit = cache.get(os.path.abspath(f))
            if hit and hit.get("sha") == h and hit.get("status") == "PASS":
                statuses[f] = "PASS"
            else:
                todo.append(f)
        if todo:
            status, text = run_check(todo)
            texts.append(text)
            for f in todo:
                statuses[f] = status
                cache[os.path.abspath(f)] = {"sha": _sha(f), "status": status, "t": time.time()}
            _save_cache(cache)
        worst = "PASS"
        for s in statuses.values():
            if s == "FAIL":
                worst = "FAIL"
            elif s == "UNVERIFIED" and worst != "FAIL":
                worst = "UNVERIFIED"
        if worst == "PASS":
            return
        if worst == "UNVERIFIED" and ev.get("hook_event_name") == "Stop" and ev.get("stop_hook_active"):
            return
        _record_firing("mermaid_figure_guard", ev)
        head = ("⛔【Mermaid 図ガード】GitHub の操作パネルに隠れる図がある（FAIL）。"
                if worst == "FAIL" else
                "⚠【Mermaid 図ガード】図の検査ができなかった（UNVERIFIED）。node と Playwright(Chromium) を確認し "
                "`python .claude/hooks/mermaid_overlay_check.py FILE.md` を手で実行して結果を最終回答に明示すること。")
        body = "\n".join(t for t in texts if t)[-3000:]
        print(json.dumps({"decision": "block",
                          "reason": head + "\n対象: " + ", ".join(files) + "\n" + body}, ensure_ascii=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
