# streamlit-sales-dashboard — Claude Code 運用ルール

<!-- HARD_RULES_START v1 -->
## ⛔ 絶対ルール Top10（毎回、回答を書く前にこの10項目に違反しないか確認する）

1. **ブランチ**: main へ直接コミット。ブランチ作成はユーザーの明示指示時のみ。作成したら「main へマージ → ブランチ削除 → push」までが完了条件。**ブランチに成果物を残したまま回答を終えることは禁止**。
2. **成果物報告**: ファイルを1つでも作成/更新/push したら、**3列表（成果物/説明/リンク）**で報告。URL は push 完了後に Contents API で存在確認（200）してから提示。未 push ファイルの URL 生成禁止。
3. **保存先**: 成果物・スクリプト・中間ファイルはすべて本リポ内。**Desktop 等リポ外への生成禁止**。使い捨てデバッグファイルは OS の temp へ。リポ内に実行ログ・コミットメッセージ用一時ファイルを作らない。
4. **ファイル名**: レポート系は `<TOPIC>_YYYYMMDD.md`（ハイフンなし）。同日再更新は `-v2`/`-v3`。本文中の日付は `YYYY-MM-DD`。README/CLAUDE.md/tasks.md/CURRENT_* は日付なし。
5. **開発者表記**: 本文中の人名は「**男座員也 / Kazuya Oza**」。`KazuyaMurayama` は URL・ID 等のシステム識別子のみ。「Murayama/村山」を表記名にしない。
6. **事前確認しない**: 即実行→事後報告（「〜してもよいですか?」を出さない）。例外は main/master への force push と repo 削除のみ。
7. **検証してから完了宣言**: 完了・修正済みと言う前に検証コマンドを実行し出力を確認する（テスト・URL 200・`git status`）。推測で「動くはず」と言わない。
8. **QC/レビュー時のスキル起動**: 品質チェック・レビュー・共有前は `sp-verification-before-completion` と `analysis-qa-checklist` の SKILL.md を読んでから実施。
9. **一次資料主義／推論による捏造の禁止**: 決定に効く数値・事実は実ファイル・実 URL・実行結果から引く。記憶・過去の要約だけで断言しない。**確認していないことを確認したかのように書かない**——選択肢は「①調べる ②調べられないなら『未確認』と明示する」の2つだけ。ファイル存在・中身・関数名・設定値の意味・ディレクトリ構成・ブランチ名・リモート状態・実行結果・件数は**必ず実コマンドで取得**する（「〜のはず」禁止）。挙動は自作の再現ロジックでなく**本体を import／実行**して確認し、**無反応を正常と解釈しない**。→ 詳細表は FACT-GROUNDING ブロック。
10. **回答末尾に「Next Action:」** を必ず付す。

> 優先順位: ユーザーの直接指示 > 本ブロック > 本文各節。詳細・背景は本文の対応セクションを参照。
> 機械ガード: `.claude/hooks/`（Desktop 書き込み拒否・終了時ブランチ/未pushチェック・push 後の報告リマインド）が本ブロックの 1,2,3,7 を自動検査する。
<!-- HARD_RULES_END -->

<!-- FACT-GROUNDING:BEGIN v1 -->
## ⛔ 事実確認の絶対原則（推論による捏造の禁止 / 2026-08-11 ユーザー指示）

**リポジトリ・ファイル・設定・実行結果について、「確認していないこと」を確認したかのように書かない。**
分からない場合は、①調べる ②調べられないなら「未確認」と明示する。この2つ以外の選択肢はない。
推論・一般論・「たぶんこうなっているはず」で埋めることを**禁止**する。

### F1. 確認せずに書いてはいけない対象（＝必ず実コマンドで取得する）

| 対象 | 禁止 | 必須の確認コマンド |
|---|---|---|
| ファイルの存在・パス | 「〜にあるはず」 | `ls` / `Glob` / `Read` |
| ファイルの中身・行番号 | 記憶・要約からの引用 | `Read` / `Grep`（実際に読む） |
| 関数名・変数名・シグネチャ | 「たぶん `_load_cfg`」 | `Grep -n "^def "` で実名を取得 |
| 設定値の意味・記法 | 「include はグロブだろう」 | **実装コードを読む**（仕様の推測禁止） |
| リポの構成・ディレクトリ | 「docs/ があるはず」 | `ls` / `Glob` で実在確認 |
| ブランチ名 | 「main だろう」 | `git rev-parse --abbrev-ref HEAD` |
| リモートの状態 | 「push できているはず」 | `git ls-tree origin/<branch> -- <path>` |
| テスト・処理の結果 | 「通るはず」「N件のはず」 | 実行して**出力を貼る** |
| 件数・統計 | 概算・目分量 | 実際に数えるスクリプトを走らせる |

### F2. 「動くはず」を禁じる — 挙動は必ず実物で確認する

仕様・挙動を述べる前に、**その通りに動くことを実際に走らせて確認**する。
- 自作の再現ロジックで検証しない。**本体を import / 実行**して確かめる。
  （2026-08-04 実例: `include` の照合を `fnmatch` で自作再現して検証し、
  本体が接頭辞一致だったため**全パターン不一致**の設定を「検証済み」と誤報告した。
  本体の `_in_scope()` を import した瞬間に判明。）
- 「無反応＝正常」と解釈しない。**無反応は故障と区別がつかない**。
  発火する条件を1つ作って**実際に発火させ**、初めて「動いている」と言える。
  （同日実例: hook が黙っていたのを「正常」と誤読。実際は payload 形式違いで
  早期 return しており、検査は一度も走っていなかった。）

### F3. 推測が混じったときの表記義務

確認できたことと、できていないことを**文中で分離**する。混ぜて書かない。
- 確認済み: 実コマンド・実出力を根拠として示す（可能なら数値・SHA・件数）。
- 未確認: 「**未確認**」と明記する。断定形で書かない。
- 確認不能: 何を試して、どこで詰まったかを1行で書く（§11.2 と同じ扱い）。

### F4. 自己申告を証拠にしない

スクリプトの「N件更新しました」等の**自己申告は証拠ではない**。
必ず**対象そのもの**を読み直して確認する（リモートの実バイト / 実ファイル / 実出力）。

### F5. 一度でも間違えた対象は、次回も必ず再確認する

「さっき確認したから同じはず」は F1 違反。ファイル・設定は編集で変わる。
特に**自分が直前に編集した対象**の状態は、記憶ではなく再取得で確認する。

> 本ブロックは §9（一次資料主義）の具体化である。§9 が抽象的で再発が止まらなかったため、
> 「どの対象を・どのコマンドで確認するか」まで降ろした。抽象原則ではなく本表に従うこと。
<!-- FACT-GROUNDING:END -->

Streamlit で構築したリアルタイム売上・営業 KPI 管理ダッシュボード。売上推移・目標達成率・顧客別分析・担当者別実績をインタラクティブに可視化。

> **本ファイルは VSCode版 / Web版 Claude Code（claude.ai）の両方で、本リポジトリの単独完結ガイドです。**
> Web版はグローバル `~/.claude/CLAUDE.md` を参照しません。本リポの運用に必要な全ルールをこの1ファイルに集約しています（他リポ・グローバルとの重複は完結性のため許容）。

---

## 1. セッション開始手順（毎回・最初に実行）

セッション開始時、次の順で必ず読み込んでから作業を始める：

1. **本ファイル（CLAUDE.md）** — 前提制約・実行ルール
2. **`tasks.md`** — セッション間引継ぎタスク（次にやること・優先順位）
3. **`FILE_INDEX.md`** — ファイル構成の索引

> 編集前に、ユーザー発話のキーワードを `FILE_INDEX.md` と照合してから対象ファイルを特定する（推測で着手しない）。

---

## 2. プロジェクト概要

### 主要ファイル
| ファイル | 役割 |
|---|---|
| `my_dashboard.py` | Streamlit アプリ本体 |
| `sales_data.csv` | 基本売上データ |
| `sales_data_extended.csv` | 拡張売上データ |
| `requirements.txt` | Python 依存ライブラリ |

### 起動コマンド
```bash
pip install -r requirements.txt
streamlit run my_dashboard.py
```

### 関連リポジトリ
| リポ | 役割 |
|---|---|
| [KazuyaMurayama/MachineLearning_App](https://github.com/KazuyaMurayama/MachineLearning_App) | 機械学習予測アプリ（姉妹アプリ） |
| [KazuyaMurayama/customer_segment_analysis](https://github.com/KazuyaMurayama/customer_segment_analysis) | 顧客セグメント分析 |
| [KazuyaMurayama/freelance-sales-pipeline](https://github.com/KazuyaMurayama/freelance-sales-pipeline) | 営業パイプライン |

---

## 3. 開発者情報・命名ルール

| 種別 | 表記 | 用途 |
|---|---|---|
| **システム識別子（変更不可）** | `KazuyaMurayama` | GitHub ユーザー名 / URL / `@KazuyaMurayama` |
| **システム識別子（変更不可）** | `kazuya.murayama.21@gmail.com` | git `user.email` / 連絡先 |
| **表記名（人間として記載する場合）** | **男座員也（Kazuya Oza / おざ かずや）** | ドキュメント本文の著者名 / コミット message 中の自己言及 |

- ドキュメント本文等で開発者名を**人間として**記載する際は **男座員也 / Kazuya Oza** を使用。
- 「Murayama」「村山」「Otokoza」「おとこざ」を**表記名**として誤用しない（システム識別子 `KazuyaMurayama` の出現は許容）。

---

## 4. ツール実行ルール

- **確認不要・即実行**。「Allow〜?」「Should I…?」等の事前確認文を出力しない。即実行 → 事後報告。
- 長時間処理は積極的にバックグラウンド実行する。
- ファイル操作（編集・検索・読み込み）は専用ツール（Edit/Write/Read/Grep/Glob）を直接使用する。
- **例外（事前確認必須）**: main への `git push --force`、`gh repo delete`、その他の不可逆・破壊的操作。

---

## 5. ブランチ管理

- **既定: main へ直接コミット**。ブランチ作成はユーザーが明示指示した場合のみ。
- ブランチを作成した場合、回答完了前に必ず `main` へマージ → ブランチ削除 → push まで完了させる。
  - 手順: `git checkout main; git pull; git merge <branch> --no-ff; git push origin main; git branch -d <branch>`
- 「完了 = main にマージ済み＆push済み」。ブランチにファイルを残したまま回答を終えない。

<!-- BRANCH_CLEANUP_START -->
### ブランチ整理スキル（自主起動）
- 次を **検知** したら、ユーザー指示が無くても **必ず** `.claude/skills/branch-cleanup/SKILL.md` を読んで起動する：`git branch -a` / `git ls-remote --heads origin` で **main 以外のブランチが残存** している／ユーザーが「ブランチ削除・整理・main に集約」を依頼した／自分が作ったブランチを完了前に放置しようとしている。
- **Web版 Claude Code（claude.ai/code）でもブランチ削除は実行可能**。「環境の制約でできない／ユーザー自身で対応を」とは回答しない。3段階で試す：① `git push origin --delete <branch>` → ② 拒否なら REST API 直接 DELETE（`gh api -X DELETE` / token curl）→ ③ それも不可な環境のみ Actions ワークフローでフォールバック（使用後は削除してリポを汚さない）。
- 手順全文・コマンド・フォールバック YAML は `.claude/skills/branch-cleanup/SKILL.md` に集約（本ファイルを肥大化させない）。
<!-- BRANCH_CLEANUP_END -->

---

## 6. ファイル保存ルール

- 生成物・スクリプト・中間ファイルはすべて**本リポジトリ内**に保存する。
- `C:\Users\user\Desktop` への出力は禁止（ユーザーが明示した場合のみ例外）。
- 一時スクリプトも本リポ内に作成し、作業後に削除またはコミットする。

---

## 7. 成果物報告ルール（毎回必須）

ファイルを1つでも作成・更新・push したら、**すべての**成果物を次の3列表で報告する。例外なし。

| 成果物 | 説明 | リンク |
|---|---|---|
| file.py | 1行説明 | [開く](https://github.com/KazuyaMurayama/streamlit-sales-dashboard/blob/main/path/to/file.py) |

**厳守事項**
1. 必ず Markdownリンク `[表示名](URL)` 形式。plain text URL 禁止。
2. `/blob/<実ブランチ>/<実パス>` 形式。リポトップ URL 禁止。
3. **報告前に URL 存在確認**: `gh api repos/KazuyaMurayama/streamlit-sales-dashboard/contents/PATH?ref=main` でステータス200を確認。
4. ブランチ名は推測せず `git rev-parse --abbrev-ref HEAD` で実値取得。
5. **push 完了後にのみ URL 生成**。未push ファイルは絶対パス＋「（ローカル）」と明記。
6. 404 を出したら即訂正版を提示し、原因を1行報告。

---

## 8. ドキュメント命名・日付ルール（v2.0 / 2026-06-03 改訂）

### ファイル名
- 基本形 `<TOPIC>_YYYYMMDD.md`（**サフィックス・ハイフンなし**）。例: `KPI_ANALYSIS_20260603.md`
- 同日中の追加更新は `-v2`、`-v3`（例: `KPI_ANALYSIS_20260603-v2.md`）。
- 日付が変わったら v サフィックスをリセット。

### 表記の区別
- **ファイル名**: ハイフン**なし** `YYYYMMDD`。
- **本文中の日付**: ハイフン**あり** `YYYY-MM-DD`。

### H1直下の日付メタデータ
レポート系 .md 新規作成時は H1直下に必ず記載し、更新時は **最終更新日のみ** 当日付に書き換える（作成日は固定）：
```
作成日: YYYY-MM-DD
最終更新日: YYYY-MM-DD
```

### 対象外（日付サフィックスを入れない）
README / CLAUDE.md / FILE_INDEX / tasks.md / CHANGELOG / LICENSE / SPEC.md / `CURRENT_*.md` / パイプライン自動生成ファイル。
- **追記型の単一集約ログ**（`*-log.md` 等、日付で分割せず単一ファイルに追記していく台帳）
- **継続更新型の設計文書**（`ALTERNATIVES.md` / `PROCESS.md` / `QUALITY.md` / `SKILLS.md` 等、旧版を別ファイルで残さないもの）

> 💡 **原則**: 日付サフィックスは「**その日時点の成果物として凍結し、後日の版と併存させる**」ことを表す。更新し続けるファイルには付けない（グローバル §10b と同一）。

### 旧形式（廃止・新規禁止）
- ❌ `2026-06-03_<TOPIC>.md` / ❌ `<TOPIC>_2026-06-03.md`
- ✅ `<TOPIC>_20260603.md`（現行ルール）

---

## 9. モデル使い分け（v2 / 2026-07-13 改訂・Fable 消費最小化）

- **メインは Sonnet**（`settings.json` の `model` に従う。現 `sonnet[1m]`）。日常の対話・調査・実装・**計画のためのドラフト/事前調査**・定型作業はすべて Sonnet が担当し、Fable の消費を抑える。
- **Fable（`claude-fable-5`）は要所のみ明示的に使う**：①方針策定 ②計画の骨子づくり ③最終チェック（QC/レビュー）。この3場面だけ、サブエージェント起動または `/model` での一時切替で Fable を呼ぶ。それ以外はメイン Sonnet で完結させる。
- 計画のための事前調査も Sonnet に委託する（Fable は調査結果を受けて骨子・方針・最終判断だけを担う）。
- ※起動モデルそのものは `settings.json` の `model` が決める。本節は「メイン Sonnet ＋ 要所のみ Fable 明示起動」という工程別の役割分担方針。難易度ベースの自動メイン切替は不可。
---

## 10. Skill 起動ルール

該当シーンでは、本リポ `.claude/skills/<name>/SKILL.md` を読んでから作業を開始する（**本リポに実在する skill のみ掲載**）。

| トリガー | スキル |
|---|---|
| 機能設計・改善アイデア出し | `.claude/skills/sp-brainstorming/SKILL.md` |
| 計画立案 | `.claude/skills/sp-writing-plans/SKILL.md` |
| 計画に沿った実行 | `.claude/skills/sp-executing-plans/SKILL.md` |
| 図表・ダッシュボード設計図 | `.claude/skills/mermaid-agents365/SKILL.md` |
| 成果物の納品・コミット前チェック | `.claude/skills/sp-verification-before-completion/SKILL.md` |

> 追加ルール（`.claude/` 配下）: `quality-rules.md`（品質）/ `cross-repo.md`（関連リポ連携）も必要時に参照。

---

## 11. データ分析・ダッシュボード固有ルール

- データファイル（`sales_data.csv` / `sales_data_extended.csv`）を直接編集する場合は変更前にバックアップを作成する。
- KPI 定義・集計ロジックを変更した場合は `FILE_INDEX.md` の該当箇所を更新する。
- Streamlit アプリの動作確認は `streamlit run my_dashboard.py` で実行する。

---

## 12. 回答スタイル

- 日本語で回答する。
- 回答末尾に「**Next Action:**」でユーザーの次アクションを具体的に推奨する。迷う場面は「**推奨:**」で明示する。
<!-- ANSWER-STYLE-HATS:BEGIN -->
- Next Action の直前に「**留保:**」を1行（黒ハット＝この結論が誤るとしたら最有力の理由）。**具体的な反例・数値・条件を必ず含める**。「注意が必要」等の抽象語だけの行は書かない（形骸化防止）。
- 方針・設計・採否を判断した回のみ「**代替案:**」を1行追加（緑ハット＝採らなかった案と棄却理由）。実行・報告のみの回は不要。
<!-- ANSWER-STYLE-HATS:END -->

---

## 13. コンテキスト管理（自動圧縮対策 / Compact Instructions）

Claude Code はコンテキスト利用率が高まると自動でテキスト要約圧縮（auto-compact, 約83.5%目安）を行う。圧縮で重要情報を失わないため以下を守る。

### 圧縮時に必ず保持する情報（`/compact` 実行・自動圧縮時に要約へ残す）
- 本リポ/タスクの目的・前提制約・現行の意思決定
- 進行中タスクと未解決課題（`tasks.md` の最新状態）
- 正典ファイル・最新成果物への参照（例: SPEC / `CURRENT_*.md` / 最新レポート）
- ファイルスコープ・モジュール境界・命名規則
- 直近のエラー・制約・回避策

### 圧縮の影響を受けない永続層（外部メモリ）に状態を書き出す
- `tasks.md`（次にやること・進捗。セッション終了時に必ず更新）
- `file_index.md` / `FILE_INDEX.md`（索引）、`session.json`（あれば進捗）
- 確定した結論・成果はレポート `.md` に保存（会話履歴に依存させない）

### 運用ルール
- 重い調査・実装はサブエージェントに委譲し、親には要約のみ戻す（コンテキスト分離）
- 利用率が高まったら警告を待たず能動的に `/compact <保持指示>` を実行。別タスクへ移る際は `/clear`（CLAUDE.md・tasks.md は残る）
- ※潜在空間ベクトル圧縮（Codex方式）は公開APIの制約上、本ハーネスでは実装不可。テキスト要約＋外部メモリで代替する

---

## 上位ガバナンスへの参照

<!-- GOVERNANCE_LINK_START -->
- 本リポの運用は [KazuyaMurayama/claude-governance](https://github.com/KazuyaMurayama/claude-governance) の正典に準拠する
- 競合した場合は本リポの CLAUDE.md が優先（リポ固有ルールが上位ガバナンスに勝つ）
- 上位ガバナンスを変更した際は、本リポの CLAUDE.md にも反映する責務がある
- 監査スクリプト: `claude-governance/audits/audit_43repos.py` を実行することで本リポの適合状況を確認できる
- 過去レポート探索（作成リポが不明・記憶と違う時）: 個別リポを推測せず横断検索する。**全リポ private 化済（2026-07-14〜）のため `raw.githubusercontent.com` の無認証取得・WebFetch は 404 になる。必ず認証付き Contents API（raw media）で取得する**:
  ```bash
  GH_TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | grep '^password=' | cut -d= -f2)
  curl -s -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github.raw" \
    "https://api.github.com/repos/KazuyaMurayama/claude-governance/contents/index/REPORT_INDEX.md?ref=main" \
    -o "$TMPDIR/REPORT_INDEX.md"
  grep -i "<日本語キーワード>" "$TMPDIR/REPORT_INDEX.md"
  ```
  （各行=`日付 | [H1日本語タイトル](URL) | パス`。ファイル名が英語でも H1 は日本語なのでヒットする。毎日06:00 JST 自動更新。ローカルなら `python claude-governance/index/search_reports.py <キーワード...>`）
<!-- GOVERNANCE_LINK_END -->

<!-- CONTEXT-HYGIENE:BEGIN -->
## コンテキスト管理・肥大化防止（全セッション共通）
auto-compact 頻発を防ぐため、コンテキストに載せる量を機械的に絞る（正典: claude-governance/templates/context-hygiene-block.md）。
- **C1 ファイル受け**: 外部出力・API応答は必ずファイルに保存し、grep/jq/python で抽出した必要フィールドのみコンテキストへ。base64 本文・全文 JSON の表示・保持は禁止（API応答は status・sha のみ）。用済み中間 JSON は削除。
- **C2 大ファイルRead制限**: 50KB 超のファイルを limit/offset なしで全文 Read しない（Grep／offset+limit 部分Read／スクリプト処理で件数のみ受領）。編集後の確認 Read 禁止。
- **C3 スクリプト統合**: 一括置換・統合は Python スクリプト＋「ちょうど1回一致」全数アサート（不一致は例外停止）。コンテキストに受け取るのは件数のみ。完了根拠はリモート実バイト検証（スクリプトの自己申告を信じない）。
- **C4 サブエージェント戻り上限**: 委託 prompt に「成果物・詳細はファイルに保存しパスを返す。最終返信は要約2KB以内」を明記。
- **C5 シリーズ作業の /clear 設計**: 定型反復作業は台帳ファイル（tasks.md 等）を状態アンカーにし、約3ユニットごとに /clear で新しいコンテキストから再開。台帳＋CLAUDE.md だけで再開できる状態を保つ。
- **C6 能動 /compact**: 利用率が高まったら警告を待たず `/compact <保持指示>`。圧縮時保持=目的・前提制約・意思決定・進行中タスク・正典ファイル参照・直近エラー。状態は tasks.md 等の永続層に書き出し会話履歴に依存させない。
- 機械ガード: `.claude/hooks/pre_read_guard.py`（PreToolUse: Read）が C2 を自動検査する。
<!-- CONTEXT-HYGIENE:END -->
