"""PostToolUse hook (Bash|PowerShell): after `git push`, remind the
deliverables-report rules (rule 2) at exactly the moment they become due.

Fail-open: any error -> exit 0.
Deployed from claude-governance/templates/hooks/ — edit there, not here.

CALIBRATION (measured 2026-09-04, narrowed 2026-09-07)
------------------------------------------------------
The original trigger -- any command whose text matched /git\\s+push/ --
fired on 89 of 600 replayed Bash/PowerShell calls = 14.83%, roughly one
in seven. That is warning-fatigue territory: the reminder appears often
enough to become background noise, and a reminder nobody reads is worth
nothing. Narrowed on measurement, not intuition. Three findings drove it:

 1. REPEATS DOMINATE. Across 938 real push calls in 682 turns, 20% of
    turns pushed more than once (up to 6+). The reminder is about the
    FINAL ANSWER, which happens once per turn, so every push after the
    first was pure noise. Firing once per turn: 682 instead of 938
    (-27%).

 2. MANY MATCHES WERE NEVER COMMANDS. 66 of 670 matches had `git push`
    only inside a heredoc body, an echo string, or a commit message --
    text, not an invocation. (This very hook fired on a Python literal
    containing the phrase while the narrowing was being measured.)

 3. FAILED PUSHES DO NOT CREATE THE OBLIGATION. 48 matches were
    rejections, `fatal:`, or "Everything up-to-date". Rule 2 is about
    reporting what was published; nothing was.

VERIFIED BEHAVIOUR (ran git, did not assume): `git push` writes its
success line ("-> main", "* [new branch]") to STDERR, not stdout, and
`git push -q` on success is COMPLETELY SILENT (rc=0, empty stderr).
So requiring positive evidence of success would silently drop every
quiet push -- 290 of 659 real matches used -q. The rule therefore
EXCLUDES FAILURES rather than requiring success: silence after a real
push invocation means it worked.

NET MEASURED EFFECT (full corpus, both rules on the SAME denominator --
every Bash/PowerShell call in all 27 transcripts, replayed through the
real hook with its real recorded output and true turn boundaries):

    old rule : 929 / 14822 = 6.27%
    new rule : 584 / 14811 = 3.94%     -37.1%

⚠️ The 14.83% quoted above came from a 600-call SAMPLE that happened to
be drawn from git-heavy stretches of work; the full-corpus rate for the
same old rule is 6.27%. Both numbers are real, they just have different
denominators. The full-corpus figure is the honest one for "how often
does this interrupt ordinary work", and it is the one to compare against
in future. Recording the discrepancy rather than quietly replacing the
number: a sample that flatters a change is exactly how calibration
becomes theatre.

Coverage of the case this hook exists for -- a successful push whose
deliverables must be reported -- is unchanged. Only repeats within one
turn, non-invocations, and failed/no-op pushes were removed.

RESIDUAL RISK: 3.94% is roughly 1 in 25 shell calls, which is not
nothing. If it still reads as noise in practice, the next lever is the
turn dedup's scope (currently per prompt_id); a per-session or
per-repo-per-day key would cut it further at the cost of missing a
second genuinely-reportable push in a long turn. Not done now because
that trade needs its own measurement.
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


# `git push` at a shell COMMAND position -- not inside a heredoc body, an
# echo string, or a commit message. Allows leading env assignments and any
# number of `cd ... &&` prefixes, which is how these commands are actually
# written here. 66 of 670 measured matches were text-only occurrences.
CMD_POS = re.compile(
    r"(?:\A|[\n;]|&&|\|\||\|)\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:cd\s+(?:\"[^\"]*\"|'[^']*'|\S+)\s*&&\s*)*"
    r"git\s+push\b")

# Evidence the push did NOT publish anything. Note the direction: we exclude
# failure rather than require success, because `git push -q` succeeds in
# total silence (verified by running it: rc=0, empty stderr) and 290 of 659
# real matches used -q. Requiring success would drop all of those.
# "Everything up-to-date" is here for the same reason as a rejection: nothing
# was published, so rule 2 has nothing to report.
FAILED = re.compile(
    r"rejected|!\s*\[remote|\bfatal:|\berror:|Permission denied|denied to"
    r"|non-fast-forward|failed to push|Everything up-to-date",
    re.IGNORECASE)

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state",
                         "post_bash_guard")


def _result_text(data):
    """Concatenate whatever the runner captured. `git push` writes its
    success line to STDERR, so stdout alone would look empty on every push."""
    tr = data.get("tool_response")
    if isinstance(tr, dict):
        return "%s\n%s" % (tr.get("stdout") or "", tr.get("stderr") or "")
    if isinstance(tr, str):
        return tr
    return ""


def _should_remind(cmd, data):
    if not CMD_POS.search(cmd or ""):
        return False
    if "--delete" in cmd:
        return False
    if FAILED.search(_result_text(data)):
        return False
    return True


def _claim_turn(data):
    """True at most once per turn. The reminder is about the FINAL ANSWER,
    which happens once; 20% of push-bearing turns pushed 2-6+ times (up to
    6+), and every repeat after the first was noise.

    Keyed on `prompt_id`, which the PostToolUse payload actually carries --
    confirmed by registering a probe hook and reading a real payload rather
    than assuming the field list. Full keys observed: cwd, duration_ms,
    effort, hook_event_name, permission_mode, prompt_id, scratchpad_dir,
    session_id, tool_input, tool_name, tool_response, tool_use_id,
    transcript_path. prompt_id is exactly "this turn", so it beats the
    transcript-size heuristic that was here first.

    Fail-OPEN (returns True) if prompt_id is missing or the state cannot be
    read or written: a missing reminder is worse than a duplicated one.
    """
    try:
        sid = re.sub(r"[^A-Za-z0-9_.-]", "_",
                     str(data.get("session_id") or "default"))[:64]
        marker = re.sub(r"[^A-Za-z0-9_.-]", "_",
                        str(data.get("prompt_id") or ""))[:80]
        if not marker:
            return True
        path = os.path.join(STATE_DIR, sid + ".turn")
        try:
            with open(path, encoding="utf-8") as f:
                if f.read().strip() == marker:
                    return False
        except OSError:
            pass
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(marker)
        return True
    except Exception:
        return True


def main():
    try:
        me = os.path.abspath(__file__)
        local = os.path.abspath(os.path.join(os.getcwd(), ".claude", "hooks", os.path.basename(__file__)))
        if me != local and os.path.exists(local):
            return
    except Exception:
        pass

    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace"))
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if _should_remind(cmd, data) and _claim_turn(data):
            # 発火記録: 無反応と故障を区別するため(CLAUDE.md §14 F2)。ledger が読む
            _record_firing("post_bash_guard", data)
            print(json.dumps({
                "decision": "block",
                "reason": (
                    "【自動リマインド】git push を検出。"
                    "最終回答に (1) 成果物3列表（成果物/説明/リンク） "
                    "(2) 各URLの存在確認（Contents API 200） "
                    "(3) ブランチが main のみであること を含めること。"
                    "既に対応済みならこのリマインドは無視してよい。"
                ),
            }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
