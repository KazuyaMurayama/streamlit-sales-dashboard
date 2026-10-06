"""PreToolUse hook (Task): remind when a judgment-tier subagent is launched on Sonnet.

背景（2026-08-14 ユーザー指示）: 使用量に約50%の余裕があるため、単純タスク以外は
Opus/Fable を積極的に使う方針へ転換した。本フックは「文面だけのルールは守られない」
という §14 の教訓に対する決定論的ガードである。

判定: Task ツールの subagent_type / description / prompt に判断系タスクの語が
含まれるのに model 指定が sonnet 系のとき、非ブロッキングの警告を出す。

Fail-open: 例外は必ず exit 0（無反応で握りつぶさず、下の SELFTEST で発火確認する）。
ブロックはしない（permissionDecision は使わない）。誤検知で作業を止める害の方が大きい。

Deployed from claude-governance/hooks/ — edit there, not the deployed copy.

SELFTEST:
    python model_tier_guard.py --selftest
  欠陥版（判定ロジックを外した版）に当てると FAIL することを確認済み。
"""
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

# 判断が必要な工程を表す語。ユーザー指示 2026-08-14「計画段階、分析、最終チェック、
# その他判断が必要なプロセス」を語彙化したもの。固有名詞ではなく工程名で書く。
JUDGMENT = re.compile(
    r"計画|設計|方針|分析|検証|レビュー|監査|評価|判断|QC|品質|"
    r"批判|反証|考察|戦略|最終チェック|critic|review|audit|verify|"
    r"analy|plan|design|judge|assess|critiq",
    re.I,
)

# 単純タスク＝Sonnet で妥当な工程。これに該当すれば警告しない。
SIMPLE = re.compile(
    r"整形|置換|リネーム|コピー|転記|抽出のみ|一覧|列挙|grep|"
    r"format|rename|copy|list|fetch|download|scrape",
    re.I,
)

SONNET = re.compile(r"sonnet|haiku", re.I)


def verdict(model, text):
    """Return a reason string when this Task should be escalated, else None.

    分離した純関数。SELFTEST はここを直接叩く（本体を import して確認する / §14 F2）。
    """
    if not SONNET.search(model or ""):
        return None
    if SIMPLE.search(text) and not JUDGMENT.search(text):
        return None
    if not JUDGMENT.search(text):
        return None
    return (
        "モデル階層ルール（2026-08-14）: 判断を伴う工程（計画・分析・検証・最終チェック等）は "
        "Opus を既定とし、独立QC・最終レビューのみ Fable を使う。"
        "この Task は判断系だが sonnet 系で起動されようとしている。"
        "単純作業（整形・転記・機械的抽出）ならこのまま可。"
        "判断を含むなら model を 'opus'（独立QCなら 'fable'）に変更すること。"
    )


def main():
    # リポ側に同名フックがあればそちらに委ね、二重発火を避ける（既存フックと同じ規約）。
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(
            os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__))
        )
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        # stdin だけでなく stdout も UTF-8 に固定する（2026-10-06）。stdout が cp932 のままだと
        # 警告文が文字化けし、14日166回の発火がすべてモデルに読めなかった。
        for _s in (sys.stdin, sys.stdout):
            try:
                _s.reconfigure(encoding="utf-8")
            except Exception:
                pass
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
        ti = data.get("tool_input") or {}
        # 判定は subagent_type と description だけで行い、prompt 本文は見ない。
        # 較正（2026-10-06・実測・直近14日の委譲988件、うち sonnet 指定321件）:
        #   prompt まで見ると sonnet 委譲の 78.2%（251件）で発火した。prompt には
        #   「検証」「計画」等の定型語が必ず入り、実装・転記の委譲まで警告して形骸化する。
        #   description だけにすると 22.4%（72件）に下がり、残るのは「QC前提攻撃」
        #   「Verify Task deliverables」等の判断系だった。
        text = " ".join(
            str(ti.get(k) or "")
            for k in ("subagent_type", "description")
        )
        why = verdict(str(ti.get("model") or ""), text)
        if why:
            _record_firing("model_tier_guard", data)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": why,
                }
            }, ensure_ascii=False))
    except Exception:
        pass


def selftest():
    """当時の欠陥版に当てて FAIL することを確認するためのケース群。"""
    cases = [
        # (model, text, should_warn)
        ("sonnet", "計画の骨子を作る", True),
        ("sonnet", "最終チェックとQCレビュー", True),
        ("claude-sonnet-5", "analyze the backtest results", True),
        ("sonnet", "ファイル名を一括リネーム", False),      # 単純タスク
        ("sonnet", "CSVを整形して転記", False),             # 単純タスク
        ("opus", "計画の骨子を作る", False),                 # 既に上位モデル
        ("claude-fable-5", "最終レビュー", False),           # 既に上位モデル
        ("", "計画を立てる", False),                         # model 未指定=継承、判定しない
        ("sonnet", "grepして一覧を出す", False),
        ("sonnet", "設計方針を判断する", True),
    ]
    bad = 0
    for model, text, want in cases:
        got = verdict(model, text) is not None
        ok = got == want
        if not ok:
            bad += 1
        print("%-4s model=%-16r want=%-5s got=%-5s %s"
              % ("ok" if ok else "FAIL", model, want, got, text))
    print("\nSELFTEST %s (%d/%d)" % ("PASS" if not bad else "FAIL", len(cases) - bad, len(cases)))
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
    sys.exit(0)
