# -*- coding: utf-8 -*-
"""PreToolUse hook (Write|Edit): undefined internal identifiers in reports.

WHY (2026-10-15, user, verbatim):
  「FULL 最良って何？変な略し方や、慣れてない言葉を使わないでほしい。
   私ももちろん、あなたも間違え、そのせいで更新の時に取り間違えるでしょう」
  Defect instance: nasdaq_backtest TOTAL4300_DIAL_SEARCH_20261014.md @ ae5f3f1
  used FULL / HOLDOUT20 / SB10 / F5 / H51 / B0 / R0 / CRN ... in the
  conclusion before (or without) any definition, and had no glossary table.

INVARIANT (the class, not the instance):
  In a report .md, every internal-identifier-like token that appears in the
  body (outside fenced code blocks and outside the glossary table itself) must
  be listed in a glossary table (用語対応表) of the SAME file, in a row that
  also carries a Japanese name/meaning. A one-time parenthetical definition in
  prose does NOT count -- the reader (and the next editor) cannot find it.

"Identifier-like" is decided by token SHAPE, never by a list of known bad
strings:
  - contains "_"                         P09_STR, sale_now_tax (outside code)
  - 2+ upper-case letters                FULL, CRN, OOS, MaxDD, TOPUP
  - letters mixed with digits            F5, H51, SB10, HOLDOUT20, sc1.875
  - X[...] expectation-style notation    E[cover]
  - lower-case 2-6 letters standing alone between Japanese text
                                         「full で最良」 (not "of the study")
Full-width letters are folded first (ＦＵＬＬ == FULL). Inline code counts as
prose unless it is code-shaped (contains _ . / ( ) = : etc.), so wrapping a
private abbreviation in backticks does not hide it.

Generally-known words (NASDAQ, CAGR, ETF, GAS ...) are in ALLOW below or in
the repo's .claude/report_quality.json "jargon_allow". Dated document names,
commit SHAs, URLs and file paths are references, not jargon, and are skipped.

Behaviour follows pre_report_quality_guard (same scope rules, same config
file, regression-only): it fires only when the edit INCREASES the number of
undefined-identifier occurrences versus the file on disk, so pre-existing debt
never blocks unrelated work. Mode: .claude/report_quality.json
"jargon_mode": "deny" | "warn" | "off"; unset = deny where the repo's
"mode" is deny (nasdaq_backtest), warn elsewhere (see _load_cfg).
Fail-open on any error.

Calibration (measured, see tests/calibrate_jargon_glossary_guard.py):
the shape rules and ALLOW were tuned against every dated report .md in all
local repos; the measured firing rate is recorded in that script's output and
in the countermeasure report.

CLI (for calibration / manual check):
  python jargon_glossary_guard.py --input FILE.md [--json]
  exit 1 if FILE has undefined identifiers, else 0.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import collections
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

try:
    from codex_adapter import normalize as _codex_normalize
except Exception:
    def _codex_normalize(d):
        if isinstance(d, dict) and d.get("tool_name") == "apply_patch":
            sys.stderr.write("[jargon_glossary_guard] codex_adapter.py not found; "
                             "Codex apply_patch payloads are NOT being checked.\n")
        return d

# Widely-known terms a general Japanese reader is expected to know (or that are
# proper names). Keep this to genuinely general vocabulary: a term belongs here
# only if it would be understood WITHOUT this repository. Project-private
# abbreviations go in the report's glossary table instead.
ALLOW = set("""
NASDAQ CAGR GAS ETF BTC ETH NISA iDeCo USD JPY EUR GDP CPI FRB FOMC FED ECB BOJ
AI API URL URI PDF CSV JSON HTML CSS SQL XML YAML OS PC ID OK NG QC QA FAQ
GitHub Google YouTube LINE JST UTC GMT Python JavaScript TypeScript Excel Word
PowerPoint VIX TOPIX NHK SNS PR IT DX SaaS CEO CFO CTO COO HR KPI KGI ROI ROE ROA
PER PBR EPS IPO M&A FX CFD REIT TV DVD CD USB GPU CPU RAM SSD LLM GPT ChatGPT
OpenAI Anthropic Claude Codex MCP CLI SDK UI UX iPhone iPad iOS Android Mac
macOS Windows Linux PowerShell VSCode Gmail SMS Wi-Fi WiFi Bluetooth NPO NGO
EU UK US USA UN WHO IMF OECD JR JA JAXA NASA NTT KDDI SBI GMO PayPay SONY NEC
IBM AWS GCP OEM B2B B2C DNA RNA PCR BMI QOL SPF PA UV UVA UVB pH LDL HDL CO2
LGBT LGBTQ PTA PTSD ADHD MRI CT ICU ER Amazon Apple Microsoft Netflix Instagram
Facebook TikTok Obsidian Notion Slack Zoom OBS Markdown Mermaid SVG PNG JPG JPEG
GIF MP3 MP4 WAV PASS FAIL REVIEW WARN TODO DONE NOTE AM PM Q1 Q2 Q3 Q4 FY CY YoY MoM QoQ S&P SP500 NYSE TSE JPX MSCI
ACWI FTSE DJIA HTTP HTTPS VOO QQQ TQQQ SPY VTI KB MB GB TB GHz MHz kWh mAh No DIY OCR PoC
""".split())
# Lower-case words that may stand alone between Japanese text: units and the
# handful of tool words this user works with daily.
ALLOW_LOWER = set("""
pp bp kg mg km cm mm ms px pt vs etc min max log sec ok yes app web email
mail http https www com jp commit push pull merge branch repo hook script
""".split())

EXT = r"(?:md|py|json|jsonl|csv|tsv|npz|npy|gs|js|ts|txt|yaml|yml|html|png|svg|jpg|pdf|xlsx|docx|pptx|ipynb|sh|ps1|toml|ini|cfg|log|pkl|parquet)"
RE_FENCE = re.compile(r"^\s*(```|~~~)")
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# ASCII-only URL body: "出典https://x.com/aよりFULL" must not swallow 「よりFULL」.
RE_URL = re.compile(r"<https?://[^>\s]+>|https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
RE_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")
RE_INLINE_CODE = re.compile(r"`([^`]+)`")
RE_FILE = re.compile(r"[A-Za-z0-9_.\-/\\~]+\." + EXT + r"(?![A-Za-z0-9])", re.I)
# A path is removed only when it LOOKS like one: rooted (./ ../ ~/ / C:\) or all
# lower-case segments. "FULL/HOLDOUT20/SB10" is a list of labels, not a path.
RE_PATH = re.compile(r"(?:(?:\.{1,2}|~|[A-Za-z]:)?[/\\])?(?:[a-z0-9_.\-~]+[/\\]){2,}[a-z0-9_.\-]*")
RE_ROOTED = re.compile(r"(?:\.{1,2}/|~/|[A-Za-z]:\\)[^\s]*")
# A dated document name: >=2 name parts before the 8-digit date
# (NDX_CANON_DIAL_RESEARCH_20261014). "FULL_20261014" is one label + a date.
RE_DATED_NAME = re.compile(r"[A-Za-z0-9]+(?:[_\-][A-Za-z0-9]+)+[_\-]\d{8}(?:-v\d+)?")
RE_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")
RE_VERSION = re.compile(r"^(?:v\d+(?:\.\d+)*|x\d+(?:\.\d+)?)$")
RE_EXPECT = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z])\[([A-Za-z_][A-Za-z0-9_ ]*)\]")
RE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])[0-9]*([A-Za-z][A-Za-z0-9]*(?:[_\-&][A-Za-z0-9]+)*(?:\.[0-9]+)?)")
RE_EMPH = re.compile(r"(?<![A-Za-z0-9])([_*]{1,3})(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])")
RE_SPACED = re.compile(r"(?<![A-Za-z0-9])([A-Z]) +([0-9]+)(?![0-9.,A-Za-z])")
RE_JA = re.compile(r"[\u3040-\u309f\u30a1-\u30fa\u30fd-\u30ff\u3400-\u9fff]")
GLOSSARY_HEAD_KEY = re.compile(r"用語|略語|略号|略称|記号|表記|識別子|呼び名|名前|名称|term|abbrev", re.I)
GLOSSARY_HEAD_VAL = re.compile(r"意味|説明|日本語|正式|定義|中身|内容|指すもの|meaning|definition", re.I)
MAX_KEYS_PER_ROW = 3
STRICT = False
MAX_KEY_CELL = 40


def _fold(s):
    return unicodedata.normalize("NFKC", s)


def _stem(tok):
    """HOLDOUT20 -> HOLDOUT, sc1.875 -> sc, P09_STR stays, F5 -> F."""
    s = re.sub(r"[\-_.]?[0-9][0-9.]*$", "", tok)
    return s or tok


def _english_run(line, start, end):
    """Number of space-separated ASCII words in the run containing [start,end)."""
    left = line[:start]
    right = line[end:]
    lw = re.search(r"((?:[A-Za-z][A-Za-z'\-]*[ ,]+)*)$", left).group(1)
    rw = re.match(r"((?:[ ,]+[A-Za-z][A-Za-z'\-]*)*)", right).group(1)
    return 1 + len(re.findall(r"[A-Za-z][A-Za-z'\-]*", lw)) + len(re.findall(r"[A-Za-z][A-Za-z'\-]*", rw))


def _is_identifier(tok, line, start, end):
    """Shapes that mark a COINED label (calibrated 2026-10-15, see module doc).

    Checked:  contains "_" (P09_STR) / letters mixed with digits (F5, H51,
              SB10, HOLDOUT20, sc1.875) / all-caps word of 4+ letters (FULL,
              TOPUP, HOLDOUT) / camel case with an internal capital run (MaxDD)
    Not checked (measured: 99.6% of 1,203 real reports and 79.8% of real
    report edits fired when these were included -- a guard that blocks four
    edits in five gets switched off): 2-3 letter acronyms (CI, RCT, SE, IS),
    Capitalised words (Phase, Sonnet, Sharpe) and lower-case words.
    STRICT=True restores them for manual audits (CLI --strict)."""
    if RE_VERSION.match(tok):
        return False
    if "_" in tok:
        return True
    letters = re.sub(r"[^A-Za-z]", "", tok)
    if not letters:
        return False
    if re.search(r"[0-9]", tok):
        return True
    core = re.sub(r"[\-&]", "", tok)
    if core.isupper() and len(letters) >= 4:
        return True
    if re.search(r"[a-z]", tok) and re.search(r"[A-Z]{2,}", tok):
        return True
    if not STRICT:
        return False
    if sum(1 for c in tok if c.isupper()) >= 2:
        return True
    if tok.isalpha() and len(tok) >= 2:
        if _english_run(line, start, end) >= 3:
            return False
        return tok.lower() not in ALLOW_LOWER
    return False


def _allowed(tok, allow, au):
    if tok in allow or tok.upper() in au:
        return True
    parts = re.split(r"[\-&]", tok)
    if len(parts) > 1 and (parts[0] in allow or parts[0].upper() in au) and all(
            p.upper() in au or re.match(r"^[0-9A-Za-z]$|^[0-9][0-9a-z.]*$", p) for p in parts[1:]):
        return True                       # USB-C, GPT-4o, Wi-Fi
    st = _stem(tok)
    return st != tok and len(st) >= 2 and (st in allow or st.upper() in au)



def _split_row(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def _is_sep(cells):
    return cells is not None and all(re.match(r"^:?-+:?$", c or "-") for c in cells)


def _ja_len(s):
    return len(RE_JA.findall(s))


def _mask(lines):
    """Lines that are not prose: matched fenced blocks and a CLOSED front matter.
    An unclosed fence or front matter hides nothing (it would otherwise hide
    the rest of the file)."""
    skip = set()
    n = len(lines)
    if n and lines[0].strip() == "---":
        for j in range(1, min(n, 60)):
            if lines[j].strip() in ("---", "..."):
                skip.update(range(0, j + 1))
                break
    i = 0
    while i < n:
        if i not in skip and RE_FENCE.match(lines[i]):
            mark = RE_FENCE.match(lines[i]).group(1)
            j = i + 1
            while j < n and not lines[j].lstrip().startswith(mark):
                j += 1
            if j < n:
                skip.update(range(i, j + 1))
                i = j + 1
                continue
        i += 1
    return skip


def _cell_tokens(cell):
    c = _clean(_fold(cell))
    c = RE_EMPH.sub(lambda m: m.group(2), c)
    toks = [m.group(0) for m in RE_EXPECT.finditer(c)]
    c = RE_EXPECT.sub(" ", c)
    toks += [m.group(1).rstrip("-&") for m in RE_TOKEN.finditer(c)]
    return toks


def find_glossary(lines, skip):
    """Return (keys:set, glossary_line_indexes:set).

    A glossary is a Markdown table outside code whose header's FIRST column
    names a term (用語/略語/略号/記号/表記...) and some column names a meaning
    (意味/説明/日本語/正式...). A body row DEFINES its first-cell tokens only if
      - the first cell is short (<= MAX_KEY_CELL chars) and names at most
        MAX_KEYS_PER_ROW tokens (one row per term, not a dumping ground), and
      - the MEANING column carries Japanese text (>= 2 Japanese characters).
    Rows that fail are treated as ordinary body text (their tokens count)."""
    keys, idx = set(), set()
    i, n = 0, len(lines)
    while i < n:
        head = _split_row(lines[i]) if i not in skip else None
        sep = _split_row(lines[i + 1]) if (head and i + 1 < n) else None
        if head and _is_sep(sep):
            vcols = [k for k, h in enumerate(head) if k > 0 and GLOSSARY_HEAD_VAL.search(h)]
            is_glo = bool(GLOSSARY_HEAD_KEY.search(head[0]) and vcols)
            if is_glo:
                idx.update((i, i + 1))
            j = i + 2
            while j < n and j not in skip and _split_row(lines[j]) is not None:
                if is_glo:
                    cells = _split_row(lines[j])
                    toks = _cell_tokens(cells[0]) if cells else []
                    meaning = " ".join(cells[k] for k in vcols if k < len(cells))
                    if (cells and toks and len(cells[0]) <= MAX_KEY_CELL
                            and len(set(toks)) <= MAX_KEYS_PER_ROW and _ja_len(meaning) >= 2):
                        keys.update(toks)
                        idx.add(j)
                j += 1
            i = j
            continue
        i += 1
    return keys, idx


def _hex_is_commit(h):
    """A lower-case hex run is a commit reference only if git knows it here."""
    try:
        import subprocess
        r = subprocess.run(["git", "cat-file", "-e", h + "^{commit}"], capture_output=True, timeout=3)
        return r.returncode == 0
    except Exception:
        return False


_HEX_CACHE = {}


def _clean(line):
    line = RE_URL.sub(" ", line)
    line = RE_LINK_TARGET.sub("] ", line)

    def _ic(m):
        body = m.group(1)
        # Code-shaped inline code (an identifier with _ . / or a call/assignment
        # that also has lower-case letters) is code. `FULL` or `FULL：（…）` is a
        # label in backticks and is read as prose.
        if not RE_JA.search(body) and re.search(r"[a-z]", body) and re.search(r"[_./()=\[\]\-\"':<> ]", body):
            return " "
        return " " + body + " "
    line = RE_INLINE_CODE.sub(_ic, line)
    line = RE_FILE.sub(" ", line)
    line = RE_ROOTED.sub(" ", line)
    line = RE_PATH.sub(" ", line)
    line = RE_DATED_NAME.sub(" ", line)

    def _hx(m):
        h = m.group(0)
        if not (re.search(r"[a-f]", h) and re.search(r"[0-9]", h)):
            return h
        # A commit reference: git knows it here, or it sits next to a
        # reference cue (commit / コミット / 版 / 正典 / brackets / @). A bare
        # lower-case hex word in a sentence ("設定 face1234 が最良") is a label.
        pre = m.string[max(0, m.start() - 8):m.start()]
        post = m.string[m.end():m.end() + 1]
        if re.search(r"(?i)commit|コミット|版|正典|[(（@:：]\s*$", pre) or post in (")", "）", "]"):
            return " "
        if h not in _HEX_CACHE:
            _HEX_CACHE[h] = _hex_is_commit(h)
        return " " if _HEX_CACHE[h] else h
    line = RE_HEX.sub(_hx, line)
    line = re.sub(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?>", " ", line)   # HTML tags, keep inner text
    line = RE_EMPH.sub(lambda m: " " + m.group(2) + " ", line)
    line = RE_SPACED.sub(lambda m: m.group(1) + m.group(2), line)
    return line


def analyze_text(text, extra_allow=()):
    """Findings: list of {line, term, key}. key is what must go in the glossary."""
    allow = set(ALLOW) | set(extra_allow or ())
    au = {a.upper() for a in allow}
    text = RE_HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text or "")
    lines = [_fold(l) for l in text.splitlines()]
    skip = _mask(lines)
    keys, gidx = find_glossary(lines, skip)
    kstems = keys  # exact keys only: F5 in the glossary does NOT define F10
    out = []
    for no, raw in enumerate(lines):
        if no in skip or no in gidx:
            continue
        line = _clean(raw)
        for m in RE_EXPECT.finditer(line):
            term = m.group(0)
            if term not in keys and term not in allow:
                out.append({"line": no + 1, "term": term, "key": term})
        line = RE_EXPECT.sub(" ", line)
        for m in RE_TOKEN.finditer(line):
            tok = m.group(1).rstrip("-&")
            if not _is_identifier(tok, line, m.start(1), m.end(1)):
                continue
            if _allowed(tok, allow, au):
                continue
            # A bare stem row (| sc | 倍率 |) defines its numbered family
            # (sc1.875, sc2.0); a numbered row (| F5 |) defines only itself.
            if tok in kstems or (_stem(tok) in kstems and _stem(tok) != tok
                                 and not re.search(r"[0-9]", _stem(tok))):
                continue
            out.append({"line": no + 1, "term": tok, "key": tok})
    return out


# ---------------------------------------------------------------- hook side
def _load_cfg():
    """jargon_mode: explicit key wins. Otherwise a repo that promoted the report
    guards to "deny" (report_quality.json "mode") gets deny, every other repo
    gets warn. Calibrated 2026-10-15: on 242 real report-changing commits the
    guard fired on 52.1% (94.8% of NEW reports carry at least one coined label
    without a glossary), so blocking by default in all repos would stop most
    report work on day one. A repo-level "off" for the numeric checks does NOT
    switch this guard off (20 repos set mode "off" for unrelated reasons)."""
    cfg = {"jargon_mode": None, "jargon_allow": [], "jargon_regression": "key"}
    u = {}
    try:
        with open(os.path.join(os.getcwd(), ".claude", "report_quality.json"), encoding="utf-8-sig") as f:
            u = json.load(f)
        if isinstance(u, dict):
            for k in cfg:
                if k in u:
                    cfg[k] = u[k]
    except Exception:
        u = {}
    if cfg["jargon_mode"] not in ("deny", "warn", "off"):
        cfg["jargon_mode"] = "deny" if (isinstance(u, dict) and u.get("mode") == "deny") else "warn"
    return cfg


def _registered_local_copy_exists():
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                                             ".claude", "hooks", base))
        if os.path.normcase(me) == os.path.normcase(local) or not os.path.exists(local):
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


def _added(before, after, allow, regression="key"):
    """What this edit ADDS. regression="key" (default): a term that had no
    undefined use before and has one now -- introducing a new private label is
    what the user objected to. "count": any increase in occurrences.
    Measured 2026-10-15 on 242 real report-changing commits (30 days, all
    repos): "count" fired on 61.2%, mostly edits that re-used labels already
    in the file; see calibrate_jargon_glossary_guard.py for the "key" rate."""
    fa = analyze_text(after, allow)
    fb = analyze_text(before, allow)
    if regression == "count":
        cb = collections.Counter(f["key"] for f in fb)
        ca = collections.Counter(f["key"] for f in fa)
        grown = {k for k in ca if ca[k] > cb.get(k, 0)}
    else:
        had = {f["key"] for f in fb}
        grown = {f["key"] for f in fa} - had
    return [f for f in fa if f["key"] in grown]


def _message(findings):
    seen, terms = set(), []
    for f in findings:
        if f["key"] not in seen:
            seen.add(f["key"])
            terms.append("%s（L%d）" % (f["key"], f["line"]))
    return ("レポート本文に、用語対応表に載っていない内部識別子・略号があります: "
            + "、".join(terms[:12]) + ("…ほか%d件" % (len(terms) - 12) if len(terms) > 12 else "")
            + "\n第一選択は日本語の言葉に置き換えること（自作の略し方をしない。2026-10-15 依頼者指摘"
              "「変な略し方や、慣れてない言葉を使わないでほしい」）。どうしても識別子を使うなら、"
              "同じファイルに用語対応表（見出し行が `| 用語 | 日本語の意味 |` の表）を置き、"
              "1列目に識別子、2列目以降に日本語の名前と意味を書く。本文中の括弧書き1回の説明は"
              "対応表の代わりにならない（更新時に探せないため）。一般語なら .claude/report_quality.json の "
              "jargon_allow に追加する。")


def main():
    if _registered_local_copy_exists():
        return
    cfg = _load_cfg()
    if cfg.get("jargon_mode") == "off":
        return
    try:
        import pre_report_quality_guard as PRQ   # same scope rules; also installs the Codex exit-2 contract
    except Exception:
        sys.stderr.write("[jargon_glossary_guard] pre_report_quality_guard.py not found next to this hook; "
                         "reports are NOT being checked.\n")
        return
    try:
        raw = sys.stdin.buffer.read()
        data = _codex_normalize(json.loads(raw.decode("utf-8", "replace")))
        tool = data.get("tool_name") or ""
        ti = data.get("tool_input") or {}
        fp = ti.get("file_path") or ""
        pcfg = PRQ._load_config()
        if not PRQ._in_scope(fp, pcfg, path_only=True):
            return
        try:
            before = PRQ._SFC.read_text(fp)
        except Exception:
            before = ""
        if not before and os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8-sig") as f:
                    before = f.read()
            except Exception:
                before = ""
        if tool == "Write":
            after = ti.get("content") or ""
        elif tool == "Edit":
            old, new = ti.get("old_string"), ti.get("new_string")
            if old is None or new is None:
                return
            after = before.replace(old, new) if ti.get("replace_all") else before.replace(old, new, 1)
        else:
            return
        if not (PRQ._in_scope(fp, pcfg, text=after) or PRQ._in_scope(fp, pcfg, text=before)):
            return
        added = _added(before, after, cfg.get("jargon_allow") or (), cfg.get("jargon_regression") or "key")
        if not added:
            return
        _record_firing("jargon_glossary_guard", data)
        msg = _message(added)
        if cfg.get("jargon_mode") == "warn":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "additionalContext": "⚠ " + msg}}))
        else:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": msg}}))
    except Exception:
        pass


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow", default="", help="comma-separated extra allowed terms")
    ap.add_argument("--strict", action="store_true", help="also flag 2-3 letter acronyms and lone English words")
    a = ap.parse_args(argv)
    global STRICT
    STRICT = bool(a.strict)
    with open(a.input, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    fs = analyze_text(text, [x for x in a.allow.split(",") if x])
    out = sys.stdout.buffer
    if a.json:
        out.write(json.dumps(fs, ensure_ascii=False).encode("utf-8") + b"\n")
    else:
        keys = collections.Counter(f["key"] for f in fs)
        out.write(("%s: %s (%d undefined terms, %d occurrences)\n" % (
            "FAIL" if fs else "PASS", a.input, len(keys), len(fs))).encode("utf-8"))
        for k, c in keys.most_common():
            out.write(("  %s x%d\n" % (k, c)).encode("utf-8"))
    return 1 if fs else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_cli(sys.argv[1:]))
    main()
    sys.exit(0)
