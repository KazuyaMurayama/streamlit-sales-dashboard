# -*- coding: utf-8 -*-
"""Detect strategy/design choices justified by the CURRENT pre-launch state.

WHY THIS EXISTS (2026-10-06)
----------------------------
User, on a note membership benchmark report (Soulful-Content
_meta/NOTE_MEMBERSHIP_BENCHMARK_20261006.md @ 325f37d):
「まだほとんどリリースしていないのに、今のフォロワー数をもとに何かの判断にするのは
おかしいのではないでしょうか？そのように論理的・戦略的、あるいは起業家の観点で
しょうもないことを書いているレポートの箇所が数箇所ある」

The report chose the plan design with reasons such as
「フォロワーが1人の段階では、会員限定だけだと記事を見つけて読む入口が無い」 and
「会員一覧は公開しない（少人数のうちは寂しく見える）」. The same defect was already
in an older report of the same repo (BENCHMARK_ANALYSIS_20260916.md:
「メンバーシップ … 今は追えない。母数がない段階では成立しない」). Before launch, the
current follower/member/article count is the starting point of what is being
built, not a constraint on its design. A strategy derived from it plans for
staying small.

INVARIANT
---------
A sentence that states the current small size of the thing being built
(followers, members, readers, customers, articles, sales — 「フォロワー1人」
「会員が少ない」「少人数のうちは」「母数がない段階」「立ち上げ初期の段階」) must
not also carry a design/strategy decision (取る・採らない・使わない・作らない・
成り立たない・入口が無い・後から足す・推奨 …). The current value may appear as a
baseline (起点・ベースライン・目標まで増やす), never as the reason.

WHAT IT CANNOT DO
-----------------
It cannot tell whether a decision is right. It reports only that a decision
and a statement of the current small state sit in the same sentence (or the
same table cell), which is the shape the user corrected. A decision that is
genuinely constrained by the present (cash in hand this month, a legal
condition) is phrased with those words, not with audience size, and is not
matched.

CALIBRATION: see tests/calibrate_startup_state_check.py (measured on every
report-scope .md in the local repos; numbers in that file's docstring).

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import re

_WHO = (r"(?:フォロワー|会員|読者層?|購読者|登録者|顧客|ユーザー|メンバー|ファン層?|視聴者|受講者|利用者|"
        r"リスト|お客様|購入者|支援者|参加者|読み手|読んでくれる人|見てくれる人|コミュニティ)")
_WHAT = r"(?:実績|売上|記事|投稿|母数|認知|知名度|露出|流入|アクセス|PV|集客|発信)"
# A small count: a number, or the words used instead of one.
_NUM = r"(?:[0-9０-９,，]+(?:人|名|件|本|PV)|ゼロ|数人|数名|一桁|ひとり|一人|片手で数えられる(?:ほど)?)"
_SMALL = (r"(?:少ない|少数|小さい|ゼロ|(?<!で)無い|(?<![でし])ない|いない|乏しい|足りない|0人|0件|0本|一桁|"
          r"育っていない|育ってない|集まっていない|ついていない|付いていない)")
# Words that mark "now / still", needed for the vaguer shapes so that a
# general statement about small creators (「フォロワーが少ないクリエイターは…」
# in a market analysis) is not read as our own current state.
_NOW = (r"(?:まだ|今は|いまは|今の|いまの|今、|いま、|現在|現状|現時点|現段階|今のところ|当面|この段階|この時点|"
        r"ほとんど|しばらく)")
# Between the noun and the "small" word only particles and degree words -- 「読者に宛てていない」
# (a statement about whom a text addresses) is not 「読者がいない」.
_GAP = r"(?:が|は|も|の)?(?:まだ|ほとんど|全く|全然|あまり|十分に)*"
_FRAME = (r"(?:の段階(?:では|だと|なので|は|で(?!(?:上位|足|開|追加)))|の状態(?:では|だと|なので|は)|のうち(?:は|から)?|しか|"
          r"だけ(?:では|だと|なので)|なので|では|という(?:現状|状況|状態)|の今|のこちら|の現状|に過ぎ|足らず|"
          r"から(?:の)?スタート|で始め|ゆえ|だから|のため)")
STATE = re.compile(
    # 1. a number for the current size, with a framing that makes it "the state now"
    _WHO + r"(?:数)?(?:が|は|も|わずか|たった|は?まだ|\s)*" + _NUM + r"(?:・[^。]{0,12})?" + _FRAME
    # 1b. a now-word before the number (「フォロワー数は現状1人」「会員が現在1人で」「いまの読者数（1人）」)
    + r"|" + _WHO + r"(?:数)?(?:が|は|も)?" + _NOW + r"[^。]{0,4}?" + _NUM
    + r"|" + _NOW + r"[^。]{0,6}?" + _WHO + r"(?:数)?(?:が|は|も)?\s*[（(]?\s*" + _NUM
    # 2. "few / none" with an explicit now-word, either order
    + r"|" + _NOW + r"[^。]{0,8}?(?:" + _WHO + r"|" + _WHAT + r")(?:数)?" + _GAP + _SMALL
    + r"|(?:" + _WHO + r"|" + _WHAT + r")(?:数)?(?:が|は)?" + _NOW + _GAP + _SMALL
    # 3. fixed phrases for the early stage
    + r"|(?:" + _WHO + r"|" + _WHAT + r")(?:数)?(?:が|は)?(?:まだ)?" + _SMALL + r"(?:うち|間|あいだ)"
    r"|少人数のうち|小規模なうち|規模が小さいうち|人が少ないうち"
    r"|(?:立ち上げ|開設|リリース|ローンチ|開始)(?:直後|初期|当初|したばかり|たばかり)(?:の|は|で)?(?:段階|うち|今|状態|なので)?"
    r"|(?:立ち上げ|開設|リリース|ローンチ)前(?:の|は|で)?(?:段階|うち|今|状態)"
    r"|まだ(?:ほとんど)?(?:リリース|公開|発信|販売|開設)して(?:い)?ない(?:段階|うち|今|状態|ので|から|ため)"
    r"|母数(?:が|は|の)?(?:まだ)?(?:無い|ない|少ない|小さい|足りない)"
    r"|(?:" + _WHO + r")(?:が|は)?(?:まだ)?少ない(?:こちら|段階|うち|今|状態|側)"
    r"|(?:まだ)?無名(?:な|の|で|だ)|名前が(?:まだ)?(?:知られていない|知られてない)|知名度が(?:まだ)?(?:低い|無い|ない)"
    r"|(?:ほとんど)?誰にも(?:ほとんど)?(?:読まれて|知られて|見られて|見つけられて)(?:い)?ない"
)
DECISION = re.compile(
    r"取る|採る|採用|採らない|選ぶ|選ばない|(?:採用|導入|実施|公開|開設|販売|追加|設定|提供|作成|検討|参入|投資)しない|使わない|"
    r"作らない|置かない|置く|やめ|見送|成り立たない|成立しない|成り立つ|成立する|追えない|追わない|向かない|向いていない|無理|"
    r"入口が(?:無|な)|入口に|入口と|推奨|べき|後回し|後から|あとから|後に足|足す|開かない|公開しない|"
    r"勝てない|意味が(?:無|な)い|効かない|不要|必要ない|寂しく見え|見せない|始める|始めない|"
    r"優先|先に|絞る|避ける|控える|待つ|延期|最初は|最初に取れる|取れる形|出さない|出す|非公開|据え置|"
    r"有料化|無料に|無料で|限定化|過剰|上げない|上げる根拠"
)
# The state written as a baseline / future milestone, or the fallacy itself named and rejected.
# 「会員30人を超えてから足す」「100人に達した段階で開く」は計画の節目であって、現状を理由にしていない。
# 「目標」は免責しない（「目標の100人に届くまでは全記事を無料」は現状を理由にした判断のまま。Fable 2026-10-06）。
BASELINE = re.compile(
    r"を超えたら|に達したら|になったら|を超えてから|に達してから|を超えた(?:段階|時点)|に達した(?:段階|時点|ら)|"
    r"到達した(?:段階|時点|ら)|増えたら|集まったら|"
    r"ベースライン|起点|出発点|基準値|スタート地点|から(?:増や|伸ば)|まで(?:増や|伸ば)|KPI|"
    r"根拠に(?:しない|使わない|ならない|すべきでない)|前提に(?:しない|置かない)|"
    r"判断(?:の根拠|材料)に(?:しない|使わない|ならない)|現状値で(?:決め|判断)(?:ない|しない)|"
    r"に関係なく|にかかわらず|に左右されない"
)
# Someone else's case or a general statement, not our own reasoning.
OTHERS = re.compile(r"^(?:\W|\*)*(?:他社|競合|他の(?:クリエイター|事業者|会社))(?:の)?事例|一般に|一般論として|通説|"
                    r"(?:他社|競合)の事例では|事例では|氏の|さんの")
QUOTE = re.compile(r"「[^」\n]{0,200}」")


def _strip_uncheckable(text):
    out = list(text)

    def blank(m):
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "

    for pat in (r"```.*?```", r"<!--.*?-->"):
        for m in re.finditer(pat, text, flags=re.DOTALL):
            blank(m)
    return "".join(out)


_CONT = re.compile(r"^\s*(?:この(?:規模|状態|段階|状況|人数|数)|その(?:規模|状態|段階|状況)|そのため|なので|だから|ゆえに|したがって)")


def _units(line):
    """Sentences of a line. A table row is one unit (the reason and the decision often
    sit in different cells). A sentence that continues the previous one (「この規模で…」
    「そのため…」) is joined to it -- the state and the decision were split across 。"""
    if line.lstrip().startswith("|"):
        yield " ".join(c.strip() for c in line.strip().strip("|").split("|"))
        return
    prev = None
    for s in re.split(r"(?<=。)", line):
        if not s.strip():
            continue
        if prev is not None and _CONT.match(s):
            prev = prev + s
            continue
        if prev is not None:
            yield prev
        prev = s
    if prev is not None:
        yield prev


def analyze_text(text):
    """Return findings: a current-small-state statement and a decision in one sentence."""
    if not text:
        return []
    findings = []
    for i, ln in enumerate(_strip_uncheckable(text).split("\n")):
        if re.match(r"^\s*\|?\s*:?-{3,}", ln):
            continue
        for s in _units(ln):
            q = QUOTE.sub("「」", s)          # quoted words are someone else's, not our reasoning
            m = STATE.search(q)
            if not m or not DECISION.search(q) or BASELINE.search(q) or OTHERS.search(q):
                continue
            findings.append({"line": i + 1, "state": m.group(0), "text": s.strip()[:90]})
    return findings
