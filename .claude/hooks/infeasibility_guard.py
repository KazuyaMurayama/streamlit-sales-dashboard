# -*- coding: utf-8 -*-
"""Stop hook: do not tell the user "it cannot be done" without having tried.

WHY (2026-10-06, loop action C01 -- reports/CORRECTION_DIGEST_20261005.md)
-------------------------------------------------------------------------
Defect class C01「未検証の断定・捏造」 was #3 in the weekly digest. One
recurring shape inside it: an answer states that a tool / service / format /
platform CANNOT do something (「できない」「非対応」「表示できない」「手段が
ありません」) although nothing in that turn tried it or read a primary source
-- and then stops looking for another way. Real corrections:
    「note は表を表示できないとは本当か？表の画像にすればよいのでは？」
       (2026-09-29, Soulful-Content. The answer had said 「note は表を表示
        できないので、投稿用は表を箇条書きに直し」 after 13 tool calls, none
        of which looked at note.)
    「添付されてたけどもう一回貼る。やり方必ずあるからまた探せ」
       (2026-09-28. The answer had said 「私からシートに書き込む手段が
        ありません」 after three attempts and stopped.)
notfound_guard.py covers "it does not exist" claims against a stale clone;
claims that something is IMPOSSIBLE were not covered by anything.

INVARIANT: an answer may not tell the user that something cannot be done
unless this turn contains an actual attempt or a primary source for that
capability. Otherwise it must try now, or give concrete alternatives.

SCOPE: the FINAL assistant text of the turn only. A claim made in an
intermediate message (text between tool calls) and dropped from the final
answer is out of scope (adversarial case M01) -- the user acts on the final
answer, and reading every interim message would multiply false fires.

WHAT IT DOES (redesigned 2026-10-06 after the Fable attack, see ADVERSARIAL)
---------------------------------------------------------------------------
1. Segments. Code fences and JSON lines are dropped. Everything else is read,
   including headings, list items, "> 注:" quotes, "[注記]" labels and table
   CELLS (each cell is a segment) -- markup does not make a claim less of a
   claim. A 「quote」 is removed unless the answer acts on it as a premise
   (「...」ため / ので / から), so 「〜できない」と書いたのは誤り still passes.
2. Claim = a negated capability, recognised by MORPHOLOGY, not a word list:
     A  <verbal noun / katakana / ASCII / 〜すること>(が|は|も)?(でき|出来)(ない|なく|ません|かね|ず)
        -- 表示できない, レンダリングできません, 表示することはできません,
           表示出来ません, できかねます, できなくなっています
     B  potential forms of native verbs (godan e-row / ichidan られ): 書けない,
        読めません, 見られません, 開けない, 使えない, 貼れない ...
     C  passive negative: 反映されません, 表示されない, 読み込まれていない
     D  非対応 / 未対応 / サポート対象外 / 対応しておりません / 不可(能) / 無理です /
        叶いません / English "does not support|cannot render|not supported|unsupported"
   EXHAUSTIVE = (手段|方法|やり方|手立て|打ち手|打つ手|選択肢|方策|アプローチ) +
     (ない|ありません|存在しない|見当たらない|見つかりませんでした|なさそう), どうやっても.
   No subject is required (それは / omitted subject / 投稿先の側では all count);
   only a cell or clause with no content before the negation (「適用できない」 alone)
   is skipped.
   NOT an assertion -- decided by what FOLLOWS the negation, not by the sentence:
     - condition: 場合/なら/とき/ければ/ても/限り/かも/可能性/ように(purpose)/形に
     - a reported problem named, not asserted: 〜できない原因/理由/件/状態/まま/もの
     - double negation: わけではない/ことはない/とは限らない/ではない,
       〜という制約は見当たらない
     - self-correction: 〜と誤解/勘違い/思い込/書いて/断定
     - a question ATTACHED to the claim (できないのでしょうか？). A trailing
       「…ですか？」 after 「できないので〜しましたが、」 does not hide the premise.
     - attributive status nouns: 未対応項目 / 併用不可の根拠 / 実行不可能な案
     - analytic/evaluative verbs (確認・判断・分離・検証・棄却 ... できない) and
       evidence use (比較に / 証拠として 使えない)
     - a refusal verb (お手伝い/お答え できません)
   Hedges are NOT exemptions any more: 〜できないようなので / でしょうから /
   仕組み / 仕様 / 設計 / 以前確認済み still assert the impossibility and act on it.
   Excuses (searched in the claim's sentence, minus negated phrases such as
   「権限の問題ではなく」「本ガードの話ではありませんが」): our own rules
   (CLAUDE.md / settings / deny / ルールにより / 禁止 / 権限), person-only
   (本人しか / 所有者しか), limits of our guards, and a restated user report
   (ご報告の通り / 伺った通り / とのこと / お手元の). NOT excuses any more:
   ユーザーが / お手伝い / 規約上 (a service's ToS is a checkable capability claim).
3. Evidence (CAPABILITY only) -- a keyword in a tool input is NOT evidence:
     a) a SPECIFIC error quoted in the claim's sentence/line: NOT_FOUND-style
        identifiers, 403 Forbidden / HTTP 404 / エラー 500, タイムアウト, denied,
        FooError, "already in use", 〜と表示された / と返った;
     b) a GENERIC failure word (エラー/失敗/拒否/上記) in the claim's line, or a
        specific error anywhere in the answer, AND this turn really tried
        something: WebFetch/WebSearch, any mcp__* call, or a shell command that
        is not a local read;
     c) a documentation citation (公式/ドキュメント/ヘルプ/URL) AND a fetch-class
        call this turn (WebFetch/WebSearch/browser- or fetch-type mcp);
     d) the claim's subject shares a WHOLE token (note != notebook) with a
        fetch-class call, a ToolSearch query, or an executed command.
   What never counts: Read / Grep / Glob / Edit / Write, read-only shell
   (cd, ls, cat, grep, sed, git status/log/diff/..., Get-Content ...), other
   mcp connector calls by keyword (a Gmail or Drive *search* for "note" is not
   a look at note), filesystem paths inside a command (cd deliverables/note),
   past tense on its own (〜できないことが分かりました/判明 after a Read),
   and a citation with no fetch (「公式ドキュメントによると」, a bare URL, 試しました).
   Offering an alternative does NOT excuse an unchecked claim: the 2026-09-29
   answer offered one (箇条書き) and was still false.
   An EXHAUSTIVE claim is blocked once even with evidence: "no way at all" is
   never proven by the means one happened to try.
4. Block ONCE per instruction (marker keyed on prompt timestamp+text):
   quote the claim, say there was no attempt/primary source, and demand: try
   it or fetch the official docs now, give >=2 concrete alternatives, and if
   it is still impossible, cite the actual error or source text.

CALIBRATION (2026-10-06, tests/calibrate_infeasibility_guard.py, real main-
agent transcripts, this module's decide() imported):
    redesign: 30 days 402 instructions, fires on 4.7% (19: 13 CAPABILITY,
    6 EXHAUSTIVE); 45 days 640 instructions, 6.4% (41).
    C01 corrections caught 4/25 (C01 is mostly wrong facts, dates and URLs --
    out of scope); capability-claim C01 caught 2/4; the real note-table
    pre-correction answer (2026-09-29) BLOCKS, as does the 2026-09-28
    「書き込む手段がありません」 answer.
    The rise from 1.8% is the price of the wider morphology; fires read by
    hand are capability claims about Claude's tools or a service (Apps Script
    の実行履歴は私からは読めません / 私からは会話をクリアできません / Markdown
    の表は表示されません / 一般口座の分は特定口座へ移せません). Generic FP
    shapes found on the way and fixed by rule (not by string): attributive
    未対応項目/不可の根拠, 〜まま/もの/形に, evidence use (比較に使えない),
    analytic 排除/検証/棄却, the excuse placed AFTER the negation
    (〜直せません（値は本人しか持たないため）), git/grep pipes split inside
    quoted patterns, relative paths (deliverables/note/...) in a command.
    Previous version (keyword-overlap evidence, subject required): 1.8% /
    2.2%, but see ADVERSARIAL. First version ever (bare 「〜できない」): 9.3%.
    The two capability C01 misses pass by design: 2026-09-04 cited the real
    error (Browser is already in use); 2026-09-07 had run ToolSearch for
    playwright -- a check was made, it was just wrong. A hook that reads the
    shape of a turn cannot judge whether a check was adequate.

ADVERSARIAL (2026-10-06, independent Fable attack, 85 cases, verbatim in
tests/fixtures/infeasibility_adversarial_20261006.json, all run through the
real hook by tests/test_infeasibility_guard.py):
    before the redesign: evasions caught 0/66, false positives 13/13.
    after:               evasions caught 64/66, false positives 1/13,
                         controls 6/6.
    Structural flaws fixed: (1) keyword overlap with ANY tool input counted as
    verification; (2) past tense was exempt whenever any tool ran; (3) a fixed
    verb list, a required subject, sentence-wide excuse words, a whole-sentence
    「？」 skip, and quote/table/[注記] lines skipped; (4) a citation without a
    fetch counted; (5) policy rules, quoted errors on another line, timeouts,
    the user's environment, double negatives, recaps and self-corrections
    fired. Known gaps (pinned as KNOWN_GAPS in the test): E18 an implicit
    claim with no negation (表示には限界があり、表は崩れます); M01 a claim made
    only in an intermediate message (out of scope); FP12 a user's network
    constraint stated without a recap marker (社内 VPN 外からは ... アクセス
    できない) -- still blocks once.

FAIL-OPEN: any exception -> exit 0. CLAUDE_HEADLESS_JOB=1 -> skip entirely.
LOOP SAFETY: stop_hook_active -> return; one block per instruction.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False

NAME = "infeasibility_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

# ---------------------------------------------------------------- claim detector
_NEG = r"(?:ない|なく|ません|ず)"
# A. 〜できない family: any verbal noun / katakana / ASCII verb + (する)(こと)(が|は|も) + でき/出来 + negation
_CAP_DEKI = re.compile(
    r"(?P<v>[一-龠々ァ-ヴーA-Za-z0-9]{1,15}|[一-龠々ァ-ヴー]{1,6}[ぁ-ん]{0,3}?[うくぐすつぬぶむる](?=こと))"
    r"(?:する)?(?:こと)?(?:が|は|も)?(?:でき|出来)(?:ない|なく|ません|かね|ず)")
# B. potential forms of native verbs (godan え段 / ichidan られ・ら抜き)
_GODAN = ("書き込め|書け|読み込め|読め|見られ|見れ|開け|送れ|貼り付けられ|貼れ|使え|扱え|載せられ|埋め込め|入れられ"
          "|動かせ|呼び出せ|呼べ|取り込め|取れ|出せ|作れ|直せ|変えられ|消せ|置け|残せ|聞け|探せ|渡せ|付けられ"
          "|戻せ|繋げ|つなげ|行え|走らせ|回せ|叩け|触れられ|上げられ|落とせ|拾え|押せ|選べ|移せ|写せ|撮れ"
          "|立ち上げられ|立てられ|飛ばせ|入れ込め|差し込め|組み込め|持ち込め|書き換えられ|登録でき")
_CAP_GODAN = re.compile(r"(?P<v>" + _GODAN + r")" + _NEG)
# C. passive negative: 反映されません / 表示されない / 読み込まれていない
_CAP_PASSIVE = re.compile(
    r"(?P<v>[一-龠々ァ-ヴー]{2,12})され(?:ない|ません|ず)"
    r"|(?P<v2>読み込まれ|有効化され|有効になっ|ロードされ|インストールされ|認識され)て(?:い|お)?(?:ない|ません|りません)")
# D. support / possibility vocabulary
_CAP_SUPPORT = re.compile(
    r"非対応|未対応|(?:対応|サポート)(?:外|対象外)|(?:対応|サポート)(?:して|され(?:て)?)(?:い|お)?(?:ない|ません|りません|ず)"
    r"|不可(?![欠避逆解視分抗侵算知])能?|無理(?=です|でした|だ|がある|があり|なので|なため|のため|。|$)"
    r"|叶い?ません|叶わ(?:ない|ず)"
    r"|\b(?:does not|doesn't|do not|don't|cannot|can't|can not|is not able to|isn't able to|unable to|won't)\s+"
    r"(?:support|render|display|show|access|open|read|write|run|execute|load|connect|edit|upload|embed|be\s+(?:used|displayed|rendered|opened))\b"
    r"|\bnot supported\b|\bunsupported\b|\bnot possible\b|\bno way to\b", re.I)
CAP_PATTERNS = (_CAP_DEKI, _CAP_GODAN, _CAP_PASSIVE, _CAP_SUPPORT)
EXHAUSTIVE = re.compile(
    r"(?:手段|方法|やり方|術|手立て|打ち手|打つ手|選択肢|方策|アプローチ)(?:は|が|も)?(?:何も|一切|他に|もう|どこにも)?"
    r"(?:ない|無い|なく|ありません|存在しない|存在しません|見当たらない|見当たりません|見つか(?:らない|らず|りません|らなかった)|なさそう)"
    r"|どうやっても|いずれの方法でも|どの方法でも")
# what follows the negation. A condition, a relative clause naming a reported
# problem, a double negation, a self-correction or a question attached to the
# claim itself make it something other than an assertion of impossibility.
# NOT here (they still assert): ようなので / でしょうから / 仕組み / 仕様 / 設計.
NOT_ASSERTED = re.compile(
    r"^(?:い|く)?(?:場合|なら|とき|時|ければ|ても|でも|限り|恐れ|可能性|かも|のでは|ように|場面|状況|ケース|範囲"
    r"|原因|理由|件|症状|状態|問題|不具合|現象|(?:の)?まま|もの|形に"
    r"|わけ(?:では|じゃ)|ことは(?:ない|ありません)|とは限ら|では(?:ない|ありません|なく)|じゃない"
    r"|という.{0,12}?(?:見当た[らり]|見つか[らり]|ありませ|なかっ|無)"
    r"|と(?:誤解|勘違い|思い込|思って|書いて|書き|言って|お伝え|説明し|早合点|断定|決めつけ))")
QUESTION = re.compile(r"^(?:の|ん)?(?:でしょう|です|だろう|ます)?か[？?。]?\s*\**\s*$|^[^、。,]{0,8}[？?]\s*\**\s*$")
# analytic / evaluative verbs: 「本データでは分離できない」 is about evidence, not capability
ANALYTIC = re.compile(r"(?:確認|判断|断定|保証|特定|検出|判定|区別|説明|推定|推測|判別|再現|見分け|証明|予測|評価"
                      r"|分離|識別|主張|回避|到達|比較|集計|両立|放置|無視|一致|反論|捕捉|防げ|言え|わから|分から"
                      r"|理解|想像|期待|納得|満足|安心|否定|断言|約束|同意|許容|省略|妥協|看過|容認|楽観|信用|信頼"
                      r"|排除|検証|再計算|計算|算出|棄却|採用)$")
# 「この表は比較に使えない」「証拠として使えない」: a judgement about evidence, not a capability
EVIDENCE_USE = re.compile(r"(?:証拠|根拠|比較|判断|評価|裏付け|材料|指標|参考|判定)(?:として|に|の対象に)(?:は|も)?$")
# the negated verb itself is a refusal of a request, not a capability claim
REFUSAL_VERB = re.compile(r"お手伝い|お答え|お引き受け|お約束|ご案内|ご提供|お受け")
# reasons that make it not Claude's capability claim. Searched in the HEAD only
# (text before the negation), and only when not itself negated
# (「権限の問題ではなく」「本ガードの話ではありませんが」 do not excuse).
EXCUSE = re.compile(
    r"権限|許可|承認|ポリシー|deny|禁止|ルール(?:により|上|で|に従|に基づ)|CLAUDE\.md|settings(?:\.json)?|安全上|倫理"
    r"|(?:者|人|オーナー)(?:しか|にしか|だけ|のみ)"
    r"|ご本人|本人(?:しか|にしか|のみ|だけ|が|は|側)|あなた(?:しか|にしか|側でしか)|ユーザー(?:しか|にしか|側でしか)"
    r"|このフック|本フック|このガード|本ガード|機械(?:的)?(?:には|では)|正規表現では|この検査"
    # the user's own report / environment, restated
    r"|(?:伺っ|ご報告|ご指摘|おっしゃっ|お知らせいただ|教えていただ)[^、。]{0,4}通り|とのこと|お手元|お使いの|ご利用の")
# a noun-type negation used attributively (未対応項目, 併用不可の根拠, 実行不可能な案) names a
# status, it does not assert that something cannot be done.
ATTRIBUTIVE = re.compile(r"^(?:の(?!で|ため|は|に)|な(?!ので|ため|のは|ん)|[一-龠ァ-ヴ])")
NEGATED_EXCUSE = re.compile(r"[^、。,]{0,24}(?:ではなく|ではありませんが|ではないが|じゃなくて|とは関係なく)[、,]?")

# ---------------------------------------------------------------- evidence
# A specific error identifier quoted in the claim's own line is evidence by itself.
SPECIFIC_ERR = re.compile(
    r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}\b|(?:HTTP|[Ss]tatus|ステータス|エラー|[Ee]rror)\s*[:：]?\s*[45]\d\d\b"
    r"|\b[45]\d\d\s*(?:Forbidden|Not Found|Unauthorized|Bad|Internal|Too Many|Service|エラー|[Ee]rror)"
    r"|\b[45]\d\d(?=\s*(?:を返|が返|で失敗|で拒否|応答))|Forbidden|Unauthorized|[Dd]enied"
    r"|[Tt]ime(?:d\s?)?out|タイムアウト|\bE[A-Z]{4,}\b|\b\w*(?:Error|Exception)\b|already in use|[Nn]ot [Ff]ound|No such"
    r"|と(?:表示され|返(?:さ|っ|り|し)|出(?:た|ま|て))|というエラー")
# generic words for "it failed": evidence only if this turn really tried something
GENERIC_ERR = re.compile(r"エラー|失敗|拒否|弾かれ|止められ|応答(?:が)?な|返って|\berror\b|\bfailed\b|上記", re.I)
# a citation of documentation: evidence only if this turn fetched something
DOC_CITE = re.compile(r"公式|ドキュメント|ヘルプ|仕様書|規格|https?://|docs?\b", re.I)
FETCH_TOOL = re.compile(r"^(?:WebFetch|WebSearch)$|^mcp__.*(?:playwright|[Bb]rowser|chrome|[Ff]etch|puppeteer|computer)", re.I)
EXEC_TOOL = ("Bash", "PowerShell")
READONLY_CMD = {
    "cd", "ls", "dir", "cat", "type", "head", "tail", "more", "less", "grep", "egrep", "rg", "find", "wc", "echo",
    "printf", "sed", "awk", "sort", "uniq", "cut", "tr", "pwd", "which", "where", "file", "stat", "du", "df", "diff",
    "true", "test", "basename", "dirname", "realpath", "jq", "tee", "xargs", "nl", "column",
    "get-childitem", "get-content", "select-string", "test-path", "get-item", "measure-object", "select-object",
    "where-object", "foreach-object", "sort-object", "format-table", "format-list", "write-output", "write-host",
    "out-string", "get-location", "set-location", "resolve-path", "split-path", "join-path"}
READONLY_GIT = {"status", "log", "diff", "show", "ls-files", "ls-tree", "grep", "branch", "rev-parse", "blame",
                "remote", "config", "shortlog", "describe", "tag", "stash", "fetch", "add", "commit", "restore", "checkout"}
# a filesystem path (absolute or relative) is not a look at the service whose name it
# contains (cd deliverables/note && ...). URLs and registry keys (HKCU/...) are kept.
_FS_PATH = re.compile(r"(?<![\w:/.])(?!HK[A-Z_]*[\\/])(?![a-z]+://)[^\s\"'|;&<>=]*[\\/][^\s\"'|;&<>]*")
STOP = {"claude", "code", "ファイル", "ツール", "こちら", "それ", "これ", "ため", "もの", "こと", "場合",
        "現在", "今回", "以下", "上記", "必要", "可能", "対応", "方法", "手段", "表示", "実行", "利用",
        "使用", "機能", "設定", "環境", "画面", "内容", "一覧", "結果", "回答", "作業", "セッション",
        "the", "md", "py", "com", "www", "https", "http", "json", "txt", "html", "and", "for", "from", "with"}


def _strip_prefix(line):
    """Drop list/heading/quote/label markup so a claim wearing it is still read."""
    return re.sub(r"^\s*(?:(?:>+|#+|[-*+・]|\d+[.)])\s*|\[[^\]\n]{1,12}\]\s*|(?:注|留保|制約|補足|備考|Note|NB)\s*[:：]\s*)*",
                  "", line)


def _clean_line(line):
    l = re.sub(r"`([^`\n]{0,200})`", r"\1", line)          # inline code: keep the name
    # 「claim」ため / ので / から: a quoted premise the answer acts on -> keep its text.
    # Any other 「quote」 (「...」と書いたのは誤り, a cited user message) is removed.
    l = re.sub(r"「([^」]{0,200})」(?=\s*(?:ため|ので|から|、|ことから|を前提|という前提|の(?:で|ため)))", r"\1", l)
    l = re.sub(r"「[^」]{0,200}」", "「」", l)
    return _strip_prefix(l)


def _segments(answer):
    """(segment, cleaned line, raw line). A segment is a sentence (ends at 。！!？? or
    a line break) or a table cell. Code fences and JSON lines are dropped."""
    a = re.sub(r"```.*?```", " ", answer or "", flags=re.S)
    out = []
    for raw in a.splitlines():
        st = raw.strip()
        if not st:
            continue
        if re.match(r"^[\[{]\s*(?:[\"\]}\d]|$)", st) or re.match(r'^[\[{].*"\s*:', st):
            continue                                             # JSON
        if st.startswith("|"):
            if re.match(r"^\|[\s:|-]+\|?$", st):
                continue                                         # table separator
            parts = [c for c in st.strip("|").split("|")]
        else:
            parts = [raw]
        for part in parts:
            line = _clean_line(part)
            for s in re.split(r"(?<=[。！!？?])", line):
                if s.strip():
                    out.append((s, line, raw))
    return out


def _content(s):
    return re.sub(r"[\W_]", "", s)


def find_claims(answer, had_tools=False):
    """[(kind, sentence, line, head, raw line)] for assertions that something cannot be done.
    `had_tools` is kept for API compatibility; past tense is NOT exempt any more."""
    out = []
    for s, line, raw in _segments(answer):
        st = s.strip()
        m = EXHAUSTIVE.search(s)
        if m:
            head, rest = s[:m.start()], s[m.end():]
            hv = re.sub(r"(?:する|できる|の)?$", "", head.rstrip())
            if (not NOT_ASSERTED.match(rest) and not QUESTION.match(rest) and _content(head + "x")
                    and not re.search(r"(?:もし|仮に|場合は)", head) and not ANALYTIC.search(hv)):
                out.append(("EXHAUSTIVE", st, line, head, raw))
            continue
        found = None
        for pat in CAP_PATTERNS:
            for m in pat.finditer(s):
                v = (m.groupdict().get("v") or m.groupdict().get("v2") or "")
                head, rest = s[:m.start()], s[m.end():]
                if NOT_ASSERTED.match(rest) or QUESTION.match(rest) or re.search(r"(?:もし|仮に)", head):
                    continue
                if v and (ANALYTIC.search(v) or REFUSAL_VERB.search(v)):
                    continue
                if pat is _CAP_DEKI and ANALYTIC.search(re.sub(r"(?:すること|こと)?(?:が|は|も)?$", "", head)):
                    continue
                if len(_content(head)) < 2 and pat is not _CAP_SUPPORT:
                    continue                                     # bare 「適用できない」 cell: no subject at all
                if EVIDENCE_USE.search(head):
                    continue                                     # 比較に使えない / 証拠として使えない: about evidence
                if pat is _CAP_SUPPORT and ATTRIBUTIVE.match(rest):
                    continue                                     # 未対応項目 / 併用不可の根拠 / 不可能な案
                if EXCUSE.search(NEGATED_EXCUSE.sub("", head + " / " + rest)):
                    continue
                found = (m.start(), ("CAPABILITY", st, line, head + v, raw))
                break
            if found:
                break
        if found:
            out.append(found[1])
    return out


def _tokens(text):
    ks = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", text or ""):
        w = w.lower()
        if len(w) >= 2 and w not in STOP:
            ks.add(w)
    for w in re.findall(r"[ァ-ヴー]{2,}|[一-龠々]{2,}", text or ""):
        if w not in STOP:
            ks.add(w)
    return ks


keywords = _tokens


def _shares(claim_ks, text):
    tk = _tokens(text)
    for k in claim_ks:
        if k.isascii():
            if k in tk:
                return True
        elif any(k in t or t in k for t in tk if not t.isascii() and len(t) >= 2):
            return True
    return False


def _is_readonly(cmd):
    cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\1\s*$", " ", cmd or "", flags=re.S | re.M)  # heredoc bodies
    cmd = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " Q ", cmd)                                # quoted arguments
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        w = re.sub(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*", "", seg).strip().split()
        if not w:
            continue
        exe = re.split(r"[\/]", w[0].strip("&'\""))[-1].lower()
        exe = re.sub(r"\.exe$", "", exe)
        if exe == "git":
            sub = next((x for x in w[1:] if not x.startswith("-")), "")
            if sub in READONLY_GIT:
                continue
            return False
        if exe not in READONLY_CMD:
            return False
    return True


def _classify(name, inp):
    """'fetch' (looked at the service / docs), 'exec' (ran something that is not a
    local read), 'search' (ToolSearch), 'mcp' (other connector call) or None."""
    if not isinstance(inp, dict):
        inp = {}
    if FETCH_TOOL.search(name or ""):
        return "fetch"
    if name == "ToolSearch":
        return "search"
    if (name or "").startswith("mcp__"):
        return "mcp"
    if name in EXEC_TOOL:
        return None if _is_readonly(inp.get("command", "")) else "exec"
    return None                                                   # Read / Grep / Glob / Edit / Write / git reads


def tool_text(name, inp):
    """Text of a call that can show the capability itself was looked at. Local
    reads (Read / Grep / Glob / Edit, read-only shell) contribute nothing."""
    try:
        kind = _classify(name, inp)
        if kind in ("fetch", "search"):
            return name + " " + json.dumps(inp, ensure_ascii=False)
        if kind == "exec":
            return _FS_PATH.sub(" ", " " + str(inp.get("command", "")))
    except Exception:
        pass
    return ""


def has_evidence(sent, line, raw, head, tools, answer):
    """Why this turn shows the capability was actually checked ("" if it does not)."""
    kinds = [(_classify(n, i), n, i) for n, i in tools]
    attempted = any(k in ("fetch", "exec", "mcp") for k, _, _ in kinds)
    fetched = any(k == "fetch" for k, _, _ in kinds)
    here = sent + "\n" + line + "\n" + raw
    if SPECIFIC_ERR.search(here):
        return "specific error quoted"           # 「NOT_FOUND で失敗」「403」「接続タイムアウト」
    if attempted and (GENERIC_ERR.search(here) or SPECIFIC_ERR.search(answer)):
        return "attempted + failure reported"    # tried now, and the failure is reported
    if fetched and DOC_CITE.search(here):
        return "fetched + source cited"          # fetched now, and the source is cited
    ks = {k.lower() if k.isascii() else k for k in _tokens(head[-60:])}
    if not ks:
        return ""
    for k, n, i in kinds:
        if k in ("fetch", "search", "exec") and _shares(ks, tool_text(n, i)):
            return "ran/fetched: " + n               # looked at / ran the named thing itself
    return False


def decide(answer, tools):
    """Return (kind, claim sentence) for the first unchecked claim, or None.
    `tools` is a list of (name, input dict) of this turn's tool calls."""
    tools = [(n or "", i if isinstance(i, dict) else {}) for n, i in (tools or [])]
    for kind, sent, line, head, raw in find_claims(answer, bool(tools)):
        if kind == "EXHAUSTIVE":
            return kind, sent
        if has_evidence(sent, line, raw, head, tools, answer or ""):
            continue
        return kind, sent
    return None


def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    """A prompt the user typed -- not a tool result or harness notification."""
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def _tool_uses(d):
    c = (d.get("message") or {}).get("content")
    if not isinstance(c, list):
        return []
    return [(b.get("name") or "", b.get("input") or {}) for b in c
            if isinstance(b, dict) and b.get("type") == "tool_use"]


def read_turn(tp):
    """(last human prompt, its timestamp, final assistant text, tool calls of this turn)."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    prompt, pts, answer, tools = None, "", "", []
    for line in data:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            prompt, pts, answer, tools = _text(d.get("message")).strip(), d.get("timestamp", ""), "", []
        elif d.get("type") == "assistant":
            tools.extend(_tool_uses(d))
            t = _text(d.get("message")).strip()
            if t:
                answer = t
    return prompt, pts, answer, tools


def main():
    if os.environ.get("CLAUDE_HEADLESS_JOB") == "1":
        return
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", os.path.basename(__file__)))
        if os.path.normcase(me) != os.path.normcase(local) and os.path.exists(local):
            return
    except Exception:
        pass
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if ev.get("stop_hook_active"):
        return
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return
    prompt, pts, answer, tools = read_turn(tp)
    hit = decide(answer, tools) if prompt else None
    if not hit:
        return
    key = hashlib.sha1((pts + (prompt or "")).encode("utf-8", "replace")).hexdigest()[:16]
    mark = os.path.join(STATE_DIR, "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_") + "_" + key)
    if os.path.exists(mark):
        return          # already blocked once for this instruction
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    kind, sent = hit
    claim = sent if len(sent) <= 160 else sent[:157] + "..."
    if kind == "EXHAUSTIVE":
        head = ("【不可能の断定（1回のみ）】回答が「手段・方法が無い」と言い切っている（「%s」）。"
                "試した手段が幾つあっても、それで「方法が無い」ことは証明できない。" % claim)
    else:
        head = ("【不可能の断定（1回のみ）】回答が「できない／非対応」と断定している（「%s」）が、"
                "このターンにその可否を実際に試したツール呼び出しも、公式ドキュメント等の一次資料の取得も無い。" % claim)
    reason = head + (
        "今このターンで次を行い、回答し直せ。"
        "①実際に試す（コマンド・ブラウザ・コネクタで操作する）か、公式ドキュメント/ヘルプを WebFetch・WebSearch で取得する。"
        "使えるツールが不明なら ToolSearch で探す。"
        "②代わりの具体策を少なくとも2つ示す（例: 表なら画像化・埋め込み・別形式。書き込みなら別コネクタ・API・スクリプト）。"
        "③それでも不可能なら、実際のエラーメッセージか一次資料の該当文を引用して根拠を示す。"
        "根拠なしに「できない」と書いて代替探しを止めないこと（CLAUDE.md §14 F1・F2）。")
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
