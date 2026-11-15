# -*- coding: utf-8 -*-
"""Stop hook: stop a final answer whose Japanese the user has called 「意味不明」「変」.

WHY (2026-11-13, user)
----------------------
「変な日本語おおくてこまってる」「実例、他セッションの会話履歴に多数あるはず」.
All 6,085 session transcripts (2026-06-16 .. 11-13) were searched: 117 user
messages carried 意味不明／分かりにくい／日本語が変 …; read one by one, 42 were
complaints about Claude's own Japanese (30 quote the bad sentence verbatim).
Classes, by count: A 省略しすぎた名詞句 13, B 裸のパラメータ・内部記号 9,
D 専門語の和語化（造語） 8, E 語の結びつき 7, G 不要な留保 6, H 長すぎる文 6,
F 論理の破綻 5, I/J/L 各4, C 英語のまま 3, K 両義 3, M 記法 2.
Examples (verbatim): 「コンテナの窓に合言葉を入れてほしい。」「くじで分けた29研究」
「T=22.5（発動線, 2,250万円）」「効果がないならやっても損はない」「stop hook, never assert it」.

Defect class (no proper nouns): 最終回答の日本語が、読み手が本文だけでは意味を
復元できない形（造語・裸の記号・英語の地の文・係り受けの崩れ・論理の破綻）になる.

The existing hooks never look at this: jargon_glossary_guard checks identifier
SHAPES in .md reports only; plain_language_guard only compares a re-wording with
its source when the user asked for one; response_length_guard counts length.

WHAT IT CHECKS (final answer text after the turn's last tool call; code blocks,
inline code, URLs and link targets removed first)
  W  wording dictionary (ja_wording_dict.json): phrasings the user has flagged.
  P  bare parameter: `name=number` written in prose (not in backticks).
  X  English prose: 3+ English words in a row containing a function word
     (「stop hook, never assert it」), outside quotes and code.
  T  textlint (no-doubled-joshi, ja-no-redundant-expression, sentence-length …)
     through a resident server (ja_textlint_server.js); a cold textlint run takes
     20-40 s here, a warm request about 2 s.
  J  LLM judge: a light model (claude -p --model haiku, user hooks not loaded)
     reads the answer for classes A/D/E/F/J/K/L and must quote the sentence
     verbatim; a quote not found in the answer is dropped.
Which checks block and which only report is set by CALIBRATION below.

CALIBRATION (実測 2026-11-15, tests/calibrate_ja_quality_guard.py imports analyze()):
corpus = 2,157 final answers (60 days, ~/.claude/projects); 283 ordinary Japanese
answers (random 300, seed 7) and 47 answers the user then complained about.
  W  2.5% of ordinary answers. All 7 hits read by hand were the flagged coinage
     itself (道具 x5, 合言葉, くじで分けた, 割り引きの規則) -> blocks.
  P  9.2%. Hits: L=7.41, h=0.05, ec_mean=232.05, CVaR95=2492, T=21.25, n=1,553 ...
     -- bare notation CLAUDE.md 11.1 already forbids -> blocks.
  X  1.4% after requiring a function word + 2 lowercase content words (was 2.5%:
     「Four Forces of Progress」「Claude Code for VS Code」 now pass). Hits were
     answers written in English -> blocks.
  T  sentence-length(100) 32.9% / complaint answers 46.8%; no-doubled-joshi 38.2% /
     38.3% (no separation) -> doubled-joshi off, sentence-length 120, all textlint
     report-only. Cold run 20-40 s, resident server ~2 s per answer.
  J  past defect sentences (11, verbatim: 月80万円の不能証明…, 窓に合言葉, 効果がない
     ならやっても損はない, バックアップ2ファイルを貼り戻して…): severity 3 on 11, 10, 10
     of 11 in three runs (the miss, 「エージェント型の道具」, is also a W entry).
     Ordinary answers: severity>=3 on 25/39 (64.1%); 30 hits read by hand, about 22
     were what the user complains about (unlabelled numbers 「262枚／9,128,824円」,
     「日本24.8%・米国66.8%」), about 8 were context the reader already had
     (「Ctrl+O」, the user's own terms 「廃盤印」「有料部分」). Too frequent for the
     real Stop, so J runs ONLY at the draft stage (answer_precheck, see _judge_here).
  All mechanical checks together block 13.1% of ordinary answers.

REVISION after the adversarial review (Fable 2026-11-15: 18 of 18 legitimate
phrasings blocked, 20 of 20 variants of the defects passed, a mark that never
survived answer_precheck's isolated HOME, J blocking at the real Stop):
  NFKC first (Ｔ＝２２．５, １日); ASCII-only path / tag stripping (「手段/道具/方法」
  and 「<合言葉>」 vanished); dictionary entries take a `near` context (「スタートの
  合図」「合言葉は安全第一」 pass) and spelling variants (合い言葉, 割引の規則, 設計で減り);
  P covers tables, > lines, 「」, n=29件, α, 1e-4, **T**, and skips pH/BMI/n/x, env
  names (ANSWER_PRECHECK=1), --opt=, ?q=, ranges (Q1=1〜3月); X skips (…) and idioms,
  and a capitalised run of <=6 words (a title, label or error text) only reports;
  text in 「」 is exempt only when the user's prompt contains it; W/P run on short
  answers too. Re-measured on the same 283 / 47 answers (seed 7, mechanical only):
  BLOCK 12.7% / 8.5% (P 9.5%, W 2.1%, X 1.4%); every W hit read was the coinage
  (道具 as 「ツール」 x5, 合言葉 for a password, 割り引きの規則).

Once per issue (check + matched phrase) per session, stored under LOCALAPPDATA
(answer_precheck isolates HOME/TEMP but not LOCALAPPDATA): a draft that blocked
passes when sent again unchanged, and the real Stop does not raise again what the
precheck raised, so a false hit costs one rewrite and never a second answer on
screen. At most MAX_BLOCKS_PER_TURN blocks per human turn. The J result is cached
by prompt version + text hash (pruned after 30 days); J unavailable (no claude,
auth error, timeout) is logged as ja_quality_guard_judge_unavailable.
Headless runs (entrypoint sdk-cli: claude -p workers) skip J.
CLI: python ja_quality_guard.py --answer FILE [--no-llm]  -> JSON, exit 1 if blocking.
fail-open: any exception -> exit 0. stop_hook_active -> mechanical checks only (no J).
Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:
    def _record_firing(*_a, **_k):
        return False
try:
    from codex_transcript import resolve as _codex_transcript
except Exception:
    def _codex_transcript(p, *_a, **_k):
        return p
try:
    import plain_language_guard as _plg
except Exception:
    _plg = None

NAME = "ja_quality_guard"
HERE = os.path.dirname(os.path.abspath(__file__))
_LAD = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
CACHE_DIR = os.path.join(_LAD, "claude_ja_quality_guard")
# Under LOCALAPPDATA, not ~/.claude/state: answer_precheck runs hooks with an isolated
# HOME whose state is thrown away, so a mark written there never reached the next
# precheck or the real Stop and the same draft blocked every time (Fable 2026-11-15).
STATE_DIR = os.path.join(CACHE_DIR, "seen")
MAX_BLOCKS_PER_TURN = 2
TOOLS_DIR = os.environ.get("JA_TEXTLINT_DIR") or os.path.join(_LAD, "claude_ja_textlint")
PORT = 47613
DICT_PATH = os.path.join(HERE, "ja_wording_dict.json")
SERVER_JS = os.path.join(HERE, "ja_textlint_server.js")

# Set from calibration (see module docstring). Checks not listed only report.
BLOCK_CHECKS = {"W", "P", "X", "J"}
JUDGE_MIN_CHARS = 80         # prose shorter than this is not sent to the model
JUDGE_TIMEOUT_S = 45         # + textlint 8 s + mechanical < answer_precheck's 90 s
CACHE_MAX_AGE_S = 30 * 86400
TEXTLINT_RULES_BLOCK = set()  # textlint rules that block (calibrated); others report

TEXTLINT_PKGS = ["textlint@14", "textlint-rule-preset-ja-technical-writing"]
# Calibrated 2026-11-15 on 283 ordinary answers / 47 answers the user then complained
# about: no-doubled-joshi fired on 38.2% / 38.3% and sentence-length(100) on 32.9% /
# 46.8% -- no separation and far too frequent, so doubled-joshi is off and
# sentence-length is relaxed to 120 and report-only. The remaining rules fire on
# 0.4-3.9% and their hits were mild style points (「〜を行う」), so all of textlint
# reports and never blocks (TEXTLINT_RULES_BLOCK stays empty).
TEXTLINTRC = {"rules": {"preset-ja-technical-writing": {
    "sentence-length": {"max": 120}, "max-comma": False, "max-ten": False,
    "max-kanji-continuous-len": False, "no-mix-dearu-desumasu": False,
    "ja-no-mixed-period": False, "no-exclamation-question-mark": False,
    "ja-no-weak-phrase": False, "no-unmatched-pair": False, "arabic-kanji-numbers": False,
    "no-invalid-control-character": False, "no-zero-width-spaces": False,
    "ja-no-space-between-full-width": False, "no-mixed-zenkaku-and-hankaku-alphabet": False,
    "ja-unnatural-alphabet": False, "no-hankaku-kana": False, "no-nfd": False,
    "no-doubled-joshi": False, "ja-no-successive-word": False}}}


# ---------------------------------------------------------------- text prep
def prose(text):
    """Answer text without code, URLs, link targets, HTML tags; NFKC-normalised so
    full-width 「Ｔ＝２２．５」「１日」 match the same patterns as ASCII."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"```.*?```", "\n", t, flags=re.S)
    t = re.sub(r"`[^`\n]*`", " ", t)
    t = t.replace("**", "")                                        # **T**=22.5
    t = re.sub(r"\[([^\]\n]*)\]\([^)\n]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"</?[A-Za-z!][^<>\n]{0,120}>", " ", t)          # HTML-like tags only
    # paths: ASCII only (\w matched Japanese, so 「手段/道具/方法」 vanished)
    t = re.sub(r"(?:[A-Za-z]:)?(?:[\\/~][A-Za-z0-9_.\-~$]+){2,}[\\/]?", " ", t)
    return t


_QUOTE = re.compile(r"「([^」\n]*)」|『([^』\n]*)』|“([^”\n]*)”|\"([^\"\n]*)\"")


def _norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def _unquoted(t, prompt=None):
    """Remove quoted spans. With `prompt`, only spans the user's own message contains
    are removed (quoting the user is not a reuse; wrapping one's own coinage in 「」
    was a way past the check, Fable 2026-11-15). Code spans stay the escape hatch."""
    if prompt is None:
        return _QUOTE.sub(" ", t)
    hay = _norm(prompt)

    def rep(m):
        inner = next(g for g in m.groups() if g is not None)
        return " " if inner.strip() and _norm(inner) in hay else m.group(0)
    return _QUOTE.sub(rep, t)


def _ja_count(t):
    return len(re.findall(r"[぀-ヿ一-鿿]", t))


def _is_japanese(t):
    ja = _ja_count(t)
    return ja >= 40 and ja >= 0.3 * max(1, len(re.findall(r"\S", t)))


# ---------------------------------------------------------------- W
_DICT = None


def _dict():
    global _DICT
    if _DICT is None:
        try:
            with io.open(DICT_PATH, encoding="utf-8") as f:
                _DICT = [dict(e, rx=re.compile(e["re"]),
                              nx=re.compile(e["near"]) if e.get("near") else None)
                         for e in json.load(f)["entries"]]
        except Exception:
            _DICT = []
    return _DICT


NEAR_W = 25


def check_wording(p, prompt=""):
    out = []
    body = _unquoted(p, prompt)
    # 「合 言葉」: spaces between Japanese characters do not hide a phrase
    body = re.sub(r"(?<=[぀-ヿ一-鿿])[ \t　]+(?=[぀-ヿ一-鿿])", "", body)
    hay = _norm(prompt)
    for e in _dict():
        for m in e["rx"].finditer(body):
            if hay and _norm(m.group(0)) in hay:
                continue   # 「ご質問の道具とは」: the user's own word
            if e["nx"] and not e["nx"].search(body[max(0, m.start() - NEAR_W):m.end() + NEAR_W]):
                continue   # 「スタートの合図」「合言葉は安全第一」: not the flagged sense
            out.append({"check": "W", "quote": _ctx(body, m), "id": e["id"], "m": m.group(0),
                        "fix": e["use"], "why": e.get("why", "")})
            break
    return out


def _ctx(t, m, w=18):
    s = t[max(0, m.start() - w):m.end() + w]
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- P
# ASCII-only lookarounds: Python's \w also matches 件, so 「n=29件」 passed before.
# Not after - ? & . / (「--depth=1」「?page=2」「obj.x=1」 are code-like, not prose).
# Greek names (α=0.05), 「約」, exponents (1e-4) count; 「Q1=1〜3月」 (a range) does not.
RE_PARAM = re.compile(r"(?<![A-Za-z0-9_`=<>!\-?&./])([A-Za-zα-ωΑ-Ω][A-Za-z0-9_]{0,24})\s?=\s?"
                      r"((?:約)?-?\d[\d,]*(?:\.\d+)?(?:e-?\d+)?%?)(?![A-Za-z0-9_=:]|\.\d|\s?[〜~])")
# Names every reader of the answer knows as a measurement, not a parameter.
PARAM_OK = {"ph", "bmi", "iq", "hba1c", "ldl", "hdl", "n", "x", "y", "z"}
RE_ENV_NAME = re.compile(r"[A-Z][A-Z0-9]*_[A-Z0-9_]+$")   # ANSWER_PRECHECK=1: an env var


def check_param(p, prompt=""):
    out = []
    hay = _norm(prompt)
    for line in p.splitlines():
        if line.startswith(("    ", "\t")):
            continue      # indented code (tables and > lines ARE checked)
        for m in RE_PARAM.finditer(_unquoted(line, prompt)):
            name = m.group(1)
            if name.lower() in PARAM_OK or RE_ENV_NAME.match(name) or (hay and _norm(m.group(0)) in hay):
                continue  # the user wrote it: answering about it is not coining it
            out.append({"check": "P", "quote": m.group(0),
                        "fix": "記号を使わず「何が・どの条件で・どうなる」を日本語で書く（例: 「T=22.5」→「発動線（資産がこの額を下回ると…）2,250万円」）"})
    return out


# ---------------------------------------------------------------- X
FUNC = set("the a an is are was were be been not never no it its this that these those to of in on for "
           "with and or but if then so as by from at into than do does did can cannot should must will "
           "would could have has had i you we they he she".split())
RE_EN_RUN = re.compile(r"[A-Za-z][A-Za-z'\-]*(?:[ ,:]{1,2}[A-Za-z][A-Za-z'\-]*){2,}")
EN_IDIOMS = re.compile(r"\b(?:end to end|step by step|state of the art|proof of concept|one by one|"
                       r"out of the box|as is|to do|pay as you go|work in progress|single source of truth)\b", re.I)
X_TITLE_MAX = 6   # a capitalised run this short is a title / UI label / error text: report only


def check_english(p):
    out = []
    for line in p.splitlines():
        s = line.strip()
        if s.startswith(("|", ">")) or not re.search(r"[぀-ヿ一-鿿]", s):
            continue   # an all-English line is a quotation / title, not prose
        # English in quotes / parentheses is a label, title or the original term
        # given next to a Japanese one (「概念実証（proof of concept）」)
        s = re.sub(r"\([^()\n]*\)", " ", _unquoted(s))
        s = EN_IDIOMS.sub(" ", s)
        for m in RE_EN_RUN.finditer(s):
            raw = re.findall(r"[A-Za-z][A-Za-z'\-]*", m.group(0))
            words = [w.lower() for w in raw]
            nf = sum(w in FUNC for w in words)
            # a sentence, not a product name: a function word plus 2+ lowercase content
            # words (「Claude Code for VS Code」 has none, 「stop hook, never assert it」 has 3),
            # or 4+ words with 2+ function words (「it is not working」)
            content = [w for w in raw if w[0].islower() and w.lower() not in FUNC]
            if not (len(words) >= 3 and nf >= 1 and (len(content) >= 2 or (nf >= 2 and len(words) >= 4))):
                continue
            title = raw[0][0].isupper() and len(words) <= X_TITLE_MAX
            out.append({"check": "X?" if title else "X", "quote": m.group(0),
                        "fix": "題名・画面の表示・エラー文なら「」で囲む。文なら日本語で書く" if title else
                        "英語の文を地の文に混ぜず日本語で書く（原語が必要なら「日本語（原語）」）"})
    return out


# ---------------------------------------------------------------- T
def _server_up(timeout=0.4):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/" % PORT, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _spawn(argv, cwd):
    kw = {"cwd": cwd, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(argv, **kw)


def ensure_textlint(wait_s=0.0):
    """Start (or install, then start) the resident server. Returns True when it answers."""
    if _server_up():
        return True
    try:
        os.makedirs(TOOLS_DIR, exist_ok=True)
        rc = os.path.join(TOOLS_DIR, ".textlintrc.json")
        with io.open(rc, "w", encoding="utf-8") as f:
            json.dump(TEXTLINTRC, f, ensure_ascii=False)
        lock = os.path.join(TOOLS_DIR, "starting.lock")
        fresh = os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 180
        if not fresh:
            open(lock, "w").close()
            if not os.path.isfile(os.path.join(TOOLS_DIR, "node_modules", "textlint", "package.json")):
                pj = os.path.join(TOOLS_DIR, "package.json")
                if not os.path.exists(pj):
                    with io.open(pj, "w", encoding="utf-8") as f:
                        f.write('{"name":"ja-textlint-hook","private":true,"version":"1.0.0"}')
                npm = "npm.cmd" if os.name == "nt" else "npm"
                node = "node"
                # install, then start the server, in one detached shell
                cmd = "%s i -s --no-audit --no-fund %s && %s \"%s\" \"%s\" %d" % (
                    npm, " ".join(TEXTLINT_PKGS), node, SERVER_JS, TOOLS_DIR, PORT)
                _spawn(["cmd", "/c", cmd] if os.name == "nt" else ["sh", "-c", cmd], TOOLS_DIR)
            else:
                _spawn(["node", SERVER_JS, TOOLS_DIR, str(PORT)], TOOLS_DIR)
    except Exception:
        return False
    end = time.time() + wait_s
    while time.time() < end:
        if _server_up():
            return True
        time.sleep(1)
    return False


def check_textlint(p, wait_s=0.0):
    if not ensure_textlint(wait_s):
        return None     # not available this time (starting or failed)
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/lint" % PORT, data=p.encode("utf-8"), method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            msgs = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    lines = p.splitlines()
    out = []
    for m in msgs:
        ln = lines[m["line"] - 1] if 0 < m.get("line", 0) <= len(lines) else ""
        rule = (m.get("rule") or "").split("/")[-1]
        out.append({"check": "T", "rule": rule, "quote": ln.strip()[:60],
                    "fix": (m.get("msg") or "").split("\n")[0][:120]})
    return out


# ---------------------------------------------------------------- J
JUDGE_PROMPT = """下の「回答」は、AI が日本語の読者に書いた回答です。読者は「その分野を知らないが理解力はある人」で、直前に「依頼」を書いた本人です。会話のそれより前の部分は読者も見ています。
読者が意味を取れない箇所だけを指摘してください。文体の好み・内容の正誤・長さ・書式は指摘しないでください。

指摘する型（過去に読者が「意味不明」と言った実例つき）:
A 省略しすぎ: 何の値か・誰のことか・どの条件かが抜けた名詞句や数値。例「月80万円の不能証明と限界診断」（何が月80万円か無い）
D 造語: 一般に通じる語（パスワード・ツール・シグナル・ランダム化など）を自作の和語や比喩に言い換え、原語を復元できない。例「コンテナの窓に合言葉を入れてほしい」「くじで分けた29研究」
E 語の結びつき: 係り受けや語の組み合わせが日本語として不自然。例「自信がつくのを待つ順番を、私は勧めません」「設計で減る」
F 論理: 否定・条件・対比が逆になっている。例「効果がないならやっても損はない」
J 手順の欠落: 読者がする作業で、どのファイル・どの画面・何をするかが抜けている。例「バックアップ2ファイルを貼り戻して保存」
K 両義: 2通りに読める、または指す先が不明。例「年率の目的（交差検証の検証側）」

severity: 3 = 読者がこの文の意味を取れない・誤解する（上の実例と同じ程度）／2 = 少し考えれば分かる／1 = 好みの範囲。
依頼の中で読者自身が使った語・その会話で読者が知っている固有名（ファイル名・コマンド名など）は指摘しない。

出力は JSON だけ: {"issues":[{"type":"A","severity":3,"quote":"回答中の文字列を一字一句そのまま（40字以内）","why":"どう読めないか（30字以内）","fix":"書き直し案"}]}
指摘が無ければ {"issues":[]}。最大5件。

依頼:
<<<
%s
>>>

回答:
<<<
%s
>>>"""
JUDGE_BLOCK_SEVERITY = 3     # severity 3 blocks; 2 is reported only (see CALIBRATION)


def judge_text(answer):
    """What the model reads: code blocks and URLs out, inline code and link text kept
    (stripping inline code left 「（ ）」 holes that the model then flagged, 2026-11-15)."""
    t = re.sub(r"```.*?```", "\n", answer or "", flags=re.S)
    t = re.sub(r"\[([^\]\n]*)\]\([^)\n]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "<URL>", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()[:6000]


def judge_context(prompt):
    c = re.sub(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>", "（貼り付け省略）", prompt or "", flags=re.S)
    c = re.sub(r"<system-reminder>.*?</system-reminder>", "", c, flags=re.S)
    return c.strip()[:1200]


PROMPT_VER = hashlib.sha1(JUDGE_PROMPT.encode("utf-8")).hexdigest()[:6]


def _judge_cache(key):
    return os.path.join(CACHE_DIR, "j_" + key + ".json")


def _prune_cache():
    try:
        now = time.time()
        for fn in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, fn)
            if fn.startswith("j_") and now - os.path.getmtime(fp) > CACHE_MAX_AGE_S:
                os.remove(fp)
    except Exception:
        pass


def _real_home_env(env):
    """answer_precheck gives hooks an isolated HOME; the child claude needs the real
    one for its login. LOCALAPPDATA is not isolated: <home>\\AppData\\Local."""
    lad = os.environ.get("LOCALAPPDATA") or ""
    if os.environ.get("ANSWER_PRECHECK") and lad.lower().rstrip("\\/").endswith(os.path.join("appdata", "local")):
        home = os.path.dirname(os.path.dirname(lad.rstrip("\\/")))
        if os.path.isdir(os.path.join(home, ".claude")):
            env["HOME"] = env["USERPROFILE"] = home
    return env


def check_judge(answer, prompt=""):
    raw_answer = answer
    txt = judge_text(answer)
    ctx = judge_context(prompt)
    key = hashlib.sha1((PROMPT_VER + "\0" + ctx + "\0" + txt).encode("utf-8", "replace")).hexdigest()[:20]
    cp = _judge_cache(key)
    try:
        if os.path.exists(cp):
            with io.open(cp, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    env = _real_home_env(dict(os.environ))
    env["JA_QUALITY_GUARD_CHILD"] = "1"
    wd = None
    try:
        exe = shutil.which("claude")
        if not exe:
            return None
        wd = tempfile.mkdtemp(prefix="jaq_")
        # --setting-sources local: the user's hooks are not loaded (no recursion);
        # --system-prompt: replaces the default prompt, so the child does not carry
        # CLAUDE.md (measured 2026-11-15: ~1,060 input tokens, 10 s, $0.0002 per call).
        r = subprocess.run([exe, "-p", "--model", "haiku", "--setting-sources", "local",
                            "--tools", "", "--strict-mcp-config", "--no-session-persistence",
                            "--output-format", "json", "--system-prompt", "あなたは日本語の文章の校閲者です。"],
                           input=(JUDGE_PROMPT % (ctx or "（なし）", txt)).encode("utf-8"), capture_output=True,
                           timeout=JUDGE_TIMEOUT_S, cwd=wd, env=env)
        out = r.stdout.decode("utf-8", "replace")
        try:
            env_ = json.loads(out)
            if isinstance(env_, dict) and "result" in env_:
                out = env_.get("result") or ""
        except Exception:
            pass
    except Exception:
        return None
    finally:
        if wd:
            shutil.rmtree(wd, ignore_errors=True)
    m = re.search(r"\{.*\}", out, flags=re.S)
    if not m:
        return None
    try:
        issues = json.loads(m.group(0)).get("issues") or []
    except Exception:
        return None
    norm = lambda s: re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
    hay = norm(raw_answer)
    res = []
    for it in issues[:5]:
        q = (it.get("quote") or "").strip().strip("「」\"")
        if len(norm(q)) < 4 or norm(q) not in hay:
            continue     # the model's quote must exist verbatim in the answer
        try:
            sev = int(it.get("severity") or 0)
        except Exception:
            sev = 0
        if sev < 2:
            continue
        res.append({"check": "J", "type": it.get("type", ""), "severity": sev, "quote": q[:60],
                    "why": (it.get("why") or "")[:60], "fix": (it.get("fix") or "")[:120]})
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with io.open(cp, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
    except Exception:
        pass
    _prune_cache()
    return res


# ---------------------------------------------------------------- analysis
def analyze(answer, use_llm=True, use_textlint=True, textlint_wait=0.0, prompt=""):
    p = prose(answer)
    res = {"japanese": _is_japanese(p), "issues": [], "textlint": "skipped", "judge": "skipped"}
    # W and P also run on short answers (a 1-line answer can carry 「合言葉」); X,
    # textlint and J only on answers that are Japanese prose.
    iss = check_wording(p, prompt) + check_param(p, prompt) if _ja_count(p) >= 8 else []
    if not res["japanese"]:
        res["issues"] = iss
        return res
    iss += check_english(p)
    if use_textlint:
        t = check_textlint(p, textlint_wait)
        res["textlint"] = "unavailable" if t is None else "ok"
        iss += t or []
    if use_llm and len(re.sub(r"\s", "", p)) >= JUDGE_MIN_CHARS:
        j = check_judge(answer, prompt)
        res["judge"] = "unavailable" if j is None else "ok"
        iss += j or []
    res["issues"] = iss
    return res


def blocking(issues):
    return [i for i in issues if (i["check"] in BLOCK_CHECKS and
                                  (i["check"] != "J" or i.get("severity", 3) >= JUDGE_BLOCK_SEVERITY)) or
            (i["check"] == "T" and i.get("rule") in TEXTLINT_RULES_BLOCK)]


LABEL = {"W": "本人に指摘された言い回し", "P": "裸のパラメータ", "X": "英語の地の文", "X?": "英語の題名・表示らしき語句",
         "T": "textlint", "J": "読み手が意味を取れない箇所"}


def reason_text(block, report):
    lines = ["【日本語の品質（同じ指摘は1回のみ）】最終回答に、読み手が意味を取れない書き方がある。直してから出し直すこと。"
             "誤検出なら、そのまま同じ回答を出せば通る（同じ箇所は2度止めない）。"
             "語そのものを話題にするときは `合言葉` のようにコードの記法で囲む。"]
    for i in block[:8]:
        extra = (" ／" + i["why"]) if i.get("why") and i["check"] == "J" else ""
        lines.append("- [%s%s] 「%s」%s → %s" % (LABEL[i["check"]], ("・" + i["type"]) if i.get("type") else "",
                                                 i["quote"], extra, i["fix"]))
    if report:
        lines.append("参考（止めない）: " + " ／ ".join("「%s」(%s)" % (i["quote"][:30], i.get("rule") or i["check"])
                                                      for i in report[:5]))
    lines.append("原則: 専門語・一般に通じる外来語はそのまま使い、初出で意味を1文添える。自作の和語や比喩に言い換えない。"
                 "何の値か・誰のことか・どの条件かを省かない。")
    return "\n".join(lines)


# ---------------------------------------------------------------- hook glue
def _entrypoint(rows):
    for d in rows:
        if d.get("entrypoint"):
            return d["entrypoint"]
    return ""


def _judge_here(rows, ev):
    """Where the model judge (J) runs: ONLY inside answer_precheck (ANSWER_PRECHECK=1).
    J flags severity-3 issues on most ordinary answers (CALIBRATION), and at the real
    Stop every block puts a second answer on screen -- the user's 2026-11-03 complaint
    「最終的なチェックの上、1回の回答にまとめて」. At the draft stage a block is a
    rewrite nobody sees. Not inside stop_hook_active continuations; headless workers
    (entrypoint sdk-cli) skip it."""
    if _entrypoint(rows) == "sdk-cli" or ev.get("stop_hook_active"):
        return False
    return bool(os.environ.get("ANSWER_PRECHECK"))


def _issue_key(i):
    # the matched phrase, not the quote with context (context shifts with whitespace)
    return hashlib.sha1((i["check"] + "\0" + _norm(i.get("m") or i["quote"])).encode("utf-8", "replace")).hexdigest()[:16]


def _seen_path(sid):
    return os.path.join(STATE_DIR, sid + ".json")


def _load_seen(sid):
    try:
        with io.open(_seen_path(sid), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_seen(sid, d):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _seen_path(sid) + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _seen_path(sid))
    except Exception:
        pass


def _emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


def main():
    if os.environ.get("JA_QUALITY_GUARD_CHILD"):
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
    if _plg is None:
        return
    tp = _codex_transcript(ev.get("transcript_path") or "")
    if not tp or not os.path.isfile(tp):
        return
    rows = _plg.read_rows(tp)
    ts = _plg.turns(rows)
    if not ts:
        return
    prompt, answer = ts[-1][0], ts[-1][2]
    if not answer.strip():
        return
    sid = "".join(ch for ch in (ev.get("session_id") or "x") if ch.isalnum() or ch in "-_")
    use_llm = _judge_here(rows, ev)
    res = analyze(answer, use_llm=use_llm, textlint_wait=8.0, prompt=prompt)
    if use_llm and res["judge"] == "unavailable":
        _record_firing(NAME + "_judge_unavailable", ev)   # visible in the firing log, not silent
    # Once per issue (check + quoted text) per session, not per answer text: the draft
    # that answer_precheck saw and the answer the real Stop reads can differ in
    # whitespace or interim lines, but the same flagged phrase is the same decision.
    seen = _load_seen(sid)
    tkey = "turn_" + hashlib.sha1(_norm(prompt).encode("utf-8", "replace")).hexdigest()[:12]
    fresh = [i for i in res["issues"] if _issue_key(i) not in seen]
    block = blocking(fresh)
    report = [i for i in fresh if i not in block]
    if block and seen.get(tkey, 0) >= MAX_BLOCKS_PER_TURN:
        report, block = block + report, []   # bounded: at most N blocks per human turn
    if not block and not report:
        return
    for i in fresh:
        seen[_issue_key(i)] = int(time.time())
    if block:
        seen[tkey] = seen.get(tkey, 0) + 1
    _save_seen(sid, seen)
    if block:
        _record_firing(NAME, ev)
        _emit({"decision": "block", "reason": reason_text(block, report)})
    else:
        _record_firing(NAME + "_review", ev)
        _emit({"systemMessage": "【日本語の参考指摘（止めない）】" + " ／ ".join(
            "「%s」(%s: %s)" % (i["quote"][:30], i.get("rule") or i["check"], i["fix"][:40]) for i in report[:5])})


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer", required=True)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-textlint", action="store_true")
    a = ap.parse_args(argv)
    with io.open(a.answer, encoding="utf-8-sig", errors="replace") as f:
        ans = f.read()
    res = analyze(ans, use_llm=not a.no_llm, use_textlint=not a.no_textlint, textlint_wait=60.0)
    res["blocking"] = blocking(res["issues"])
    sys.stdout.buffer.write((json.dumps(res, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return 1 if res["blocking"] else 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_cli(sys.argv[1:]))
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
