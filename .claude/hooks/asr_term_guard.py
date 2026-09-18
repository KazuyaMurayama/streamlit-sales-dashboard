# -*- coding: utf-8 -*-
"""PreToolUse (Write|Edit|MultiEdit): 音声認識の既知の誤変換を成果物に残さない。

THE DEFECT THIS EXISTS FOR (2026-09-15)
---------------------------------------
YouTube 自動生成字幕から作ったデッキに「万友（蛮勇）」「前頭前夜（前頭前野）」
「農科学者（脳科学者）」等の誤変換がそのまま残り、それを「⚠ 自動生成字幕のため
逐語引用不可」という注釈で**開示**して済ませていた。ユーザーの指示（2026-09-15）:
注釈は載せるな、リスクが減る仕組みを置け。

誤変換は読者向け本文に**存在してはならない**もので、存在を断って許されるもの
ではない。したがって書き込み時に拒否する。

DESIGN
------
- 辞書: <cwd>/config/asr_glossary.json の "terms" {誤: 正}。加えて
  ~/.claude/asr_glossary.json があれば併合（全リポ共通の語）。辞書が無ければ何もしない
  （全リポに配布しても、辞書の無いリポでは no-op）。
- 対象: Write の content / Edit の new_string / MultiEdit の edits[].new_string のうち、
  書き込み先が .md のもの。transcripts/ 配下は対象外（生の字幕はそのまま保存し、
  正規化は fetch_transcript.py が別途行う。ここで拒否すると取得自体ができなくなる）。
- 判定: 辞書の「誤」文字列が含まれていたら deny。修正候補を並べて返す。
- 辞書は「動画本体または Whisper 再転写で確認した語」だけ入れる。文脈で両方あり得る
  語（決済/決裁）は入れない——正しい文を壊すため。

CALIBRATION (実測 2026-09-15)
-----------------------------
  transcripts/XJpM-eFVmnM（マナビジネス, auto/ja, 7,620字）: 辞書一致 4 語
  transcripts/s7qyV_6u2lE（The Solutions, auto/ja, 12,652字）: 辞書一致 22 語
  decks/CREATOR_BRAIN_40S_20260915.md（v1・欠陥版）: 「万友」「前頭前夜」「農科学者」
      「大価」「加素性」「レジレンス」を含む留保欄 → deny（欠陥版で発火することを確認）
  decks/CREATOR_BRAIN_40S_20260915-v2.md: 一致 0 → allow
  Whisper medium（CPU, 2分クリップ 119 秒）は「脳科学者」「危機感」を正しく転写した。
  YouTube 字幕は両方誤っていた。辞書の語はこの照合で確認したものだけ。

FAIL-OPEN on any exception. 出力は PreToolUse の permissionDecision JSON。

Deployed from claude-governance/templates/hooks/ -- edit there, not here.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_fired
except Exception:
    def _record_fired(name, ev):
        return False

GLOBAL_GLOSSARY = os.path.join(os.path.expanduser("~"), ".claude", "asr_glossary.json")
SKIP_RE = re.compile(r"(^|/)transcripts?/", re.I)
EXT_RE = re.compile(r"\.(md|markdown|mdx)$", re.I)


def load_glossary(cwd=None):
    cwd = cwd or os.getcwd()
    terms = {}
    for p in (GLOBAL_GLOSSARY, os.path.join(cwd, "config", "asr_glossary.json")):
        try:
            d = json.load(io.open(p, encoding="utf-8"))
            t = d.get("terms", d) if isinstance(d, dict) else {}
            terms.update({k: v for k, v in t.items() if isinstance(k, str) and isinstance(v, str) and k != v and not k.startswith("_")})
        except Exception:
            continue
    return terms


# 対訳表記（「誤→正」「正→誤」「誤 → 正」）は *defect ではなく documentation* である。
# README / CLAUDE.md / SKILL.md は誤変換の実例を挙げて仕組みを説明しており、
# それを deny すると「ガードが自分の説明文書の保守をブロックする」状態になる。
# 2026-09-16 実測: README.md 5 語・SKILL.md 3 語・CLAUDE.md 1 語が、実害ゼロで deny されていた。
_ARROW = u"(?:→|->|=>|＞)"


def _pair_spans(text, wrong):
    """`wrong` が対訳表記の一部として現れる位置を返す。"""
    import re as _re
    w = _re.escape(wrong)
    pats = (
        u"%s\\s*%s\\s*\\S" % (w, _ARROW),      # 誤→正
        u"\\S\\s*%s\\s*%s" % (_ARROW, w),      # 正→誤
    )
    spans = []
    for pat in pats:
        for m in _re.finditer(pat, text):
            spans.append((m.start(), m.end()))
    return spans


def find_hits(text, terms):
    """[(誤, 正, 件数)] を出現順で返す。対訳表記の出現は数えない。"""
    hits = []
    for wrong, right in terms.items():
        n = text.count(wrong)
        if not n:
            continue
        # 対訳表記として現れている分を差し引く
        exempt = 0
        for st, en in _pair_spans(text, wrong):
            exempt += text.count(wrong, st, en)
        n -= exempt
        if n > 0:
            hits.append((wrong, right, n))
    return hits


def _payload_texts(ti):
    """(path, text) の組を返す。"""
    out = []
    p = ti.get("file_path") or ti.get("filePath") or ""
    if isinstance(ti.get("content"), str):
        out.append((p, ti["content"]))
    if isinstance(ti.get("new_string"), str):
        out.append((p, ti["new_string"]))
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            out.append((e.get("file_path") or p, e["new_string"]))
    return out


def analyze(ti, terms):
    hits_all = []
    for path, text in _payload_texts(ti):
        q = (path or "").replace("\\", "/")
        if not EXT_RE.search(q) or SKIP_RE.search(q):
            continue
        hits_all.extend(find_hits(text, terms))
    return hits_all


def _read_payload():
    """stdin を UTF-8 バイトとして読む。

    実測 2026-09-15: `json.load(sys.stdin)` は Windows の既定 stdin 符号化（cp932）で
    復号するため、content に日本語を含むペイロードで UnicodeDecodeError → 外側の
    except で exit 0 → **誤変換入りの書き込みが黙って通った**。この hook は日本語の
    content を見るのが仕事なので、バイトで読んで UTF-8 で復号する。
    """
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8", "replace")
    return json.loads(raw.decode("utf-8", "replace"))


def main():
    try:
        payload = _read_payload()
    except Exception:
        return 0
    terms = load_glossary(payload.get("cwd"))
    if not terms:
        return 0
    hits = analyze(payload.get("tool_input") or {}, terms)
    if not hits:
        return 0
    _record_fired("asr_term_guard", payload)
    reason = (u"音声認識の既知の誤変換が成果物に残っている %d 語: %s。"
              u"注釈で開示するのではなく本文を直すこと（config/asr_glossary.json）。"
              % (len(hits), "、".join(u"「%s」→「%s」×%d" % h for h in hits[:8])))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}},
                     ensure_ascii=False))
    return 0


def _selftest():
    terms = {"万友": "蛮勇", "前頭前夜": "前頭前野", "農科学者": "脳科学者"}
    cases = [
        ("red: 誤変換を含む deck の Write は deny",
         {"file_path": "C:/r/decks/X_20260915.md", "content": "落ちたのは万友であり、前頭前夜の話"}, 2),
        ("red: Edit new_string にも効く",
         {"file_path": "C:/r/decks/X_20260915.md", "old_string": "a", "new_string": "農科学者いわく"}, 1),
        ("green: 正しい語のみ",
         {"file_path": "C:/r/decks/X_20260915.md", "content": "蛮勇と前頭前野と脳科学者"}, 0),
        ("green: transcripts/ は対象外（生字幕は保存させる）",
         {"file_path": "C:/r/transcripts/x.md", "content": "万友"}, 0),
        ("green: .py は対象外",
         {"file_path": "C:/r/scripts/x.py", "content": "万友"}, 0),
    ]
    bad = 0
    for name, ti, want in cases:
        got = len(analyze(ti, terms))
        ok = got == want
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else " -> got %d" % got))
        bad += 0 if ok else 1
    print("selftest: %d/%d ok" % (len(cases) - bad, len(cases)))
    return 1 if bad else 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if "--scan" in sys.argv:
        # CLI: python asr_term_guard.py --scan <file.md> [cwd]  → 一致一覧（較正用）
        p = sys.argv[sys.argv.index("--scan") + 1]
        terms = load_glossary(sys.argv[sys.argv.index("--scan") + 2] if len(sys.argv) > sys.argv.index("--scan") + 2 else None)
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        hs = find_hits(txt, terms)
        print("%s: %d 語 %s" % (os.path.basename(p), sum(n for _, _, n in hs), [(w, r, n) for w, r, n in hs]))
        sys.exit(0)
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
