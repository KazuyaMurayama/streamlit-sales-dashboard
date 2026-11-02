# -*- coding: utf-8 -*-
"""Stop hook: do not assert the state of something outside this machine without reading it this turn.

WHY (2026-11-02, loop action C01 -- reports/CORRECTION_DIGEST_20261102.md)
-------------------------------------------------------------------------
Defect class (no proper nouns): 画面・リモート・シート・公開ページ・デプロイ先の
「いまの状態」を、このターンに実際に取得せず、前回の作業の記憶から現在形・完了形で
断定する（「表示されています」「push 済みです」「本番は〜を使っています」）。
Real corrections (index/correction_history.jsonl, class C01):
    2026-10-30 tax-advisor 「表示されてないと思います。添付のようになってますよ。
        再度ログインはしてます」 -- the answer had told the user that the
        connection screen was up on the other Chrome and to leave it open.
    2026-10-08 nasdaq_backtest 「ちゃんとスプレッドシートみろ。ポジションサイズ
        間違えてるぞ」 -- the answer had said 「本番 GAS は実際の運用額を使って
        います。発注目安は、Positions の実残高2,601万円を基準に計算されています」
        in a turn whose only external read was `git ls-tree origin/main` (it
        proves the push claim in the same answer, not the sheet claim).

WHY A NEW HOOK, NOT AN EXTENSION
--------------------------------
  - unverified_identifier_guard.py checks IDENTIFIERS (URLs) inside a
    hand-off. Neither defect contained a URL; both were state claims.
  - infeasibility_guard.py checks NEGATED CAPABILITY (「できない」). Its claim
    morphology, exemptions and evidence rules are tuned to that shape, it is
    itself under redesign (C01, 10 recurrences after adoption), and adding a
    second claim family would make its calibration unreadable.
  - batch_verify_guard.py only runs when the turn CHANGED something. The
    measured defect is the opposite: nothing was touched this turn, the
    claim was carried over from memory.
  - notfound_guard.py covers "it does not exist" from a stale clone only.
  Shared code is reused, not copied: codex_transcript.resolve (transcript
  adapter) and firing_log.record (firing ledger).

INVARIANT
---------
The FINAL assistant text of the turn asserts, in the present-perfect /
progressive / completed form, the state of one of these external kinds:
    SCREEN   画面・ブラウザ・タブ・ログイン状態の表示       (表示されています / 開いたままです)
    REMOTE   GitHub・origin・リモートブランチ               (push 済み / GitHub 上にあります)
    SHEET    スプレッドシート・GAS・トリガー                (シートに入っています / GAS は〜を使っています)
    PUBLISH  公開ページ・デプロイ先・本番                   (公開済み / 本番に反映されています)
and THIS TURN (since the last human prompt) contains no tool call that reads
or contacts that kind of state:
    SCREEN   browser / computer-use / chrome MCP, WebFetch, Read of an image,
             an image the user attached, the Artifact tool
    REMOTE   git push / fetch / ls-remote / pull / ls-tree|log|show|diff|
             rev-parse on origin, gh api|pr|repo, api.github.com, GitHub MCP
    SHEET    gviz / docs.google.com/spreadsheets / sheets.googleapis /
             script.google.com / clasp pull|push|run|logs|deploy..., Google
             Drive|Sheets MCP, a browser call in a turn that touched those hosts
    PUBLISH  WebFetch, curl / wget / Invoke-WebRequest / requests / urllib,
             browser MCP, the Artifact tool, deploy commands
-> block once per instruction, quoting the sentence and naming the read that
   is missing.
Contact counts, not correctness (same rule as unverified_identifier_guard):
`git push` in the turn is evidence for a 「push しました」 claim because its
output is the state. A hook that reads the shape of a turn cannot judge
whether the read it finds was the right one (the 2026-10-30 turn did read a
browser -- the other account's one); that residual is listed under KNOWN GAPS.

NOT AN ASSERTION (decided per sentence; the sentence still has to carry the
kind's predicate to be a claim at all):
    - explicitly unverified: 未確認 / 未検証 / 確認していない / 確かめていない /
      見ていない / 不明 / 分かりません  (the user asked for exactly this marker)
    - conditional or open: the predicate is followed by なら / 場合 / とき /
      れば / ても / か(どうか) / ように / 予定, or the sentence ends in ？
    - a restatement of what the user reported: とのこと / ご報告 / 伺った /
      おっしゃる / 添付の画像 / お手元
    - quoted 「...」 text and fenced code are removed before reading
NOT exempt: はず / と思います / でしょう. A guess about the current state,
handed to the user as the state, is the defect; write 未確認 or go and look.
A subagent's report (Agent tool) is NOT evidence -- it is a self-report
(AGENTS.md §5.3). See CALIBRATION for what that costs.

CALIBRATION (2026-11-02, tests/calibrate_external_state_claim_guard.py,
decide() imported, newest 120 main-agent transcripts under ~/.claude/projects,
instructions de-duplicated by (timestamp, prompt) because resumed sessions
repeat earlier rows):
    first draft     600 instructions, 38 fires = 6.3%. Read by hand: about
                    20 FP, dominated by the nouns 記事 / ページ (local
                    manuscripts, 「記事の中心になっていました」), セル inside
                    キャンセル, 「表示されています」 about a report table, the
                    generic 「になっています」 (「GitHub に上げない設定に
                    なっています」 = local .gitignore), and conditions placed
                    BEFORE the predicate (「採用と言っていただければ、本番に反映」).
    after the fixes 800 instructions (2026-09-09..11-02), 16 fires = 2.0%;
                    1500 instructions (2026-07-14..11-02), 47 fires = 3.1%
                    (PUBLISH 19 / REMOTE 16 / SHEET 8 / SCREEN 4).
                    The 16 of the 800 window read by hand: 11 match the
                    invariant (7 「push 済み」 in turns with no tool call at
                    all, 「本番 GAS は実際の運用額を使っています」, 「GAS の仕組み
                    （本番に反映済み）」, 「GitHub に secrets が登録されていない」,
                    「有料記事はまだ公開されていない」); 5 are low-value FP: four
                    restate a long-settled fact (「nt-001 は note で公開済み」)
                    and one is a local manuscript (「公開記事に…残っていたので
                    消しました」). Kept: there is no shape that separates
                    "settled long ago" from "remembered from last turn".
    C01 recall: 2026-10-08 sheet case BLOCKS; 2026-10-30 screen case passes
    (KNOWN GAP G1+G2: that answer presupposed the screen with 「出ていても」
    and the turn did call browser tools -- on the other account's Chrome).
    RED/GREEN: tests/test_external_state_claim_guard.py 28/28 with this hook
    (29/29 with --old-hooks); with a no-op in its place the 8 RED cases
    (incl. one Codex rollout) FAIL; `--old-hooks` replays the
    RED cases through the 25 other Stop hooks in HOOK_MANIFEST: none blocks on
    the state claim (review_gate blocks the GAS case once with its generic
    self-review, near_duplicate_guard on an unrelated file rule).

V2 (2026-11-02, after an independent Sonnet attack: ~110 inputs, 45 misses /
~26 FP on v1; verbatim in tests/fixtures/external_state_attack_20261102.json)
    exempt now: negatives (していません / されていません / 済みではありません /
    されておらず), 済みの+noun and 済み列, でしたら / であれば / だったら,
    instructions (〜てください), '...' quotes, local artefacts (ローカル・手順書・
    設計・コード上・下書き・*.md の列), 「※シートは未確認」 waives only SHEET
    (a nounless 「ただし未確認」 waives the sentence before it); a condition
    clause (〜れば、) and a restatement exempt only within their own clause.
    stricter evidence: REMOTE = fetch / ls-remote / pull / push / gh api|pr /
    api.github.com in THIS turn, not swallowed (|| true) and not reported as
    failed in its tool_result; bare `git log|ls-tree origin/...` no longer
    counts. PUBLISH = curl/wget/requests..., not a bare URL / echo / clone /
    pip. browser & WebFetch count only when their host (input URL, the
    result's "Page URL", or the last navigation) matches the claim's target.
    vocabulary: 入りました / 反映されました / 更新しました / 稼働中 / 正常に動作 /
    配信 / 差分はありません / 一致・同期しています / ブランチは main だけ /
    リモートブランチを削除しました / 入れました / アップしました / 走っています.
    scope: the final answer is every text block after the last tool call,
    joined; the one-block marker uses uuid / timestamp and falls back to the
    prompt's ordinal + claim (same prompt text typed again is not suppressed).
    tests: 174/174 (with --old-hooks); the v1 copy passes 109/173 (61 attack +
    3 turn-shape cases FAIL). 800 instructions: 25 fires = 3.1% (v1 2.0%);
    read by hand ~15 match the invariant, ~10 FP: nt-001 公開済み x3,
    「画面に出ていて止められない」 (explanation), 「VS Code のウィンドウが開いて
    いるため残っています」, 「2026年公開で…上位に入っています」 (third-party
    stats), 「note を入口として使っている」, a browser sheet write whose
    run_code result names no URL, a local manuscript, one unclear.
    V2 known gaps: English claims; bare 「main にあります」; no MAIL kind
    (メールは送信されました); ls-remote of another repo; an old image Read;
    an unspecific claim (本番に反映) accepts any HTTP contact; 「でも」 is no
    longer an exemption (「push 済みでも問題ありません」 blocks).

KNOWN GAPS
----------
    G1 the read was of the wrong object (other browser profile, other sheet
       tab): passes -- contact is checked, not identity.
    G2 a state claim with no state predicate (「接続画面のタブが出ていても…
       そのまま残してください」 presupposes the screen without asserting it).
    G3 claims made only in an intermediate message are out of scope (the user
       acts on the final answer), as in infeasibility_guard.
    G4 English-only claims ("it's deployed") are not read.

FAIL-OPEN: any exception -> exit 0. CLAUDE_HEADLESS_JOB=1 -> skip.
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
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:  # adapter missing: say so, do not fail silently
    def _codex_transcript(p, *_a, **_k):
        if p:
            sys.stderr.write("[external_state_claim_guard] codex_transcript.py not found next to this hook; "
                             "Codex transcripts are NOT being read." + chr(10))
        return p

NAME = "external_state_claim_guard"
TAIL_BYTES = 4 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

KINDS = ("SCREEN", "REMOTE", "SHEET", "PUBLISH")
LABEL = {"SCREEN": "画面・ブラウザの表示", "REMOTE": "リモート（GitHub・origin）",
         "SHEET": "スプレッドシート・GAS", "PUBLISH": "公開ページ・デプロイ先"}
HOWTO = {
    "SCREEN": "browser_snapshot / browser_take_screenshot（本人の Chrome なら playwright-ext）で今の画面を取る",
    "REMOTE": "git fetch origin -q の後に git ls-tree origin/<branch> -- <path>、または git ls-remote で取る"
              "（fetch の無い origin/… はローカルの古い記録で、証拠にならない）",
    "SHEET": "gviz（/gviz/tq?tqx=out:csv）・clasp pull・Drive/Sheets コネクタで該当シートを読む",
    "PUBLISH": "WebFetch / curl / ブラウザで公開先の URL を開き、中身を確かめる",
}

# --- nouns that name an external kind -----------------------------------------------------------
NOUN = {
    # SCREEN nouns gate only the 「表示されています」 predicate (DISPLAY); they are never paired with the
    # generic STATE_VERB -- 「設定には入っていないため、ダイアログで毎回選択」 is about a local config.
    "SCREEN": re.compile(r"画面|ブラウザ|タブ|ウィンドウ|ダイアログ|ポップアップ|ボタン|フォーム|マイページ|ダッシュボード|"
                         r"(?<![A-Za-z])(?:Chrome|Edge)(?![A-Za-z])|ログイン|ページ|サイト", re.I),
    # bare main / master is NOT a remote noun for the generic verbs (v2, attack): 「main には3件のコミットが
    # 入っています」 after a local git log is about the local branch.
    "REMOTE": re.compile(r"GitHub|origin|リモート|プルリク|\bPR\b", re.I),
    # katakana boundary: キャンセル / レシート are not セル / シート (calibration FP)
    "SHEET": re.compile(r"(?<![ァ-ヴー])(?:シート|スプレッドシート|トリガー|セル)(?![ァ-ヴー])|(?<![A-Za-z])GAS(?![A-Za-z])|"
                        r"Apps\s?Script|Code\.gs|gviz", re.I),
    # 記事 / ページ were nouns here in the first run and produced 14 of 38 fires on local manuscripts
    # (「記事の中心になっていました」「FAIL が残っています」); a manuscript is not a published page.
    "PUBLISH": re.compile(r"公開|(?<![A-Za-z])note(?![A-Za-z_.\-])|(?<![A-Za-z])LP(?![A-Za-z])|本番|デプロイ|配信|"
                          r"Artifact|アーティファクト|GitHub Pages|Vercel|Netlify", re.I),
}
STATE_VERB_KINDS = ("REMOTE", "SHEET", "PUBLISH")

# --- predicates ----------------------------------------------------------------------------------
_PROG = r"(?:てい|てお|ており|てあり|てあ|てま|てる)"           # progressive / resultative stem
# 「表示されています」 is a screen claim only next to a screen / page noun -- otherwise it is usually
# a document or table being described (calibration: 「正典の行は4万円高く表示されています」).
DISPLAY = re.compile(r"表示(?:され" + _PROG + r"|済|中です|中|されました)|(?:出|映っ|見え)" + _PROG + r"(?:ます|る)")
# A kind-specific predicate implies its kind without a noun.
OWN_PRED = {
    "SCREEN": re.compile(r"(?:画面|タブ|ウィンドウ|ダイアログ|ポップアップ|ボタン)[^。\n]{0,20}?"
                         r"(?:出" + _PROG + r"|開い" + _PROG + r"|開いたまま|映っ" + _PROG + r"|残っ" + _PROG + r")|"
                         r"ログイン(?:済|され" + _PROG + r"|し" + _PROG + r"|できてい|した状態)"),
    "REMOTE": re.compile(r"(?:push|プッシュ|マージ)\s*(?:済|しました|し" + _PROG + r"|され" + _PROG + r"|できてい|"
                         r"(?:は|が|も|まで|を)?完了)|"
                         r"(?:GitHub|origin|リモート)[^。\n]{0,6}?(?:上|側)?[^。\n]{0,4}?(?:に|へ|で|の|は|と)[^。\n]{0,24}?"
                         r"(?:あります|あること|入っ" + _PROG + r"|入りました|反映され|載っ" + _PROG + r"|存在し|残っ" + _PROG +
                         r"|上がっ" + _PROG + r"|最新です|一致し|同じ|同期し|差分は(?:ありません|ない|無い|なし)|更新され)|"
                         r"(?:リモート|origin)[^。\n]{0,12}?(?:削除しました|消しました|削除済)|"
                         r"ブランチは\s*(?:origin/)?main\s*(?:だけ|のみ)", re.I),
    "SHEET": re.compile(r"(?:シート|スプレッドシート|GAS|Apps\s?Script|トリガー)[^。\n]{0,30}?"
                        r"(?:書き込(?:まれ" + _PROG + r"|みました|み済|ん" + _PROG + r"|みが完了)|記入(?:済|しました|され" + _PROG + r"))",
                        re.I),
    "PUBLISH": re.compile(r"(?:公開|デプロイ|リリース|配信)(?:済|しました|され" + _PROG + r"|されました|し" + _PROG +
                          r"|中です|(?:は|が|を)?完了)|"
                          r"本番[^。\n]{0,15}?(?:(?:反映|適用)(?:済|され" + _PROG + r"|しました|させました|されました)|入っ" +
                          _PROG + r"|動い" + _PROG + r"|稼働|使っ" + _PROG + r"|使われ" + _PROG + r"|正常に動作|動作し" + _PROG + r")"),
}
# A generic state verb is a claim only when the sentence also names an external noun.
# 「になっています」 was dropped after calibration: 「GitHub に上げない設定になっています」 (a local
# .gitignore) and 「GAS 通知のリンク先は〜になっています」 (read from the local Code.gs) dominated it.
STATE_VERB = re.compile(r"(?:入っ|書き込まれ|記入され|使っ|使われ|計算され|設定され|動い|登録され|稼働し|残っ|"
                        r"反映され|置かれ|載っ|上がっ|更新され|配信され|動作し|走っ|アップされ)" + _PROG + r"|"
                        r"入りました|入れました|アップしました|アップ済|反映されました|更新しました|更新されました|稼働中|正常に動作|"
                        r"(?:反映|書き込み|記入|登録|設定|送信|提出|申請|更新)(?:済|しました|させました|が完了|は完了|を完了)")

# --- exemptions ----------------------------------------------------------------------------------
UNVERIFIED = re.compile(r"未確認|未検証|確認(?:でき)?て(?:い)?ない|確認できていません|確認していません|確かめ(?:られ)?て(?:い)?ない|"
                        r"確かめていません|見て(?:い)?ない|見ていません|不明|分かりません|わかりません|確認待ち|確認が(?:必要|要る)")
RESTATE = re.compile(r"とのこと|ご報告|ご指摘の(?:とおり|通り)|伺っ|伺った|おっしゃ|お知らせいただ|"
                     r"添付(?:の|された)(?:画像|スクショ|スクリーンショット|画面|写真)|"
                     r"お手元|頂いた画像|いただいた画像|と書かれて|との(?:こと|ご連絡)|"
                     # a recorded source is named: 「公開済みと tasks.md にあります」 -- the claim is the record's
                     r"(?:と|として)[^。\n]{0,30}(?:にあります|に書かれ|に記録|に記載|の記録では)")
ADVERSATIVE = re.compile(r"(?:が|けど|けれど|けれども|ものの)[、,]")
# The sentence is about a local artefact, not the external thing (v2, attack F11-F25, F37, F39).
LOCAL = re.compile(r"ローカル|手元|手順書|設計書|設計では|設計上|仕様書|コード上|コード内|コードに|コードでは|ソース|下書き|"
                   r"原稿|記事の中|ファイル内|\.git/config|設定ファイル|生成した\s*HTML|HTML\s*では|を読むと|を見ると|という記述|"
                   # a column / label of a local ledger: 「tasks.md の公開済み列を更新しました」
                   r"[\w.-]+\.(?:md|json|ya?ml|csv|txt)\s?(?:の|に|を|で)|(?:列|欄|カラム|ラベル)(?:を|に|は|の|で)")
# What follows the predicate within a few characters turns it into a condition / question / plan.
FOLLOW_OPEN = re.compile(r"^[^。\n]{0,10}?(?:なら|場合|とき|時は|れば|ても|でしたら|であれば|だったら|"
                         r"か(?:どうか|否か|を|確|は|も|[？?])|ように|予定|前提|か$)")
FOLLOW_OPEN_FUTURE = re.compile(r"^み?に(?:なる|なり|する|し)")      # 「公開済みになります」 is a forecast
# negative state is not blocked (v2): 「まだ push していません」「反映されていません」「公開済みではありません」
FOLLOW_NEG = re.compile(r"^み?(?:ません|ない|なかっ|ず[、。]|らず|では(?:あり|な)|じゃな)")
# 「push 済みのコミット」「公開済みの記事」「公開済み列」: attributive, the noun is the topic
FOLLOW_ATTR_SUMI = re.compile(r"^み?\s?(?:の|[一-龠ァ-ヴA-Za-z0-9])")
QUESTION_END = re.compile(r"[？?]\s*\**\s*$|(?:か|かな|でしょうか|ですか|ますか)[。．]?\s*\**\s*$")
# an instruction to the reader: 「確認してから進めてください」「設定済みにしてください」
IMPERATIVE_END = re.compile(r"(?:ください|下さい|してほしい|お願いします|お願いいたします|ましょう|すること)[。！!]?\s*\**\s*$")
ATTRIB_TAIL = re.compile(r"[るた](?:[0-9]|[一-龠ァ-ヴA-Za-z]|もの|ところ|ほう)")
COND_BEFORE = re.compile(r"(?:もし|仮に)[^、,]*$|(?:れば|たら|なら|場合は|ときは|次第|でしたら|であれば|だったら)[、,][^、,]*$")


def _segments(answer):
    """Sentences of the final answer: code fences dropped, table cells split, quotes removed."""
    out, fence = [], False
    for line in (answer or "").splitlines():
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if fence or not s:
            continue
        if s.startswith("{") and s.endswith("}"):
            continue
        s = re.sub(r"「[^「」\n]{0,200}」|『[^『』\n]{0,200}』|\"[^\"\n]{0,200}\"|“[^”\n]{0,200}”|‘[^’\n]{0,200}’"
                   r"|(?<![A-Za-z])'[^'\n]{0,200}'(?![A-Za-z])", "「」", s)
        s = s.replace("`", "").replace("**", "")
        cells = [c for c in s.split("|")] if s.startswith("|") else [s]
        for c in cells:
            c = c.strip()
            if not c or re.fullmatch(r"[-: ]+", c):
                continue
            for sent in re.split(r"(?<=[。！!？?])", c):
                sent = sent.strip()
                if sent:
                    out.append(sent)
    return out


def _is_open(sent, m):
    """True when the predicate at match `m` is conditional / negative / attributive / a question /
    an instruction / restated / about a local artefact / marked unverified."""
    if UNVERIFIED.search(sent) or LOCAL.search(sent):
        return True
    head, tail = sent[:m.start()], sent[m.end():]
    r = RESTATE.search(sent)
    # a restatement exempts unless an adversative clause separates it from the claim:
    # 「問題なければ、とのことですが、main に push 済みです」 still asserts the push.
    if r and not (r.end() <= m.start() and ADVERSATIVE.search(sent[r.end():m.start()])):
        return True
    if FOLLOW_OPEN.search(tail) or FOLLOW_OPEN_FUTURE.match(tail) or FOLLOW_NEG.match(tail):
        return True
    if QUESTION_END.search(sent) or IMPERATIVE_END.search(sent):
        return True
    # a condition clause BEFORE the predicate, in the same clause only (no 、 between)
    if COND_BEFORE.search(head):
        return True
    g = m.group(0)
    if g.endswith(("てい", "てお")) and ATTRIB_TAIL.match(tail):
        return True
    if g.endswith("済") and FOLLOW_ATTR_SUMI.match(tail):
        return True
    return False


def _sentence_kinds(sent):
    got = set()
    for kind in KINDS:
        for m in OWN_PRED[kind].finditer(sent):
            if not _is_open(sent, m):
                got.add(kind)
                break
    for m in DISPLAY.finditer(sent):
        if not _is_open(sent, m) and NOUN["SCREEN"].search(sent):
            got.add("SCREEN")
            break
    for m in STATE_VERB.finditer(sent):
        if _is_open(sent, m):
            continue
        for kind in STATE_VERB_KINDS:
            if NOUN[kind].search(sent):
                got.add(kind)
    return got


def _nouns(sent):
    return set(k for k in KINDS if NOUN[k].search(sent)) | (
        {"REMOTE"} if re.search(r"push|プッシュ|マージ", sent, re.I) else set())


def find_claims(answer):
    """[(kind, sentence)] for every asserted external-state sentence of the final answer.
    A separate sentence marked unverified (「※シートは未確認」) exempts only the kinds it names, or,
    naming none (「ただし未確認。」), the kinds claimed in the sentence just before it."""
    sents = _segments(answer)
    claims, waived, prev = [], set(), set()
    for sent in sents:
        if UNVERIFIED.search(sent):
            named = _nouns(sent)
            waived |= (named or prev)
            prev = set()
            continue
        got = _sentence_kinds(sent)
        for kind in KINDS:
            if kind in got:
                claims.append((kind, sent))
        prev = got
    return [(k, s) for k, s in claims if k not in waived]


# --- evidence ------------------------------------------------------------------------------------
BROWSER = re.compile(r"^mcp__.*(?:playwright|[Bb]rowser|chrome|computer|puppeteer)", re.I)
GITHUB_MCP = re.compile(r"^mcp__.*github", re.I)
SHEETS_MCP = re.compile(r"^mcp__.*(?:Google_Drive|[Ss]heets|spreadsheet).*(?:read|download|get|values|export)", re.I)
SHELL = ("Bash", "PowerShell")
# REMOTE contact = something that talks to the remote this turn. A bare `git log origin/main` or
# `git ls-tree origin/...` without fetch reads the LOCAL copy of the remote ref (v2, attack EV).
REMOTE_CMD = re.compile(r"git\s+(?:-C\s+\S+\s+)?(?:push|fetch|ls-remote|pull)\b|\bgh\s+(?:api|pr)\b|api\.github\.com", re.I)
SWALLOW = re.compile(r"\|\|\s*(?:true|:|exit\s+0|echo)\b|-ErrorAction\s+SilentlyContinue", re.I)
FAILED_OUT = re.compile(r"fatal:|\berror:|\[rejected\]|rejected|Permission denied|Could not read|Authentication failed|"
                        r"failed to push|non-fast-forward", re.I)
SHEET_HOST = re.compile(r"gviz|docs\.google\.com/spreadsheets|sheets\.googleapis|script\.google\.com|"
                        r"clasp\s+(?:pull|push|run|logs|deploy|deployments|versions|status|open)|SpreadsheetApp", re.I)
HTTP_CMD = re.compile(r"\bcurl\b|\bwget\b|Invoke-WebRequest|Invoke-RestMethod|\biwr\b|\birm\b|requests\.(?:get|post)\(|"
                      r"urllib\.request|httpx\.(?:get|post)|\bfetch\(", re.I)
DEPLOY_CMD = re.compile(r"clasp\s+(?:deploy|push)|\bvercel\b|\bnetlify\b|firebase\s+deploy|wrangler|gh-pages|npm\s+run\s+deploy",
                        re.I)
IMAGE_PATH = re.compile(r"\.(?:png|jpe?g|gif|webp|bmp)$", re.I)
URL = re.compile(r"https?://([^/\s\"'<>|)]+)", re.I)
GOOGLE = ("docs.google.com", "script.google.com", "sheets.googleapis.com")


def _blob(inp):
    try:
        return json.dumps(inp, ensure_ascii=False)
    except Exception:
        return ""


def _host(text):
    m = URL.search(text or "")
    return m.group(1).lower().split(":")[0] if m else None


def evidence(tools, prompt_has_image=False):
    """[(kind, host or None)] that this turn's tool calls actually read or contacted.
    `tools` items are (name, input) or (name, input, result_text)."""
    ev = []
    if prompt_has_image:
        ev.append(("SCREEN", None))
    nav = None
    for t in tools:
        name, inp = t[0], t[1]
        res = t[2] if len(t) > 2 else ""
        b = _blob(inp)
        if BROWSER.search(name):
            # the page a browser call acted on: its own URL, else the 'Page URL' its result reports,
            # else the last page navigated to in this turn
            pu = re.search(r"Page URL:\s*(\S+)", res or "")
            own = _host(b) or (_host(pu.group(1)) if pu else None)
            h = own or nav
            if own:
                nav = own
            ev += [("SCREEN", h), ("PUBLISH", h)]
            if h and any(h.endswith(g) for g in GOOGLE):
                ev.append(("SHEET", h))
        elif name == "WebFetch":
            h = _host(b)
            ev += [("SCREEN", h), ("PUBLISH", h)]
            if h and any(h.endswith(g) for g in GOOGLE):
                ev.append(("SHEET", h))
            if h and "github" in h:
                ev.append(("REMOTE", h))
        elif name in ("Artifact", "ArtifactData", "ArtifactComments"):
            ev += [("SCREEN", None), ("PUBLISH", None)]
        elif name == "Read":
            if IMAGE_PATH.search(str(inp.get("file_path") or "")):
                ev.append(("SCREEN", None))
        elif GITHUB_MCP.search(name):
            ev.append(("REMOTE", None))
        elif SHEETS_MCP.search(name):
            ev.append(("SHEET", None))
        elif name in SHELL:
            cmd = str(inp.get("command") or "")
            if SWALLOW.search(cmd) or FAILED_OUT.search(res or ""):
                continue        # a failure that was swallowed or reported is not contact
            if REMOTE_CMD.search(cmd):
                ev.append(("REMOTE", None))
            if SHEET_HOST.search(cmd):
                ev += [("SHEET", None), ("PUBLISH", None)]     # clasp / gviz read the deployed GAS too
            if HTTP_CMD.search(cmd):
                ev.append(("PUBLISH", _host(cmd)))
            if DEPLOY_CMD.search(cmd):
                ev.append(("PUBLISH", None))
    return ev


def _target(kind, sent):
    """Host the claim is about, when the sentence names one; None = unspecific."""
    h = _host(sent)
    if h:
        return h
    if kind in ("PUBLISH", "SCREEN") and re.search(r"(?<![A-Za-z])note(?![A-Za-z_.\-])", sent, re.I):
        return "note.com"
    if kind in ("PUBLISH", "SCREEN") and re.search(r"GitHub", sent, re.I):
        return "github"
    return None


def _verified(kind, sent, ev):
    tgt = _target(kind, sent)
    for k, h in ev:
        if k != kind:
            continue
        if tgt is None or h is None or tgt in h or h.endswith(tgt):
            return True
    return False


def decide(answer, tools, prompt_has_image=False):
    """Return (kind, sentence) for the first external-state claim this turn did not read, or None."""
    tools = [t if isinstance(t, tuple) else tuple(t) for t in (tools or [])]
    tools = [(t[0] or "", t[1] if isinstance(t[1], dict) else {}) + tuple(t[2:3]) for t in tools]
    claims = find_claims(answer or "")
    if not claims:
        return None
    ev = evidence(tools, prompt_has_image)
    for kind, sent in claims:
        if not _verified(kind, sent, ev):
            return kind, sent
    return None


# --- transcript ----------------------------------------------------------------------------------
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _has_image(msg):
    c = (msg or {}).get("content")
    return isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "image" for b in c)


def is_prompt(d, strict=True):
    """A prompt the user typed -- not a tool result or harness notification.
    strict=False for converted Codex rows, which carry no promptSource/permissionMode."""
    if d.get("type") != "user" or d.get("isSidechain"):
        return False
    if strict and not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    if not t and _has_image(d.get("message")):
        return True
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:",
                                         "<system-reminder>"))


def _tool_uses(d):
    c = (d.get("message") or {}).get("content")
    if not isinstance(c, list):
        return []
    return [(b.get("name") or "", b.get("input") or {}) for b in c
            if isinstance(b, dict) and b.get("type") == "tool_use"]


def _result_text(b):
    c = b.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c if isinstance(x, dict))
    return ""


class Turn(object):
    """Accumulates one instruction: tools (with their results) and the FINAL answer, i.e. every text
    block after the last tool call, joined (v2: an answer split over several rows is read whole)."""

    def __init__(self, d, ordinal):
        self.prompt = _text(d.get("message")).strip() or "[image]"
        self.ts = d.get("timestamp") or ""
        self.uid = d.get("uuid") or ""
        self.ordinal = ordinal
        self.img = _has_image(d.get("message"))
        self.tools, self.parts, self._ids = [], [], {}

    def add(self, d):
        c = (d.get("message") or {}).get("content")
        if d.get("type") == "assistant":
            if isinstance(c, str):
                self.parts.append(c)
                return
            for b in c or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    self._ids[b.get("id")] = len(self.tools)
                    self.tools.append([b.get("name") or "", b.get("input") or {}, ""])
                    self.parts = []
                elif b.get("type") == "text" and (b.get("text") or "").strip():
                    self.parts.append(b.get("text"))
        elif d.get("type") == "user" and isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in self._ids:
                    self.tools[self._ids[b["tool_use_id"]]][2] = _result_text(b)[:4000]

    @property
    def answer(self):
        return "\n".join(p.strip() for p in self.parts).strip()

    def tool_list(self):
        return [tuple(t) for t in self.tools]


def iter_turns(rows):
    strict = any(isinstance(d, dict) and ("promptSource" in d or "permissionMode" in d) for d in rows)
    cur, n = None, 0
    for d in rows:
        if not isinstance(d, dict) or d.get("isSidechain"):
            continue
        if is_prompt(d, strict):
            if cur is not None:
                yield cur
            n += 1
            cur = Turn(d, n)
        elif cur is not None:
            cur.add(d)
    if cur is not None:
        yield cur


def read_turn(tp):
    """The last Turn of the transcript (or None)."""
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    rows = []
    for line in data:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    last = None
    for t in iter_turns(rows):
        last = t
    return last


REASON = (
    "【外部状態の断定（1回のみ）】回答が{label}の今の状態を断定している（「{claim}」）が、"
    "このターン（最後のユーザー発言以降）に、その状態を実際に読んだツール呼び出しが無い。"
    "前回の作業の記憶で「表示済・反映済・push 済」と書くと、実物と食い違っても気付けない"
    "（2026-10-30「表示されてないと思います。添付のようになってますよ」、2026-10-08「ちゃんとスプレッドシートみろ」）。"
    "今このターンで次を行い、回答し直せ。"
    "①実際に取得する: {howto}。"
    "②取得した内容に合わせて文を直す（食い違っていたらそれを報告する）。"
    "③取得できないなら断定をやめ、その文に「未確認」と明記する。"
    "サブエージェントの報告は証拠にならない（AGENTS.md §5.3）。"
)


def main():
    if os.environ.get("CLAUDE_HEADLESS_JOB") == "1":
        return
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()),
                                             ".claude", "hooks", os.path.basename(__file__)))
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
    tp = _codex_transcript(ev.get("transcript_path") or "")
    if not tp or not os.path.isfile(tp):
        return
    turn = read_turn(tp)
    if turn is None:
        return
    hit = decide(turn.answer, turn.tool_list(), turn.img)
    if not hit:
        return
    kind, sent = hit
    # One block per instruction. The instruction is identified by its uuid / timestamp; when the row
    # carries neither (v2, attack T1b), the same prompt text typed again would share a key forever, so
    # the prompt's position and the claim are added to the key instead.
    ident = turn.uid or turn.ts or ("#%d|%s" % (turn.ordinal, sent))
    key = hashlib.sha1((ident + "|" + turn.prompt).encode("utf-8", "replace")).hexdigest()[:16]
    sid = "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")
    mark = os.path.join(STATE_DIR, sid + "_" + key)
    if os.path.exists(mark):
        return          # already blocked once for this instruction
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    claim = sent if len(sent) <= 160 else sent[:157] + "..."
    reason = REASON.format(label=LABEL[kind], claim=claim, howto=HOWTO[kind])
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
