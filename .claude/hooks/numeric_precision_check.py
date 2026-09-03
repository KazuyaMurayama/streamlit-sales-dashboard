# -*- coding: utf-8 -*-
"""Detect over-precision numbers in report text (有効数字4桁ルール / 2026-07-24 指示).

Rule: displayed values use 4 significant figures (round at the 5th).
  OK : 187.8万円, 83.06%, 1234, 0.9983
  NG : 2278.8212180746564万円, 29.113456%

Scope guards (false-positive avoidance) — the checker deliberately IGNORES:
  - fenced code blocks and inline code (raw/full-precision values are allowed there)
  - dates (2026-07-24), times, version strings (v1.2.3), file names
  - long digit strings without a decimal point (IDs, sha, 12桁マイナンバー, epoch ms)
  - values inside HTML comments
Only decimal numbers with >4 significant digits in PROSE/TABLE text are flagged.
"""
import re

# a decimal number, optionally signed, captured with its surroundings
# Boundaries must be ASCII-aware only. Python's \w matches Japanese characters,
# so `(?![\w])` silently skipped every number followed by 万円/%/かな — i.e. almost
# all real report values. (Found 2026-08-04 by auditing the checker's own misses.)
NUM = re.compile(r"(?<![0-9A-Za-z_.])(-?\d+\.\d+)(?![0-9A-Za-z_.])")
DATEISH = re.compile(r"\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|v?\d+\.\d+\.\d+")
# A line quoting a source's own measurement. Rounding these would misquote the
# source, so the 4-sigfig rule does not apply to them.
CITATION_CTX = re.compile(
    r"et al\.|\(20\d\d\)|\b(?:RCT|SD|CI)\b|[Pp]\s*[<=]\s*0?\.\d|95%\s*CI|"
    r"\bn\s*=\s*\d|\bN\s*=\s*\d|arxiv|doi|"
    # 「253.89 ± 5.59 mg CE/g」等の実測値±SD 表記。丸めると出典の誤引用になる。
    r"±|\+/-", re.I)


def _strip_uncheckable(text):
    """Blank out regions where full precision is legitimate, preserving offsets."""
    out = list(text)

    def blank(m):
        # Preserve newlines. Blanking them collapsed the line count (331 -> 315 in
        # one real report), so the line number computed from the scanned text no
        # longer indexed the same line in the raw text — the citation/±/P<0.05
        # guards were silently consulting the WRONG line and never fired on real
        # files, even though they passed on isolated strings.
        # (2026-08-04, found by diffing scan vs raw newline counts.)
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "

    for m in re.finditer(r"```.*?```", text, flags=re.DOTALL):
        blank(m)
    for m in re.finditer(r"`[^`\n]*`", text):
        blank(m)
    for m in re.finditer(r"<!--.*?-->", text, flags=re.DOTALL):
        blank(m)
    for m in DATEISH.finditer(text):
        blank(m)
    # DOI / URL / citation identifiers are not measurements (found in real-world QC
    # 2026-08-03: doi 10.1371 etc. were flagged as over-precision).
    for m in re.finditer(r"(?:doi:?\s*|https?://\S*?)10\.\d{4,9}/\S*", text, flags=re.I):
        blank(m)
    for m in re.finditer(r"\b10\.\d{4,9}(?:/\S*)?", text):
        blank(m)
    for m in re.finditer(r"https?://\S+", text):
        blank(m)
    # --- classes added after the 2026-08-04 sample audit of 233 alleged TPs ---
    # arXiv IDs (2203.11171, arXiv:1706.03762) dominated the "over-precision"
    # bucket. They are identifiers, and their YYMM. prefix mimics a decimal.
    for m in re.finditer(r"arxiv:?\s*\d{4}\.\d{4,5}(?:v\d+)?", text, flags=re.I):
        blank(m)
    for m in re.finditer(r"(?<![\d.])(?:1[6-9]|2[0-9])(?:0[1-9]|1[0-2])\.\d{4,5}(?![\d])", text):
        blank(m)
    # ISO-8601 timestamps with fractional seconds (created_at: ...T02:37:31.815138)
    for m in re.finditer(r"\d{1,2}:\d{2}:\d{2}\.\d+", text):
        blank(m)
    # Statutory / spec constants: exact by definition, rounding them is WRONG.
    # 20.315% = 所得税15%+復興特別2.1%+住民税5%（申告分離課税）
    # 55.945% = 所得税45%+復興特別+住民税10%（総合課税の最高税率）
    # 99.97x% = HEPA等級, 13.333in = PowerPoint 16:9 スライド幅, 365.2422 = 太陽年
    CONSTANTS = (r"20\.315|55\.945|99\.99[0-9]|13\.333|11\.733|"
                 r"365\.24\d*|1\.0000|0\.0000")
    for m in re.finditer(r"(?<![0-9.])(?:" + CONSTANTS + r")(?![0-9])", text):
        blank(m)
    # --- classes added after the 2026-08-04 in-scope audit (38件中35件が誤検知) ---
    # Markdown table alignment rows: |---:|---:|---:| — the dashes+colons were
    # being read as digits by the surrounding scan and mis-attributed to whatever
    # numbers sat nearby, producing phantom values with wrong line numbers.
    for m in re.finditer(r"^\s*\|[\s:|-]+\|\s*$", text, flags=re.M):
        blank(m)
    # 通貨建ての価格は末尾 .99/.95 等が実際の価格であり丸めると誤記になる。
    for m in re.finditer(r"[$¥€£]\s?\d[\d,]*\.\d+", text):
        blank(m)
    # 通貨単位が日本語で後置される場合（576.07ドル / 8.71ドル/日 / 1234.56円）。
    # 実際に授受された金額は事実そのものであり、丸めると史実・記録の誤記になる。
    # （2026-08-04 実コーパス: エーリック＝サイモン賭けの清算額「576.07ドル」を誤検知）
    for m in re.finditer(r"\d[\d,]*\.\d+\s*(?:ドル|円|ユーロ|ポンド|元|ウォン)", text):
        blank(m)
    # 暗号資産の数量は「4桁に丸める」と別の金額になる（0.78049 BTC / 1.5625 BTC は
    # 3.125÷2 の厳密値）。単位付きの数量は full precision が正しい。
    for m in re.finditer(r"\d+\.\d+\s*(?:BTC|ETH|XRP|SOL|BNB|枚|oz|ct)\b", text, flags=re.I):
        blank(m)
    # 年.月 のバージョン/シーズン表記（2025.05 今季完売 / v2025.05）
    for m in re.finditer(r"(?<![\d.])(?:19|20)\d{2}\.(?:0[1-9]|1[0-2])(?![\d])", text):
        blank(m)
    # 規格・試験法の番号（AOAC 2011.25法 / JIS Z 8801.1）は名称であって測定値ではない。
    for m in re.finditer(r"(?:AOAC|JIS|ISO|ASTM|IEC|EN)\s*[A-Z]?\s*\d+(?:\.\d+)+", text):
        blank(m)
    # 法定開示された料率（信託報酬・実質コスト等）は開示値そのもの。丸めると誤記になる。
    for m in re.finditer(r"(?:信託報酬|管理報酬|経費率|実質コスト|報酬率)[^\n]{0,24}?\d+\.\d+\s*%",
                         text):
        blank(m)
    for m in re.finditer(r"年率?\s*\d+\.\d+\s*%\s*(?:（税込）|\(税込\))", text):
        blank(m)
    return "".join(out)


def sigfigs(numstr):
    """Count significant figures of a decimal string."""
    s = numstr.lstrip("-").replace(".", "")
    s = s.lstrip("0")  # leading zeros are not significant (0.9983 -> 9983)
    return len(s.rstrip()) if s else 0


def analyze_text(text):
    """Return a list of findings: dicts with line, value, sigfigs, suggestion."""
    if not text:
        return []
    scan = _strip_uncheckable(text)
    lines_raw = text.split("\n")
    findings = []
    for m in NUM.finditer(scan):
        raw = m.group(1)
        n = sigfigs(raw)
        if n <= 4:
            continue
        line = scan.count("\n", 0, m.start()) + 1
        # Cited third-party measurements must be reproduced verbatim; rounding a
        # source's reported figure misquotes it. (2026-08-04 audit: RCT rows such
        # as "内臓脂肪面積: 105.33→101.15 cm² (P<0.05)" were flagged.)
        src = lines_raw[line - 1] if line - 1 < len(lines_raw) else ""
        if CITATION_CTX.search(src):
            continue
        try:
            val = float(raw)
            # round to 4 significant figures for the suggestion
            from decimal import Decimal
            if val == 0:
                sug = "0"
            else:
                import math
                exp = math.floor(math.log10(abs(val)))
                q = round(val, -(exp - 3))
                sug = ("%g" % q)
        except Exception:
            sug = "(4桁に丸める)"
        findings.append({"line": line, "value": raw, "sigfigs": n, "suggestion": sug})
    return findings
