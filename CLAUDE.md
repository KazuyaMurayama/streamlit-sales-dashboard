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
9. **一次資料主義**: 決定に効く数値・事実は実ファイル・実 URL・実行結果から引く。記憶・過去の要約だけで断言しない。
10. **回答末尾に「Next Action:」** を必ず付す。

> 優先順位: ユーザーの直接指示 > 本ブロック > 本文各節。詳細・背景は本文の対応セクションを参照。
> 機械ガード: `.claude/hooks/`（Desktop 書き込み拒否・終了時ブランチ/未pushチェック・push 後の報告リマインド）が本ブロックの 1,2,3,7 を自動検査する。
<!-- HARD_RULES_END -->

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
- 過去レポート探索（作成リポが不明・記憶と違う時）: 個別リポを推測せず、`curl -s https://raw.githubusercontent.com/KazuyaMurayama/claude-governance/main/index/REPORT_INDEX.md | grep <日本語キーワード>` で横断検索する（各行=`日付 | [H1日本語タイトル](URL) | パス`。ファイル名が英語でも H1 は日本語なのでヒットする。約340KBのため WebFetch でなく curl→grep が確実。毎日06:00 JST 自動更新。ローカルなら `python claude-governance/index/search_reports.py <キーワード...>`）
<!-- GOVERNANCE_LINK_END -->
