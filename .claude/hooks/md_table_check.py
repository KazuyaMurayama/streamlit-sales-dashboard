"""GFM pipe-table column-count validator (pure stdlib).

GitHub Flavored Markdown only renders a pipe table when the header row's
cell count equals the delimiter row's (`|---|---|`) cell count. When they
differ, GitHub falls back to rendering the raw pipe-delimited text (the
"table breakage" this checker exists to catch).

Public API: analyze_text(text) -> (criticals, warnings)
  criticals: header cell count != delimiter cell count (breaks rendering)
  warnings:  a data row's cell count != header cell count (renders, but
             columns may misalign)
Each finding is a dict: {"line": int, "header": int, "sep": int, "cell": str}
  (for warnings, "sep" holds the offending data row's cell count and "cell"
  is the first cell of that row, kept as the same shape for simplicity).

False-positive avoidance is the priority:
  - Content inside fenced code blocks (``` or ~~~) is skipped entirely.
  - Escaped pipes (\\|) are masked before counting cells.
  - Exactly one leading/trailing unescaped pipe is stripped before splitting.
  - A row is only a "delimiter row" if EVERY cell matches ':?-+:?' AND the
    raw line contains at least one unescaped pipe. The pipe requirement is
    what keeps this from misfiring on frontmatter '---', setext H2
    underlines, and horizontal rules, none of which are table delimiters.
  - A table is only recognized when a non-delimiter row is immediately
    followed by a delimiter row (the header+delimiter pairing GFM requires).

Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import io
import os
import re
import sys

FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
DELIM_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")

EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def _mask_escaped_pipes(line):
    """Replace \\| with a placeholder so it is not treated as a cell separator."""
    return line.replace("\\|", "\x00")


def _split_cells(line):
    """Strip at most one leading/trailing unescaped pipe, then split on |."""
    s = _mask_escaped_pipes(line.rstrip("\n").rstrip("\r"))
    stripped = s.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\x00|"):
        # avoid double-stripping when the last char is an escaped pipe placeholder
        stripped = stripped[:-1]
    cells = stripped.split("|")
    return [c.strip().replace("\x00", "\\|") for c in cells]


def _is_delimiter_row(raw_line):
    if "|" not in _mask_escaped_pipes(raw_line):
        return False
    cells = _split_cells(raw_line)
    if not cells:
        return False
    return all(DELIM_CELL_RE.match(c) for c in cells)


def _looks_like_row(raw_line):
    """A candidate table row: contains at least one unescaped pipe, not blank."""
    line = raw_line.rstrip("\n").rstrip("\r")
    if not line.strip():
        return False
    return "|" in _mask_escaped_pipes(line)


def analyze_text(text):
    criticals = []
    warnings = []

    lines = text.splitlines()
    n = len(lines)
    in_fence = False

    i = 0
    while i < n:
        raw = lines[i]

        fence_m = FENCE_RE.match(raw)
        if fence_m:
            in_fence = not in_fence
            i += 1
            continue

        if in_fence:
            i += 1
            continue

        if not _looks_like_row(raw):
            i += 1
            continue

        # candidate header row: next line must be a delimiter row
        if i + 1 < n and not in_fence:
            nxt = lines[i + 1]
            if not FENCE_RE.match(nxt) and _looks_like_row(nxt) and _is_delimiter_row(nxt):
                header_cells = _split_cells(raw)
                sep_cells = _split_cells(nxt)
                header_line_no = i + 1  # 1-indexed
                sep_line_no = i + 2

                if len(header_cells) != len(sep_cells):
                    criticals.append({
                        "line": header_line_no,
                        "header": len(header_cells),
                        "sep": len(sep_cells),
                        "cell": header_cells[0] if header_cells else "",
                    })
                    # still scan following data rows against header length for warnings,
                    # but skip past header+sep either way
                    j = i + 2
                    header_len = len(header_cells)
                else:
                    j = i + 2
                    header_len = len(header_cells)

                # consume data rows
                body_rows = 0
                while j < n and not FENCE_RE.match(lines[j]) and _looks_like_row(lines[j]) and not _is_delimiter_row(lines[j]):
                    body_rows += 1
                    data_cells = _split_cells(lines[j])
                    if len(data_cells) != header_len:
                        warnings.append({
                            "line": j + 1,
                            "header": header_len,
                            "sep": len(data_cells),
                            "cell": data_cells[0] if data_cells else "",
                        })
                    j += 1

                # A delimiter row with no data row after it does not render as a
                # table at all: GitHub emits the header+delimiter as a table with
                # an empty body and drops the following pipe lines into a
                # paragraph. The usual cause is a blank line accidentally spliced
                # between the delimiter row and the first data row, which is
                # invisible in the source but destroys the rendering.
                if body_rows == 0:
                    criticals.append({
                        "line": sep_line_no,
                        "header": header_len,
                        "sep": 0,
                        "cell": header_cells[0] if header_cells else "",
                    })

                i = j
                continue

        i += 1

    return criticals, warnings


_FENCE_ANY_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def unclosed_fence_line(text):
    """Line number of a code fence that is never closed, or 0 if balanced.

    An unclosed fence swallows every heading, table and paragraph after it into
    a single code block. It is invisible in the source and strictly worse than
    a broken table, so it belongs in the same gate.
    """
    inside = False
    start = 0
    for i, line in enumerate(text.split("\n"), 1):
        if _FENCE_ANY_RE.match(line):
            if inside:
                inside = False
            else:
                inside = True
                start = i
    return start if inside else 0


def _describe(c):
    """Human-readable cause for a critical finding."""
    if c.get("kind") == "fence":
        return "コードフェンスが閉じていない（以降が全てコード扱いになる）"
    if c["sep"] == 0:
        return f"区切り行の直後に本文行が無い（表「{c['cell']}」が描画されない）"
    return (f"MDテーブル列数不一致: ヘッダー{c['header']}列 != 区切り行{c['sep']}列"
            f"（先頭セル「{c['cell']}」）")


def _read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except Exception:
        return None


def _scan_root(root):
    all_criticals = []
    all_warnings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            text = _read_text(path)
            if not text:
                continue
            criticals, warnings = analyze_text(text)
            fence = unclosed_fence_line(text)
            if fence:
                criticals.append({"line": fence, "header": 0, "sep": -1,
                                  "cell": "", "kind": "fence"})
            for c in criticals:
                c["path"] = path
                all_criticals.append(c)
            for w in warnings:
                w["path"] = path
                all_warnings.append(w)
    return all_criticals, all_warnings


def main():
    args = sys.argv[1:]
    fmt = "plain"
    if "--format" in args:
        idx = args.index("--format")
        fmt = args[idx + 1]
        del args[idx:idx + 2]

    if "--file" in args:
        idx = args.index("--file")
        path = args[idx + 1]
        text = _read_text(path)
        if text is None:
            sys.exit(0)
        criticals, _warnings = analyze_text(text)
        fence = unclosed_fence_line(text)
        if fence:
            criticals.append({"line": fence, "header": 0, "sep": -1,
                              "cell": "", "kind": "fence"})
        if criticals:
            for c in criticals:
                print(f"{path}:{c['line']}: {_describe(c)}")
            sys.exit(1)
        sys.exit(0)

    if "--scan" in args:
        idx = args.index("--scan")
        root = args[idx + 1]
        criticals, warnings = _scan_root(root)
        if fmt == "github":
            for c in criticals:
                print(f"::error file={c['path']},line={c['line']}::{_describe(c)}")
            for w in warnings:
                print(f"::warning file={w['path']},line={w['line']}::MDテーブル列数不一致(データ行): "
                      f"ヘッダー{w['header']}列 != データ行{w['sep']}列（先頭セル「{w['cell']}」）")
        else:
            for c in criticals:
                print(f"CRITICAL {c['path']}:{c['line']}: {_describe(c)}")
            for w in warnings:
                print(f"WARNING  {w['path']}:{w['line']}: header={w['header']} data={w['sep']} cell={w['cell']}")
            print(f"\n{len(criticals)} CRITICAL, {len(warnings)} WARNING")
        sys.exit(1 if criticals else 0)

    print("usage: md_table_check.py --file PATH | --scan ROOT [--format github]", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    # Windows consoles often default to cp932/mbcs, which cannot encode many
    # Unicode characters (emoji, some CJK punctuation) that legitimately show
    # up in table cells. Force UTF-8 stdout/stderr so --scan output never
    # crashes mid-run on an otherwise-valid finding. Only done for direct CLI
    # execution (not on import) so it never interferes with pytest's capture.
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
