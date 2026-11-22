# -*- coding: utf-8 -*-
"""push_link_report_guard -- Stop hook (2026-11-19).

INVARIANT (one sentence, no proper nouns):
  An answer that ends an instruction in which the assistant pushed to GitHub, or in which the
  user asked for a link, must carry a clickable Markdown link to the pushed file on GitHub
  (`[name](https://github.com/<owner>/<repo>/blob/<branch>/<path>)`) for every pushed repo, and a
  deliverables table must never point at a local path.

WHY (2026-11-18/19, one session, four complaints from the user):
  - 「リンクミスしてるぞ。ワンクリックで開くルール」 -- deliverables table listed local paths.
  - 「ローカルへの保存は一切NG ... なぜできていないのでしょうか？」 -- table cells said
    `C:\\Users\\...（ローカル）` and asked the user to run a command.
  - 「リンクは？ルール違反してるぞ」 -- after a fix was pushed the answer said the file "opens from
    the link in the previous answer" and carried no link at all.
  - 「レポートのリンクは？」「早く」 -- the user had to ask twice more.
  The only existing mechanism was post_bash_guard's PostToolUse reminder, which ends with
  「既に対応済みならこのリマインドは無視してよい」 -- the model judged "the previous answer had a
  table" as 対応済み and the reminder had no teeth. response_length_guard also tells the model not to
  repeat the previous answer's deliverables table, which reads as "omit links on a follow-up".
  This guard makes the rule a Stop-time block instead of a reminder.

CHECKS (on the LAST instruction only = rows after the last prompt the user typed):
  P1 PUSH_NO_LINK   a push went through in this instruction -- read from git's own "To <remote>" block
                    and its ref lines (so `if ($?) { git push }`, `bash -lc`, scripts, sub-agents count;
                    a rejected / deleted / up-to-date ref does not), from a `git push -q` command whose
                    result shows no failure, from a Contents API PUT, or from an MCP push tool -- and the
                    final answer has no clickable link `[name](https://github.com/<owner>/<repo>/blob/<branch>/<path>)`
                    (or /commit/) for that owner, repo and pushed branch. Links inside code, comments,
                    images, empty labels, placeholders (<branch>), /tree/, raw, repo tops do not count.
  P2 ASKED_NO_LINK  the user's own words ask for a link (「リンクは？」「URLを出して」「どこから開ける」,
                    or a bare 「早く」 after such a request) and the answer has no GitHub file link (any
                    non-local http link when the user asked about a paper / site / product).
  P3 DEFLECT        after a push or a request for the link, the answer sends the user to an earlier
                    answer (「リンクは前の回答のものから開けます」「先ほどの表のとおり」).
  P4 LOCAL_IN_TABLE a deliverables table / link column / 「リンク:」 line points at the local machine
                    (drive letter, /c/Users, /home, UNC, %USERPROFILE%, ~/, localhost, （ローカル）, 未push,
                    or a link whose target is not http(s)).
  The user saying 「リンクは要らない」 turns P1-P3 off (direct instruction outranks the rule).

CALIBRATION (measured 2026-11-19 on the newest 300 transcripts under ~/.claude/projects; headless
  `claude -p` worker sessions excluded because the hook skips them via CLAUDE_HEADLESS_JOB):
  v2: 268 interactive instructions -> 16 blocks (6.0%): PUSH_NO_LINK 14, LOCAL_IN_TABLE 2, DEFLECT 0.
  The first v2 draft hit DEFLECT twice on 「前の回答のとおり」-type sentences not about links; the object
  is now required to be the link or the table.
  v1 measured 6.4% but a different model's attack fixture (templates/hooks/tests/fixtures/push_link_report_attack_20261119.json,
  91 cases) showed v1 missed 55 of 64 evasions and wrongly blocked 19 of 27 benign cases; v2 passes all 91.
  Hand review of the 14 PUSH_NO_LINK hits: pushes whose final answer carries no /blob/ link for that
  repo (e.g. "Waiting on the quality check." after a push), i.e. the invariant, not noise.
  The session that motivated the guard: all 3 complained-about answers block, the 3 answers that fixed
  them pass (templates/hooks/tests/fixtures/push_link_report_session_20261119.json).

FAIL-OPEN: any exception -> exit 0. CLAUDE_HEADLESS_JOB=1 -> skip.
LOOP SAFETY: stop_hook_active -> return; one block per instruction.
Transcript reading is reused from external_state_claim_guard (read_turn), not copied.
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

NAME = "push_link_report_guard"
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME + "_seen")

SHELLS = ("Bash", "PowerShell")

# ---------------------------------------------------------------- push detection
# v2 (2026-11-19, after a different model's attack: 55 of 64 evasions passed v1). A push is read
# from what git printed, not from how the command was spelled -- `if ($?) { git push }`,
# `bash -lc "git push"`, `VAR=x git push`, scripts that push, sub-agents that push all print the
# same "To <remote>" block. Each block is judged on its own ref lines, so a later failure in the same
# command (a branch delete, a rejected first try, a second "Everything up-to-date") no longer cancels
# a push that went through.
TO_RE = re.compile(r"(?m)^(?:[^\n]{0,12}?:\s*)?\s*To\s+(\S+)\s*$")
REF_OK_RE = re.compile(r"^\s*(?:\+\s*)?(?:[0-9a-f]{4,}\.\.\.?[0-9a-f]{4,}|\*\s*\[new (?:branch|reference)\])"
                       r"\s+\S+\s+->\s+(\S+)")
GH_REMOTE_RE = re.compile(r"github\.com[:/]+([^/\s:]+)/([^/\s]+?)(?:\.git)?/?$")
# `git push -q` prints nothing on success (measured 2026-11-19: every push in the session that motivated
# this guard used -q), so a push command whose result shows no "To" line is read from the command.
GIT_PUSH_CMD = re.compile(r"(?<![\w./\\-])git(?:\.exe)?['\"]?(?:\s+(?:-[cC]\s+\S+|--?[\w-]+(?:=\S+)?))*"
                          r"\s+push(?![-.\w])(?P<rest>[^\n;&|)]*)")
DRY_RE = re.compile(r"--dry-run\b|(?<!\S)-n\b|--porcelain\b")
DELETE_ONLY_RE = re.compile(r"--delete\b|(?<!\S)-d\b|(?<!\S):\S+")
# The tool did not run, or git said it did not send anything.
NOT_RUN = ("hook error", "denied", "doesn't want to proceed", "was rejected", "timed out after",
           "interrupted", "everything up-to-date", "fatal:", "error: failed to push", "[rejected]",
           "could not read from remote", "authentication failed", "no such file or directory")
CD_RE = re.compile(r"(?:\bcd|\bSet-Location|\bpushd)\s+(?:-Path\s+)?[\"']?([^\"';&|\r\n]+?)[\"']?\s*(?:&&|;|\||\r?\n|$)")
GITC_RE = re.compile(r"\bgit\s+-C\s+[\"']?([^\"'\s;&|]+)")
ASSIGN_RE = re.compile(r"(?:^|[;&\n]|\s)(?:\$)?([A-Za-z_]\w*)\s*=\s*[\"']?([^\"';&|\s]+)")
# Contents API writes (CLAUDE.md §3 prefers Node.js + REST API over gh)
PUT_LINE_RE = re.compile(r"\bPUT\b[^\n]*?/repos/([^/\s]+)/([^/\s]+)/contents/[^\s?]+[^\n]*?\b20[01]\b")
HTML_URL_RE = re.compile(r"\"html_url\"\s*:\s*\"https://github\.com/([^/\"]+)/([^/\"]+)/blob/([^/\"]+)/")
MCP_PUSH_RE = re.compile(r"github.*(?:push_files|create_or_update_file)", re.I)


def _strip_shell_text(cmd):
    """Drop heredoc bodies, quoted strings and comments: text that is written or echoed, not run."""
    cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", "<<H", cmd or "", flags=re.S)
    cmd = re.sub(r"@'.*?'@|@\".*?\"@", "Q", cmd, flags=re.S)          # PowerShell here-strings
    cmd = re.sub(r"\"(?:\\.|[^\"\\])*\"|'[^'\n]*'", "Q", cmd)
    cmd = re.sub(r"(?m)(^|\s)#[^\n]*", r"\1", cmd)
    return cmd


def _repo_from_path(p):
    p = (p or "").strip().rstrip("/\\")
    if not p:
        return ""
    parts = re.split(r"[\\/]", p)
    for i, seg in enumerate(parts):
        if seg.lower() == "repos" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


_ORIGIN_CACHE = {}


def _origin(d):
    """(owner, repo) from `git -C d remote get-url origin`, or ('', '')."""
    if not d:
        return ("", "")
    d = re.sub(r"^/([a-zA-Z])/", lambda m: m.group(1) + ":/", d)   # Git Bash /c/... -> c:/...
    if d in _ORIGIN_CACHE:
        return _ORIGIN_CACHE[d]
    out = ("", "")
    try:
        if os.path.isdir(d):
            import subprocess
            r = subprocess.run(["git", "-C", d, "remote", "get-url", "origin"], capture_output=True,
                               text=True, timeout=3)
            m = GH_REMOTE_RE.search((r.stdout or "").strip())
            if m:
                out = (m.group(1), m.group(2))
    except Exception:
        pass
    _ORIGIN_CACHE[d] = out
    return out


def _blocks(res):
    """[(owner, repo, [ok dest branches])] for every "To <github remote>" block in a tool result."""
    out = []
    ms = list(TO_RE.finditer(res or ""))
    for i, m in enumerate(ms):
        g = GH_REMOTE_RE.search(m.group(1))
        if not g:
            continue
        body = res[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(res)]
        branches = []
        for ln in body.splitlines()[:60]:
            if "[new tag]" in ln:
                continue
            r = REF_OK_RE.match(ln)
            if r:
                branches.append(re.sub(r"^refs/heads/", "", r.group(1)))
        if branches:
            out.append((g.group(1), g.group(2), branches))
    return out


def _cmd_repo(cmd, m_start, cwd):
    """Repo for a push command whose output did not name it: git -C / cd / the row's cwd."""
    assigns = dict((k, v) for k, v in ASSIGN_RE.findall(cmd))
    seg = cmd[m_start:]
    g = GITC_RE.search(seg[:200])
    cds = CD_RE.findall(cmd[:m_start])
    d = g.group(1) if g else (cds[-1].strip() if cds else cwd)
    d = re.sub(r"\$\{?(\w+)\}?", lambda mm: assigns.get(mm.group(1), mm.group(0)), d or "")
    if d and cwd and not re.match(r"^(?:[A-Za-z]:|/|~|\$|%)", d):
        d = os.path.join(cwd, d)
    owner, repo = _origin(d)
    if not repo:
        repo = _repo_from_path(d)
    if repo.startswith(("$", "%", ".")) or repo.lower() in ("repos", "user"):
        repo = ""
    return owner, repo


def pushes(tools, with_index=False):
    """-> [{'owner','repo','branches'}] (empty strings / set = unknown) for pushes that went through.
    tools: (name, input, result[, cwd]). The harness strips a leading `cd <cwd> &&` from the recorded
    command (measured 2026-11-19), so the row's cwd is the fallback for the repo."""
    out = []
    for idx, t in enumerate(tools):
        name, inp, res = t[0], t[1] or {}, (t[2] if len(t) > 2 else "") or ""
        cwd = (t[3] if len(t) > 3 else "") or ""
        found = []
        cmd = (inp.get("command") or "") if isinstance(inp, dict) else ""
        run = _strip_shell_text(cmd)
        invs = list(GIT_PUSH_CMD.finditer(run))
        dry = bool(invs) and all(DRY_RE.search(m.group("rest")) for m in invs)
        if not dry:
            for owner, repo, br in _blocks(res):
                found.append({"owner": owner, "repo": repo, "branches": set(br)})
        if not found and name in SHELLS and not TO_RE.search(res) \
                and not any(k in res.lower() for k in NOT_RUN):
            for m in invs:
                rest = m.group("rest")
                if DRY_RE.search(rest) or DELETE_ONLY_RE.search(rest) and not re.search(r"\s\S+:\S+", rest):
                    continue
                if "--tags" in rest and not re.search(r"\S+\s+\S", rest.replace("--tags", "")):
                    continue
                mo = GIT_PUSH_CMD.search(cmd)          # cd "$REPO" survives only in the raw command
                owner, repo = _cmd_repo(cmd, mo.start() if mo else len(cmd), cwd)
                found.append({"owner": owner, "repo": repo, "branches": set()})
                break
        for m in PUT_LINE_RE.finditer(res):
            found.append({"owner": m.group(1), "repo": m.group(2), "branches": set()})
        if re.search(r"\bPUT\b", json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else ""):
            for m in HTML_URL_RE.finditer(res):
                found.append({"owner": m.group(1), "repo": m.group(2), "branches": {m.group(3)}})
        if MCP_PUSH_RE.search(name) and isinstance(inp, dict) and not re.search(r"(?i)\berror\b", res[:300]):
            found.append({"owner": inp.get("owner") or "", "repo": inp.get("repo") or "",
                          "branches": {inp["branch"]} if inp.get("branch") else set()})
        for f in found:
            out.append((idx, f) if with_index else f)
    return out


# ---------------------------------------------------------------- links the user can click
def _visible(text):
    """Text as rendered: no fenced code, no inline code, no HTML comments."""
    t = re.sub(r"(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*$", " ", text or "")
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(`+)(?!`).+?(?<!`)\1", " ", t)
    return t


MDLINK_RE = re.compile(r"(?<!!)\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\s*\)")
FILE_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/(blob|commit)/(\S+)$")


def clickable(text):
    """[(label, url)] Markdown links a reader can click (not images, not empty, not in code)."""
    out = []
    for lab, url in MDLINK_RE.findall(_visible(text)):
        if not lab.strip():
            continue
        out.append((lab, url.strip("<>").strip()))
    return out


def file_links(text):
    """[(owner, repo, kind, rest)] clickable links to a file or commit on GitHub, with no placeholder."""
    out = []
    for _lab, url in clickable(text):
        m = FILE_URL_RE.match(url.replace(" ", "%20"))
        if not m or re.search(r"[<>{}]|\.\.\.|%3C|%3E", url):
            continue
        owner, repo, kind, rest = m.groups()
        if kind == "blob" and not re.match(r"[^/]+/.+[^/]$", rest):
            continue
        out.append((owner, repo, kind, rest))
    return out


def _satisfied(p, links):
    for owner, repo, kind, rest in links:
        if p["owner"] and owner.lower() != p["owner"].lower():
            continue
        if p["repo"] and repo.lower() != p["repo"].lower():
            continue
        if kind == "blob" and p["branches"] and not re.match(r"[0-9a-f]{7,40}/", rest) \
                and not any(rest.startswith(b + "/") for b in p["branches"]):
            continue
        return True
    return False


# ---------------------------------------------------------------- local paths shown as deliverables
LOCAL_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-zＡ-Ｚａ-ｚ][:：][\\/¥＼]"
    r"|(?i:/[a-z]/users/)|/mnt/[a-z]/|/home/[^/\s|]+/|(?<![\w.])/Users/[^/\s|]+/"
    r"|\\\\wsl[$.]|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_$.-]+\\"
    r"|%USERPROFILE%|%HOMEPATH%|\$env:\w+|\$HOME\b|(?<![\w/])~[\\/]"
    r"|file:/|localhost|127\.0\.0\.1"
    r"|[（(【\[]\s*(?:ローカル|local)\s*[）)】\]]|ローカル(?:保存|のみ|パス|リンク|ファイル|に)|(?i:\blocal only\b)|未\s*push")
PATHISH_RE = re.compile(r"(?:^|[\s`(（:：])(?:\.{1,2}[\\/])?[\w.-]+(?:[\\/][\w. -]+)+\.\w{1,6}\b")
LINK_HEAD_RE = re.compile(r"(?i)(?:リンク|links?|urls?|ＵＲＬ|保存先|置き場|所在|場所|パス|path|開く)\s*$")
DELIV_HEAD_RE = re.compile(r"(?i)成果物|ファイル|\bfiles?\b|deliverable")
LABEL_LINE_RE = re.compile(r"(?im)^\s*(?:>\s*)*(?:[-*+]|\d+[.)])?\s*\**\s*(?:リンク|links?|urls?|ＵＲＬ|保存先|置き場|所在|場所|パス|path)\s*\**\s*[:：]\s*(.+)$")
REFDEF_RE = re.compile(r"(?m)^\s{0,3}\[([^\]]+)\]:\s*<?(\S+?)>?\s*$")
HREF_RE = re.compile(r"(?i)<a\s[^>]*href\s*=\s*[\"']?([^\"'\s>]+)")


def _targets(cell, refs):
    t = [u for _l, u in clickable(cell)]
    t += [refs.get(r.lower(), "") for r in re.findall(r"\]\[([^\]]+)\]", cell)]
    t += HREF_RE.findall(cell)
    return [x for x in t if x]


def _is_local_target(u):
    if re.match(r"(?i)https?://", u):
        return bool(re.match(r"(?i)https?://(?:localhost|127\.|0\.0\.0\.0|\[::1\])", u))
    return not re.match(r"(?i)#|mailto:|tel:", u)


def _http_ok(cell, refs):
    return any(re.match(r"(?i)https?://", u) and not _is_local_target(u) for u in _targets(cell, refs))


def _check_cell(cell, refs, link_col):
    """True when a cell shown as where a deliverable lives points at the local machine."""
    if any(_is_local_target(u) for u in _targets(cell, refs)):
        return True
    if _http_ok(cell, refs):
        return False
    if LOCAL_RE.search(cell):
        return True
    return link_col and bool(PATHISH_RE.search(cell))


def _split_row(ln):
    ln = re.sub(r"^\s*(?:>\s*)+", "", ln).strip()
    ln = re.sub(r"`[^`]*`", lambda m: m.group(0).replace("|", "\x00"), ln)
    if ln.startswith("|"):
        ln = ln[1:]
    if ln.endswith("|") and not ln.endswith("\\|"):
        ln = ln[:-1]
    return [c.replace("\x00", "|").strip() for c in re.split(r"(?<!\\)\|", ln)]


SEP_RE = re.compile(r"^\s*(?:>\s*)*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$|^\s*(?:>\s*)*\|\s*:?-+:?\s*\|\s*$")


def _tables(text):
    """[(header cells, [row cells])] for GFM tables (leading pipe optional, inside quotes too) and HTML."""
    lines = (text or "").splitlines()
    out, i = [], 0
    while i < len(lines) - 1:
        if "|" in lines[i] and SEP_RE.match(lines[i + 1]):
            head = _split_row(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_split_row(lines[j]))
                j += 1
            out.append((head, rows))
            i = j
            continue
        i += 1
    for tb in re.findall(r"(?is)<table.*?</table>", text or ""):
        trs = [re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", tr) for tr in re.findall(r"(?is)<tr.*?</tr>", tb)]
        if trs:
            out.append((trs[0], trs[1:]))
    return out


def local_rows(answer):
    text = _visible(answer or "")
    refs = dict((k.lower(), v) for k, v in REFDEF_RE.findall(text))
    bad = []
    for head, rows in _tables(text):
        hs = [re.sub(r"[*_`]", "", h).strip() for h in head]
        link_cols = [k for k, h in enumerate(hs) if LINK_HEAD_RE.search(h)]
        deliv = any(DELIV_HEAD_RE.search(h) for h in hs) or bool(link_cols)
        if not deliv:
            continue
        for r in rows:
            row = " | ".join(r)
            if any(k < len(r) and _check_cell(r[k], refs, True) for k in link_cols):
                bad.append(row)
            elif any(DELIV_HEAD_RE.search(h) for h in hs) and not _http_ok(row, refs) \
                    and (LOCAL_RE.search(row) or any(_is_local_target(u) for u in _targets(row, refs))):
                bad.append(row)
    for m in LABEL_LINE_RE.finditer(text):
        if _check_cell(m.group(1), refs, True):
            bad.append(m.group(0).strip())
    return bad


# ---------------------------------------------------------------- the user asking for a link
LINK_WORD = r"(?:(?<![ァ-ヴー])リンク|ＵＲＬ|(?<![A-Za-z])(?:[Uu][Rr][Ll]s?|[Ll]inks?|[Hh]yperlinks?)(?![A-Za-z]))"
ASK_RES = [
    re.compile(LINK_WORD + r"\s*(?:は|って)?\s*[？?]"),
    re.compile(LINK_WORD + r"\s*(?:は|が|も)?\s*(?:どこ|まだ|無|な[いしく]|出て|切れ|ミス|違反|おかし|開けな|間違|貼られ|付いて)"),
    re.compile(LINK_WORD + r"\s*(?:を|も)?\s*(?:出|貼|示|教|くれ|くだ|下さ|ちょうだい|載|付け|添|提示|送|共有|張|頂|いただ|欲|ほし)"),
    re.compile(r"(?i)\b(?:where|what|send|give|share|post|show|provide|need|missing|no)\b[^.?!\n]{0,40}"
               r"\b(?:urls?|links?|hyperlinks?)\b"),
    re.compile(r"(?:どこ|どれ)\s*(?:から|で)\s*(?:開|見)|ワンクリックで開"),
]
NOLINK_RE = re.compile(LINK_WORD + r"\s*(?:は|も)?\s*(?:要らない|いらない|不要|なしで|無しで|なくていい|無くていい)"
                       r"|(?i:\bno links?\b|\bwithout (?:a )?links?\b)")
NONREPO_RE = re.compile(r"(?i)論文|文献|出典|サイト|ページ|ニュース|動画|YouTube|公式|商品|Amazon|楽天|購入|店|予約|申込|記事|"
                        r"\bpaper\b|\bsite\b|\barticle\b|\bvideo\b|\bproduct\b")
REPO_RE = re.compile(r"(?i)レポート|ファイル|成果物|資料|原稿|報告書|リポ|push|github|\.md\b|\.py\b")
# Pointing the user at an earlier answer instead of giving the link (2026-11-19: 「リンクは前の回答の
# ものから開けます」 after a push, then 「先ほどの表のとおりです」-type answers).
# The object must be the link or the table: 「前の回答のとおり」「前の回答の Next Action に書いた」 are not
# about links (measured 2026-11-19: both DEFLECT hits of the first draft on 267 real instructions).
DEFLECT_RE = re.compile(r"(?:前の|前回の|先ほどの|さっきの|上の|上記の|以前の|既出の|直前の)\s*(?:(?:回答|返信|メッセージ)\s*の\s*)?(?:表|一覧|リンク|URL)"
                        r"[^。\n]{0,20}?(?:のとおり|の通り|から開|から見|に(?:書|記|載|あ)|を(?:参照|ご覧|見て))"
                        r"|(?:リンク|URL)\s*は\s*(?:上|前|先ほど)")
QUOTED_RE = re.compile(u"「[^」\\n]*」|『[^』\\n]*』")
SHORT_FOLLOWUP_RE = re.compile(r"^\s*(?:早く|はやく|はよ|まだ[？?]?|で[？?]|それで[？?]|急いで|至急|おい|[？?]+)\s*[!！。]*\s*$")


def own_words(prompt):
    """Only the user's own words: slash-command arguments kept, injected blocks dropped
    (<browser_instruction>, <pasted_content ...>, <system-reminder> mention links without asking --
    measured 2026-11-19: 4 of 5 P2 hits)."""
    p = re.sub(r"(?s)<command-args>(.*?)</command-args>", r" \1 ", prompt or "")
    return re.sub(r"(?s)<([A-Za-z_][\w-]*)[^>]*>.*?</\1>", " ", p)


def asks_link(text):
    return any(r.search(text or "") for r in ASK_RES)


def decide(prompt, answer, tools, after_push=None, all_text=None, prev_prompt=None):
    """-> None, or (code, detail).
    answer: the final answer (text after the last tool call).
    after_push: all assistant text written after the last successful push. A link shown in a message
    after the push but before a later tool call counts: the user saw it.
    all_text: every assistant message of the instruction (a local-path table shown mid-instruction
    was still shown to the user -- measured 2026-11-19 on the session that motivated this guard).
    prev_prompt: the instruction before this one (a bare 「早く」 continues a request for the link)."""
    answer = answer or ""
    if not answer.strip():
        return None          # interrupted / no answer: nothing was shown to check
    bad = local_rows(all_text if all_text else answer)
    if bad:
        return ("LOCAL_IN_TABLE", bad[0][:160])
    own = own_words(prompt)
    if NOLINK_RE.search(own):
        return None          # the user's direct instruction outranks the rule
    seen = answer if not after_push else (after_push + "\n" + answer)
    links = file_links(seen)
    pushed = pushes(tools or [])
    if pushed:
        missing = [p for p in pushed if not _satisfied(p, links)]
        if missing:
            names = sorted(set((p["repo"] or "(repo unknown)") +
                               ("@" + "/".join(sorted(p["branches"])) if p["branches"] else "") for p in missing))
            return ("PUSH_NO_LINK", ", ".join(names))
    asked = asks_link(own) or (bool(SHORT_FOLLOWUP_RE.match(own)) and asks_link(own_words(prev_prompt)))
    # quoted text (「前の回答のリンクから開けます」と書いていた) is an apology, not a deflection
    deflect = DEFLECT_RE.search(QUOTED_RE.sub(" ", _visible(answer)))
    if deflect and (pushed or asked or not links):
        return ("DEFLECT", deflect.group(0)[:80])
    if asked:
        ok = bool(links)
        if not ok and NONREPO_RE.search(own) and not REPO_RE.search(own):
            ok = any(re.match(r"(?i)https?://", u) and not _is_local_target(u) for _l, u in clickable(seen))
        if not ok:
            return ("ASKED_NO_LINK", (own or "").strip()[:80])
    return None


# --- transcript: reuse external_state_claim_guard's Turn / is_prompt; add cwd and text positions ---
try:
    import external_state_claim_guard as _E
except Exception:
    _E = None

if _E is not None:
    class LinkTurn(_E.Turn):
        def __init__(self, d, ordinal):
            _E.Turn.__init__(self, d, ordinal)
            self.texts = []          # (number of tool calls seen so far, text)

        def add(self, d):
            n0 = len(self.tools)
            _E.Turn.add(self, d)
            if d.get("type") != "assistant":
                return
            cwd = d.get("cwd") or ""
            for t in self.tools[n0:]:
                if len(t) == 3:
                    t.append(cwd)
            c = (d.get("message") or {}).get("content")
            if isinstance(c, str) and c.strip():
                self.texts.append((len(self.tools), c))
            for b in c if isinstance(c, list) else []:
                if isinstance(b, dict) and b.get("type") == "text" and (b.get("text") or "").strip():
                    self.texts.append((len(self.tools), b.get("text")))

        def after_push(self):
            idx = [i for i, _r in pushes(self.tool_list(), with_index=True)]
            if not idx:
                return ""
            last = max(idx)
            return "\n".join(t for n, t in self.texts if n > last)

        def all_text(self):
            return "\n".join(t for _n, t in self.texts)


def iter_link_turns(rows):
    """Same instruction boundaries as external_state_claim_guard.iter_turns, with LinkTurn."""
    strict = any(isinstance(d, dict) and ("promptSource" in d or "permissionMode" in d) for d in rows)
    cur, n = None, 0
    for d in rows:
        if not isinstance(d, dict) or d.get("isSidechain"):
            continue
        if _E.is_prompt(d, strict):
            if cur is not None:
                yield cur
            n += 1
            cur = LinkTurn(d, n)
        elif cur is not None:
            cur.add(d)
    if cur is not None:
        yield cur


def read_turn(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - 4 * 1024 * 1024))
        data = f.read().decode("utf-8", "replace").splitlines()
    rows = []
    for line in data:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    prev, last = None, None
    for t in iter_link_turns(rows):
        prev, last = last, t
    if last is not None:
        last.prev_prompt = prev.prompt if prev is not None else ""
    return last


REASON = {
    "PUSH_NO_LINK": (
        u"【push 後のリンク欠落（1回のみ）】このターンで GitHub に push した（リポ: {d}）のに、最終回答に"
        u"そのリポの `[ファイル名](https://github.com/<owner>/<repo>/blob/<branch>/<path>)` 形式のリンクが無い。"
        u"「前の回答のリンクから開けます」「リンクは上にあります」は不可（2026-11-19「リンクは？ルール違反してるぞ」）。"
        u"push したファイルを `git ls-tree origin/<branch> -- <path>` か Contents API 200 で確かめ、"
        u"成果物/説明/リンク の3列表で今回 push した全ファイルを書いて回答し直せ。"
        u"前の回答と同じ行でも、今回 push したファイルは再掲してよい（response_length_guard の再掲禁止より優先）。"),
    "ASKED_NO_LINK": (
        u"【リンクを求められたのにリンクが無い（1回のみ）】ユーザーがリンクを求めている（「{d}」）が、"
        u"最終回答にクリックできる Markdown リンク `[名前](https://...)` が1つも無い。"
        u"実在を確かめた GitHub の /blob/ リンクを、回答の先頭に書いて回答し直せ。"),
    "DEFLECT": (
        u"【リンクを前の回答に回した（1回のみ）】最終回答が「{d}」と、リンクを前の回答・上の表に回している。"
        u"ユーザーは今の回答だけを見て開く（2026-11-19「リンクは？ルール違反してるぞ」「レポートのリンクは？」「早く」）。"
        u"対象ファイルの GitHub の /blob/ リンクを実在確認（`git ls-tree origin/<branch> -- <path>`）してから、"
        u"成果物/説明/リンク の3列表でこの回答に書き直せ（再掲は response_length_guard の再掲禁止より優先）。"),
    "LOCAL_IN_TABLE": (
        u"【成果物表にローカルパス（1回のみ）】成果物表の行がローカルのパスを指している（「{d}」）。"
        u"ローカル保存・ローカルリンクの提示は一切不可（2026-11-18「ローカルへの保存は一切NG」）。"
        u"push を止めている原因を自分で直して push し、GitHub の /blob/ リンクに置き換えて回答し直せ。"
        u"push がどうしても不可能なら、試したコマンドとエラー文を1行で書き、表にはパスを書かない。"),
}


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
    if _E is None:
        sys.stderr.write("[push_link_report_guard] external_state_claim_guard.py not found next to this hook; "
                         "transcript is NOT being read." + chr(10))
        return
    tp = _E._codex_transcript(ev.get("transcript_path") or "")
    if not tp or not os.path.isfile(tp):
        return
    turn = read_turn(tp)
    if turn is None:
        return
    hit = decide(turn.prompt, turn.answer, turn.tool_list(), turn.after_push(), turn.all_text(),
                 getattr(turn, "prev_prompt", ""))
    if not hit:
        return
    code, detail = hit
    ident = turn.uid or turn.ts or ("#%d" % turn.ordinal)
    key = hashlib.sha1((ident + "|" + turn.prompt + "|" + code).encode("utf-8", "replace")).hexdigest()[:16]
    sid = "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")
    mark = os.path.join(STATE_DIR, sid + "_" + key)
    if os.path.exists(mark):
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    _record_firing(NAME, ev)
    reason = REASON[code].format(d=detail)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:  # one block per hook per human instruction (stop_once.py, 2026-11-22)
        import stop_once
        stop_once.install("push_link_report_guard")
    except Exception:
        pass
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
