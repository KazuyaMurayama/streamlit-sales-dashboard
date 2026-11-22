# -*- coding: utf-8 -*-
"""抜き取り監査（acceptance audit）: 「N件すべて合格」を、書き手の検査ではなく、無作為に抜いた実物を
別のモデルが依頼者の発言の全文と照合した結果で報告するための道具。全リポ共通（~/.claude/hooks と各リポの
.claude/hooks に配布。イベント登録なし）。

WHY (2026-11-22)
----------------
Soulful-Content で、修正指示53項目を70本に当てると漏れ0の記事は0本（中央値18項目の漏れ）だったのに、
機械のゲートは70本すべてを合格にし、Claude Code は「○」と報告した。ユーザー:
  「検査の設計スキルが弱いのでは？…それで「すべて合格した」と報告したということでは？」
  「Fableの攻撃でも防除できるレベルの検証を作るため、という目的を解決できるのか、それで。もっとよい方法あるなら
   そっちでやれよ。あと、記事の件に限定せずに全リポ向けの汎用性も備えるものでやれよ。」
v1 の対策（verification_design_guard の正規表現）は Fable の攻撃86件のうち29件しか止めず、しかも止めても
検査の質は上がらない。Fable の反証（scratchpad vd/design_v2_fable.md）の要点:
  1. 要求の分母を書き手が決めると、53項目中8項目だけ書いて「網羅100%」になる。
  2. 測るべきは「検査と見本の一致」ではなく「合格にした実物」。今回は k=1 でも違反が出た。
  3. 強制は言い回しでなく、ファイルの変更と hash で掛ける。
この道具はその3点を実装する:
  * 分母 = 依頼者の発言の逐語（会話記録から機械で抜く。書き手の要約を通さない。前の回の指示も含む）
  * 標本 = 合格にした対象から乱数で抜く（書き手が選ばない）。抜いた時点の中身の hash を記録する
  * 判定 = 書き手と別のモデル（Fable）が、検査のコードを見ずに、発言の全文と標本を読んで判定する
  * 報告 = score が出す1行をそのまま最終回答に貼る（違反の件数・違反した要求・言える上限）。監査の後に
           標本の中身が変わっていたら、その行に「監査後に変更」と出る

使い方
------
  python ~/.claude/hooks/acceptance_audit.py sample --repo <repo> --k 5 [--since 2026-11-01] <files...>
      -> 監査 ID と、Fable に渡す依頼文を出す（資料 packet.md は ~/.claude/state/audit/<ID>/）
  Agent(model="fable") に依頼文をそのまま渡す（最大12ターン）。Fable が verdicts.json を書く
  python ~/.claude/hooks/acceptance_audit.py score <ID>
      -> 最終回答に貼る1行（【抜き取り監査 AUDIT-<ID>】…）と、違反した要求の一覧
対象が1件なら k=1（その1件を読む）。対象のファイルが無い作業（設定変更・一回きりの操作）には使わない。
"""
import argparse
import glob
import hashlib
import io
import json
import math
import os
import random
import re
import sys
import time

STATE = os.path.join(os.path.expanduser("~"), ".claude", "state", "audit")
PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
MAX_PROMPT = 20000   # longer prompts are cut WITH a visible marker (Fable U5b)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except Exception:
        return None


def _norm(p):
    return os.path.normcase(os.path.abspath(p)).replace("\\", "/").rstrip("/")


def _text(row):
    c = (row.get("message") or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return ""
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


SYS_PREFIX = ("<", "[SYSTEM", "[Request interrupted", "Caveat:", "This session is being continued",
              "Stop hook feedback", "Another Claude session")


def _is_human(row):
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain") or row.get("isCompactSummary"):
        return False
    o = row.get("turnOrigin") or (row.get("origin") or {}).get("kind")
    if o and o != "human":
        return False
    # VS Code puts <system-reminder>/<ide_selection> before the typed words: judge the words, not the wrapper
    t = _clean(_text(row))
    return bool(t) and not t.startswith(SYS_PREFIX)


LEAD_TAG = re.compile(r"^\s*<([A-Za-z_][\w-]*)\b[^>]*>.*?</\1>", re.S)


def _clean(t):
    """The words the requester typed. Pasted text is kept (it is often the instruction itself); any other
    leading <tag>...</tag> block the client puts before the words is removed, whatever its name (Fable U2)."""
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S)
    t = re.sub(r"<pasted_content[^>]*>(.*?)</pasted_content>", lambda m: m.group(1), t, flags=re.S)
    t = t.strip()
    while True:
        m = LEAD_TAG.match(t)
        if not m:
            break
        t = t[m.end():].strip()
    return t


QUEUED_WAKE = ("<task-notification>", "<agent-message", "<cross-session", "Another Claude session")


def _queued(row):
    """A prompt typed while the model was working: stored only as a queued_command attachment (Fable U4)."""
    a = row.get("attachment") or {}
    pr = a.get("prompt")
    if row.get("type") != "attachment" or a.get("type") != "queued_command" or not isinstance(pr, str):
        return ""
    return "" if pr.lstrip().startswith(QUEUED_WAKE) else _clean(pr)


def user_requests(repo, since):
    """Every human prompt of every conversation that worked in `repo`: a row's cwd under it, or the repo's
    path in any tool input (sessions started in the home folder, Fable U3). Typed-while-working prompts
    included (U4). claude -p / SDK conversations excluded (their prompts were written by Claude).
    -> (list of (timestamp, text), number of prompts cut at MAX_PROMPT)"""
    root = _norm(repo)
    base = os.path.basename(os.path.abspath(repo).rstrip("\\/"))
    out, seen, cut = [], set(), 0
    for fp in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        try:
            if time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(fp))) < since:
                continue
            with io.open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if base not in content:
                continue
            flat = content.lower().replace("\\\\", "/").replace("\\", "/")
            hit, worker, got = root in flat, False, []
            for ln in content.splitlines():
                if '"user"' not in ln and "queued_command" not in ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("entrypoint") and r.get("entrypoint") not in ("claude-vscode", "cli", "claude-desktop"):
                    worker = True
                    break
                cwd = _norm(r.get("cwd") or "") if r.get("cwd") else ""
                if cwd and (cwd == root or cwd.startswith(root + "/")):
                    hit = True
                if (r.get("timestamp") or "")[:10] < since:
                    continue
                # a prompt given in another repo of the same conversation is not about this one;
                # one given from a parent folder (the home folder) may be (Fable U3)
                if cwd and not (cwd == root or cwd.startswith(root + "/") or root.startswith(cwd + "/")):
                    continue
                t = _queued(r) or (_clean(_text(r)) if _is_human(r) else "")
                if t:
                    got.append((r.get("timestamp") or "", t))
            if worker or not hit:
                continue
            for ts, t in got:
                k = hashlib.sha1(t.encode("utf-8", "replace")).hexdigest()
                if k in seen:
                    continue
                seen.add(k)
                if len(t) > MAX_PROMPT:
                    cut += 1
                    t = t[:MAX_PROMPT] + u"\n（以下 %d 字省略）" % (len(t) - MAX_PROMPT)
                out.append((ts, t))
        except Exception:
            continue
    out.sort()
    return out, cut


PACKET_HEAD = u"""# 抜き取り監査の資料（AUDIT-{id}）

あなたは書き手と別の判定者です。書き手の検査（ゲート・スクリプト・チェックリスト）は見せません。見ないでください。
下の「依頼者の発言」だけを要求の正典として、「標本」の各ファイルを読み、依頼者が求めたことに反している箇所を探してください。

手順:
1. 依頼者の発言から、標本に当てはまる要求を自分で列挙する（発言の逐語を引用。書き手の要約は存在しない前提）。
   後の発言が前の発言を取り消している場合は後を優先し、その旨を書く。
2. 標本ごとに、各要求について violated / ok / na を判定し、violated には該当箇所の逐語を根拠に書く。
3. 結果を次の JSON で {verdicts} に書く（このファイル以外は書かない）:
   {{"model": "<あなたのモデル名>", "requirements": [{{"id": "R1", "quote": "発言の逐語", "at": "発言の日時"}}],
     "items": [{{"path": "<標本のパス>", "verdicts": [{{"req": "R1", "verdict": "violated|ok|na", "evidence": "逐語"}}]}}]}}
   標本1つにつき、当てはまる要求すべてに判定を付ける。読めなかった標本は "verdicts": [] とし、理由を "note" に書く。
4. 返信は日本語で、違反の件数と重い違反3つまでを 1KB 以内。

## 依頼者の発言（{n_req}件・{since} 以降・{repo} で作業した会話から機械で抽出。古い順）
"""


def _default_since(repo, files):
    """From the first commit of the sampled population (earlier instructions still bind), at least 30 and at
    most 90 days back (Fable U6)."""
    import subprocess
    lo = time.strftime("%Y-%m-%d", time.localtime(time.time() - 90 * 86400))
    hi = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    try:
        dirs = sorted({os.path.dirname(f) for f in files})[:50]
        out = subprocess.run(["git", "-C", repo, "log", "--reverse", "--format=%cs", "--"] + dirs,
                             capture_output=True, timeout=30).stdout.decode("utf-8", "replace").split()
        first = out[0] if out else hi
    except Exception:
        first = hi
    return max(lo, min(first, hi))


def _ledger(rec):
    """Append-only record of every draw. -> how many earlier draws (12 h) overlap this population by half."""
    lp = os.path.join(STATE, "ledger.jsonl")
    pop = set(rec["files"])
    n = 0
    try:
        with io.open(lp, encoding="utf-8") as f:
            for ln in f:
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get("t", 0) >= rec["created"] - 12 * 3600 and len(pop & set(o.get("files") or [])) * 2 >= len(pop):
                    n += 1
    except Exception:
        pass
    try:
        os.makedirs(STATE, exist_ok=True)
        with io.open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": rec["created"], "id": rec["id"], "repo": rec["repo"], "files": rec["files"],
                                "sample": sorted(rec["sample"])}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return n


def cmd_sample(a):
    files = []
    for f in a.files:
        files.extend(glob.glob(f) or [f])
    if a.list:
        with io.open(a.list, encoding="utf-8") as f:
            files.extend(l.strip() for l in f if l.strip())
    files = sorted({os.path.abspath(f) for f in files if os.path.isfile(f)})
    if not files:
        sys.exit("対象のファイルがありません")
    since = a.since or _default_since(a.repo, files)
    reqs, cut = user_requests(a.repo, since)
    if not reqs:
        # no denominator, no audit (Fable S5)
        print(u"依頼者の発言が0件です（%s 以降・%s）。--repo と --since を確かめてください。監査は作りません。" % (since, _norm(a.repo)))
        sys.exit(2)
    # The writer does not choose the draw: no --seed. AUDIT_SEED exists for the tests only and is
    # printed in the line when used (Fable S3).
    env_seed = os.environ.get("AUDIT_SEED")
    seed = int(env_seed) if env_seed else int.from_bytes(os.urandom(8), "big")
    k = min(a.k, len(files))
    picked = sorted(random.Random(seed).sample(files, k))
    aid = time.strftime("%Y%m%d%H%M%S") + "-" + hashlib.sha1(("%s%d%s" % (files, seed, os.urandom(4))).encode()).hexdigest()[:6]
    d = os.path.join(STATE, aid)
    os.makedirs(d, exist_ok=True)
    verdicts = os.path.join(d, "verdicts.json").replace("\\", "/")
    packet = os.path.join(d, "packet.md").replace("\\", "/")
    with io.open(packet, "w", encoding="utf-8") as f:
        f.write(PACKET_HEAD.format(id=aid, verdicts=verdicts, n_req=len(reqs), since=since, repo=_norm(a.repo)))
        for ts, t in reqs:
            f.write(u"\n### %s\n\n%s\n" % (ts[:16].replace("T", " "), t))
        f.write(u"\n## 標本（対象 %d 件から乱数で %d 件）\n\n" % (len(files), k))
        for p in picked:
            f.write(u"- %s\n" % p.replace("\\", "/"))
    prompt = (u"抜き取り監査 AUDIT-%s。最大12ターン。資料 %s を読み、その手順どおりに標本を判定して %s に JSON を書く。"
              u"書き手の検査のコードは読まない。返信は日本語で 1KB 以内。" % (aid, packet, verdicts))
    rec = {"id": aid, "repo": _norm(a.repo), "since": since, "population": len(files), "files": files,
           "seed_fixed": bool(env_seed), "k": k, "sample": {p: sha(p) for p in picked}, "n_requests": len(reqs),
           "cut": cut, "packet_sha": sha(packet), "prompt": prompt, "created": int(time.time())}
    rec["draw_no"] = _ledger(rec) + 1
    with io.open(os.path.join(d, "sample.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print(u"AUDIT-%s: 対象 %d 件から %d 件を抜きました。依頼者の発言 %d 件（%s 以降）。" % (aid, len(files), k, len(reqs), since))
    if rec["draw_no"] > 1:
        print(u"⚠ この対象の抽選は12時間で%d回目です（score の行に出ます）。" % rec["draw_no"])
    print(u"\n次の依頼文を Agent(model=\"fable\") に一字も足さずにそのまま渡す（足すと監査は無効）:\n")
    print(prompt)


def upper_bound(x, k, conf=0.95):
    """One-sided Clopper-Pearson upper bound of the violation rate."""
    if k == 0:
        return 1.0
    if x == 0:
        return 1 - (1 - conf) ** (1.0 / k)
    if x >= k:
        return 1.0
    lo, hi = x / k, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        # P(X <= x | p=mid)
        cdf = sum(math.comb(k, i) * mid ** i * (1 - mid) ** (k - i) for i in range(x + 1))
        if cdf > 1 - conf:
            lo = mid
        else:
            hi = mid
    return hi


VERDICTS = ("violated", "ok", "na")


def score(aid):
    d = os.path.join(STATE, aid)
    with io.open(os.path.join(d, "sample.json"), encoding="utf-8") as f:
        rec = json.load(f)
    vp = os.path.join(d, "verdicts.json")
    if not os.path.exists(vp):
        return None, u"AUDIT-%s: verdicts.json がありません（別モデルの判定がまだ）" % aid
    with io.open(vp, encoding="utf-8") as f:
        v = json.load(f)
    reqs = {r.get("id"): r.get("quote", "") for r in v.get("requirements") or []}
    items = {os.path.normcase(os.path.abspath(i.get("path", ""))): i for i in v.get("items") or []}
    bad, unread, changed, hit = 0, 0, 0, {}
    for p, h0 in rec["sample"].items():
        it = items.get(os.path.normcase(os.path.abspath(p)))
        if sha(p) != h0:
            changed += 1
        if not it or not it.get("verdicts"):
            unread += 1
            continue
        vals = [str(x.get("verdict") or "").strip().lower() for x in it["verdicts"]]
        # an unknown value, a sheet of only "na", or no requirement at all is not a reading (Fable S11, S11b)
        if not reqs or any(x not in VERDICTS for x in vals) or all(x == "na" for x in vals):
            unread += 1
            continue
        vs = [x for x in it["verdicts"] if str(x.get("verdict") or "").strip().lower() == "violated"]
        if vs:
            bad += 1
        for x in vs:
            hit[x.get("req")] = hit.get(x.get("req"), 0) + 1
    k = rec["k"]
    read = k - unread
    ub = upper_bound(bad, read)
    model = v.get("model") or u"不明"
    line = (u"【抜き取り監査 AUDIT-%s】対象%d件から無作為に%d件を、書き手と別のモデル（%s）が依頼者の発言%d件"
            u"（要求%d件に整理）と照合: 違反あり%d件／%d件" % (aid, rec["population"], k, model, rec["n_requests"],
                                                   len(reqs), bad, read))
    if unread:
        line += u"・読めなかった標本%d件" % unread
    if rec.get("seed_fixed"):
        line += u"・乱数を固定した抽選"
    if rec.get("draw_no", 1) > 1:
        line += u"・この対象の抽選%d回目" % rec["draw_no"]
    if rec.get("cut"):
        line += u"・長い発言%d件を途中で省略" % rec["cut"]
    if sha(os.path.join(d, "packet.md")) != rec.get("packet_sha", sha(os.path.join(d, "packet.md"))):
        line += u"・⚠ 資料（packet.md）が抽選の後に書き換えられている"
    if bad == 0 and read:
        line += u"。この標本で言えるのは、違反のある割合が%.0f%%未満（95%%）まで" % (ub * 100)
    elif bad:
        line += u"。合格とは言えない（違反のある割合の推定 %.0f%%）" % (100.0 * bad / read)
    if changed:
        line += u"。⚠ 監査後に標本%d件の中身が変わっている（この監査は今の中身を見ていない）" % changed
    line += u"。"
    top = sorted(hit.items(), key=lambda x: -x[1])
    detail = [u"- %s（%d件）: %s" % (r, n, (reqs.get(r) or "")[:120].replace("\n", " ")) for r, n in top]
    res = {"id": aid, "bad": bad, "read": read, "k": k, "unread": unread, "changed": changed, "ub": ub,
           "line": line, "scored": int(time.time())}
    with io.open(os.path.join(d, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return res, line + ("\n違反した要求:\n" + "\n".join(detail) if detail else "")


def cmd_score(a):
    res, text = score(a.id.replace("AUDIT-", ""))
    print(text)
    sys.exit(0 if res and res["bad"] == 0 and not res["unread"] and not res["changed"] else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd")
    s = sp.add_parser("sample")
    s.add_argument("--repo", required=True)
    s.add_argument("--k", type=int, default=5)
    s.add_argument("--since")
    s.add_argument("--list")
    s.add_argument("files", nargs="*")
    c = sp.add_parser("score")
    c.add_argument("id")
    a = ap.parse_args()
    if a.cmd == "sample":
        cmd_sample(a)
    elif a.cmd == "score":
        cmd_score(a)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
