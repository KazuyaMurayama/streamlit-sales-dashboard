# -*- coding: utf-8 -*-
"""PostToolUse: 制作過程（何を直したか・どう検証したか）の本文混入を止める。

THE DEFECT THIS EXISTS FOR
--------------------------
The rule was already written -- analysis-qa-checklist/SKILL.md L17:
「制作過程（監査した／N件是正した／正確率）は成果物ではなく報告に書く。
 読者向け本文に置かない」-- and md_report_qa.py already implemented the
`process_leak` check. Neither ran, because running them depended on the author
remembering to at the end of a long task.

v2 (2026-09-09). v1 was measured against the user's own list of violations and
returned **exit 0 on every one of them**:

    前回の私の主張 / 一部撤回する / 本人が正しい / 前回55点→訂正後62点 /
    私の調査不足だった / 独立レビューの採点は77/100 / レビュー指摘を反映済み /
    二巡の点検を経て / 三件の誤記を直しました / 品質スコア 92/100 /
    ファクトチェック済み / 初版では…撤回した

v1's vocabulary was overfitted to the four reports that were on disk when it
was written ("N件是正", "監査", "正確率"). The class is not those literals; it
is **writing your own authoring/correction history into reader-facing text**.
v2 therefore composes SELF x ACT rather than listing surface forms, and
normalizes the text first so that emphasis marks, table pipes, ZWSP and
intra-paragraph newlines cannot split a match (all measured bypasses).

v3 (2026-09-09) -- measured against the corpus rather than reasoned about.
A new suite (tests/test_process_leak_corpus.py) replays every §1 bypass and
every §2 false positive verbatim. v2 scored 34/39 blocked, 15/15 passed. The
five survivors and their causes:

    審査を2周した              ACT lacked 審査
    当レポートは…確認済み        ACT lacked 確認 (also broke 本報告書)
    誤りを発見し、訂正した        the 誤り rule required が, not を
    verify_citations.py       _normalize stripped `_`, turning the name into
                              verifycitations -- the NORMALISER, added to
                              defeat Markdown emphasis, was itself a bypass
    Shift_JIS ファイル          errors="replace" (the corpus's own proposed
                              fix) stops the crash but NOT the bypass: cp932
                              bytes decoded as utf-8/replace become mojibake
                              that no pattern can match. Needs real encoding
                              detection -- see _read_text.

v3 result: 39/39 blocked, 15/15 passed, 67/67 including structural holes.

Sources for v2's patterns:
  - the user's verbatim list (2026-09-09)
  - templates/hooks/tests/fixtures/process_leak_attack_corpus_20260908.md
    (adversarial review; §1 bypasses, §2 false positives, §3 structural holes)

FALSE POSITIVES ARE A REAL COST. v1 blocked the bare word 「監査」 anywhere,
which makes auditing/accounting/medical reports unwritable -- and a guard with
a high false-positive rate gets switched off, which is how this class survived.
v2 requires a self-reference near the process verb, keeps the negation escape
(「確認できなかった」= a legitimate scope limitation the reader needs), and
leaves tool-name exposure ADVISORY.

FAIL-OPEN on any exception. LOOP-SAFE: PostToolUse fires once per call.

⚠ WIRING: invoke this hook DIRECTLY. The idiom
    python hook.py || python3 hook.py || exit 0
converts a block (exit 2) into a pass (exit 0): the second interpreter reruns
with stdin already consumed, fails json.load, and exits 0. Measured
2026-09-09: DIRECT exit=2 / WIRED exit=0. Use instead:
    sh -c 'P=$(command -v python3 || command -v python) || exit 0; exec "$P" .claude/hooks/process_leak_guard.py'

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_fired
except Exception:  # firing_log 未配備でも本体は動く
    def _record_fired(name, ev):
        return False

ADVISORY_LABELS = {"ツール名の露出"}
# 拡張子・大文字ゆれで回避されないようにする（実測: Outputs/ OUTPUTS/ .MD が素通り）
SCOPE_RE = re.compile(r"(^|/)(outputs|session|reports?|docs)/", re.I)
EXT_RE = re.compile(r"\.(md|markdown|mdx)$", re.I)
# レポート命名規約 <TOPIC>_YYYYMMDD.md はディレクトリを問わず対象にする
REPORT_NAME_RE = re.compile(r"_\d{8}(?:-v\d+)?\.(md|markdown|mdx)$", re.I)

# 自己言及語。「筆者/我々/当レポート/本報告書」等の言い換えも押さえる。
SELF = (r"(本書|本レポート|本稿|本資料|本文書|本報告書?|本節|本改訂|当レポート|"
        r"筆者|我々|執筆者|著者|初版|旧版|前版|前回|当初|初出|私|わたし|Claude)")
# 制作工程を表す行為語。
# 審査/確認/検品 は 2026-09-09 の実測で抜けていた:
#   「審査を2周した。」          -> ACT に審査が無く素通り
#   「当レポートは全出典を確認済み。」-> ACT に確認が無く素通り(本報告書も同様)
# 「確認」は単独では日常語すぎるが、ここは SELF との共起でしか使われない
# ので誤検出しない。実測: MUST_PASS 15件すべて通過を維持。
ACT = (r"(監査|点検|審査|検品|レビュー|査読|校閲|校正|検証|照合|突合|精査|"
       r"ファクトチェック|fact-?check|チェック|確認|是正|修正|訂正|差し替え|"
       r"改め|撤回|反映|通過|合格|採点|スコア)")
# 「確認できなかった」型＝主張の適用範囲を狭める正当な記述。消させてはならない。
NEG = r"(?![^。\n]{0,60}(ない|なかった|できず|限[りら]|範囲では|とどま|及ばな|時点))"

# 第三者が主語なら制作過程ではない。実測の誤検出:
#   「金融庁は2024年に12件を是正するよう命じた」「論文の統計に誤りが見つかり撤回された」
# 行内に第三者主語・受動の出典表現があれば、その行は制作過程と見なさない。
THIRD_PARTY = re.compile(
    r"(金融庁|厚労省|省庁|議会|委員会|当局|裁判所|NRC|NASA|報道|論文|"
    r"[A-Z][a-z]+\s+\d{4}|\(\d{4}\)|（\d{4}）|によれば|とされる|"
    r"命じた|勧告|された。|されている)")

PROCESS_LEAK = [
    # --- 件数・スコアの自己申告（助数詞・漢数字・語順逆転に対応） ---
    (r"(\d+|[一二三四五六七八九十]+|[０-９]+)\s*(件|か所|箇所|ヶ所|項目|点)"
     r"[^。|\n]{0,12}(是正|修正|訂正|差し替え|直し)", "是正件数の自己申告"),
    (r"(是正|修正|訂正)(件数|箇所)?\s*[:：]?\s*\d", "是正件数の自己申告(逆順)"),
    (r"(\d+|[一二三四五六七八九十]+)\s*(巡|周|回|ラウンド)(目)?の?\s*"
     r"(点検|監査|レビュー|チェック|査読|校閲)", "点検ラウンドの記述"),
    # 「監査を2周実施した」= 語順が逆（行為→回数）。上の式は回数→行為しか見ない。
    (r"(監査|点検|審査|レビュー|チェック|査読|校閲|校正)\s*を?\s*"
     r"(\d+|[一二三四五六七八九十]+)\s*(巡|周|回|ラウンド)", "点検ラウンドの記述"),
    # 「レビュー指摘をすべて反映済み」= 受けた指摘を取り込んだという制作過程。
    (r"(レビュー|指摘|コメント|フィードバック)[^。\n]{0,10}"
     r"(反映|対応)(済み|した|しました|しています)", "受領指摘への対応の露出"),
    (r"(レビュー|採点|スコア|正確[率度]|整合率|品質|QC)\s*[:：は]?\s*"
     r"\d+\s*(/\s*100|点|%|％)", "自己採点の露出"),
    # --- 自作物の工程開示（SELF × ACT。否定文脈は除外） ---
    (SELF + NEG + r"[^。\n]{0,40}" + ACT +
     r"[^。\n]{0,10}(済み|した|しています|を経て|を通|完了|通過|合格)",
     "自作物の検証工程の開示"),
    # --- 版履歴・前版の主張への言及（ユーザー指摘の中核クラス） ---
    (r"(初版|旧版|前版|前回|当初|初出|v\d)[^。\n]{0,40}"
     r"(撤回|改め|訂正|修正|誤|主張|判定|見立て|評価)", "自分の前版への言及"),
    (r"(一部)?撤回(する|した|します)", "自分の主張の撤回"),
    (r"(前回|当初)\s*\d+\s*点\s*(→|->|から)", "自作物の版間スコア比較"),
    # --- 過失の告白・正誤比較 ---
    (r"(私|わたし|Claude|筆者)の\s*(調査不足|誤り|ミス|見落とし|拡大解釈|"
     r"手抜き|不足|勇み足)", "自分の過失の告白"),
    (r"(本人|ユーザー|あなた|ご指摘)(が|の)\s*正し", "自分と依頼者の正誤比較"),
    (r"(ご指摘|指摘)の\s*とおり", "依頼者の指摘への応答"),
    # 「誤りを発見し、訂正した」= が でなく を。助詞ひとつで抜けていた。
    (r"(誤り|ミス|間違い|誤記)(が|を)\s*(あった|あり|判明|見つか|発見|検出)",
     "自己申告の誤り報告"),
    # --- 品質宣言・第三者確認の自慢 ---
    (r"(本(書|レポート|稿)は|これが)\s*最終(版|稿)", "自作物への品質宣言"),
    (r"(第三者|独立)(の目|レビュ|確認)", "第三者確認の露出"),
    (r"(確定した内容のみ|精査のうえ|精査した上で|精査済み)", "自作物の選別工程の開示"),
    # --- 内部ツール・工程名の露出 ---
    # \b は日本語の直前で境界にならないので使えない。.py 付きの表記
    # (verify_citations.py) が素通りしていたため明示的に許す。
    (r"(coverage-critic|fact-check-reviewer|analysis-qa-checklist|"
     r"verify_citations(\.py)?|md_report_qa(\.py)?|check_research_report|"
     r"サブエージェント|critic)",
     "内部工程名の露出"),
    (r"Claude\s*Code", "ツール名の露出"),
]

BACKMATTER_HEAD = re.compile(
    r"^#{1,6}\s*[\d.\s]*(参考文献|出典|情報源|references|bibliography|"
    r"改訂履歴|変更履歴|更新履歴|版履歴|revision history|changelog|"
    r"付録|付記|補遺|appendix|謝辞|免責)",
    re.I)
BACKMATTER_BOLD = re.compile(
    r"^\*\*(改訂履歴|変更履歴|更新履歴|版履歴|revision history|changelog)\*\*\s*$",
    re.I)
# 巻末の後ろに本文が再開したら、そこからは再び検査対象に戻す。
# （実測の穴: 先頭に「## 出典」を1行置くだけで全文が対象外になっていた）
BODY_RESUME = re.compile(
    r"^#{1,6}\s*[\d.\s]*(結論|考察|まとめ|本文|分析|要約|概要|提言|推奨|"
    r"背景|方法|結果|議論|summary|conclusion|analysis|findings)", re.I)

ZW = u"​‌‍﻿"


def _normalize(text):
    """強調記号・表罫線・ZWSP・段落内改行で分断された語を復元してから検査する。

    実測された回避: `**3件**を**是正**` / `| 是正 | 3件 |` / `監​査`（ZWSP）/
    `誤りが\nあった`。いずれも行単位・素の正規表現では一致しない。
    """
    text = re.sub(u"[%s]" % ZW, "", text)
    # `_` is BOTH an emphasis marker and an ordinary identifier character.
    # Stripping it unconditionally turned verify_citations.py into
    # verifycitations.py, so the internal-tool-name rule could never match --
    # the normalizer, added to defeat emphasis, had become a bypass of its own
    # (measured 2026-09-09). Remove it only where it is not between two
    # identifier characters, i.e. where it is really emphasis.
    text = re.sub(r"[*`~]+", "", text)
    text = re.sub(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])", "", text)
    return text


def _scan_lines(text):
    """行番号を保ったまま、検査に使う正規化済みの行を返す。

    段落内改行の結合は行番号を壊すため、各行に「次の行を連結した仮想行」を
    足して評価する（2行にまたがる分断だけを救う。それ以上は追わない）。
    """
    raw = _normalize(text).split("\n")
    out = []
    for i, line in enumerate(raw):
        joined = line + (raw[i + 1] if i + 1 < len(raw) else "")
        out.append((i + 1, line.replace("|", " "), joined.replace("|", " ")))
    return out


def _body_ranges(lines):
    """検査対象の行番号集合。巻末は除外するが、本文が再開したら復帰する。"""
    active = True
    keep = set()
    for i, l in enumerate(lines):
        if BACKMATTER_HEAD.match(l) or BACKMATTER_BOLD.match(l):
            active = False
        elif BODY_RESUME.match(l):
            active = True
        if active:
            keep.add(i + 1)
    return keep


def _read_text(path):
    """Decode a .md file whatever its encoding. Returns "" if unreadable.

    WHY NOT io.open(..., errors="replace") (measured 2026-09-09)
    ------------------------------------------------------------
    The attack corpus proposed errors="replace" so the guard would stop
    skipping non-UTF-8 files. That stops the CRASH but not the BYPASS:

        u"監査を2周実施し、3件を是正しました。".encode("cp932")
          .decode("utf-8", "replace")
        -> '\ufffd\u010d\u2026\u20262\u2026\u2026{\u2026\uff0c3\u2026...'

    The Japanese is destroyed, so no pattern can match it and the file sails
    through. Saving as Shift_JIS was a free bypass either way. Decoding has to
    actually succeed, so try the encodings that occur on this machine in order
    and keep the first that round-trips cleanly.

    Order matters: utf-8 first (the norm), then the Windows locale codec, then
    the UTF-16 variants a BOM would indicate. errors="replace" survives as the
    last resort so an exotic encoding still gets a best-effort scan rather than
    a silent skip.
    """
    try:
        raw = io.open(path, "rb").read()
    except Exception:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        for enc in ("utf-16",):
            try:
                return raw.decode(enc)
            except Exception:
                pass
    for enc in ("utf-8-sig", "utf-8", "cp932", "euc-jp", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def _targets(ti):
    paths = []
    for k in ("file_path", "filePath", "path", "notebook_path"):
        v = ti.get(k)
        if isinstance(v, str) and v:
            paths.append(v)
    # MultiEdit: edits[] に file_path が入る
    for e in (ti.get("edits") or []):
        if isinstance(e, dict):
            v = e.get("file_path") or e.get("filePath")
            if isinstance(v, str) and v:
                paths.append(v)
    if paths:
        return paths
    if not (ti.get("command") or ""):
        return []
    try:
        # -uall で未追跡ディレクトリを展開、-z で quotepath による八進エスケープを回避
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "-z", "-uall"],
            stderr=subprocess.DEVNULL).decode("utf-8", "replace")
    except Exception:
        return []
    return [rec[3:] for rec in out.split("\0") if len(rec) > 3]


def _in_scope(p):
    q = p.replace("\\", "/")
    if not EXT_RE.search(q):
        return False
    return bool(SCOPE_RE.search(q) or REPORT_NAME_RE.search(os.path.basename(q)))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    ti = payload.get("tool_input") or {}

    targets = [t for t in _targets(ti) if _in_scope(t)]
    targets = [t for t in targets if os.path.isfile(t)]
    if not targets:
        return 0

    hits = []
    advisory = []
    for tgt in targets:
        # 非 UTF-8 は「読めるように」ではなく「正しく復号」しなければ意味がない。
        # replace で読むと日本語が壊れて素通りする（_read_text の docstring）。
        text = _read_text(tgt)
        if not text:
            continue
        rows = _scan_lines(text)
        keep = _body_ranges([r[1] for r in rows])
        for lineno, line, joined in rows:
            if lineno not in keep:
                continue
            for pat, label in PROCESS_LEAK:
                # 一致した本体（line か joined）と同じ文字列で第三者判定する。
                # line だけで判定すると、空行+次行の結合で一致した場合に
                # 第三者主語を見落とす（実測: 「金融庁は…12件を是正」が L6 空行で誤検出）。
                hit_text = None
                if re.search(pat, line):
                    hit_text = line
                elif re.search(pat, joined):
                    hit_text = joined
                if hit_text is None:
                    continue
                # 第三者の行為を述べた文は制作過程ではない（ツール名の露出は別枠）。
                if label not in ADVISORY_LABELS and THIRD_PARTY.search(hit_text):
                    continue
                rec = "%s L%d %s: %s" % (tgt, lineno, label,
                                         hit_text.strip()[:60])
                (advisory if label in ADVISORY_LABELS else hits).append(rec)
                break

    if hits:
        _record_fired("process_leak_guard", payload)
        sys.stderr.write(
            u"⛔【process_leak】制作過程が読者向け本文に混入 %d件。\n"
            u"何を修正したか・どう検証したか・前版で何を間違えたかは『報告』に"
            u"書くもので、『成果物』に書くものではない"
            u"（analysis-qa-checklist/SKILL.md L17）。\n"
            u"読者に必要なのは『いま何が正しいか』だけ。経緯を残すなら"
            u"巻末の「## 付録 改訂履歴」へ移設すること。\n%s\n"
            % (len(hits), "\n".join(hits[:10])))
        return 2
    if advisory:
        sys.stderr.write(
            u"⚠【process_leak・警告のみ】ツール名の露出 %d件。"
            u"レポートの主題がツール自体なら無視してよい。\n%s\n"
            % (len(advisory), "\n".join(advisory[:5])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
