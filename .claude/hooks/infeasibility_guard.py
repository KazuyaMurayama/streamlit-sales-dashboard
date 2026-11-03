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

REDESIGN 2026-11-03 (C01 recurred 10 times after adoption; reports/CORRECTION_DIGEST_20261102.md)
---------------------------------------------------------------------------------------------
Sorting the 10 answers before those corrections (transcript replay, this module and the neighbours
imported): 1 is external_state_claim_guard's (sheet state asserted), 1 is delegation_guard v3's
(decision request), 1 is primarily external_state's known gap (screen state, wrong browser read),
4 are wrong facts / stale premises / new instructions (out of scope), and 2 -- plus a sentence of
the screen case -- are this class and passed v1:
  CLASS: the answer says nothing can be done now, or stops to wait for an external event (a mail,
  another session's push, a job), without checking whether the blocking condition still holds.
Added (by morphology / turn shape, not strings):
  B2   ichidan potential + negation (閉じられません, 届けられない); stems whose られ is passive in
       practice (求め・認め・含め・考え・忘れ・信じ ...) excluded.
  E    zero-count capability: <potential verb>る … は 0本 / 1件もありません (今すぐ私が直せる記事は0本です).
  WAIT a sentence whose continuation is conditional on an external event -- 〜たら / 次第 / てから /
       たあと + an own future act or 「一言ください」 -- where the event is of a kind this turn can look
       at (MAIL / REMOTE push・session / JOB / WEB). It passes when this turn contacted that kind
       (Gmail-type connector; git fetch|ls-remote|pull, origin/, gh; a background job or agent launched;
       a browser / fetch) -- unless the answer itself says part of that check is not done (未確認 /
       まだ確かめていません about the same thing), or the deferred step IS the check (「push を確かめた
       あと…します」), which never passes. Not WAIT: the user's own act (ご確認いただいたら・許可・ログ
       イン・決まったら -- delegation_guard's domain), contingencies (問題が出たら・必要が出たら・割ったら),
       branches (〜なら、), procedures with no event kind (位置を目で確かめてから打ちます), progressive
       descriptions (確認してから消しています).
  Boundary with delegation_guard v4.1: it treats 「an external event to wait for」 as a stake that
  excuses a stall and any MCP call as an attempt; WAIT checks only that excuse (was the event looked
  at?), never request / stall wording.
Calibration (real main-agent turns, old = git HEAD copy, new = this file, both decide() imported):
  7 days 76 turns 1.3% -> 3.9% (+2); 21 days 381 turns 2.4% -> 3.4% (+4: three are the answers the
  user then corrected, one unclear 「私からは別のセッションを始められないためです」). Tests:
  tests/test_infeasibility_guard.py (19 new rows; HOOK=<HEAD copy> fails the 10 BLOCK rows).
V2 (same day, Sonnet attack -- tests/fixtures/infeasibility_guard_attack_20261103.json, 101 cases):
  v1 let 15/42 evasions through (35.7%) and stopped 14/43 legitimate answers (32.6%); 45 days showed 3 B2
  false fires. Fixed: dictionary / まで待つ / のを待つ / を待つ / 確認でき次第 / 時点で / のち / 届くと forms and
  an event named in the sentence before; work launched in an EARLIER turn and still running
  (pending_jobs(): launch ids minus <task-notification> status ids, read in the 4 MB window, same idea as
  delegation_guard.bg_pending but implemented here) and schedulers / SendMessage / detached processes
  excuse a job wait; 完了通知 is a job, not a mail; one kind's tool is no evidence for another (an Agent
  does not check a push; quoted strings / echo do not count; Gmail must be a read call); descriptions
  (自動で / されます / 設計 / 手順: lines), the user's own work (手動で…, or an answer that asks the user
  to paste / run / reply) and own checks of a job already run this turn pass; B2 needs Claude's side
  (こちら・私・ここから・画面・タブ・ツール ...) and not a past report; E needs a self / now marker
  (私・今すぐ・いま・このターン), skips 0件でした and analytic verbs, and reads a table row's
  「直せる記事 | 0本」. Attack re-run: evasions 38/42 caught (left: 3 English, 1 B2 without Claude's
  side -- by design), legitimate 2/43 stopped (both synthetic: a wait with no launch in the transcript,
  one launch closed by its notification while the text says 4 remain). 45 days 654 turns: 3.1% -> 3.7%
  (+4: three answers the user then corrected, one unclear). Tests 143/143 (HEAD copy 126/143).

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
          "|立ち上げられ|立てられ|飛ばせ|入れ込め|差し込め|組み込め|持ち込め|書き換えられ|登録でき|試せ")
_CAP_GODAN = re.compile(r"(?P<v>" + _GODAN + r")" + _NEG)
# B2 (2026-11-03). Ichidan potential by MORPHOLOGY, not by list: <kanji>(い段/え段 kana)?られ + negation
# -- 閉じられません / 届けられない / 止められません. The list above missed 閉じられません (2026-10-30).
# Stems whose られ is passive/honorific in practice (求められない, 認められない) are not capability.
_CAP_ICHIDAN = re.compile(
    r"(?P<v>(?![求認含定与考感課迫褒責決避忘信耐比])[一-龠][いきぎしじちにびみりえけげせぜてでねべめれ]?)られ" + _NEG)
# E (2026-11-03). Zero-count capability: 「今すぐ私が直せる記事は0本です」 says nothing can be done, with no
# negation verb to anchor on (2026-10-28: the blocking condition -- another session still writing -- was
# never checked and had ended long before).
_POT = r"(?:" + _GODAN + r"|[一-龠々ァ-ヴー]{1,8}(?:でき|出来|られ))る"
_CAP_ZERO = re.compile(
    r"(?P<v>" + _POT + r")[^。、]{0,15}?(?:は|が|も)\s*(?:0|０|ゼロ)\s*(?:本|件|個|つ|点|行|枚|人|社|ファイル|項目)?"
    r"(?=\s*(?:です|でした|だ|。|$|\*|（|\())"
    r"|(?P<v2>" + _POT + r")[^。、]{0,15}?(?:は|が)(?:一つも|1つも|ひとつも|1本も|1件も|何も)(?:ありません|ない|無い)"
    r"|(?P<v3>" + _POT + r")[^。、:：]{0,15}?\s*[:：]\s*\**\s*(?:0|０|ゼロ)\s*(?:本|件|個|つ|点|行|枚|人|社|ファイル|項目)?\s*\**\s*$"
    r"|(?P<v4>(?:でき|やれ)る)こと(?:は|が)[^。]{0,8}?(?:ありません|ない|無い)")
# B2 / E are read only when the side that cannot act is Claude's (its tools, access, operations) or "now":
# a market explanation (証拠金なしでは建てられません), a past report (切り分けられませんでした) and a limit of an
# answer's basis (注入されていなければ答えられない) are not capability claims about this turn (45-day FPs).
SELF_SIDE = re.compile(r"こちら|私|ここ(?:から|では|で)|当方|自分|Claude|このセッション|このターン|ツール|コネクタ"
                       r"|ブラウザ|\bAPI\b|MCP|画面|タブ|ダイアログ|ウィンドウ|ボタン|設定|コマンド|ターミナル")
NOW_SIDE = re.compile(r"私|こちら|ここから|自分|今すぐ|いま|今は|現時点|このターン|当方")
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
CAP_PATTERNS = (_CAP_DEKI, _CAP_GODAN, _CAP_ICHIDAN, _CAP_PASSIVE, _CAP_SUPPORT, _CAP_ZERO)
_ZERO_CELL = re.compile(r"^(?P<v>.{0,30}?" + _POT + r")[^|]{0,15}$")
_ZERO_VAL = re.compile(r"^\s*\**\s*(?:0|０|ゼロ)\s*(?:本|件|個|つ|点|行|枚|人|社|ファイル|項目)?\s*\**\s*$")
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

# ---------------------------------------------------------------- WAIT (2026-11-03, v2 after the Sonnet attack)
# Class: the answer stops and waits for an EXTERNAL EVENT (a mail to arrive, another session / person
# to finish and push, a job to end, a page to reflect) -- or defers its own check of one -- although
# whether the event has already happened is checkable now and this turn did not check it, or the
# answer itself says part of the check is not done. Real cases (correction_history C01):
#   2026-10-21 「案内メールが届いたら「届いた」と一言ください」 with 「迷惑メールに入っている可能性は、
#       まだ確かめていません」 -> 「…にとどいているので確認して」
#   2026-10-28 「向こうの push が終わったら…検査します」 / 「文体セッションの push を確かめたあと、残りの
#       15本を検査します」 -> 「文体セッションの push はとっくに終わっているので、残りの15本を進めて」
# Boundary: delegation_guard v4.1 treats 「an external event to wait for」 as a stake that EXCUSES a
# stall, and v3 excuses a request when the turn made any MCP call. This family checks exactly that
# excuse -- was the awaited event looked at? -- and nothing else (no request / stall wording).
# The user's own act (ご確認いただいたら / 許可したら / ログインしたら / 手動で…終わったら) is NOT an event
# here: waiting for the user is delegation_guard's question.
# v2 (attack fixtures/infeasibility_guard_attack_20261103.json): the dictionary / terminal forms of the
# wait (終わるまで待ちます・届くのを待って・push を待ちます・確認でき次第・終わった時点で・したのち・届くと),
# an event named only in the previous sentence (「…終わっていません。終わったら検査します」), work still
# running from an EARLIER turn (pending_jobs(): launches minus completion notifications in the read
# window), schedulers / messages / detached processes as a job, one kind's evidence no longer standing
# in for another's, descriptions of a design or procedure (自動で / されます / 設計 / 手順:) passed.
_EV_VERB = (r"(?:届い|届き|着い|到着し|来|終わっ|終わり|終え|終了し|完了し|済ん|反映され|公開され|揃っ|返っ|返ってき|戻っ"
            r"|入っ|出|空い|解除され|push\s*され|push\s*し|マージされ|確定し|処理され|生成され|書き終わ|走り終わ"
            r"|確かめ|確認し|確認でき|調べ|見)")
_EV_COND = r"(?:たら|次第|てから|た(?:あと|後|のち|時点で|段階で|うえで|上で)(?:で|に)?|るまで|るのを待っ)"
# dictionary form + まで待つ / のを待つ / と(すぐ): 「push が終わるまで待ちます」「メールが届くのを待って」「届くと、すぐ」
_EV_DICT = r"(?:届く|着く|終わる|終える|終了する|完了する|済む|反映される|公開される|揃う|返ってくる|戻る|push\s*される|マージされる|来る)"
WAIT = re.compile(
    r"(?P<ev>[^。、]{0,40}?)(?P<verb>" + _EV_VERB + r")" + _EV_COND +
    r"|(?P<ev2>[^。、]{0,40}?)(?P<verb2>" + _EV_DICT + r")(?:まで|のを)待(?=ち|っ)" +
    r"|(?P<ev3>[^。、]{0,40}?)(?P<verb3>" + _EV_DICT + r")と(?=[、,]|\s*すぐ)" +
    # noun + を待つ: 「別セッションの push を待ってから」「向こうの push を待ちます」「完了を待って」
    r"|(?P<ev4>[^。、]{1,40}?)(?P<verb4>を)待(?=ち|っ)")
OWN_CHECK = re.compile(r"^(?:確かめ|確認し|確認でき|調べ|見)$")
# what makes the sentence a stop: an own non-past act (〜します / 進めます / 検査します), or a request to be told
CONTINUE = re.compile(r"(?<!てい)(?<!てお)(?<!でい)(?:ます|ましょう|る予定|る方針)(?:[。．]|$|\s|\*|（|\()"
                      r"|(?:一言|ご連絡|連絡|お知らせ|知らせて|教えて|送って|声をかけて)(?:ください|下さい|いただ|頂|もら)")
# the answer hands the user a piece of work (paste / run / press / reply): a job- or page-type wait in such an
# answer is a wait on the user's work -- delegation_guard's question, not this hook's (45-day FPs 09-28, 10-28)
USER_WORK = re.compile(r"(?:貼って|貼り付けて|実行して|押して|開いて|入力して|操作して|ログインして|設定して|インストールして"
                       r"|ダウンロードして|アップロードして|選んで|許可して|クリックして|返信して|返して|送って)(?:ください|下さい|いただ)")
ASK_USER = re.compile(r"(?:一言|ご連絡|連絡|お知らせ|知らせて|教えて|送って|声をかけて)(?:ください|下さい|いただ|頂|もら)")
# the continuation describes a design / automation / output, not Claude's own next act
DESCRIBES = re.compile(r"自動|され(?:ます|る)|設計|仕組み|仕様|ようになって|(?:届き|消え|出|始まり|残り|流れ|走り)ます|走らせます")
DESC_LINE = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*)?(?:手順|設計|仕様|注意|仕組み|例|動作)\s*[0-9０-９]*\s*(?:\*\*)?\s*[:：]")
# the event's actor is the user / a person deciding: delegation_guard's domain
USER_EVENT = re.compile(r"ご|お[一-龠]|いただ|頂|本人|あなた|ユーザー|ご自身|決ま|承認|許可|ログイン|判断|返答|回答|答え|返事|指示"
                        r"|手動|お手元|そちらで|お手数")
# a contingency (「問題が出たら」「必要が出たら」「1,650万円を割ったら」) is a rule for the future, not a wait
# on an event that may already have happened; neither is a branch on a condition (「〜なら、…確認してから」).
CONTINGENCY = re.compile(r"場面|場合|問題|不具合|エラー|必要|ズレ|違和感|疑問|異常|変化|差分|割っ|割り込|超え|下回|上回|気にな|困っ")
COND_BRANCH = re.compile(r"(?:もし|仮に)|(?:なら|場合は|ときは|時は|であれば|でしたら)[、,]")
UNVERIFIED = re.compile(r"未確認|未検証|(?:確かめ|確認し|調べ|見)て(?:い)?(?:ない|ません)"
                        r"|確認できて(?:い)?(?:ない|ません)|(?:確かめ|確認|チェック)(?:は|も)?(?:まだ|未)")
_Q = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
# kinds of awaited event -> what this turn must contain to have looked at it. A tool of one kind is not
# evidence for another (an Agent launch does not check a push; a git fetch does not check a mail).
EV_KINDS = (
    ("MAIL", re.compile(r"メール|返信|受信|着信|\bmail\b", re.I),
     lambda n, c: bool(re.search(r"gmail|mail|outlook", n, re.I) and re.search(r"search|get|list|read|fetch|thread", n, re.I))
     or bool(re.search(r"\b(?:imap|mail)\b", c, re.I))),
    ("REMOTE", re.compile(r"push|プッシュ|コミット|マージ|ブランチ|セッション|リモート|origin|GitHub|PR\b|プルリク|反映|作業", re.I),
     lambda n, c: bool(re.search(r"github", n, re.I)) or bool(re.search(
         r"git\s+(?:-C\s+\S+\s+)?(?:fetch|ls-remote|pull)\b|origin/|@\{u\}|\bgh\s+(?:api|pr|run|repo)\b|api\.github\.com", c))),
    ("JOB", re.compile(r"処理|計算|ジョブ|実行|タスク|ビルド|テスト|\bCI\b|エージェント|サブエージェント|[0-9０-９一二三四五六七八九十]体"
                       r"|完了通知|バックグラウンド|学習|集計|収集|調査|検証|レビュー|ダウンロード|生成|変換|書き出し|結果|出力"),
     None),   # see _job_seen / pending_jobs
    ("WEB", re.compile(r"画面|ページ|サイト|表示|公開|デプロイ|ブラウザ|審査|掲載|URL", re.I),
     lambda n, c: bool(FETCH_TOOL.search(n)) or bool(re.search(r"\bcurl\b|\bwget\b|Invoke-WebRequest|Invoke-RestMethod", c))),
)


def _wait_match(m):
    for k in ("", "2", "3", "4"):
        if m.group("verb" + k) is not None:
            return m.group("ev" + k) or "", m.group("verb" + k), k
    return "", "", ""


def find_waits(answer):
    """[(sentence, event clause, verb)] for sentences that stop on an external event."""
    out = []
    prev = ""
    for s, line, raw in _segments(answer):
        if DESC_LINE.match(raw) or DESC_LINE.match(line):
            prev = s
            continue
        for m in WAIT.finditer(s):
            ev, verb, form = _wait_match(m)
            rest = s[m.end():]
            if not _content(ev):
                if re.search(r"(?:ください|下さい|いただけ|お願い)", prev):
                    continue             # the sentence before asks the user for it: the user's act
                ev = prev[-40:]          # 「…終わっていません。終わったら検査します」: the event is in the sentence before
            if COND_BRANCH.search(s[:m.end()]) or USER_EVENT.search(ev + verb) or CONTINGENCY.search(ev):
                continue
            # only an event of a kind this turn could have looked at (mail / remote / job / web). A procedure
            # step (「位置を目で確かめてから打ちます」) or an unnamed event (「データが届いたら」) is not checked.
            kinds = [k for k, rx, _f in EV_KINDS if rx.search(ev + verb)]
            if not kinds:
                continue
            waits = form in ("2", "4") or (form == "3")
            if not _content(ev) or not (waits or CONTINUE.search(rest)):
                continue
            if re.search(r"[？?]\s*\**\s*$", rest) or DESCRIBES.search(rest):
                continue
            if set(kinds) <= {"JOB", "WEB"} and USER_WORK.search(answer or ""):
                continue
            if ASK_USER.search(rest) and kinds == ["JOB"]:
                continue                 # 「〜が終わったら教えてください」: the user runs the job -- delegation_guard
            out.append((s.strip(), ev.strip(), verb))
            break
        prev = s
    return out


JOB_TOOLS = ("Agent", "Task", "Monitor", "TaskOutput", "BashOutput", "Workflow", "CronCreate", "ScheduleWakeup",
             "SendMessage")
DETACH = re.compile(r"Start-Process|Start-Job|\bnohup\b|\bstart\s+/b\b|&\s*$|\bsetsid\b|\bdisown\b", re.I)


def _job_seen(tools):
    """The turn launched / scheduled / messaged something that will report back by itself."""
    for n, i in tools:
        i = i or {}
        if n in JOB_TOOLS:
            return True
        if n in EXEC_TOOL:
            c = _Q.sub(" Q ", str(i.get("command", "")))
            if i.get("run_in_background") and not re.match(r"^\s*sleep\b", c):
                return True
            if DETACH.search(c):
                return True
    return False


_LAUNCH_ID = re.compile(r"agentId: ([0-9a-f]{8,})|background with ID: (\w+)|resumedAgentId\W{1,8}([0-9a-f]{8,})")
_DONE_ID = re.compile(r"<task-id>(\w+)</task-id>.{0,600}?<status>(?:completed|failed|killed|stopped)", re.S)


def pending_jobs(rows):
    """How many subagents / background commands launched anywhere in the read window (this turn or an
    earlier one) have no completion notification yet. Same idea as delegation_guard.bg_pending(), kept
    here so the hooks stay independent: ids from the launch results minus ids in <task-notification>
    status lines. A foreground agent result carries <usage> (it has finished). A launch whose result has
    no id is counted anonymously and is closed by a notification without an id."""
    launched, done, anon = set(), set(), 0
    bg_calls = {}
    for d in rows:
        if not isinstance(d, dict) or d.get("isSidechain"):
            continue
        c = (d.get("message") or {}).get("content")
        if d.get("type") == "assistant" and isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    inp = b.get("input") or {}
                    if b.get("name") in ("Agent", "Task") or (b.get("name") in EXEC_TOOL and inp.get("run_in_background")):
                        bg_calls[b.get("id")] = True
            continue
        raw = json.dumps(d, ensure_ascii=False)
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in bg_calls:
                    r = json.dumps(b.get("content"), ensure_ascii=False)
                    ids = [x for m in _LAUNCH_ID.finditer(r) for x in m.groups() if x]
                    if ids and "<usage>" not in r:
                        launched.update(ids)
                    elif not ids and "<usage>" not in r:
                        anon += 1
        for m in _LAUNCH_ID.finditer(raw):
            if m.group(3):
                launched.add(m.group(3))
        for m in _DONE_ID.finditer(raw):
            done.add(m.group(1))
        if "<task-notification" in raw and not _DONE_ID.search(raw):
            anon = max(0, anon - raw.count("<task-notification"))
    return len(launched - done) + anon


def wait_unchecked(sent, ev, verb, tools, answer, pending=0):
    """"" if this turn looked at the awaited event, else a short reason."""
    clause = ev + verb
    kinds = [k for k, rx, _f in EV_KINDS if rx.search(clause)]
    # JOB evidence counts only when the event is a job and nothing else (an Agent does not check a push)
    job_ok = kinds == ["JOB"] and (_job_seen(tools) or pending > 0)
    if OWN_CHECK.match(verb):
        ran = any(_classify(n, i) in ("exec", "fetch", "mcp") for n, i in tools)
        if kinds == ["JOB"] and (job_ok or ran):
            return ""                          # 「結果を確認してから、コミットします」 after running it this turn
        return "own check deferred"            # 「push を確かめたあと…します」: the check itself is not done
    ks = _tokens(clause)
    # the answer itself says part of the check is not done (in a sentence about the same thing)
    for s2, _l, _r in _segments(answer):
        if s2.strip() != sent and UNVERIFIED.search(s2) and ks and _shares(ks, s2):
            return "answer admits the check is not done"
    if job_ok:
        return ""
    for k, rx, f in EV_KINDS:
        if k not in kinds or k == "JOB":
            continue
        for n, i in tools:
            c = _Q.sub(" Q ", str((i or {}).get("command", ""))) if n in EXEC_TOOL else ""
            if re.match(r"^\s*(?:echo|printf|Write-(?:Output|Host))\b", c):
                continue
            if f(n, c):
                return ""
    return "event not looked at this turn"


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
                v = (m.groupdict().get("v") or m.groupdict().get("v2") or m.groupdict().get("v3") or "")
                head, rest = s[:m.start()], s[m.end():]
                if pat is _CAP_ICHIDAN and (not SELF_SIDE.search(head) or re.match(r"\s*でし", rest)):
                    continue
                if pat is _CAP_ZERO and (not NOW_SIDE.search(head + m.group(0)) or re.match(r"\s*でし", rest)
                                         or ANALYTIC.search(re.sub(r"(?:でき|出来|られ)る$", "", v))):
                    continue
                if NOT_ASSERTED.match(rest) or QUESTION.match(rest) or re.search(r"(?:もし|仮に)", head):
                    continue
                if v and (ANALYTIC.search(v) or REFUSAL_VERB.search(v)):
                    continue
                if pat is _CAP_DEKI and ANALYTIC.search(re.sub(r"(?:すること|こと)?(?:が|は|も)?$", "", head)):
                    continue
                if len(_content(head)) < 2 and pat is not _CAP_SUPPORT and pat is not _CAP_ZERO:
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
    for raw in (answer or "").splitlines():
        st = raw.strip()
        if not st.startswith("|") or re.match(r"^\|[\s:|-]+\|?$", st):
            continue
        cells = [_clean_line(c) for c in st.strip("|").split("|")]
        for a, b in zip(cells, cells[1:]):
            m = _ZERO_CELL.match(a.strip())
            if m and _ZERO_VAL.match(b) and NOW_SIDE.search(a) \
                    and not ANALYTIC.search(re.sub(r"(?:でき|出来|られ)る.*$", "", m.group("v"))):
                out.append(("CAPABILITY", (a.strip() + " | " + b.strip()), st, a, raw))
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


def decide(answer, tools, pending=0):
    """Return (kind, claim sentence) for the first unchecked claim, or None.
    `tools` is a list of (name, input dict) of this turn's tool calls."""
    tools = [(n or "", i if isinstance(i, dict) else {}) for n, i in (tools or [])]
    for kind, sent, line, head, raw in find_claims(answer, bool(tools)):
        if kind == "EXHAUSTIVE":
            return kind, sent
        if has_evidence(sent, line, raw, head, tools, answer or ""):
            continue
        return kind, sent
    for sent, ev, verb in find_waits(answer):
        if wait_unchecked(sent, ev, verb, tools, answer or "", pending):
            return "WAIT", sent
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
    pending = 0
    if prompt and answer and find_waits(answer):
        try:
            size = os.path.getsize(tp)
            with open(tp, "rb") as f:
                f.seek(max(0, size - TAIL_BYTES))
                rows = []
                for line in f.read().decode("utf-8", "replace").splitlines():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
            pending = pending_jobs(rows)
        except Exception:
            pending = 0
    hit = decide(answer, tools, pending) if prompt else None
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
    if kind == "WAIT":
        head = ("【確かめずに待機（1回のみ）】回答が外部の出来事を待って作業を止めている（「%s」）が、その出来事がもう"
                "起きたかを、このターンで確かめていない（または回答自身が「まだ確かめていない」と書いている）。" % claim)
        reason = head + (
            "待つ前に、今このターンで確かめよ。"
            "メールなら受信箱全体（迷惑メール・すべてのフォルダ・送信元や件名を絞らない検索）、"
            "他のセッション・他の人の push なら git fetch のあと git log origin/<branch>（ブランチは git rev-parse で取得）、"
            "処理・ジョブなら出力ファイルやプロセス、画面・公開ページなら実際に開いて読む。"
            "起きていれば、そのまま続きの作業を行って結果を報告し直せ。"
            "起きていなければ、確かめた手段と結果を1文書いてから待つ（「確かめたら進めます」と確認を先送りしない）。")
        sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))
        return
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
