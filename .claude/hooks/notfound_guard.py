# -*- coding: utf-8 -*-
"""Stop hook: never assert "it does not exist" from a stale local clone.

THE DEFECT THIS EXISTS FOR (measured 2026-08-26)
------------------------------------------------
The user asked whether two reports existed. Both did — on the GitHub remote,
and both were listed in the cross-repo index. The answer said they did not,
because every search ran against the LOCAL working tree and a LOCAL copy of
`index/REPORT_INDEX.md`:

    deep-research              local main was  7 commits behind ( 9 .md unseen)
    academic-research-agent_v1 local master   11 commits behind ( 4 .md unseen)
    claude-governance/index    local copy 1 commit behind -> 0 keyword hits,
                               remote copy same day        -> 12 keyword hits

`find` and `grep -r` read bytes on disk. They cannot see a file that was never
pulled. Treating their silence as proof of absence is the same error shape as
reading an unauthenticated `gh` failure as a 404 — a tool that CANNOT see the
thing returns empty, and empty gets read as "not there".

WHY PROSE COULD NOT HAVE PREVENTED IT
-------------------------------------
CLAUDE.md §14 F1 already says to confirm remote state with `git ls-tree
origin/<branch>`. It did not fire, for the reason this whole hook system
exists: rules requiring the author to opt in do not run when the author feels
certain. Nothing felt wrong — `find` had "already answered". Worse, F1's own
line "ファイルの存在 -> ls / Glob" positively licensed the local scan.

So the trigger cannot be the model's judgement. It has to be the SHAPE OF THE
CLAIM. Any answer that asserts what does or does not exist gets checked against
whether this turn actually looked at the remote.

DETECTION: two layers, calibrated red-green on the real failing answer
----------------------------------------------------------------------
L1 negation — 存在しません / 見つかりません / 該当なし / ヒットしません ...
L2 inventory claim — a COUNT or exhaustiveness word about repos/files
   (「全走査」「1本しか」「50リポ中…42」「登録件数: 0」).

L2 is not redundant. Two of the six real misses contained no negation at all;
they were counts. A count about what exists IS an existence claim, and it is
exactly how the error was phrased. Measured on the verbatim failing answer:
L1 alone = 3 false negatives; L1+L2 = 0, with 0 false positives over a control
set of 6 legitimate count sentences ("12件ヒットしました", "11/11 PASS").

The scan runs over the WHOLE answer, not sentence-by-sentence: the disclaiming
sentence and the count that licensed it were adjacent in the real transcript.

EVIDENCE OF LOOKING: a `git fetch`/`ls-remote`/`git show origin/...` (or the
GitHub API) in THIS turn's tool calls. Absent that, an existence claim is
unverified and the hook blocks once with instructions.

DELIBERATELY NOT DONE
---------------------
Does not block on a fetch that merely happened — it cannot tell whether the
search that followed was well-formed. It closes the "never looked" hole, which
is the one that actually fired. Nor does it auto-run fetch: a Stop hook that
mutates 43 repos as a side effect would be a far worse failure than the bug.

LOOP SAFETY: `stop_hook_active` -> return, so at most one block per answer.
FAIL-OPEN: any exception -> exit 0.
Deployed from claude-governance/templates/hooks/ — edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "notfound_guard")

# --- L1: explicit absence -------------------------------------------------
NEG = re.compile(
    u"存在しません|存在しない|存在せず|見つかりません|見つからな|見つけられ"
    u"|見当たりません|見当たらな|該当なし|該当する[^。]{0,12}(ない|ありません)"
    u"|しか存在|のみ存在|ヒットしません|ヒットしない|1件も|一件も"
    u"|未作成|作成されていません|登録されていません|保存されていません"
    u"|記録されていません|残っていません|残っていない"
    # Plain negation. The adversarial pass broke the guard with nothing more
    # exotic than 「ありません」 and 「確認できませんでした」 -- 11 of 34 cases.
    # Bare 「ない」 is deliberately NOT here: it is too common in ordinary prose
    # and INV/PROPER_NOUN carry the rest of the discrimination.
    u"|ありません|ありませんでした|無いです|無いようです|ないようです"
    u"|確認できません|確認できなかった|取得できません|参照できません"
    # Round 5: four more measured misses. 「0件」 is the count form of
    # absence and appeared verbatim in a slipped case.
    u"|発見できません|発見できなかった|検出されません|検出されなかった"
    u"|確認できず|見つけられず|0件でした|ゼロ件"
    u"|(?:は|も|が)[^。\n]{0,8}(?:未確認|不明)です",
    re.IGNORECASE)

# English is a separate pattern purely so IGNORECASE cannot leak into the
# Japanese alternatives above (it would not matter today, but the two vocab
# sets drift independently). Sentence-initial "Not found" used to miss.
NEG_EN = re.compile(
    r"not\s+found|no\s+such\s+file|does\s+not\s+exist|doesn't\s+exist"
    r"|no\s+match|nothing\s+found|no\s+record|no\s+trace"
    r"|could\s?n[o']t\s+find|unable\s+to\s+find|couldn't\s+locate"
    r"|there\s+is\s+no\b|there\s+are\s+no\b|not\s+present",
    re.IGNORECASE)

# --- L2: inventory / exhaustiveness claim ---------------------------------
INV = re.compile(
    u"(リポ|repo|ファイル|件数|本|件|個)[^。\n]{0,10}"
    u"(しかない|だけ|のみ|は\\d+|:\\s*\\d+|＝\\s*\\d+|=\\s*\\d+)"
    u"|全走査|全て検索|すべて検索|全リポ|全リポジトリ|横断検索"
    u"|網羅的に(探|検索|走査)|全ファイルを(検索|走査|確認)")

# Evidence that the remote was actually consulted this turn.
REMOTE = re.compile(
    r"git\s+fetch|git\s+ls-remote|git\s+ls-tree\s+origin|git\s+show\s+origin"
    r"|git\s+log\s+origin|git\s+pull|api\.github\.com|gh\s+api"
    # Round 5: a BARE `origin/main` no longer counts. `git diff origin/main`
    # and `--set-upstream-to=origin/main` read a LOCAL ref that can be days
    # stale -- precisely the 2026-08-26 shape. Only the verbs above, which
    # actually contact the remote, clear this gate.
    )

# The cross-repo index is NOT sufficient evidence of absence. It is rebuilt by
# cron at 21:00 UTC daily, so a file committed after the last build stays
# invisible to it for up to 24h WHILE THE INDEX ITSELF STILL LOOKS CURRENT.
# Measured on the two files that caused this hook: SELF_ESTEEM was invisible
# for 4.9h, PROTAGONIST v3 for 16.3h. A second session independently made this
# same mistake — it confirmed the index covered "全47リポ・1034件" but never
# compared the index build time against the file's creation time. Coverage was
# right; the time axis was never checked. So an index read does NOT clear this
# gate; only a ref/API lookup, which sees a file committed minutes ago, does.
INDEX_ONLY = re.compile(r"REPORT_INDEX|search_reports\.py")

# Local-only search tools: their emptiness proves nothing about the remote.
#
# `search_reports.py` and a bare REPORT_INDEX read belong here too: both answer
# from a local snapshot that can trail the remote, and a session that ran only
# those still believes it "searched everything".
LOCAL_ONLY = re.compile(
    r"\bfind\b|\bgrep\b|\bls\b|\brg\b|Glob|Grep"
    r"|search_reports\.py|REPORT_INDEX")


# --- THE 2026-08-31 DEFECT: an existence claim resting on NOTHING AT ALL ---
#
# Measured on the verbatim answer (fixture: tests/fixtures/defect_20260831.txt):
#     zero tool calls  -> SILENT   <- the miss
#     one local grep   -> BLOCK
# The user asked about a person whose record sat in outreach/MATCHER_LOG.md,
# committed and pushed 11 days earlier. The answer said the record could not be
# found after searching nothing, because three compactions had dropped the
# context (compact_boundary at transcript rows 996/2402/2755; the 2402 and 2755
# summaries retained 0 occurrences of Matcher/the person's name/outreach).
#
# The old LOCAL_ONLY precondition made this UNREACHABLE: it required evidence of
# a local search before nagging, so "searched, wrongly" was caught while
# "searched nothing" walked free. The incentive was exactly inverted -- the
# cheapest way to pass the gate was to do no work.
#
# Not every unsourced negation should block: an ordinary conversational "there
# is no such option" must stay silent. The discriminator is whether the claim is
# about a NAMED THING -- a person, a file, a repo path, an identifier. Those are
# recoverable by search, so asserting their absence without one is not licensed.
# Sentences whose absence-claim is about the world, not about this repo's
# contents, plus completion reports that happen to name a file. Six measured
# false-positives all had this shape; none is recoverable by searching, so
# forcing a lookup would be pure friction.
BENIGN = re.compile(
    # General knowledge / API surface: the absence is a fact about the
    # world, not about this repo, so no search could confirm it.
    u"(?:Python|Node|Java|Go|Rust|Ruby|PHP)[ \u3000]*[0-9.]*[ \u3000]*(?:\u3067\u306f|\u306b\u306f)"
    u"|(?:\u30aa\u30d7\u30b7\u30e7\u30f3|\u30d5\u30e9\u30b0|\u5f15\u6570|\u30d1\u30e9\u30e1\u30fc\u30bf|\u30e1\u30bd\u30c3\u30c9|\u95a2\u6570|\u5c5e\u6027|\u30ec\u30a4\u30e4|\u30e2\u30fc\u30c9|\u6a5f\u80fd)"
    u"[^\u3002\n]{0,20}(?:\u306f|\u304c)[^\u3002\n]{0,10}"
    u"(?:\u5b58\u5728\u3057\u307e\u305b\u3093|\u3042\u308a\u307e\u305b\u3093|\u6307\u5b9a|\u4e0d\u8981|\u306e2|\u306e\u307f)"
    # Completion / test reports that merely name a file.
    u"|(?:\u3059\u3079\u3066|\u5168\u3066)[ \u3000]*PASS"
    u"|[0-9]+[ ]*/[ ]*[0-9]+[ ]*(?:PASS|passed)"
    u"|\u66f4\u65b0\u6e08\u307f"
    u"|\u5909\u66f4\u306f[^\u3002\n]{0,20}(?:\u306e\u307f|\u3060\u3051)\u3067\u3059"
    u"|(?:\u79fb\u884c|\u8ffd\u52a0|\u524a\u9664|\u4fee\u6b63)\u3057\u3066\u304f\u3060\u3055\u3044"
    # A pointer to documentation is not an absence claim about a repo.
    u"|see[ ]+[A-Za-z0-9_./-]+[ ]+for[ ]+details"
    # Round 5: the most common completion phrases in this repo's own
    # answers. They assert an absence of PROBLEMS, not of files.
    u"|\u554f\u984c(\u306f)?\u3042\u308a\u307e\u305b\u3093"
    u"|\u554f\u984c\u306a\u3057|\u30a8\u30e9\u30fc(\u306f)?\u3042\u308a\u307e\u305b\u3093"
    u"|\u30a8\u30e9\u30fc\u306f\u3042\u308a\u307e\u305b\u3093\u3067\u3057\u305f"
    u"|\u5931\u6557(\u306f)?\u3042\u308a\u307e\u305b\u3093|no\u005ferrors?\b"
    # Round 6: progress/no-concern replies. 「特にありません」 answers a
    # question about opinions, and 「残り3件」 reports work state -- neither
    # asserts that a file is absent, and no search could confirm either.
    u"|\u7279\u306b(\u306f)?\u3042\u308a\u307e\u305b\u3093"
    u"|\u7279\u306b(\u306f)?\u306a\u3044|\u7279\u6bb5(\u306f)?\u3042\u308a\u307e\u305b\u3093"
    u"|\u6b8b\u308a(\u306f)?[^\u3002\n]{0,12}\u4ef6"
    u"|\u9032\u6357|\u5b8c\u4e86\u3057\u307e\u3057\u305f|\u5bfe\u5fdc\u6e08\u307f",
    re.IGNORECASE)

PROPER_NOUN = re.compile(
    # Honorifics: 様 and all-hiragana names were missing, so 「よしだ様」 walked.
    u"[\u3040-\u309f\u4e00-\u9fff\u30a0-\u30ff]{2,}[\u3000 ]*"
    u"(?:\u3055\u3093|\u69d8|\u6c0f)"
    # A file name with an extension.
    r"|[A-Za-z0-9_/-]{3,}\.(?:md|py|js|ts|json|ya?ml|txt|csv)"
    # A path-like token. Requires a segment >=4 chars containing _ or - or an
    # uppercase run, so and/or, TCP/IP, read/write and http://host/docs no
    # longer qualify -- all four were measured false-positives.
    r"|(?<![:/\w])[A-Za-z][A-Za-z0-9_-]{3,}/[A-Za-z0-9_-]{4,}(?![/\w])"
    r"|MATCHER|HANDOFF|BUSINESS\.md|REPORT_INDEX")

# Searching one's OWN transcript is what recovers a compaction-dropped fact, so
# a turn that did it has performed the step this branch exists to force.
SELFREF = re.compile(
    r"\.claude[/\\]projects[/\\][^\s\"']*\.jsonl")

REASON = (
    u"【存在ゲート】この回答は「無い／これだけしかない」という趣旨の"
    u"存在に関する主張を含むが、このターンでリモートを見た形跡がない。\n"
    u"ローカルの作業ツリーは古い可能性がある。実測（2026-08-26）では "
    u"deep-research が7コミット、academic-research-agent_v1 が11コミット遅れ、"
    u"未取得の .md が計13本あった。find / grep はディスク上のバイトしか"
    u"読まないので、pull していないファイルは原理的に見えない。\n"
    u"以下を実行してから、結論を述べ直すこと:\n"
    u"1) 対象リポで `git fetch origin -q` を実行する"
    u"（横断的に探すなら `python .claude/scripts/sync_all.py`）\n"
    u"2) 作業ツリーではなく **リモートのツリー** を検索する:\n"
    u"   `git ls-tree -r origin/<branch> --name-only | grep -i <KEY>`\n"
    u"   ※ ブランチは推測せず `git rev-parse --abbrev-ref '@{u}'` で取得。"
    u"master のリポもある\n"
    u"3) 横断インデックスはローカルを信用せず必ずリモート版を使う:\n"
    u"   `git show origin/main:index/REPORT_INDEX.md`"
    u"（claude-governance。ローカル版は 0 件、リモート版は 12 件ヒットした）\n"
    u"4) 索引は H1 タイトルのみを持つ。章見出しや本文の語は載らないので、"
    u"索引が空でも本文 grep は別途行う\n"
    u"5) **索引の鮮度を確認する**。索引は 21:00 UTC の cron 生成なので、"
    u"その後に作られたファイルは最大24時間ぶん載らない"
    u"（実測: SELF_ESTEEM 4.9時間、PROTAGONIST v3 16.3時間ぶん不可視）。"
    u"索引冒頭の生成時刻と、探しているファイルの想定作成時期を突き合わせよ。"
    u"**「索引に無い」は「存在しない」ではない**\n"
    u"確認の結果やはり存在しないなら、**何をどう調べたか**（fetch 済み・"
    u"検索した ref・検索語）を明示した上でそう述べてよい。"
)

def _sid(ev):
    s = ev.get("session_id") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64]


def _load(p):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(p, d):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def _read_turn(transcript_path):
    """Return (answer_text, tool_text, user_question) for the latest turn.

    `user_question` matters because an answer may refer to the subject only by
    pronoun (「お尋ねの記録は見つかりません」). The name that makes the claim
    checkable sits in the question, so PROPER_NOUN scans both.

    `tool_text` concatenates the commands/inputs of this turn's tool calls, so
    the hook can tell whether the remote was consulted.

    Only the last 4000 rows are considered. NOTE: readlines() still reads the
    whole file into memory -- the window bounds the PARSING cost, not the I/O.
    Measured 0.15s on a 33MB transcript, 0.57s on 200MB, which is why this has
    not been optimised further.
    """
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-4000:]
    except Exception:
        return "", "", ""

    rows = []
    for ln in lines:
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue

    def _text(r):
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result"
                   for b in c):
                return None
            return next((b.get("text") for b in c
                         if isinstance(b, dict) and b.get("type") == "text"),
                        None)
        return c if isinstance(c, str) else None

    user_idx = [i for i, r in enumerate(rows)
                if r.get("type") == "user" and _text(r)]
    if user_idx:
        start = user_idx[-1]
        ask = _text(rows[start]) or ""
    else:
        # A turn with more than 4000 rows pushes its own user row out of the
        # window. Returning "" here silenced the guard for exactly the turns
        # that ran the most tools -- where an unverified absence claim is most
        # likely, not least. Scan the whole window instead and lose only `ask`.
        start = -1
        ask = ""

    answer, tools = [], []
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in ((r.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                answer.append(b.get("text") or "")
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                for k in ("command", "pattern", "path", "file_path",
                          "prompt", "query"):
                    v = inp.get(k)
                    if isinstance(v, str):
                        tools.append(v)
    return "\n".join(answer), "\n".join(tools), ask


def main():
    # Defer to a registered repo-local copy, matching the existing convention.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return

    if ev.get("stop_hook_active"):
        return

    tp = ev.get("transcript_path")
    if not tp:
        return
    answer, tools, ask = _read_turn(tp)
    if not answer:
        return

    # Split into sentences so BENIGN can be judged against the sentence that
    # actually carries the claim. Scanning the whole answer meant one stray
    # "26/26 PASS" cleared the gate for every other sentence in the turn --
    # measured as 6 straight bypasses of the real 2026-08-31 defect text.
    sentences = [t for t in re.split(u"[。\n]", answer) if t.strip()]
    claim_sents = [t for t in sentences
                   if NEG.search(t) or NEG_EN.search(t) or INV.search(t)]
    if not claim_sents:
        return

    # A claim survives only if its OWN sentence is not benign.
    live = [t for t in claim_sents if not BENIGN.search(t)]
    if not live:
        return

    # Did this turn actually consult the remote?
    #
    # Reading the index does not count on its own (see INDEX_ONLY): it lags
    # file creation by up to 24h. Require evidence of a ref/API lookup, which
    # would see a file committed minutes ago.
    # Evidence must be a TOOL CALL, never prose. The block message below
    # quotes `git fetch` / `git ls-tree origin` verbatim, so an answer that
    # merely echoed the instructions used to clear this gate without running
    # anything (measured: 3 cases).
    if REMOTE.search(tools):
        blob = (tools or "") + "\n" + (answer or "")
        ref_lookup = re.search(
            r"git\s+fetch|git\s+ls-tree|git\s+ls-remote|git\s+pull"
            r"|git\s+log\s+origin|api\.github\.com|gh\s+api", tools or "")
        if ref_lookup or not INDEX_ONLY.search(blob):
            return

    # Two ways to reach a block.
    #
    # (a) The claim rests on a local-only search, whose emptiness proves nothing
    #     about the remote. This is the 2026-08-26 shape.
    # (b) The claim rests on NO search at all and names a thing the user asked
    #     after. This is the 2026-08-31 shape -- see PROPER_NOUN above.
    #     Requiring LOCAL_ONLY here previously let this walk free.
    #
    # A turn that grepped its own transcript has done the recovery step that (b)
    # exists to force, so SELFREF clears it.
    # Recovering a compaction-dropped fact means grepping this session's own
    # transcript -- and that grep is itself a `grep`, so LOCAL_ONLY matches it
    # too. Checked in the other order, the turn that did exactly the right
    # thing fell into branch (a) and got blocked anyway. SELFREF wins.
    if SELFREF.search(tools):
        return

    if not LOCAL_ONLY.search(tools):
        # Nothing was searched. Block only when the claim names something a
        # search could have settled -- in the claim sentence itself or in the
        # question it answers.
        subject = "\n".join(live)
        if not (PROPER_NOUN.search(subject) or PROPER_NOUN.search(ask)):
            return

    # One block per answer-shape per session.
    path = os.path.join(STATE_DIR, _sid(ev) + ".json")
    key = hashlib.sha1(answer.encode("utf-8", "replace")).hexdigest()[:16]
    if _load(path).get("key") == key:
        return
    _save(path, {"key": key})

    # ensure_ascii=True + BYTES: under Windows CP932 several kanji end in byte
    # 0x5C (「表」= 0x95 0x5C), which is read back as a backslash and kills the
    # payload with "Invalid \escape". Do not simplify to print(ensure_ascii=False).
    payload = json.dumps({"decision": "block", "reason": REASON},
                         ensure_ascii=True)
    sys.stdout.buffer.write(payload.encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
