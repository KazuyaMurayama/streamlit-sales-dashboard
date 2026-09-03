"""PreToolUse hook (Read): deny full reads of files >50KB without limit/offset (context-hygiene C2).

Prevents auto-compact churn from loading huge files into context.
Allows: partial reads (limit/offset/pages), files <=50KB, images/PDF/notebooks.
Fail-open: any error -> exit 0. JSON deny only (never exit 2).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import sys

MAX_BYTES = 50_000
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf", ".ipynb"}


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return  # repo copy takes over; avoid double-firing with the global copy
    except Exception:
        pass

    try:
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
        ti = data.get("tool_input") or {}
        if ti.get("limit") or ti.get("offset") or ti.get("pages"):
            return
        fp = ti.get("file_path") or ""
        if not fp or not os.path.isfile(fp):
            return
        if os.path.splitext(fp)[1].lower() in SKIP_EXT:
            return
        size = os.path.getsize(fp)
        if size > MAX_BYTES:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "context-hygiene C2: このファイルは {:,} bytes（50KB超）。"
                        "全文Readはコンテキスト肥大の主因のため禁止。代替: "
                        "(1) Grep で必要行だけ抽出 (2) Read に offset+limit を付けて必要範囲だけ読む "
                        "(3) スクリプトで処理し件数・検証結果のみ受け取る"
                        "（CLAUDE.md コンテキスト管理節 C1〜C3 参照）。".format(size)
                    ),
                }
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
