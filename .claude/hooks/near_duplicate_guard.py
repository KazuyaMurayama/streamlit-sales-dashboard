# -*- coding: utf-8 -*-
"""ほぼ同じ内容のファイルを、版管理せずに同じリポの中へ2つ以上置いたままターンを終えさせない。

WHY（2026-09-30 依頼者指摘）
    「ほとんど同じようでいて少し違う内容のファイルを、バージョン管理せず2つ以上作るのをやめろ。
    修正が何度も入るとき片方しか直せないミスが起きる。このリポに限らず」。
    実例: Soulful-Content の原稿 deliverables/note/nt-040-...-DRAFT.md と、そこから生成して
    コミットしていた投稿用 _posts/nt-040-.../02_body.md（commit 8d18336。1つ前の ef181e2 では
    02_body_free.md と 03_body_paid.md の2つに分かれて同居）。2026-09-19 にも同じ形で、直した
    欠陥が _posts 側だけに残った（そのときは「鮮度チェック」を足しただけで重複自体は残した）。
    ほかに計画書の v1/v2 併存（v1 は後で廃盤印を付けた）。
    固有名（_posts/ や -DRAFT）では塞がない。塞ぐのは次の不変条件:
      「ターンの終わりに、同じリポの中で、生きている（廃盤でない）テキストファイル同士が
        ほぼ同じ内容で、そのうち少なくとも1つがこのターンで作成・変更されたもの、であってはならない」

解消法（止めるメッセージにも出す）
    1. 片方を正にして、もう一方を削除する（版は git の履歴で持つ）
    2. 古い方の本文1行目（front matter の直後）に「⛔ 廃盤（YYYY-MM-DD）: 理由。後継: …」を書く
       （deprecation_guard.py がその後の編集を止める。印の判定は deprecation_guard.mark_in_text を
       import して同じ基準を使う: front matter 直後の最初の非空行、または front matter の status）
    3. 生成物はコミットせず、必要なときに生成する（.gitignore に入れれば比較対象から外れる）

2つの場面で動く（settings.json の Stop と PreToolUse に登録する）:
    Stop        主。このターンで変わったファイルを git から得る（shell 経由の書き込みも拾うため）:
                  git status / git diff HEAD のうち max(mtime, ctime) がターン開始以降のもの
                  （ctime も見るのは、Copy-Item / cp -p で mtime を古いまま複製しても作成時刻は新しいため）
                  ＋ ターン開始以降のコミットで変わったファイル（ターン内でコミット済みでも拾う）。
                ターン開始はトランスクリプトを末尾から遡り、最後の依頼者の発言の時刻を取る（行数の上限なし）。
                対象リポは cwd のリポと、このターンの Write/Edit/シェル のパスが属するリポ。
                各ファイルをリポ内の他の追跡・未追跡ファイル（.gitignore 対象外）と、同じ群
                （文書／コード）の中で比べ、ほぼ同じなら1回だけ止める。
                時間の上限 5 秒。超えたら残りは見ずに、止める代わりに systemMessage で警告する
                （黙って通さない）。途中までの計算はキャッシュに残るので次のターンは続きから速く済む。
    PreToolUse  Write で新しいファイルを作るとき、その内容が既存の生きたファイルとほぼ同じなら
                警告を注入する（拒否はしない）。拒否しない理由: ①正規の手順「後継を書く → 旧版に
                廃盤印」の1手目を止めてしまう ②シェル経由の作成は見えないので、拒否しても抜け道が残り
                止める層は Stop に一本化した方が判定が1か所で済む ③Stop が必ず止めるので、Write 時は
                「このあと止まる」と先に知らせるだけで足りる。

判定（ほぼ同じ）— 2026-09-30 Fable 攻撃的検証（30件中24件見逃し）を受けて作り直した
    群: 拡張子で「コード」（CODE_EXTS）と「文書」（それ以外のテキスト。拡張子なし・.rst・.markdown
        ・.json 等も含む）の2群に分け、群の中で比べる。拡張子を変えただけの複製（.md → .txt）も拾う。
        NUL を含むもの・既知のバイナリ拡張子は対象外。300KB 超は先頭 300KB で比べる。
    正規化: NFKC（全角英数→半角）。文書は文字・数字以外（句読点・記号・空白・改行）を全部除く。
        コードは空白と改行だけ除く。句読点の置換（。→.）・全角数字・改行位置（折り返し・段落結合）・
        表を箇条書きにしただけの差は、この段階で消える。
    指紋: 正規化後の文字 8-gram の集合から、crc32 の下位2ビットが 0 のもの（約1/4）を残す
        （mod サンプリング。Jaccard と包含率の不偏な推定になる）。集合なので段落の並べ替えにも強い。
    判定（sa, sb = 2ファイルの指紋）:
        jaccard = |sa∩sb| / |sa∪sb| ≥ JACCARD[群]              … 全体がほぼ同じ（順序によらない）
        または 包含率 = |sa∩sb| / min(|sa|,|sb|) ≥ CONTAIN[群] かつ 小さい方が MIN_SKETCH 以上
                                                              … 片方がもう片方の一部（無料部分・有料部分）
        または 合算包含: 1つのファイルの CONTAIN[群] 以上が、それぞれ大部分がそのファイルに含まれる
               2つ以上の別ファイルで覆われる（3分割以上して1片ずつが小さい形）
    完全一致も対象にする（初版は配布コピーと区別がつかないとして外していたが、配布コピーはルート直下
    の .claude/ にしか無く、そこは除外で足りる）。
    除外ディレクトリ: どこにあっても .git node_modules venv .venv __pycache__ site-packages、
        リポのルート直下の .claude/ .codex/ だけ（hooks/skills は claude-governance の templates から
        deploy_all.py が配る複製で、正は templates にある）。build/ dist/ docs/ などは対象。
    速度: 指紋は <git-dir>/near_dup_cache.pkl に (サイズ, mtime_ns) をキーにして残す。
        キャッシュが無いファイルは、対象ファイルとサイズの近い順（±50% を先頭）に計算する。

較正（実測 2026-09-30, tests/calibrate_near_duplicate_guard.py）
    対象: C:/Users/user/Desktop/repos 配下の git リポ 48個の、直近30日・各最大50コミット＝2,210コミット。
    各コミットで追加・変更されたファイルを、そのコミット時点のツリーの同じ群の生きたファイルと比べた
    （ペア単位。合算包含は数えていない）。
    発火 32コミット（1.45%）、重複を畳んだペア 133組。
      111組  Soulful-Content の原稿 *-DRAFT.md と、生成してコミットした _posts/*/0?_body*.md
             （狙ったクラスそのもの）
       10組  別の形の真陽性: nt-001 の原稿 .md と貼り付け用 .txt（拡張子違い。初版は見逃した）/
             governance の verify_citations.py の複製（完全一致。初版は対象外にしていた）/ 提案資料と
             顧客向け版 / 保育園申請ガイドの同文2本 / README_20260304.md と README.md / 職務経歴書の日付版
             2本（日付付きで併存させる命名規約とぶつかるが、古い方に廃盤印で解消できる）/ audits の
             holdout_*.json の v1 と v3、同じデータを別名で置いたもの（2組）、tool と tool_v3
       12組  灰色（仕組み上の包含）: holdout_union_*.json が tool/websearch の結果を合わせた集計なので
             各部分を 82〜99% 含む（11組。いずれも上の真陽性と同じコミットで、発火コミット数は増えない）/
             happiness-system の DAILY_UPDATES.md と DAILY_UPDATES_DETAIL.md（1組・1コミット）
    閾値の根拠（掃引）:
      文書 Jaccard 0.4〜0.6 と 0.7 の差は 1コミット（holdout_tool_openalex と _fields: J 0.55・包含 0.72 の
      派生データ）。0.7 にしたのは、Fable の合成した誤検知（同じ定型60段落＋固有40〜90段落のレポート
      J 0.53〜0.64・包含 0.71〜0.79／同じ見出しの議事録 J 0.59）を止めないため。例の nt-040 は 8d18336 で
      J 0.88、ef181e2 の無料部分は包含 0.97・有料部分は 0.95。文書の包含 0.8 は 0.7〜0.9 で 1コミット差。
      コードは Jaccard 0.6〜0.9・包含 0.8〜0.95 で発火数が同じ（33→ 文書閾値込みで 32）。兄弟フック
      （pre_read_guard と pre_write_guard）は J 0.53・包含 0.72。定型の多い .ps1 2本（宛先だけ違う。灰色）
      J 0.87 を止めないよう Jaccard 0.9・包含 0.95 にした。MIN_SKETCH は 25〜200 で発火数が同じ。
    Fable の攻撃ハーネス（attack_ndg.py）: 見逃し 30/34 → 4/34。残りは ルート直下 .codex/（仕様の除外）、
    ネストした別の git リポ、tool_use の記録が無い別リポへのシェル書き込み、行の70%に1字ずつ足す
    （J 0.61・包含 0.76。50% までは止まる。Jaccard 0.7 と引き換えの既知の穴）。誤検知狙い 10件は 0件。
    3,000ファイルの合成リポ（キャッシュ無しの初回）は 5 秒で打ち切り、
    systemMessage で警告する（サイズの近い順に見るので、同サイズの複製は打ち切り前に見つかって止まる）。
    PreToolUse を警告止まりにした理由は上の「2つの場面」。
"""
import io
import json
import os
import pickle
import re
import subprocess
import sys
import time
import unicodedata
import zlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from firing_log import record as _record_firing
except Exception:  # pragma: no cover
    def _record_firing(*_a, **_k):
        return False
try:
    import deprecation_guard as _dg
    _genuine_user_text = _dg._genuine_user_text
    mark_in_text = _dg.mark_in_text          # 廃盤印の判定は deprecation_guard と同じ関数
    _touched_files = _dg.touched_files
except Exception:  # pragma: no cover - deprecation_guard が無い環境用の同じ基準のコピー
    _dg = None
    _MB = re.compile(r"^\s*(?:#|//|<!--|--|;)?\s*⛔\s*廃盤[（(]\d{4}-\d{2}-\d{2}[）)]")
    _FS = re.compile(r"^\s*status:\s*[\"']?(?:deprecated|廃盤)[\"']?\s*$", re.I)
    _PR = re.compile(r"^\s*(?:#!|#.*-\*-.*coding|#\s*coding[:=])")

    def mark_in_text(text):
        lines = (text or "").lstrip("﻿").split("\n")[:240]
        i, fm = 0, None
        if lines and lines[0].strip() == "---":
            for j in range(1, min(len(lines), 200)):
                if lines[j].strip() in ("---", "..."):
                    fm = next((ln.strip() for ln in lines[1:j] if _FS.match(ln)), None)
                    i = j + 1
                    break
        while i < len(lines) and (not lines[i].strip() or _PR.match(lines[i])):
            i += 1
        return lines[i].strip() if i < len(lines) and _MB.match(lines[i]) else fm

    def _genuine_user_text(r):
        if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
            return None
        c = (r.get("message") or {}).get("content")
        if isinstance(c, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                return None
            return next((b.get("text") for b in c if isinstance(b, dict) and b.get("type") == "text"), None)
        return c if isinstance(c, str) else None

    def _touched_files(calls, cwd):
        out = set()
        for _n, inp in calls:
            fp = inp.get("file_path") or inp.get("notebook_path")
            if fp:
                out.add(fp if os.path.isabs(fp) else os.path.join(cwd or os.getcwd(), fp))
        return out

CODE_EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".gs", ".sh", ".bash", ".zsh", ".ps1",
             ".psm1", ".bat", ".cmd", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cc",
             ".cpp", ".hpp", ".cs", ".php", ".pl", ".lua", ".r", ".sql", ".vbs", ".scala", ".dart"}
BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svgz", ".pdf", ".zip", ".gz",
               ".7z", ".tar", ".rar", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".pptx", ".ppt", ".pyc",
               ".pyo", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3",
               ".mp4", ".m4a", ".wav", ".mov", ".avi", ".webm", ".parquet", ".pkl", ".pickle", ".npy",
               ".npz", ".db", ".sqlite", ".sqlite3", ".bin", ".class", ".jar", ".psd", ".ai", ".heic"}
EXCLUDED_ANY = {".git", "node_modules", "venv", ".venv", "__pycache__", "site-packages"}
EXCLUDED_ROOT = {".claude", ".codex"}
MAX_BYTES = 300 * 1024
GRAM = 8
SAMPLE_MASK = 3      # crc32 & 3 == 0 のものを残す（約1/4）
# ── 閾値（較正で決めた。docstring の「較正」参照） ──
JACCARD = {"prose": 0.7, "code": 0.9}
CONTAIN = {"prose": 0.8, "code": 0.95}
MIN_SKETCH = 50      # 包含の規則を使う最小の指紋数（正規化後およそ 200 字）
PIECE_CONTAIN = 0.8  # 合算包含で「1片の大部分が含まれる」とみなす率
try:  # テスト（打ち切りの確認）用に環境変数で縮められる
    TIME_BUDGET = float(os.environ.get("NEAR_DUP_TIME_BUDGET", "5"))
except ValueError:
    TIME_BUDGET = 5.0
CACHE_NAME = "near_dup_cache.pkl"
CACHE_VERSION = 2

_NONWORD = re.compile(r"[\W_]+", re.U)
_WS = re.compile(r"\s+", re.U)


def group_of(rel, head_bytes=None):
    """'code' / 'prose' / None（比較しない）。head_bytes を渡すとバイナリ判定もする。"""
    ext = os.path.splitext(rel)[1].lower()
    if ext in BINARY_EXTS:
        return None
    if head_bytes is not None and b"\0" in head_bytes[:8192]:
        return None
    return "code" if ext in CODE_EXTS else "prose"


def sketch_text(text, group):
    """正規化 → 8-gram → mod サンプリングした crc32 の frozenset。"""
    t = unicodedata.normalize("NFKC", text or "")
    t = _NONWORD.sub("", t) if group == "prose" else _WS.sub("", t)
    if len(t) < GRAM:
        return frozenset()
    grams = {t[i:i + GRAM] for i in range(len(t) - GRAM + 1)}
    return frozenset(h for h in (zlib.crc32(g.encode("utf-8")) for g in grams) if not h & SAMPLE_MASK)


def metrics(sa, sb):
    inter = len(sa & sb)
    small = min(len(sa), len(sb))
    union = len(sa) + len(sb) - inter
    return {"jaccard": inter / float(union) if union else 0.0,
            "contain": inter / float(small) if small else 0.0, "n_small": small, "inter": inter}


def decide(m, group):
    """指標 dict と群から「ほぼ同じ」かを決める（閾値はここだけで使う）。"""
    if not m or not m.get("inter"):
        return False
    return m["jaccard"] >= JACCARD[group] or (m["contain"] >= CONTAIN[group] and m["n_small"] >= MIN_SKETCH)


def compare(sa, sb, group):
    m = metrics(sa, sb)
    return decide(m, group), m


def covered_by_pieces(whole, pieces, group):
    """whole の CONTAIN 以上が、それぞれ大部分が whole に含まれる2つ以上の片で覆われるか。
    pieces: [(名前, 指紋)]。返り値: (覆った片の名前のリスト, 覆った率) または None。"""
    used, cov = [], set()
    for name, sp in pieces:
        if not sp:
            continue
        inter = whole & sp
        if len(inter) >= PIECE_CONTAIN * len(sp):
            used.append(name)
            cov |= inter
    if len(used) >= 2 and whole and len(cov) >= CONTAIN[group] * len(whole) and len(whole) >= MIN_SKETCH:
        return used, len(cov) / float(len(whole))
    return None


def _excluded(rel):
    parts = rel.replace("\\", "/").split("/")
    if parts and parts[0] in EXCLUDED_ROOT:
        return True
    return any(p in EXCLUDED_ANY for p in parts[:-1])


def _eligible(rel):
    return not _excluded(rel) and group_of(rel) is not None


def _git(root, args, timeout=10):
    try:
        p = subprocess.run(["git", "-C", root] + args, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            return None
        return p.stdout.decode("utf-8", "replace")
    except Exception:
        return None


def _git_root(path):
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and not os.path.isdir(d):
        nxt = os.path.dirname(d)
        if nxt == d:
            return None
        d = nxt
    out = _git(d, ["rev-parse", "--show-toplevel"]) if d else None
    return os.path.abspath(out.strip()) if out else None


def repo_files(root):
    """追跡ファイル＋未追跡（.gitignore 対象外）で、比較対象になりうるもの（相対パス）。"""
    out = _git(root, ["-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if out is None:
        return []
    return sorted({f for f in out.split("\0") if f and _eligible(f)})


def _fresh_time(full):
    st = os.stat(full)
    return max(st.st_mtime, st.st_ctime)


def changed_files(root, since_epoch):
    """このターンで作成・変更されたファイル（相対パス）。since_epoch が None なら作業ツリーの差分全部。"""
    rels = set()
    ents = (_git(root, ["-c", "core.quotepath=false", "status", "--porcelain", "-z", "-uall"]) or "").split("\0")
    i = 0
    while i < len(ents):
        e = ents[i]
        i += 1
        if len(e) < 4:
            continue
        if e[0] in "RC":
            i += 1  # -z のリネームは「新 NUL 旧」の順。旧を読み飛ばす
        if "D" in e[:2]:
            continue
        rels.add(e[3:])
    for p in (_git(root, ["-c", "core.quotepath=false", "diff", "--name-only", "HEAD"]) or "").splitlines():
        rels.add(p.strip())
    fresh = set()
    for r in rels:
        if not r or not _eligible(r):
            continue
        full = os.path.join(root, r)
        try:
            if not os.path.isfile(full):
                continue
            if since_epoch is not None and _fresh_time(full) < since_epoch - 1:
                continue
        except Exception:
            continue
        fresh.add(r)
    if since_epoch is not None:
        iso = datetime.fromtimestamp(since_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log = _git(root, ["-c", "core.quotepath=false", "log", "--since=" + iso,
                          "--name-only", "--diff-filter=AMRC", "--pretty=format:"]) or ""
        for p in log.splitlines():
            p = p.strip()
            if p and _eligible(p) and os.path.isfile(os.path.join(root, p)):
                fresh.add(p)
    return sorted(fresh)


class Index(object):
    """リポ内ファイルの指紋（(サイズ, mtime_ns) キーのキャッシュ付き）。"""

    def __init__(self, root):
        self.root = root
        self.dirty = False
        self.path = None
        gd = _git(root, ["rev-parse", "--absolute-git-dir"])
        if gd:
            self.path = os.path.join(gd.strip(), CACHE_NAME)
        self.data = {}
        try:
            with open(self.path, "rb") as f:
                obj = pickle.load(f)
            if obj.get("v") == CACHE_VERSION:
                self.data = obj.get("files") or {}
        except Exception:
            self.data = {}

    def stat(self, rel):
        try:
            st = os.stat(os.path.join(self.root, rel))
            return st.st_size, st.st_mtime_ns
        except Exception:
            return None

    def cached(self, rel):
        key = self.stat(rel)
        e = self.data.get(rel)
        return e if (e is not None and key is not None and e[0] == key) else None

    def get(self, rel):
        """(群, 指紋, 廃盤か) または None。"""
        e = self.cached(rel)
        if e is not None:
            return e[1]
        key = self.stat(rel)
        if key is None:
            return None
        val = None
        try:
            with open(os.path.join(self.root, rel), "rb") as f:
                raw = f.read(MAX_BYTES)
            grp = group_of(rel, raw)
            if grp:
                text = raw.decode("utf-8", "replace")
                val = (grp, sketch_text(text, grp), bool(mark_in_text(text)))
        except Exception:
            val = None
        self.data[rel] = (key, val)
        self.dirty = True
        return val

    def save(self, keep):
        if not self.dirty or not self.path:
            return
        try:
            files = dict((k, v) for k, v in self.data.items() if k in keep)
            tmp = self.path + ".tmp%d" % os.getpid()
            with open(tmp, "wb") as f:
                pickle.dump({"v": CACHE_VERSION, "files": files}, f, protocol=2)
            os.replace(tmp, self.path)
        except Exception:
            pass


def find_pairs(root, targets, deadline):
    """targets（相対パス）それぞれについて、同じ群の生きた他ファイルでほぼ同じものを探す。
    戻り値: (発見のリスト [(a, b, 指標)], 見られなかったファイル数)"""
    cand = repo_files(root)
    live = set(cand)
    idx = Index(root)
    tg = []
    for a in targets:
        if a not in live:
            continue  # .gitignore 済み（生成物を追跡から外した）など、リポに属さないものは対象外
        v = idx.get(a)
        if v and v[1] and not v[2]:
            tg.append((a, v))
    if not tg:
        idx.save(live)
        return [], 0
    sizes = [idx.stat(a)[0] for a, _v in tg]

    def prio(rel):
        st = idx.stat(rel)
        if st is None:
            return (2, 0)
        near = min(abs(st[0] - s) / float(max(s, 1)) for s in sizes)
        return (0 if idx.cached(rel) is not None else (1 if near <= 0.5 else 2), near)

    others = sorted((r for r in cand), key=prio)
    found, seen, skipped = [], set(), 0
    tnames = set(a for a, _v in tg)
    loaded = {}
    for n, b in enumerate(others):
        if time.time() > deadline:
            skipped = len(others) - n
            break
        vb = idx.get(b)
        if not vb or not vb[1] or vb[2]:
            continue
        loaded[b] = vb
        for a, va in tg:
            if a == b or va[0] != vb[0] or (b, a) in seen:
                continue
            seen.add((a, b))
            near, m = compare(va[1], vb[1], va[0])
            if near:
                found.append((a, b, m))
    # 合算包含: 分割片（どちらの向きも）
    if not skipped:
        pairs_done = set((a, b) for a, b, _m in found) | set((b, a) for a, b, _m in found)
        for a, va in tg:
            pieces = [(b, vb[1]) for b, vb in loaded.items() if b != a and vb[0] == va[0]]
            r = covered_by_pieces(va[1], pieces, va[0])  # a（変更）が既存の複数片で覆われる
            if r and not all((a, p) in pairs_done for p in r[0]):
                found.append((a, " + ".join(r[0]), {"jaccard": 0.0, "contain": r[1], "pieces": len(r[0])}))
        for b, vb in loaded.items():
            if b in tnames:
                continue
            pieces = [(a, va[1]) for a, va in tg if va[0] == vb[0]]
            r = covered_by_pieces(vb[1], pieces, vb[0])  # 既存の b が、このターンの複数片で覆われる
            if r and not all((p, b) in pairs_done for p in r[0]):
                found.append((" + ".join(r[0]), b, {"jaccard": 0.0, "contain": r[1], "pieces": len(r[0])}))
    idx.save(live)
    return found, skipped


def _emit(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=True).encode("ascii"))
    sys.stdout.buffer.flush()


def _parse_ts(s):
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def _rows_backward(path, block=1 << 20):
    """トランスクリプトの行を末尾から順に返す（ファイル全体を一度に読まない）。"""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        rest = b""
        while pos > 0:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + rest
            lines = buf.split(b"\n")
            rest = lines[0]
            for ln in reversed(lines[1:]):
                if ln.strip():
                    yield ln
        if rest.strip():
            yield rest


def read_turn(transcript_path):
    """(ターン開始時刻 epoch, このターンのツール呼び出し [(name, input)])。
    末尾から最後の依頼者の発言まで遡る（行数の上限なし）。読めなければ (None, [])。"""
    calls = []
    try:
        for ln in _rows_backward(transcript_path):
            try:
                r = json.loads(ln.decode("utf-8", "replace"))
            except Exception:
                continue
            if _genuine_user_text(r):
                return _parse_ts(r.get("timestamp") or ""), list(reversed(calls))
            if r.get("type") == "assistant":
                for b in reversed((r.get("message") or {}).get("content") or []):
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        calls.append((b.get("name"), b.get("input") or {}))
    except Exception:
        pass
    return None, list(reversed(calls))


# ---- 1つの文書の中の「同じ対象を並べた表」の重複（2026-10-02 依頼者指摘） ----
# WHY: 要レビュー一覧（Soulful-Content/_meta/REVIEW_REQUIRED_FILES_20260918.md）に、同じ記事を行に並べた表が
#   2つ（§0「生きている原稿の一覧」記事|題名|状態 と「一覧表. ドラフト31本」記事|タイトル|最初の1文|重要メッセージ）
#   あり、更新のたびに片方だけ直す・読み手が同じ情報を2度読む、が起きた。依頼者「似たような表を複数作るのは
#   やめて。リポを限定せず、レポート全般に」。ファイル単位の重複（上）と同じクラスを、表の単位で塞ぐ。
# 不変条件: 1つの .md の中に、同じ対象（行の見出しの値）を5件以上・小さい方の60%以上で共有する表を2つ置かない。
#   列名・列の数・行の順・リンクの有無が違っても、行の見出しが同じ対象なら重複とみなす（列を足して1表にする）。
#   見出しの列は固定しない（どの列でもよい）。値の種類が少ない列（判定・○×など）は見出しとみなさない。
# 例外: 表の直前の行に <!-- dup-table-ok: 理由（10字以上） --> を書いた表は比べない（理由が無ければ無効）。
# 止めるのは悪化したターンだけ（table_findings の docstring）。前からある重複は systemMessage で知らせる。
# 較正（2026-10-02, tests/calibrate_duplicate_tables.py。48リポの直近30日・各最大50コミット）:
#   止めたコミット 35/2,239（1.56%）。うち13件が狙った実例（要レビュー一覧の2つの表。2026-09-18 から
#   10回の更新すべてで止まっていた）、ほかに BOOK12_TASKS の §1 と §4 の表（記事ID と「回」が両方にある）、
#   book_summary/tasks.md、同じカメラ仕様の2表、など。灰色は happiness-system/DAILY_UPDATES.md の日次ログ
#   7件（日ごとの表に同じファイルが並ぶ。スクリプトの自動生成で Claude のターン外なので Stop は動かない）。
#   HEAD の表を含む .md 1,800本のうち重複の表あり 115本（6.39%＝既存の負債。触っても悪化しなければ止めない）。
# 攻撃検証（2026-10-02, Sonnet。scratchpad の attack_tables.py。依頼者「Fable はほぼ使わない」により Sonnet）:
#   初版は見逃し 15/17（2列の表を列数だけで外していた・短い値を比べていなかった）→ 直して 4/17、誤検知 0/11。
#   残る穴: HTML の <table>、行と列を入れ替えた表、5行未満の重複（5→3 にすると誤検知が 1/11、負債が 6.3%→10.7% に増える）。
DUP_MIN_SHARED = 5
DUP_RATIO = 0.6
DUP_OK = re.compile(r"<!--\s*dup-table-ok\s*[:：]\s*(.{10,}?)\s*-->")
_TBL_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)[^)]*\)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_NUMERIC = re.compile(r"^[\d.,]+(?:[a-z%万億円件人年月日倍点]{0,3})$")


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _cell_keys(cell):
    """セルを比べるための値。リンクは表示文字列と、リンク先の最後の部分の両方。"""
    out = set()
    for txt, url in _LINK.findall(cell):
        for v in (txt, url.rstrip("/").split("/")[-1].split("#")[0]):
            v = _NONWORD.sub("", unicodedata.normalize("NFKC", v).lower())
            if len(v) >= 3:
                out.add(v)
    plain = _NONWORD.sub("", unicodedata.normalize("NFKC", _LINK.sub(r"\1", cell)).lower())
    if len(plain) >= 3:
        out.add(plain)
    return out


def md_tables(text):
    """[(開始行番号1始まり, 見出し行, [行のセル並び], 例外の理由, 表の中身の crc32)]。コードブロックの中は見ない。"""
    lines = text.splitlines()
    out, i, fence = [], 0, False
    while i < len(lines):
        if _FENCE.match(lines[i]):
            fence = not fence
            i += 1
            continue
        if (not fence and "|" in lines[i] and i + 1 < len(lines) and _TBL_SEP.match(lines[i + 1])):
            head = _cells(lines[i])
            j, rows = i + 2, []
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_cells(lines[j]))
                j += 1
            k = i - 1
            while k >= 0 and not lines[k].strip():
                k -= 1
            m = DUP_OK.search(lines[k]) if k >= 0 else None
            sig = zlib.crc32(chr(10).join(x.strip() for x in lines[i:j]).encode("utf-8"))
            out.append((i + 1, head, rows, m.group(1) if m else None, sig))
            i = j
            continue
        i += 1
    return out


def _key_columns(rows):
    """見出しになり得る列 = 値が5種以上で、行の8割以上が互いに違う列。[(列番号, {行番号: 値の集合})]。"""
    ncol = max((len(r) for r in rows), default=0)
    cols = []
    for c in range(ncol):
        vals = {n: _cell_keys(r[c]) for n, r in enumerate(rows) if c < len(r)}
        vals = {n: v for n, v in vals.items() if v and not all(_NUMERIC.match(k) for k in v)}
        distinct = {frozenset(v) for v in vals.values()}
        if len(distinct) >= DUP_MIN_SHARED and len(distinct) >= 0.8 * len(vals):
            cols.append((c, vals))
    return cols


def _match(a, b):
    """セルどうしが同じ対象か: 値のどれかが一致、または短い方（4字以上）が長い方（40字以下）に含まれる。
    長い方の上限は、説明文のセル（「nt-007 の見出し…／nt-010 の…」）が中の ID で見出しの列に一致するのを防ぐため。"""
    for x in a:
        for y in b:
            if x == y:
                return True
            s, l = (x, y) if len(x) <= len(y) else (y, x)
            if len(s) >= 4 and len(l) <= 40 and s in l:
                return True
    return False


def _norm_cell(cell):
    return _NONWORD.sub("", unicodedata.normalize("NFKC", _LINK.sub(r"", cell)).lower())


def _similar(x, y):
    """見出し以外のセルが同じ情報か（片方だけ直して古くなった版も拾うため、完全一致でなく文字2-gramの重なり）。"""
    if not x or not y:
        return False
    if x == y:
        return True
    if min(len(x), len(y)) < 8 or _NUMERIC.match(x) or _NUMERIC.match(y):
        return False  # 短い値・数字は完全一致だけ（200万円/300万円、1962/1912 を同じとみなさない）
    ga = {x[k:k + 2] for k in range(len(x) - 1)}
    gb = {y[k:k + 2] for k in range(len(y) - 1)}
    return len(ga & gb) / float(len(ga | gb)) >= 0.6


def _shared_info(rows_a, rows_b, pairs, ka, kb):
    """対応する行で、見出し以外の列に同じ情報（同じ値）が入っている列の組があるか。半分以上の行で似ていれば有り。"""
    na = max((len(r) for r in rows_a), default=0)
    nb = max((len(r) for r in rows_b), default=0)
    for i in range(na):
        if i == ka:
            continue
        for j in range(nb):
            if j == kb:
                continue
            vals = [(_norm_cell(rows_a[x][i]) if i < len(rows_a[x]) else "",
                     _norm_cell(rows_b[y][j]) if j < len(rows_b[y]) else "") for x, y in pairs]
            vals = [(u, v) for u, v in vals if u and v]
            sim = sum(1 for u, v in vals if _similar(u, v))
            if sim >= DUP_MIN_SHARED and sim >= 0.6 * len(vals):
                return True
    return False


def duplicate_tables(text):
    """同じ対象の同じ情報を並べた表の組 [(行A, 行B, 共有数, 小さい方の行数)]。
    条件: ①見出しの列どうしで、同じ対象が5件以上・小さい方の60%以上 ②その対象の行で、見出し以外にも
    同じ情報の列がある（＝同じ値が2か所にあり、片方だけ直すと食い違う）。②が無い表（同じ項目名で別の対象を
    説明する仕様の表、同じ対象の別の指標の表）は重複に数えない。"""
    return [h[:4] for h in _dup_pairs(text)]


GENERIC_KEY_HEAD = {"項目", "項", "内容", "属性", "要素", "パラメータ", "パラメーター", "設定", "指標", "条件", "仕様",
                    "軸", "観点", "区分", "item", "field", "property", "key", "attribute", "parameter", "name"}


def _generic_head(head):
    """「項目|内容」の形（1行＝1属性で、別々の物を同じ項目名で説明する表）か。見出し列の列名で判定する。"""
    return bool(head) and _NONWORD.sub("", unicodedata.normalize("NFKC", head[0]).lower()) in GENERIC_KEY_HEAD


def _dup_pairs(text):
    """duplicate_tables の中身。各組に (行A, 行B, 共有数, 小さい方, 表Aの crc32, 表Bの crc32)。
    2列だけの表どうしで、見出しの列名が「項目」「条件」等の汎用語の組（1行＝1属性で、別々の製品・人物を
    同じ項目名で説明する表）は比べない（2026-10-02 攻撃検証で、列数だけで外すと2列の一覧表の重複を12件見逃した）。"""
    tbls = [t for t in md_tables(text) if not t[3]]
    keyed = [(t[0], t[2], _key_columns(t[2]), t[4], max((len(r) for r in t[2]), default=0)) for t in tbls]
    out = []
    for x in range(len(keyed)):
        for y in range(x + 1, len(keyed)):
            la, ra, ca, sa, wa = keyed[x]
            lb, rb, cb, sb, wb = keyed[y]
            if wa <= 2 and wb <= 2 and _generic_head(tbls[x][1]) and _generic_head(tbls[y][1]):
                continue
            best = None
            for ka, va in ca:
                for kb, vb in cb:
                    pairs = []
                    for na, a in va.items():
                        nb = next((n for n, b in vb.items() if _match(a, b)), None)
                        if nb is not None:
                            pairs.append((na, nb))
                    small = min(len(va), len(vb))
                    if (len(pairs) >= DUP_MIN_SHARED and len(pairs) >= DUP_RATIO * small
                            and (not best or len(pairs) > best[2]) and _shared_info(ra, rb, pairs, ka, kb)):
                        best = (la, lb, len(pairs), small, sa, sb)
            if best:
                out.append(best)
    return out


def table_findings(text, head_text):
    """(止める組, 知らせるだけの組)。止めるのは、このターンで悪化したときだけ:
    ①ファイルが新しい（HEAD に無い） ②重複の組が HEAD より増えた ③重複の組のどちらかの表を、このターンで
    変えた（片方の表だけ直して食い違う、が起きる場面そのもの）。HEAD から変わらない古い重複は知らせるだけ
    （1行直すために長い文書の表の統合を強いない。既存の負債 2.3% のファイルを触るたびに止めると形骸化する）。"""
    cur = _dup_pairs(text)
    if not cur:
        return [], []
    if head_text is None:
        return [c[:4] for c in cur], []
    head_sigs = {t[4] for t in md_tables(head_text)}
    if len(cur) > len(_dup_pairs(head_text)) or any(c[4] not in head_sigs or c[5] not in head_sigs for c in cur):
        return [c[:4] for c in cur], []
    return [], [c[:4] for c in cur]


def _fmt_tables(hits):
    lines = []
    for path, la, lb, shared, small in hits[:8]:
        lines.append("  - %s: %d行目の表と %d行目の表が同じ対象を %d件共有（小さい方 %d件）" % (path, la, lb, shared, small))
    if len(hits) > 8:
        lines.append("  ほか %d 組" % (len(hits) - 8))
    return "\n".join(lines)


TABLE_RESOLVE = (
    "解消法: 2つの表を1つにまとめる（列を足す）。消す側の表の列で必要なものは残す表へ移し、"
    "消す側は削除する。本当に別物（例: 期間の違う集計）なら、片方の表の直前の行に "
    "<!-- dup-table-ok: 理由（10字以上） --> を書く。")


def _fmt_pairs(root_pairs):
    lines = []
    for a, b, m in root_pairs[:8]:
        if m.get("pieces"):
            what = "%d片の合算で %.0f%% を覆う" % (m["pieces"], 100 * m.get("contain", 0))
        else:
            what = "全体の一致 %.0f%%／小さい方の包含 %.0f%%" % (100 * m.get("jaccard", 0), 100 * m.get("contain", 0))
        lines.append("  - %s\n    %s\n    （%s）" % (a, b, what))
    if len(root_pairs) > 8:
        lines.append("  ほか %d 組" % (len(root_pairs) - 8))
    return "\n".join(lines)


RESOLVE = (
    "解消法（どれか1つ）:\n"
    "  1. 片方を正にして、もう一方を削除する（版は git の履歴で持つ）\n"
    "  2. 古い方の本文1行目（front matter の直後）に「⛔ 廃盤（YYYY-MM-DD の形の日付）: 理由。後継: <正のファイル>」を書く\n"
    "  3. 生成物ならコミットせず必要時に生成する（.gitignore に入れて追跡を外す）")


def on_stop(ev):
    if ev.get("stop_hook_active"):
        return
    deadline = time.time() + TIME_BUDGET
    since, calls = (None, [])
    if ev.get("transcript_path"):
        since, calls = read_turn(ev["transcript_path"])
    cwd = ev.get("cwd") or os.getcwd()
    paths = set()
    try:
        paths = set(_touched_files(calls, cwd))
    except Exception:
        pass
    roots = []
    for p in [cwd] + sorted(paths):
        r = _git_root(p)
        if r and r not in roots:
            roots.append(r)
    found, cut, tbl_block, tbl_warn = [], [], [], []
    for root in roots:
        if time.time() > deadline:
            cut.append((root, -1))
            continue
        targets = changed_files(root, since)
        if not targets:
            continue
        for rel in targets:
            if os.path.splitext(rel)[1].lower() not in (".md", ".markdown"):
                continue
            try:
                with io.open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except Exception:
                continue
            if mark_in_text(text) or "|" not in text:
                continue
            head = _git(root, ["show", "HEAD:" + rel.replace("\\", "/")])
            b, w = table_findings(text, head)
            tbl_block += [(os.path.join(root, rel),) + x for x in b]
            tbl_warn += [(os.path.join(root, rel),) + x for x in w]
        pairs, skipped = find_pairs(root, targets, deadline)
        found += [(os.path.join(root, a), os.path.join(root, b), m) for a, b, m in pairs]
        if skipped:
            cut.append((root, skipped))
    note = ""
    if cut:
        note = "near_duplicate_guard: %g秒を超えたので比較を打ち切った（%s）。残りは次のターンにキャッシュ付きで見る。" % (
            TIME_BUDGET, "、".join("%s 残り%s" % (r, ("%dファイル" % n) if n >= 0 else "全部") for r, n in cut))
        sys.stderr.buffer.write((note + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
    if tbl_block:
        _record_firing("near_duplicate_guard", ev)
        _emit({"decision": "block", "reason": (
            "【同じ対象・同じ情報の表が1つの文書に2つ】このターンで作成・変更した文書に、同じ対象を行に並べ、"
            "同じ値を持つ表が2つ以上ある。直すたびに片方しか直らず、読み手は同じ情報を2度読む"
            "（2026-10-02 依頼者指摘。要レビュー一覧の「生きている原稿の一覧」と「一覧表」の実例）。\n"
            + _fmt_tables(tbl_block) + "\n" + TABLE_RESOLVE)})
        return
    if found:
        _record_firing("near_duplicate_guard", ev)
        _emit({"decision": "block", "reason": (
            "【ほぼ同じファイルの併存】このターンで作成・変更したファイルと、ほぼ同じ内容の生きたファイルが"
            "同じリポにある。版管理せずに2つ置くと、修正のたびに片方しか直らない"
            "（2026-09-30 依頼者指摘。nt-040 の原稿と投稿用、計画書 v1/v2 の実例）。\n"
            + _fmt_pairs(found) + "\n" + RESOLVE + (("\n" + note) if note else ""))})
    elif tbl_warn:
        _emit({"systemMessage": "⚠ near_duplicate_guard: このターンで触った文書に、前からある重複の表がある"
               "（このターンでは悪化していないので止めない）。1つの表にまとめることを勧める。\n"
               + _fmt_tables(tbl_warn)})
    elif cut:
        # 黙って通さない: 見られなかったことを利用者に見える形で知らせる（止めはしない）
        _record_firing("near_duplicate_guard", ev)
        _emit({"systemMessage": "⚠ " + note + " このターンで作成・変更したファイルに、ほぼ同じ内容の"
               "ファイルが無いことは確認できていない。"})


def on_pre_tool(ev):
    if ev.get("tool_name") != "Write":
        return
    ti = ev.get("tool_input") or {}
    fp = ti.get("file_path") or ""
    if not fp:
        return
    if not os.path.isabs(fp):
        fp = os.path.join(ev.get("cwd") or os.getcwd(), fp)
    if os.path.exists(fp):
        return  # 上書きは Stop が見る
    content = ti.get("content") or ""
    root = _git_root(fp)
    if not root:
        return
    rel_new = os.path.relpath(fp, root).replace("\\", "/")
    grp = group_of(rel_new, content[:8192].encode("utf-8", "replace"))
    if _excluded(rel_new) or not grp or mark_in_text(content):
        return
    sn = sketch_text(content.encode("utf-8", "replace")[:MAX_BYTES].decode("utf-8", "ignore"), grp)
    if not sn:
        return
    deadline = time.time() + TIME_BUDGET
    idx = Index(root)
    cand = repo_files(root)
    hits, skipped = [], 0
    for n, rel in enumerate(cand):
        if time.time() > deadline:
            skipped = len(cand) - n
            break
        v = idx.get(rel)
        if not v or v[0] != grp or v[2] or not v[1]:
            continue
        near, m = compare(sn, v[1], grp)
        if near:
            hits.append((rel_new, rel, m))
    idx.save(set(cand))
    if not hits:
        return
    _record_firing("near_duplicate_guard", ev)
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": (
        "⚠ これから作るファイルは、既存の生きたファイルとほぼ同じ内容です。このまま両方を残すと"
        "ターン終了時に near_duplicate_guard が止めます。\n" + _fmt_pairs(hits) + "\n" + RESOLVE)}})


def _registered_local_copy_exists():
    """別のリポ内コピーが存在し、かつそのリポの settings に登録されているときだけ True。"""
    try:
        me = os.path.abspath(__file__)
        base = os.path.basename(__file__)
        local = os.path.abspath(os.path.join((os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()), ".claude", "hooks", base))
        if os.path.normcase(me) == os.path.normcase(local) or not os.path.exists(local):
            return False
        for name in ("settings.json", "settings.local.json"):
            try:
                with open(os.path.join(os.getcwd(), ".claude", name), encoding="utf-8-sig") as f:
                    if base in f.read():
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def main():
    if _registered_local_copy_exists():
        return
    try:
        ev = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    try:
        name = ev.get("hook_event_name")
        if name == "Stop" or (name is None and "stop_hook_active" in ev and "tool_name" not in ev):
            on_stop(ev)
        elif name in ("PreToolUse", None) and ev.get("tool_name"):
            on_pre_tool(ev)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
