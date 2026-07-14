"""PreToolUse hook (Write|Edit): deny Markdown table column-count breakage.

GFM pipe tables only render when the header row's cell count equals the
delimiter row's. This hook denies a Write/Edit that would introduce (or
worsen) that mismatch in a .md file.

- Write: analyze tool_input.content directly.
- Edit: apply old_string -> new_string (respecting replace_all) to the
  current on-disk content in memory, then analyze the result. This is
  regression-only: only denies when the edit INCREASES the number of
  CRITICAL (header != delimiter) findings versus the pre-edit file, so an
  unrelated edit to an already-broken file is never blocked.

Fail-open: any error -> exit 0 (never blocks on our own bug).
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import json
import os
import sys


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import md_table_check  # noqa: E402
    except Exception:
        return

    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name") or ""
        tool_input = data.get("tool_input") or {}
        fp = tool_input.get("file_path") or ""

        if not fp.lower().endswith(".md"):
            return

        if tool_name == "Write":
            content = tool_input.get("content") or ""
            criticals, _warnings = md_table_check.analyze_text(content)
            if criticals:
                c = criticals[0]
                _deny(c)
            return

        if tool_name == "Edit":
            old_string = tool_input.get("old_string")
            new_string = tool_input.get("new_string")
            replace_all = bool(tool_input.get("replace_all"))
            if old_string is None or new_string is None:
                return

            try:
                with open(fp, encoding="utf-8-sig") as f:
                    before_content = f.read()
            except Exception:
                before_content = ""

            criticals_before, _ = md_table_check.analyze_text(before_content)

            if replace_all:
                after_content = before_content.replace(old_string, new_string)
            else:
                after_content = before_content.replace(old_string, new_string, 1)

            criticals_after, _ = md_table_check.analyze_text(after_content)

            if len(criticals_after) > len(criticals_before):
                # find a finding present after but not clearly before (best-effort: just report first)
                c = criticals_after[0]
                _deny(c)
            return
    except Exception:
        pass


def _deny(c):
    reason = (
        f"MDテーブル列数不一致: 行{c['line']} ヘッダー{c['header']}列≠区切り行{c['sep']}列"
        f"（先頭セル「{c['cell']}」）。区切り行の `---` セルを{c['header']}個に揃えてから保存。"
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


if __name__ == "__main__":
    main()
    sys.exit(0)
