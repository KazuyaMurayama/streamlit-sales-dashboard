# -*- coding: utf-8 -*-
"""Shared library: did an update touch the late body but leave the opening stale?

WHAT THIS ENFORCES
------------------
The user's rule (2026-09-11): a report's opening must carry the important
points of every chapter, more important material earlier, and an UPDATE must
refresh that opening -- not append a new final chapter. "The first 20% should
carry 80% of the value."

WHAT IS ACTUALLY ENFORCEABLE (be honest about the gap)
------------------------------------------------------
Only part of it. This module checks ONE invariant:

    the document HAS an opening summary section,
    the edit changed >= K lines outside the opening block,
    and the opening block came out byte-identical

That is a property of the DIFF. It does not and cannot measure "the opening
states the important points" (naming a section is not summarising it), nor
"more important material earlier" (importance is a judgement). Those stay with
review_gate.py and the human. Claiming more would repeat the mistake this
module was built after.

WHY NOT A VOCABULARY CHECK (measured 2026-09-11, design REJECTED)
------------------------------------------------------------------
The first design flagged late headings whose "finding words" (訂正/未確認/誤り
/リスク...) did not appear in the opening. An adversarial review by a different
model built a faithful prototype and ran it over 254 real reports:

    fires on 57/254 files (22.4%), 69 findings, precision ~3 in 10
    19 concrete bypasses, 12 false positives (11 from real files)

The three that killed it:
  * The design's OWN headline example was silent. COCONALA_COPY_20260820.md
    L412 「存在しないURLを本人に提示した」 contains no finding word. Corpus-wide,
    17 of 18 late headings dated after 作成日 have none -- the vocabulary
    discards 94% of real appended updates.
  * A 目次 neutralises it completely: prepending a TOC drops findings 1 -> 0,
    because every heading's words now appear in the opening. 34/254 files
    already have one.
  * False positives cluster on reports ABOUT problems: 「## 問題集計」,
    「### 6-3 失敗事例 ― New Coke」, 「### 5-1. 撤回型」, and
    「### 6-6. 大きな Vault の性能 — 実測済み（問題なし）」 -- flagged by the
    word 問題 in a heading that says there is no problem.

A guard that is right 3 times in 10 gets muted. This module therefore uses NO
vocabulary at all: nothing to dodge by renaming a heading, and a TOC changes
nothing because the test is whether the opening block's BYTES changed.

THE OPENING BLOCK -- measured, not chosen (259 reports >= 60 lines)
-------------------------------------------------------------------
    has a 結論/サマリー/要約/概要/Executive/TL;DR section :  93 (36%)
    else ends at the first horizontal rule                 : 153
    else falls back to 20% of the document                 :  13
    resulting size: median 4.7% of the doc, p10 1.3%, p90 19.6%

So the 結論-section rule alone would cover only a third of real reports; the
`---` fallback carries most of them. Both were needed.

BUT THE `---` FALLBACK WAS INITIALLY WRONG (fixed 2026-09-11). These repos put
a horizontal rule directly under the 作成日:/最終更新日: block, so the fallback
returned an "opening block" of 5-8 lines holding the H1 and two dates. 66 of
120 flagged updates were that shape: no conclusion inside the block, therefore
every edit anywhere in the document counted as a late-only append. A rule is
now treated as a front-matter terminator whenever nothing but the title, blank
lines and metadata precedes it -- see _has_prose(). The earlier `i > 3` cutoff
assumed YAML at lines 1-3 and caught none of these.

CALIBRATION (git history as ground truth, not invented cases)
--------------------------------------------------------------
Replayed the most recent real update of every in-scope report across 43 repos.
905 tracked report files; 337 of them have >= 2 commits and so have a genuine
before/after pair to judge.

    K=1  fires on 161/337 updates (47.8%)
    K=3  fires on 121/337 (35.9%)
    K=5  fires on 107/337 (31.8%)   <- the bare diff invariant, BEFORE the
    K=10 fires on  83/337 (24.6%)      has_conclusion() gate below
    K=20 fires on  43/337 (12.8%)

A FIRST PASS ON 30 FILES SAID 20.0% AND THAT NUMBER WAS WRONG. The sample was
one repo's worth of history; the full corpus is 337 pairs and 31.8%. Recorded
here because the small-sample figure is exactly the kind of self-flattering
calibration this module's own rules forbid.

WHERE THE FIRING ACTUALLY COMES FROM (measured, and it matters)
    docs WITH a 結論/サマリー section : 108 of 337; K=5 fires on 26 (24.1%)
    docs WITHOUT one                 : 229 of 337; K=5 fires on 81

So 81 of 107 firings (76%) are on reports that have NO opening summary at all.
On those the guard is not detecting "the summary went stale" -- there is no
summary to go stale, the 20%-fallback opening block is arbitrary, and every
future edit will fire again. Per the user's rule such a report IS defective,
but a warning that repeats on every update of a file the author is not going to
restructure is the definition of a guard that gets muted.

FINAL SHIPPED CONFIGURATION -- K=5 plus the has_conclusion() gate

    raw K=5                      107/337 (31.8%)
    + has 結論                    26/337 ( 7.7%)
    + date-bump bypass CLOSED     29/337 ( 8.6%)  <- SHIPPED
    + has 結論 AND new heading    14/337 ( 4.2%)  rejected, see analyze()

The +3 between 7.7% and 8.6% are updates that were INVISIBLE until
_opening_signature() stopped counting a mandatory 最終更新日 bump as "the
opening was refreshed". One of them, Soulful-Content 70b23868, is a plan
RETRACTION appended as a new final chapter -- the user's complaint verbatim.

7.7% is the number to hold this module to. For scale, this codebase already
ruled that 35.9% meant 形骸化確実 and narrowed that hook to 1.8%. The 4.2%
variant was tighter still but bought that tightness by reopening three bypasses
in the author's own writing style, which is the wrong side of the one
requirement stated most plainly: 「『発火しない』というミスを…繰り返しています」.

PRECISION, by reading all 26 flagged late sections (not a sample): about 18 are
genuine -- roughly 7 in 10, against ~3 in 10 for the rejected vocabulary design.
Representative true positives, each appended while the opening stayed
byte-identical:

    「⚠️ 価格の不整合を是正した。…最低料金が 6,000円 のまま、実売は 7,000円」 L380
    「⚠️ §4.7 で訂正した。ゼロは法が求める水準ではない」                        L65
    「§0 で『最大の限界』としたジャンルの偏りが、その後の1,069本で解消した」      L103
    「⚠️ 2026-08-25 に目標が手取り月30万円・2経路へ改定された」                 L167

Note what the third and fourth do: they INVALIDATE a claim the opening still
makes, from the bottom of the document. That is the failure mode the user
described, and no vocabulary list would catch them.

The remaining ~8 are appended tables -- a 2x2 impact/difficulty matrix repeated
across three generated enterprise reports, an anti-pattern table, a product
link table. Legitimate detail expansion. They are the accepted cost: warn-mode
means an author can read the line and move on.

K=5 keeps the real violations (COCONALA commit 363da05 added 33 lines at L380
and touched nothing else -> fires, outside=33, opening_end=14) while letting a
typo-fix pass. K is configurable per repo via .claude/report_quality.json.

NOT A HOOK BY ITSELF. summary_freshness_guard.py drives it at Stop, because
PreToolUse(Write|Edit) cannot see a file written by a Bash heredoc. (An earlier
version of this line claimed "0 of 3 report writes went through Write|Edit" --
that was a single session. Corpus-wide across 770 transcripts it is Write 916 /
Edit 3,614 / Bash 621, so Bash is ~12%. The Stop design is still right, but for
the weaker reason that SOME writes bypass the tool, not all of them.)
"""
import io
import os
import re

CONCLUSION_RE = re.compile(
    r"^#{1,3}\s*[\d.§\s]*"
    u"(結論|サマリー|要約|概要|まとめ|Executive|TL;?DR|Summary)",
    re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,3}\s")
RULE_RE = re.compile(r"^---+\s*$")
REPORT_NAME_RE = re.compile(r"_\d{8}(?:-v\d+)?\.(md|markdown|mdx)$", re.I)
SCOPE_DIRS = ("outputs/", "reports/", "docs/", "output/", "report/", "_meta/")
# Never our own analysis prose: generated data, third-party material, and the
# test fixtures that must quote violations verbatim to be evidence.
EXCLUDE_DIRS = ("data/", "materials/", "drafts/", "node_modules/", "session/",
                ".git/", "vendor/", "fixtures/", "tests/", "_archived",
                "_archive/", ".venv/")


def _has_dir(path_lower, name):
    """True if `name` is a WHOLE path segment of path_lower.

    Substring matching is wrong here and was a real bug: "AppData/" contains
    "data/", so every file under C:\\Users\\<u>\\AppData\\... was silently
    excluded -- including the temp dirs the tests run in, which made the
    end-to-end case look like the guard was dead (measured 2026-09-11).
    Compare segments, not substrings.
    """
    seg = name.lower().strip("/")
    return ("/" + seg + "/") in path_lower


def in_scope(path):
    q = (path or "").replace("\\", "/")
    if not re.search(r"\.(md|markdown|mdx)$", q, re.I):
        return False
    low = "/" + q.lower()
    for d in EXCLUDE_DIRS:
        # "_archived" is a prefix marker, not a full segment name.
        if d.endswith("/"):
            if _has_dir(low, d):
                return False
        elif d.lower() in low:
            return False
    if REPORT_NAME_RE.search(os.path.basename(q)):
        return True
    return any(_has_dir(low, d) for d in SCOPE_DIRS)


FRONTMATTER_RE = re.compile(
    r"^\s*(?:[-*>|]|\d+\.|\*\*|__)*\s*"
    u"(?:作成日|最終更新日|更新日|日付|作成者|著者|バージョン|版|対象|"
    u"Date|Author|Version|Updated|Created|Status|Tags?)"
    r"\**\s*[:：]")


def _has_prose(lines):
    """Does this candidate opening block contain anything but a title and metadata?

    Measured 2026-09-11: this is the single biggest source of false firing. 66 of
    120 flagged updates had an "opening block" of <=8 lines, because these repos
    put the horizontal rule directly under 「最終更新日:」 -- so the block held the
    H1 and two date lines and nothing else. There is no conclusion in it to go
    stale, and every edit anywhere in the document therefore looked like a
    late-only append. The rule is a front-matter terminator whenever nothing but
    the title, blank lines and metadata precedes it, regardless of line number
    (the earlier `i > 3` cutoff assumed YAML at lines 1-3 and missed all of these).
    """
    for l in lines:
        t = l.strip()
        if not t:
            continue
        if t.startswith("#"):
            continue                      # the title itself
        if RULE_RE.match(t):
            continue                      # a YAML opener
        if FRONTMATTER_RE.match(t):
            continue
        if re.match(r"^[A-Za-z_][\w.-]*\s*:", t):
            continue                      # generic YAML key
        return True
    return False


def opening_end(lines):
    """Index (exclusive) where the opening block ends.

    Priority, in the order measured to matter:
      1. the end of the first 結論/サマリー/... section        (36% of reports)
      2. the first horizontal rule after the front matter     (153 of 259)
      3. 20% of the document                                  (13 of 259)
    """
    n = len(lines)
    if n == 0:
        return 0
    limit = max(1, int(n * 0.5))
    for i, l in enumerate(lines[:limit]):
        if CONCLUSION_RE.match(l):
            for j in range(i + 1, n):
                if HEADING_RE.match(lines[j]):
                    return j
            return n
    limit = max(1, int(n * 0.3))
    for i, l in enumerate(lines[:limit]):
        if RULE_RE.match(l) and _has_prose(lines[:i]):
            return i
    return max(10, int(n * 0.20))


def _norm(lines):
    """Trailing whitespace is not a content change."""
    return [l.rstrip() for l in lines]


def _opening_signature(lines):
    """The part of the opening block that carries MEANING.

    ⛔ THE BUG THIS EXISTS FOR (found by adversarial QC, 2026-09-11, and it was
    already live in git history). The first version compared the opening block
    byte-for-byte. But CLAUDE.md §10b REQUIRES bumping 最終更新日 on every
    update, and that line lives inside the opening block. So:

        follow the documented rule  ->  the opening block differs
                                    ->  analyze() returns None
                                    ->  the guard is silent

    Obeying the rules disabled the guard. The known true positive (COCONALA
    363da05) was caught ONLY because that update also forgot the date bump.

    Not hypothetical -- Soulful-Content 70b23868 is the shape verbatim:

        -**作成日**: 2026-09-02 ／ **最終更新日**: 2026-09-02
        +**作成日**: 2026-09-02 ／ **最終更新日**: 2026-09-04
        +## §10 本人検証の結果と訂正（2026-09-04 追記）

    A plan RETRACTION ("14日プラン撤回") appended as a new final chapter, the
    opening otherwise untouched -- the user's complaint word for word, and the
    shipped guard said nothing.

    So the comparison drops what cannot carry a conclusion: metadata lines,
    blank lines, and horizontal rules; and normalises whitespace so that a
    stray space or a full-width space cannot be used to dodge the check.
    """
    out = []
    for l in lines:
        t = l.strip()
        if not t:
            continue                        # blank-line churn is not content
        if RULE_RE.match(t):
            continue
        if FRONTMATTER_RE.match(t):
            continue                        # 最終更新日 etc -- REQUIRED to change
        out.append(re.sub(r"[\s　]+", " ", t))
    return out


def analyze(before_text, after_text, k=5):
    """Return a finding dict, or None.

    finding = {"outside": <lines changed after the opening block>,
               "opening_end": <line number>,
               "first_late_line": <1-based line of the first late change>}

    Returns None when the opening block changed, when the document is short,
    or when fewer than k lines changed outside it.
    """
    if not after_text:
        return None
    after = _norm(after_text.split("\n"))
    if len(after) < 60:
        return None                     # too short to have a buried section
    before = _norm((before_text or "").split("\n"))
    if not before:
        return None                     # brand-new file: nothing to compare

    oend = opening_end(after)
    # Compare MEANING, not bytes -- a 最終更新日 bump is mandatory and must not
    # count as "the opening was refreshed". See _opening_signature().
    #
    # Each side's opening block is located independently: inserting one blank
    # line near the top shifts opening_end by one, so slicing BEFORE at AFTER's
    # index compares misaligned regions and the signatures differ for a reason
    # that has nothing to do with the conclusion (adversarial QC case A2).
    before_sig = _opening_signature(before[:opening_end(before)])
    if before_sig != _opening_signature(after[:oend]):
        return None                     # the opening WAS refreshed -- correct

    import difflib
    sm = difflib.SequenceMatcher(None, before[oend:], after[oend:],
                                  autojunk=False)
    outside = 0
    first = None
    new_heading = None
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        outside += max(i2 - i1, j2 - j1)
        if first is None:
            first = oend + j1 + 1
        if new_heading is None:
            for l in after[oend + j1:oend + j2]:
                if HEADING_RE.match(l) or l.startswith("####"):
                    new_heading = l.strip()
                    break
    if outside < k:
        return None

    # --- the two narrowing conditions (measured 2026-09-11) -----------------
    # Unfiltered, this fires on 107 of 337 real updates (31.8%). This codebase
    # has already ruled on that number once: unverified_identifier_guard was
    # measured at 35.9%, judged 形骸化確実, and narrowed to 1.8%. Shipping at
    # 31.8% would repeat a mistake already written down.
    #
    # (1) The document must HAVE an opening summary. 81 of the 107 firings were
    #     on reports with no 結論/サマリー section at all -- there the guard is
    #     not detecting a stale summary, it is re-reporting a structural defect
    #     the author is not fixing this turn, on every future edit forever.
    # REJECTED NARROWING 1 -- "the late change must add a HEADING". Tempting: it
    #     is literally what the user described (「新しく最後の章を追加していく」)
    #     and it measured 14 of 337 (4.2%) with good precision. It was dropped
    #     because it reopens three bypasses from the adversarial corpus, and
    #     all three are this author's normal writing style, not contrived:
    #       A8  **判定（2026-08-27 追検証）**: ...   a bolded verdict line
    #       A9  > **2026-08-01 の変更**: ...        a blockquote
    #       A6  | 7 | 訂正: 122名 -> 269名 |        a row added to a table
    #     A guard with a documented evasion that matches how the user actually
    #     appends findings fails the one requirement stated most plainly:
    #     「『発火しない』というミスをあなたは繰り返しています」. The heading is
    #     still REPORTED when present -- it just cannot gate the finding.
    #
    # REJECTED NARROWING 2 -- "pure append" (nothing deleted). This is why
    #     reasoning alone is untrustworthy here: it sounds like the exact
    #     definition of tacking on a chapter, measures 27 (8.0%), and LOSES
    #     COCONALA 363da05, because that edit touched one line while appending
    #     its 33. Unmeasured, it would have shipped a guard blind to the very
    #     case it was built for.
    if not has_conclusion(after):
        return None

    return {"outside": outside, "opening_end": oend,
            "first_late_line": first or (oend + 1),
            "new_heading": new_heading}


def has_conclusion(lines):
    """Does the document open with a 結論/サマリー-style section at all?

    Takes the already-split lines. Only the first half is searched: a 「まとめ」
    at the very end of a long report is a closing section, not an opening one.
    """
    if isinstance(lines, str):
        lines = lines.split("\n")
    return any(CONCLUSION_RE.match(l)
               for l in lines[:max(1, int(len(lines) * 0.5))])


def read_text(path):
    """Decode whatever encoding the file is in. Empty string on failure."""
    try:
        raw = io.open(path, "rb").read()
    except Exception:
        return ""
    for enc in ("utf-8-sig", "utf-8", "cp932", "euc-jp", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def unreferenced_sections(text):
    """Sections whose number the opening block never mentions.

    A weaker, secondary proxy for 「冒頭が全章の要点を含む」. Naming a section
    is NOT summarising it -- 「詳細は §8」 passes this and states nothing -- so
    this is advisory only and never blocks. Reported so the author can see
    which chapters the opening ignores entirely.
    """
    lines = text.split("\n")
    if len(lines) < 60:
        return []
    oend = opening_end(lines)
    opening = "\n".join(lines[:oend])
    out = []
    for l in lines[oend:]:
        m = re.match(r"^##\s*(?:§\s*)?(\d+(?:\.\d+)?)", l)
        if not m:
            continue
        num = m.group(1)
        if re.search(r"(?:§|#|\bsection\s*)?\b" + re.escape(num) + r"\b",
                     opening):
            continue
        out.append((num, l.strip()[:60]))
    return out
