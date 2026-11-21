# -*- coding: utf-8 -*-
"""Stop hook: a check that stands in for the user's instructions must be attacked by Fable,
and a report that a check passed must say what the check does not look at.

WHY (2026-11-21, Soulful-Content)
---------------------------------
The user's 53 instructions (waves 1-3) were replaced by a gate script that counted a few words.
The gate passed all 70 priority articles, the agent marked them all 「○」 and reported them done.
An audit that read the articles against the 53 items found 0 of 70 articles without a miss
(median 18 missed items per article). Only 8 of 53 items were ones a word count can decide.
The user (2026-11-21):
  「検査の設計スキルが弱いのでは？漏れを発生され脆弱な検証方法をとり、問題がすべての記事に残っている
   というひどいありさま、かつ、それで「すべて合格した」と報告したということでは？」
  「この件に限らず、毎回、Claude Codeが、検証計画する仕様を改善するように、FABLEで批判的に再発防止をすべきでは？」
Defect turns: 2026-11-20T14:26 (04017a97) 「第2弾が ○ 34本→70本」 on the grounds 「第2弾の検査の FAIL が0」;
2026-11-17T04:36 / 07:26 (e1ef5f8d): phase2_gate.py written and used without anyone attacking it.

INVARIANTS (no proper nouns)
----------------------------
(A) design: a turn that creates or changes a CHECKER -- a script/rule file/judge prompt that returns
    pass/fail verdicts on deliverables, a plan section that sets the pass criteria, or a delegation
    that tells another agent to write one -- must dispatch Fable (Task/Agent, model fable), AFTER the
    last change of that checker, told to attack it, naming the review spec verification-plan-review.md
    and the checker; and the final answer must say what Fable found (「Fable の反証で N 点…」).
    Otherwise block once per checker per instruction.
    Escape: the final answer says plainly 「この検査は未反証です」 (and then (B) still applies).
(B) report: an answer whose text (or a ledger/report .md it writes) reports a check passed
    (「FAIL 0」「FAIL: 0」「70/70 PASS」「70本すべて合格」「○にしました」「検査は全部通過」…) must, in a
    sentence about the check, name what the check does not look at (with a count or a list), or say
    the instructions were not verified by it, or point to the item x check table that shows every
    item is covered. A negated disclosure (「見ていない項目はありません」) does not count.
    Otherwise block once per instruction.

Not covered (documented by the Fable attack 2026-11-21, attack.py in the scratchpad):
  - the quality of the attack (the spec lists what the attacker must try; the hook sees only that
    Fable was sent after the change and that the answer reports what it found);
  - a checker written by a script whose source is not in the command (python C:/tmp/patch.py,
    git apply of a patch file), by a background process, or in a temp folder outside any repo
    (a pass claimed from it is still (B));
  - unit tests (files with def test_/assert under tests/ or test_*.py) and hooks under .claude/hooks
    or templates/hooks (countermeasure_gate already requires an attack for hooks);
  - the second stop of the same instruction passes (block once, so a rewrite cannot loop).

stop_hook_active is NOT honoured: an answer rewritten after another hook's feedback is still checked
(CORRECTION_DIGEST_20261121 cause 1). Each block fires once per mark, so there is no loop.

CALIBRATED 2026-11-21: see tests/test_verification_design_guard.py (defect replays) and the numbers
in index/HOOK_MANIFEST.json.

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
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

NAME = "verification_design_guard"
SPEC = "verification-plan-review.md"
TAIL_BYTES = 8 * 1024 * 1024
STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "state", NAME)

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
AGENT_TOOLS = ("Task", "Agent")

SCRIPT_EXT = re.compile(r"\.(?:py|js|mjs|cjs|ts|ps1|sh|gs|ipynb)$", re.I)
RULE_EXT = re.compile(r"\.(?:json|ya?ml|toml)$", re.I)
TEMP_PATH = re.compile(r"/AppData/Local/Temp/|^/tmp/|/scratchpad/|^[A-Za-z]:/Windows/Temp/", re.I)
CHECKER_NAME = re.compile(r"gate|check|verif|validat|audit|lint|judge|(?:^|_)qa(?:_|\.|$)|accept|grader|scorer|criteria|rubric|判定|検査", re.I)
TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__)/|(?:^|/)test_[^/]*$|_test\.[a-z]+$|\.test\.[a-z]+$|(?:^|/)conftest\.py$", re.I)
UNIT_TEST_BODY = re.compile(r"\bdef test_|\bassert\b|unittest|pytest|\bdescribe\(|\bexpect\(")
HOOK_PATH = re.compile(r"/\.claude/hooks/|/templates/hooks/|^\.claude/hooks/|^templates/hooks/", re.I)
# a body that emits pass/fail verdicts makes a checker whatever the name
VERDICT_BODY = re.compile(r"\b(?:FAIL|PASS|MISS)\b|不合格|合格|[\"']\s*[○×✗✓]\s*[\"']|sys\.exit\(\s*1\s+if|exit\(\s*0\s+if|\b[Rr]eject(?:ed)?\b|\b[Vv]erdict\b")
JUDGE_MD = re.compile(r"判定役|判定(?:し|する|せよ|を返)|judge|grader|合格\s*/\s*不合格|PASS\s*/\s*FAIL|MISS", re.I)
PLAN_HEAD = re.compile(
    r"(?m)^#{1,6}\s*[^\n]*(?:検証|検査|受理|合格|判定|完了の?条件|受け入れ|検収|チェックリスト|QC|品質(?:確認|基準)"
    r"|acceptance|verification|definition of done)", re.I)
PLAN_LINE = re.compile(r"(?:なら|れば|で|を)\s*(?:受理|合格|完了|○)(?:する|とする|にする)|受理の(?:基準|条件)|合格の(?:基準|条件)")

# shell commands that write files; every script/rule path token in such a command is a candidate
SHELL_MUTATE = re.compile(
    r"(?<![<>&\d])>{1,2}(?!&)|\btee\b|\bcp\b|\bmv\b|\bsed\s+-i|\bperl\s+-[a-z]*i|Out-File|Set-Content|Add-Content|WriteAll(?:Text|Lines|Bytes)"
    r"|Copy-Item|Move-Item|\bgit\s+(?:apply|checkout\s+[^\n;|&]*--|restore\b(?!\s+--staged))|\bcurl\b[^\n;|&]*\s-o\b|write_text|write_bytes|\.write\("
    r"|\bsed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*i|shutil\.(?:copy|move)|json\.dump|writeFileSync|fs\.writeFile|(?:^|[;|&]\s*)sc\s", re.I | re.M)
PATH_TOKEN = re.compile(r"([\w./\\:~$-]*[\w-]+\.(?:py|js|mjs|cjs|ts|ps1|sh|gs|json|ya?ml|toml|md))(?![\w])")
VERDICT_FLAG = r"(?:[^;|&\n]*?)\s--(?:gate|check|verify|accept|audit|qa|lint|judge)\b"
# a delegation that tells another agent to write/change a checker
MAKE_VERB = re.compile(r"作って|作る|作成|書いて|書く|直して|直す|修正|変更|追加|実装|緩め|更新|write|create|implement|fix|modify|add", re.I)
CHECKER_WORD = re.compile(r"[\w-]*(?:gate|check|verif|validat|judge|audit)[\w-]*\.(?:py|js|ts|ps1|sh)|ゲート|検査(?:スクリプト|の(?:コード|規則|ルール))|判定役|受理の(?:基準|条件)|合格の(?:基準|条件)|\bgate\b|checker|validator|grader|rubric", re.I)

# the checker is the object of the verb: 「ゲートを作って」「phase2_gate.py を書いて」「write a checker」
_CK = r"(?:" + CHECKER_WORD.pattern + r"|検査|チェック)"
_CK2 = r"(?:" + _CK + r"|判定(?:スクリプト|ロジック|処理|の(?:コード|基準))|受理(?:スクリプト|処理)|合否(?:の基準|判定))"
AGENT_MAKE = re.compile(_CK2 + r"\s*(?:を|に|も|の(?:コード|規則|ルール|判定|条件|閾値|基準)を)[^。\n]{0,12}?(?:" + MAKE_VERB.pattern + r"|用意|準備|決めて|組んで|整備|仕上げ)(?!\s*(?:しないで|しない|せず|ない|禁止))"
                        r"|\b(?:write|create|implement|add|build|make|set up|prepare)\s+(?:\w+\s+){0,4}?(?:checker|validator|gate|grader|rubric|check(?:s| script)?|acceptance (?:test|criteria))\b", re.I)

ATTACK = re.compile(u"壊せ|壊して|攻撃|反証|突破|すり抜|穴を|抜け道|見逃し|批判的|break|attack|bypass|adversar|evade|red[- ]?team|falsif", re.I)
FAKE_ATTACK = re.compile(u"(?:反証|攻撃|批判)(?:は|を)?(?:不要|しない|しなくて|せず|いらない)|(?:要約|転記|まとめる)(?:する)?だけ|要約して(?!返)|summari[sz]e (?:it|the spec) only", re.I)
FABLE_RESULT = re.compile(r"(?:Fable|フェイブル)[^。\n]{0,80}(?:指摘|破れ|反証|見つけ|穴|抜け|漏れ|直し|直した|残っ)", re.I)

# (B) a report that a check passed
_N = r"(?<![\d.,])\d+\s*"
PASS = re.compile(
    r"(?:FAIL|NG|MISS|不合格|違反|エラー|漏れ|指摘|残り)\s*(?:は|が|の(?:数|件数)?は)?\s*(?:合計\s*)?[:=：]?\s*0\s*(?:件|本|個)?(?![\dxX.,])"
    r"|\|\s*(?:FAIL|NG|MISS|不合格)\s*\|\s*0\s*\|"
    r"|(?:FAIL|NG|MISS|不合格|違反)\s*(?:は|が)?\s*(?:ありません|なし|無し|ゼロ|ひとつもない|1つもない)"
    r"|(?:すべて|全て|全部|全件|全\s*\d+\s*(?:本|件|記事|ファイル|項目)|" + _N + r"(?:本|件|記事|ファイル|項目)(?:すべて|とも|全部|中\s*\d+\s*(?:本|件)))"
    r"[^。\n]{0,20}?(?:合格|PASS|通過|通りました|通った|通って|クリア|○|満たし)"
    r"|(\d+)\s*/\s*(\d+)\s*(?:PASS|passed|合格|通過)|\ball (?:checks|tests) passed\b|\b0 failed\b|exit code\s*0\b|合格率(?:は)?\s*100|✅"
    r"|(?:検査|ゲート|チェック|判定|監査|gate|check)[^。\n]{0,20}?(?:合格(?:です|でした|しました|した)|PASS|通過|通りました|通った|グリーン|\bOK\b|問題(?:は)?(?:ありません|なし|見つかりませんでした)|該当なし|基準を満たし)"
    r"|" + _N + r"本(?:が|は|とも)?[^。\n]{0,15}基準を満たし"
    r"|○\s*に\s*(?:しました|した|変え|更新)|○を付け|(?:が|を|は)\s*○\s*(?:に|と)?[^。\n]{0,10}?" + _N + r"本", re.I)
PASS_NOT = re.compile(
    r"ではなく|に(?:は)?なっていません|に(?:は)?なっていない|目指し|誤り|でしたが|と報告し|予定(?!どおり|通り)|なら|れば|たら|を条件|を受理の条件|まで(?:に|は)"
    r"|(?:不合格|FAIL|NG|MISS|違反)\s*(?:は|が)?\s*[1-9]|[1-9]\d*\s*(?:件|本)(?:が)?\s*(?:残|不合格|FAIL)|0x[0-9a-f]"
    r"|ビルド|単体テスト|pytest|unit test|テスト(?:は)?\s*\d+\s*(?:件|/)|試験\d*件|「[^」]*(?:合格|FAIL|○)[^」]*」", re.I)
CHECK_WORD = re.compile(r"検査|ゲート|チェック|テスト|判定|監査|gate|check|test|lint|audit", re.I)
_NEG = r"(?:な|ませ)"
_HIDE = (r"(?:見てい" + _NEG + r"|見ません|見ない|しか見|だけ(?:を)?見|対象外|範囲外|拾え" + _NEG + r"|拾わ" + _NEG + r"|捉え" + _NEG
         + r"|確かめてい" + _NEG + r"|確かめられてい" + _NEG + r"|確かめられ" + _NEG + r"|確認してい" + _NEG + r"|検証してい" + _NEG
         + r"|未確認|未検証|読んでい" + _NEG + r"|未読|含まれ" + _NEG + r"|含ま" + _NEG + r"|入ってい" + _NEG + r"|カバーしてい" + _NEG
         + r"|判定でき" + _NEG + r"|保証し" + _NEG + r"|意味し" + _NEG + r")")
DISC_COUNT = re.compile(_HIDE + r"[^。\n]{0,40}?\d+\s*(?:項目|個|件|点|本|指示)|\d+\s*(?:項目|個|件|点|指示)[^。\n]{0,30}?" + _HIDE)
DISC_LIST = re.compile(_HIDE + r"[^。\n:：]{0,15}[:：]\s*\S{2,}")
DISC_INSTR = re.compile(r"(?:指示|依頼|要件)(?:どおり|通り|の(?:通り|とおり)?)?[^。\n]{0,20}?(?:確かめてい(?:な|ませ)|確かめられてい(?:な|ませ)|確認してい(?:な|ませ)|未確認|未検証|分から(?:な|ず)|わから(?:な|ず)|判定でき(?:な|ませ))")
DISC_TABLE = re.compile(r"(?:全項目|すべての(?:指示|項目))[^。\n]{0,20}見て[^。\n]{0,40}(?:対応表|[\w./-]+\.(?:md|json|csv))")
DISC_NEG = re.compile(_HIDE + r"[^。\n]{0,20}?(?:はありません|は無い|はない|はなし|はゼロ|は0|\s*[:：]\s*(?:なし|無し|0\s*(?:件|項目)?|ありません|ゼロ))|(?:は|が)?(?:ありません|ない)。?$")
UNREVIEWED_DECL = re.compile(r"未反証(?:です|だ|のまま|で(?:す|、)|。|$)(?!の点)")
SENT = re.compile(r"[^。\n]+")


def _norm(p):
    return str(p or "").replace("\\", "/").strip("\"'")


def _in_repo(p):
    """A git work tree (worktrees of a repo often live in the temp folder), or a scripts/ folder."""
    d = os.path.dirname(p)
    for _ in range(10):
        if not d or os.path.exists(os.path.join(d, ".git")):
            return bool(d)
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return "/scripts/" in p        # the work tree may already be gone (calibration on old transcripts)


def _disk_body(p):
    for base in ("", os.environ.get("CLAUDE_PROJECT_DIR") or "", os.getcwd()):
        f = os.path.join(base, p) if base and not os.path.isabs(p) else p
        try:
            if os.path.isfile(f) and os.path.getsize(f) < 400000:
                with io.open(f, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        except Exception:
            continue
    return ""


def is_checker(p, body="", flagged=()):
    """Is the file at p a checker? body = the new text written by the call (may be partial)."""
    p = _norm(p)
    base = os.path.basename(p)
    if HOOK_PATH.search(p):
        return False
    if TEMP_PATH.search(p) and not _in_repo(p):
        return False
    disk = None
    if TEST_PATH.search(p):
        disk = _disk_body(p)
        if UNIT_TEST_BODY.search(body or "") or UNIT_TEST_BODY.search(disk):
            return False          # a unit test of code, not a check that stands in for instructions
    if SCRIPT_EXT.search(p):
        if CHECKER_NAME.search(base) or base.lower() in flagged:
            return True
        if VERDICT_BODY.search(body or ""):
            return True
        if disk is None:
            disk = _disk_body(p)
        hits = len(VERDICT_BODY.findall(disk))
        return hits >= 5 and hits * 2000 >= len(disk)   # verdicts dense in the file (a gate), not a tool that prints FAIL once in a while
    if RULE_EXT.search(p):
        return bool(CHECKER_NAME.search(base) or re.search(r"rule|banned|forbid|threshold|禁止", base, re.I))
    if p.lower().endswith(".md"):
        return bool(JUDGE_MD.search(body or "") and re.search(r"prompt|judge|判定|review|grader|rubric", p, re.I))
    return False


def _edit_body(inp):
    parts = []
    for k in ("content", "new_string", "new_source"):
        v = inp.get(k)
        if isinstance(v, str):
            parts.append(v)
    for e in inp.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            parts.append(e["new_string"])
    return "\n".join(parts)


_SCRIPT_WRITE = re.compile(r"\.write\(|write_text|write_bytes|open\([^)\n]*['\"][wa]b?\+?['\"]|WriteAll(?:Text|Lines|Bytes)|writeFileSync|fs\.writeFile|shutil\.(?:copy|move)|json\.dump", re.I)
_INLINE = re.compile(r"\b(?:python3?|py|node|perl|ruby)\b[^\n;|&]*?(?:\s-\s|\s-$|\s-c\s|\s-e\s|<<)", re.I | re.M)
_SEG = re.compile(r"\s*(?:;|&&|\|\||\||\n)\s*")


def _expand_vars(cmd):
    """Resolve S=/path ... $S/x.py so that a scratchpad path is seen as a scratchpad path."""
    env = {}
    for k, v in re.findall(r"(?:^|[\s;&])([A-Za-z_]\w*)=['\"]?([^\s;&'\"]+)", cmd):
        env[k] = v
    return re.sub(r"\$\{?([A-Za-z_]\w*)\}?", lambda m: env.get(m.group(1), m.group(0)), cmd)


def shell_write_targets(cmd):
    """Paths a shell command writes. A path that is only run (python scripts/gate.py) is not written."""
    cmd = _expand_vars(cmd or "")
    out = set()
    tok = r"['\"]?([\w./\:~$-]*[\w-]+\.[A-Za-z]{1,5})['\"]?"
    for m in re.finditer(r"(?<![<>&\d])>{1,2}(?!&)\s*" + tok, cmd):
        out.add(m.group(1))
    for m in re.finditer(r"\btee\b(?:\s+-a)?\s+" + tok, cmd):
        out.add(m.group(1))
    for m in re.finditer(r"(?:Out-File|Set-Content|Add-Content|Copy-Item|Move-Item)\b([^\n;|]*)", cmd, re.I):
        out.update(t.group(1) for t in PATH_TOKEN.finditer(m.group(1)))   # any parameter order
    for m in re.finditer(r"WriteAll(?:Text|Lines|Bytes)\s*\(\s*" + tok, cmd, re.I):
        out.add(m.group(1))
    for m in re.finditer(r"\bcurl\b[^\n;|&]*\s-o\s+" + tok, cmd):
        out.add(m.group(1))
    head = re.sub(r"(?ms)<<-?\s*['\"]?(\w+)['\"]?([^\n]*)\n.*?^\1\s*$", r"\2", cmd)
    for seg in _SEG.split(head):
        seg = seg.strip()
        if re.search(r"\b(?:sed\s+(?:-[A-Za-z]+\s+)*-[A-Za-z]*i|perl\s+-[a-z]*i|git\s+(?:apply|checkout|restore)\b)", seg):
            out.update(m.group(1) for m in PATH_TOKEN.finditer(seg))
        elif re.search(r"(?:^|\s)(?:cp|mv|Copy-Item|Move-Item|cpi|copy|move)\s", seg, re.I):
            words = seg.split()
            toks = [m.group(1) for m in PATH_TOKEN.finditer(seg)]
            last = words[-1].strip("'\"") if words else ""
            if toks and (last == toks[-1] or last.endswith(toks[-1])):
                out.add(toks[-1])
            elif toks and (last.endswith("/") or last.endswith("\\") or last in (".", "..") or "." not in os.path.basename(last)):
                out.add(last.rstrip("/\\") + "/" + os.path.basename(_norm(toks[0])))   # cp src/gate.py scripts/
    if _INLINE.search(cmd) and _SCRIPT_WRITE.search(cmd):
        for m in re.finditer(r"['\"]([^'\"\n]*?[\w-]+\.[A-Za-z]{1,5})['\"]", cmd):
            out.add(m.group(1))       # p='scripts/phase2_gate.py' in a heredoc that writes
        for m in re.finditer(r"\b(?:python3?|node)\s+-\s+" + tok, cmd):
            out.add(m.group(1))       # python - scripts/gate.py <<EOF (p = sys.argv[1])
    return out


def _run_as_checker(events):
    cmds = "\n".join(str((e[2] or {}).get("command") or "") for e in events if e[0] == "call" and e[1] in SHELL_TOOLS)
    return {m.group(1).lower() for m in re.finditer(r"([\w.-]+\.(?:py|js|ts|ps1|sh))" + VERDICT_FLAG, cmds)}


def checker_changes(events):
    """[(index, label)] of checker changes in the turn, in order."""
    flagged = _run_as_checker(events)
    out = []
    for k, e in enumerate(events):
        if e[0] != "call":
            continue
        name, inp = e[1], e[2] or {}
        if name in EDIT_TOOLS:
            p = _norm(inp.get("file_path") or inp.get("notebook_path"))
            body = _edit_body(inp)
            if is_checker(p, body, flagged):
                out.append((k, os.path.basename(p)))
            elif p.lower().endswith(".md") and (not TEMP_PATH.search(p) or _in_repo(p)) and (PLAN_HEAD.search(body) or PLAN_LINE.search(body)):
                out.append((k, os.path.basename(p) + "（検証の節）"))
        elif name in SHELL_TOOLS:
            cmd = str(inp.get("command") or "")
            if re.search(r"\bclaude\s+-p\b", cmd) and CHECKER_WORD.search(cmd) and MAKE_VERB.search(cmd):
                out.append((k, "claude -p に書かせた検査"))
            if not SHELL_MUTATE.search(cmd):
                continue
            for tok in sorted(shell_write_targets(cmd)):
                if tok.lower().endswith(".md") or not PATH_TOKEN.fullmatch(tok):
                    continue
                if is_checker(tok, "", flagged):
                    out.append((k, os.path.basename(_norm(tok))))
        elif name in AGENT_TOOLS:
            text = " ".join(v for kk in ("prompt", "description") for v in [inp.get(kk)] if isinstance(v, str))
            if AGENT_MAKE.search(text) and not (ATTACK.search(text) and _agent_model(inp).startswith(("fable", "claude-fable"))):
                out.append((k, "サブエージェントに書かせた検査"))
    return out


def _agent_model(inp):
    m = inp.get("model")
    if isinstance(m, str) and m.strip():
        return m.strip().lower()
    st = inp.get("subagent_type")
    if not isinstance(st, str) or not st:
        return ""
    name = st.split(":")[-1]
    for base in (os.path.expanduser("~"), os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()):
        f = os.path.join(base, ".claude", "agents", name + ".md")
        try:
            with io.open(f, encoding="utf-8", errors="replace") as fh:
                mm = re.search(r"(?m)^model:\s*['\"]?([\w.\-\[\]]+)", fh.read(2000))
            if mm:
                return mm.group(1).lower()
        except Exception:
            continue
    return ""


def attacks(events):
    """[(index, text)] of Fable calls told to attack with the spec named."""
    out = []
    for k, e in enumerate(events):
        if e[0] != "call" or e[1] not in AGENT_TOOLS:
            continue
        inp = e[2] or {}
        if "fable" not in _agent_model(inp):
            continue
        text = " ".join(v for kk in ("prompt", "description") for v in [inp.get(kk)] if isinstance(v, str))
        if SPEC in text and ATTACK.search(text) and not FAKE_ATTACK.search(text):
            out.append((k, text))
    return out


def unattacked(events):
    """Labels of checker changes with no Fable attack after them that names them."""
    atk = attacks(events)
    bad = []
    for k, label in checker_changes(events):
        stem = re.sub(r"（.*", "", label)
        generic = label.endswith("検査") and "（" not in label
        ok = any(ak > k and (generic or stem in at or os.path.splitext(stem)[0] in at) for ak, at in atk)
        if not ok and label not in bad:
            bad.append(label)
    return bad


def all_text(events):
    return "\n".join(e[1] for e in events if e[0] == "text")


def _md_bodies(events):
    out = []
    for e in events:
        if e[0] == "call" and e[1] in EDIT_TOOLS:
            p = _norm((e[2] or {}).get("file_path"))
            if p.lower().endswith(".md"):
                out.append(_edit_body(e[2] or {}))
    return "\n".join(out)


def pass_claim(text):
    for m in SENT.finditer(text or ""):
        s = m.group(0)
        if s.strip().startswith("|") and not re.search(r"\d", s):
            continue          # a bare table cell such as 「| 全件 | ○ |」
        if PASS.search(s) and not PASS_NOT.search(s):
            return s.strip()
    return ""


def ledger_claim(md):
    rows = re.findall(r"(?m)^\|[^\n]*\|\s*(?:○|✅|PASS|合格)\s*\|\s*$", md or "")
    if len(rows) >= 2:
        return "台帳に ○ を %d 行" % len(rows)
    return pass_claim(md)


def disclosed(text):
    for m in SENT.finditer(text or ""):
        s = m.group(0)
        if DISC_NEG.search(s):
            continue
        if DISC_TABLE.search(s):
            return True
        if not CHECK_WORD.search(s):
            continue          # the sentence must be about the check (「章に入っていない記事は…」 is not)
        if DISC_COUNT.search(s) or DISC_LIST.search(s) or (DISC_INSTR.search(s) and CHECK_WORD.search(s)):
            return True
    return False


def decide(events):
    """Returns a list of (kind, detail) problems, or []."""
    text = all_text(events)
    out = []
    bad = unattacked(events)
    if bad and not (UNREVIEWED_DECL.search(text) and not re.search(r"未反証の(?:点|項目)?(?:は)?(?:ありません|ない|なし)", text)):
        out.append(("design", bad))
    elif not bad and attacks(events) and checker_changes(events) and not FABLE_RESULT.search(text):
        out.append(("design_result", [lbl for _k, lbl in checker_changes(events)]))
    claim = pass_claim(text) or ledger_claim(_md_bodies(events))
    if claim and not disclosed(text):
        out.append(("report", claim))
    return out


# --- transcript reading (same turn split as batch_verify_guard) ---------------------------------
def _text(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_prompt(d):
    if d.get("type") != "user" or d.get("isSidechain") or not ("promptSource" in d or "permissionMode" in d):
        return False
    if d.get("promptSource") == "system":
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    t = _text(d.get("message")).strip()
    return bool(t) and not t.startswith(("<task-notification", "<local-command", "<command-name>", "Caveat:"))


def turns(lines, headless=False):
    """Yield (prompt, timestamp, events). headless=True starts a turn before the first prompt
    (a turn longer than the tail that was read)."""
    prompt, pts, events, seen = ("" if headless else None), "", [], set()
    for line in lines:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("isSidechain"):
            continue
        if _is_prompt(d):
            if prompt is not None:
                yield prompt, pts, events
            prompt, pts, events, seen = _text(d.get("message")).strip(), d.get("timestamp", ""), [], set()
        elif d.get("type") == "assistant" and prompt is not None:
            c = (d.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    bid = b.get("id") or ""
                    if bid and bid in seen:
                        continue
                    seen.add(bid)
                    events.append(("call", b.get("name", ""), b.get("input") or {}))
                elif b.get("type") == "text" and (b.get("text") or "").strip():
                    events.append(("text", b["text"].strip()))
    if prompt is not None:
        yield prompt, pts, events


def read_turn(tp):
    size = os.path.getsize(tp)
    with open(tp, "rb") as f:
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read().decode("utf-8", "replace").splitlines()
    last = None
    for t in turns(data):
        last = t
    if last is None and size > TAIL_BYTES:
        for t in turns(data[1:], headless=True):
            last = t
    return last


USER_WORDS = ("依頼者の指摘（2026-11-21）:「検査の設計スキルが弱いのでは？漏れを発生され脆弱な検証方法をとり、"
              "問題がすべての記事に残っている…それで「すべて合格した」と報告した」"
              "「毎回、Claude Codeが、検証計画する仕様を改善するように、FABLEで批判的に再発防止をすべきでは？」。")
REASON_DESIGN = ("【検査の設計を Fable が反証していない（1回のみ）】このターンは合否を出す検査を作った・変えた（%s）が、"
                 "その変更の後に Fable に壊させていない。" + USER_WORDS +
                 "報告の前に、~/.claude/" + SPEC + " の7観点（網羅・検査の種類・感度・特異度・すり抜け・前の指示・報告の層）で、"
                 "Agent(model=\"fable\") に反証させること。プロンプトに「" + SPEC + "」と検査のファイル名を書き、"
                 "依頼者の指示の逐語（全回の累積）と検査のコードを1つの資料ファイルにまとめ、最大12ターン・返信は日本語の要約2KB以内。"
                 "指摘を直してから、最終回答に Fable の指摘と直したことを書く。"
                 "今回反証できないなら、最終回答に「この検査は未反証です」と書き、その検査の合格を指示の達成として扱わない。")
REASON_RESULT = ("【Fable の反証の結果が回答に無い（1回のみ）】検査（%s）を Fable に反証させたが、最終回答に何が破れ、"
                 "何を直したかが書かれていない。" + USER_WORDS + "Fable の指摘の要点と、直したこと・直していないことを書くこと。")
REASON_REPORT = ("【検査の合格を報告しているのに、その検査が見ていないものが書かれていない（1回のみ）】「%s」は"
                 "検査に通ったことを伝えているが、その検査がどの指示・項目を見ていないかが無い。" + USER_WORDS +
                 "最終回答に次を書くこと。(1) 合格したのはどの層か（機械の検査／書き手と別のモデルが読んだ判定／依頼者が読んだ）。"
                 "(2) その検査が見ていない指示・項目を数か一覧で（例:「検査が見ていない項目: 53項目中45項目（読めば決まる項目）」）。"
                 "依頼の全項目を検査が見ているなら、対応表のファイルを示して「依頼の全項目を検査が見ている（対応表: パス）」と書く。"
                 "「見ていない項目はありません」のような否定だけの文は数えない。見ていない項目を「直った」「完了」「○」と言わない。")


def _mark(ev, key):
    sid = "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")
    return os.path.join(STATE_DIR, sid + "_" + hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:16])


def _first_time(ev, key):
    mark = _mark(ev, key)
    if os.path.exists(mark):
        return False
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(mark, "w").close()
    except Exception:
        pass
    return True


def main():
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
    tp = ev.get("transcript_path") or ""
    if not os.path.isfile(tp):
        return
    t = read_turn(tp)
    if not t:
        return
    prompt, pts, events = t
    turn_key = pts + (prompt or "")[:200]
    reasons = []
    for kind, detail in decide(events):
        if kind == "design":
            new = [c for c in detail if _first_time(ev, "design:" + turn_key + c)]
            if new:
                reasons.append(REASON_DESIGN % "・".join(new))
        elif kind == "design_result" and _first_time(ev, "result:" + turn_key):
            reasons.append(REASON_RESULT % "・".join(detail))
        elif kind == "report" and _first_time(ev, "report:" + turn_key):
            reasons.append(REASON_REPORT % detail[:60])
    if not reasons:
        return
    _record_firing(NAME, ev)
    sys.stdout.buffer.write(json.dumps({"decision": "block", "reason": "\n".join(reasons)}, ensure_ascii=True).encode("ascii"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
