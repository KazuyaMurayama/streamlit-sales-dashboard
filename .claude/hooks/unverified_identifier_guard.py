# -*- coding: utf-8 -*-
"""Stop hook: never hand the user an identifier you did not actually open.

THE DEFECT THIS EXISTS FOR (measured 2026-09-03)
------------------------------------------------
The answer gave the user a three-step procedure with three URLs to open.
Two of the three were invented:

    given  https://coconala.com/mypage/setting/phone   -> real /mypage/sms
    given  https://coconala.com/mypage/identifications -> real /mypage/user_identification
    given  https://coconala.com/mypage/nda             -> correct

They were assembled from English words ("settings" + "phone") rather than
read off the site. The settings page linked to all three; one read would have
produced the right answers. The step ORDER was wrong too, for the same reason:
NDA cannot be signed before identity approval, which the real screen states.

WHY PROSE COULD NOT HAVE PREVENTED IT
-------------------------------------
This was NOT a case of not knowing the rule. The same answer carried a
留保 line saying, in the author's own words, that the three URLs had not been
opened. The rule was known, the gap was known, and the procedure shipped
anyway -- the disclaimer functioned as an indulgence. CLAUDE.md §14 F1 and
§11.2 both already forbade this.

So a countermeasure made of more prose fails by construction: it addresses a
reader who already read the prose and shipped regardless. It has to be a gate
that does not ask the author whether they feel confident.

The 2026-09-03 follow-up compounded this. The countermeasure that WAS written
for it was one memory file plus a §7.6 section inside a single repo's markdown
-- prose, in 1 of 44 repos, nothing global, nothing mechanical. The user had
explicitly asked for something not limited to one repository.

DETECTION: the shape of the OUTPUT, not the confidence of the author
--------------------------------------------------------------------
Fire only when BOTH hold:

  1. The answer hands the user something to ACT ON. Not every mention of a URL
     is a hazard -- quoting a source, citing a repo, or reporting what was
     fetched are all fine. The hazard is an instruction: 「このURLを開く」,
     a numbered 手順 table, 「〜を実行してください」. That is the moment the
     verification cost transfers to the user, who cannot cheaply tell a real
     path from a plausible one.

  2. That instruction contains a third-party http(s) URL which this turn never
     fetched. Scope is deliberately narrow -- see the note at `bad = [...]` in
     main() for the measurement that ruled repo paths out.

Both conditions are read off the transcript. Neither consults the model's
sense of certainty, which is what failed.

WHY "INSTRUCTION" IS THE TRIGGER, NOT "URL PRESENT"
---------------------------------------------------
A hook that fired on every URL would fire on nearly every answer, be muted
within a day, and protect nothing. The 2026-09-03 harm needed the handoff:
"自分の作業なら404で気付いて直せるが、他人に渡した瞬間に検証コストは相手の
時間になる" (from the memory written that day). Gate on the handoff.

DELIBERATELY NOT DONE
---------------------
Does not fetch URLs itself. A Stop hook that issues network requests as a side
effect of answering would be a worse defect than the bug -- it would leak the
content of answers to third-party hosts. It reports which identifiers are
unverified and makes the author go look.

Does not verify correctness, only that the identifier was CONTACTED. An author
who opens a URL and then mistypes it is out of scope; the measured failure was
never opening it at all.

LOOP SAFETY: `stop_hook_active` -> return, so at most one block per answer.
FAIL-OPEN: any exception -> exit 0. A broken guard must not wedge a session.
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

# --- Firing-log recording (defect 2, 2026-09-03) ----------------------------
#
# Same rationale and format as countermeasure_gate.py: the ledger's
# V2_NO_FIRING_LOG check reads ~/.claude/state/<hook>/, and this guard
# previously never wrote there despite existing specifically to catch a
# self-violation class in OTHER answers. Format matches notfound_guard.py's
# convention. Every step is wrapped -- a broken guard must not wedge a
# session, and that includes its own bookkeeping.
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "unverified_identifier_guard")


def _fire_sid(ev):
    s = ev.get("session_id") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64]


def _record_fired(ev):
    """Best-effort: write/update
    ~/.claude/state/unverified_identifier_guard/<sid>.json with last_fired
    (ISO8601 UTC) and a cumulative count. Never raises."""
    try:
        path = os.path.join(STATE_DIR, _fire_sid(ev) + ".json")
        prev = {}
        try:
            with io.open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}
        count = prev.get("count", 0)
        if not isinstance(count, int):
            count = 0
        data = {
            "last_fired": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "count": count + 1,
        }
        os.makedirs(STATE_DIR, exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

# --- Condition 1: is this answer telling the user to DO something? ---------
#
# Japanese imperative/procedural forms plus the table-and-numbered-step shapes
# that a 手順書 takes. 「開いてください」「アクセスし」「実行してください」.
# 「以下の手順」 and a numbered step that contains a URL both count.
INSTRUCT = re.compile(
    u"(?:を|に|へ)[^。\n]{0,8}(?:開いて|アクセスして|移動して|遷移して|入力して"
    u"|押して|クリックして|実行して|登録して|申請して|提出して|設定して)"
    u"(?:ください|下さい|ほしい|欲しい|もらえ)"
    u"|(?:開く|アクセスする|実行する|押す)[^。\n]{0,6}$"
    u"|以下の(?:手順|ステップ|URL|リンク|流れ)"
    u"|次の(?:手順|ステップ|URL|リンク)"
    u"|手順(?:は|:|：)"
    u"|(?:本人|ユーザー|あなた)(?:が|に)[^。\n]{0,10}(?:作業|実行|対応)"
    u"|Next Action"
    u"|\\|\\s*\\d+\\s*\\|"          # a numbered row in a markdown table
    u"|^\\s*\\d+[.)]\\s",           # "1. ..." / "1) ..." numbered step
    re.MULTILINE)

# An explicit hand-off phrase is on its own sufficient -- it names the transfer
# of work to the user even without an imperative verb.
HANDOFF = re.compile(
    u"本人作業|ユーザー(?:側|)作業|お手数ですが|やっていただく|してもらう"
    u"|あなたの作業|要対応|ご対応")

# --- Identifiers that can be verified, and are worth verifying -------------
#
# External http(s) URLs. Excludes localhost/127.0.0.1 (nothing to fabricate --
# the user's own machine) and example.com (conventionally a placeholder).
URL = re.compile(r"https?://[^\s<>\"'\)\]\|`]+")
# github.com/gitlab.com blob+tree links are EXCLUDED here, deliberately, and
# this is the single most important calibration decision in the file.
#
# Measured over 27 real transcripts / 2516 assistant turns: including them made
# the guard fire on 35.9% of ALL turns, and 3253 of the 3579 flagged
# identifiers (90.9%) were exactly these. That is not a safety net, it is a
# nag that gets muted within a day -- and a muted guard protects nothing.
#
# They are excluded because they are ALREADY governed, more strictly, by a
# different rule: CLAUDE.md §9 requires every deliverable URL to be confirmed
# with `git ls-tree origin/<branch> -- <path>` before it is reported, and
# post_bash_guard.py enforces that on push. Double-gating them buys no safety
# and spends the entire noise budget. The 2026-09-03 harm was a THIRD-PARTY
# site (coconala.com) whose paths cannot be guessed and are not covered by §9.
URL_SKIP = re.compile(
    r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::\d+)?"
    r"|example\.(?:com|org|net)"
    r"|^https?://(?:www\.)?(?:github|gitlab)\.com(?:/|$)")

# Repo-relative paths in an instruction: "scripts/foo.py", "docs/BAR_20260101.md".
# Requires a slash and a file extension so that ordinary prose containing a
# slash ("A/Bテスト", "入出力") does not register as a path.
PATH = re.compile(
    r"(?<![\w/.-])((?:[A-Za-z0-9_.-]+/){1,6}[A-Za-z0-9_.-]+"
    r"\.(?:py|md|json|ya?ml|js|ts|tsx|sh|ps1|gs|txt|csv|html|toml|ini|cfg))")

# --- Evidence that an identifier was actually contacted this turn ----------
#
# For a URL: a fetch/navigate tool ran against it, or curl/wget named it.
# Substring containment is the test -- the tool input records the URL verbatim.
FETCH_TOOLS = ("WebFetch", "browser_navigate", "browser_snapshot",
               "browser_find", "browser_click", "browser_evaluate",
               "WebSearch", "curl", "wget", "Invoke-WebRequest")

# Trailing punctuation that markdown/prose glues onto a URL but is not part of
# it. Stripped before comparison so a fetched URL still matches its mention.
TRAIL = u".,;:!?、。）)]」』>　"


def _sid(ev):
    s = ev.get("session_id") or "default"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64]


def _read_turn(transcript_path):
    """Return (answer_text, tool_blob, read_paths) for the latest turn.

    `tool_blob` is every tool input concatenated, used to ask "was this URL
    contacted?". `read_paths` collects file_path/path/notebook_path values so
    a path mentioned in an instruction can be checked against what was opened.

    Windowed to the last 4000 rows, matching notfound_guard.py: bounds parsing
    cost on multi-hundred-MB transcripts. readlines() still does full I/O.
    """
    try:
        with io.open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-4000:]
    except Exception:
        return "", "", set()

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
    # If the turn is longer than the window its own user row is gone; scan the
    # whole window rather than going silent on exactly the busiest turns.
    start = user_idx[-1] if user_idx else -1

    answer, tools, paths = [], [], set()
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
                for k in ("command", "pattern", "path", "file_path", "url",
                          "prompt", "query", "notebook_path", "urls"):
                    v = inp.get(k)
                    if isinstance(v, str):
                        tools.append(v)
                    elif isinstance(v, list):
                        tools.extend(x for x in v if isinstance(x, str))
                for k in ("file_path", "path", "notebook_path"):
                    v = inp.get(k)
                    if isinstance(v, str):
                        paths.add(v.replace("\\", "/"))
    return "\n".join(answer), "\n".join(tools), paths


def _unverified_urls(answer, tools):
    """URLs presented to the user that this turn never contacted."""
    out = []
    for raw in URL.findall(answer):
        u = raw.rstrip(TRAIL)
        if not u or URL_SKIP.search(u):
            continue
        if u in out:
            continue
        # Contacted if the exact URL appears in any tool input. Compared after
        # stripping trailing punctuation so markdown's "(url)." still matches.
        if u in tools:
            continue
        # A URL differing only by a trailing slash is the same resource.
        if u.rstrip("/") and u.rstrip("/") in tools:
            continue
        out.append(u)
    return out


def _unverified_paths(answer, tools, read_paths):
    """Repo paths presented to the user that this turn never opened."""
    norm = set()
    for p in read_paths:
        norm.add(p)
        norm.add(p.rsplit("/", 1)[-1])
    out = []
    for m in PATH.findall(answer):
        p = m.replace("\\", "/")
        if p in out:
            continue
        # Opened directly, named in any tool input (cat/sed/grep on it), or
        # reachable as the tail of an absolute path that was opened.
        if p in tools or p in norm:
            continue
        if any(q.endswith("/" + p) or q == p for q in norm):
            continue
        out.append(p)
    return out


REASON = u"""⛔ 未検証の識別子をユーザーに渡そうとしている（2026-09-03 の再発）

この回答は**ユーザーに実行させる手順**を含んでいるが、その中の次の識別子は
**このターンで一度もアクセスしていない**:

%s

なぜ止めるか: 2026-09-03、ココナラの本人確認手順で3つ中2つのURLが捏造だった
（`/mypage/setting/phone` → 実在は `/mypage/sms`、`/mypage/identifications` →
実在は `/mypage/user_identification`）。英単語を組み立てて作った文字列だった。
そのときの回答には「3つのURLを実際に開いて確認していない」という留保が付いて
いた——**未検証と分かった上で出した**。留保欄は判断に効くリスクを書く場所で
あって、自分の手抜きを開示して免責される場所ではない。

自分の作業なら404で気付いて直せる。他人に渡した瞬間、検証コストは相手の時間に
なる。手順書は成果物であり、成果物には検証義務がある。

いま行うこと:
 1. 上の識別子を1つずつ実アクセスする
    - URL      : WebFetch / playwright で開き、200 と中身を確認する
    - リポパス : `git ls-tree -r origin/<branch> --name-only | grep -F <PATH>`
                 （ローカルの `ls` は clone が古いと嘘をつく）
 2. **正解の入手経路を先に探す**。ココナラの例では設定ページのリンク一覧を
    1回読めば3つとも正解が得られた。推測より探索の方が速いことが多い。
 3. 実在しなかったものは、実在する識別子に**差し替える**。見つからなければ
    その手順を出さない（推測で埋めない）。
 4. ボタンの先の画面を実査できないなら、**そこで手順を止める**。押した先を
    想像で書かない。
 5. 手順の**順序**も実画面で確認する。2026-09-03 は順序も誤っていた（NDA は
    本人確認の承認後でないと締結できず、画面にその旨が明記されていた）。

「留保付きで未検証のまま出す」は選択肢に含めない。未検証の識別子を含む手順は、
留保の有無にかかわらず不合格である。
正典: ~/.claude/CLAUDE.md §14 F1 / memory feedback_no_fabricated_identifiers.md
"""


def main():
    # Defer to a registered repo-local copy, matching the existing convention.
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(
            os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        return

    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return

    if ev.get("stop_hook_active"):
        return

    tp = ev.get("transcript_path")
    if not tp:
        return
    answer, tools, read_paths = _read_turn(tp)
    if not answer:
        return

    # Condition 1: is the user being told to act?
    if not (INSTRUCT.search(answer) or HANDOFF.search(answer)):
        return

    # Condition 2: does the instruction carry a URL never contacted?
    #
    # URLs ONLY. Repo-path checking was implemented, measured, and removed:
    # over the same 2516 turns it produced 148 of 190 blocks (78%) while the
    # measured 2026-09-03 harm was entirely third-party URLs. The flagged paths
    # were overwhelmingly Claude describing files it had just written across a
    # multi-turn task -- verifiable in one `ls`, and wrong at no cost to the
    # user. Guessing `/mypage/setting/phone` is different in kind: the user
    # cannot tell a real path from a plausible one without opening it, and a
    # stale clone cannot be consulted for a third-party website at all.
    # Keeping both would have spent the noise budget on the harmless half.
    # `_unverified_paths` is retained and tested for a future opt-in.
    bad = [u"URL   " + u for u in _unverified_urls(answer, tools)]
    if not bad:
        return

    # Cap the listing: a long answer can mention many, and the point is made
    # by the first few. The count keeps the scale honest.
    shown = bad[:12]
    if len(bad) > len(shown):
        shown.append(u"... 他 %d 件" % (len(bad) - len(shown)))
    body = u"\n".join(u"  - " + b for b in shown)

    _record_fired(ev)

    out = {"decision": "block", "reason": REASON % body}
    # ensure_ascii=True + buffer.write: CP932 consoles mangle kanji whose
    # second byte is 0x5C (「表」= 0x95 0x5C) through a text stream, which
    # corrupts the JSON. Learned on md_date_guard.py.
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
