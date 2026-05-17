# 他リポジトリ参照ルール (Cross-Repository Reference Guide)

Claude Code Web版（claude.ai/code）はセッション開始時に1リポジトリを選択する仕様だが、
**パブリック GitHub リポジトリの内容は WebFetch / GitHub REST API 経由で取得可能**。
「別リポジトリだから読めません」と返答することは禁止。本ガイドに従って取得すること。

---

## 1. トリガー条件

以下のいずれかに該当したら即座に取得を試みる：

- ユーザーが他リポジトリ名・URL・ファイルパスを発話した
- 現在のセッションに存在しないファイルへの参照が必要になった
- 「別リポの〜」「あっちのプロジェクトの〜」等の他リポ参照表現

**禁止応答:** 「このセッションでは別リポジトリにアクセスできません」で打ち切ること。

---

## 2. 取得メソッド（優先順位順）

### 第1選択: WebFetch で raw コンテンツを取得（最速）

```
https://raw.githubusercontent.com/<OWNER>/<REPO>/<BRANCH>/<PATH>
```

例:
- `https://raw.githubusercontent.com/KazuyaMurayama/NASDAQ_backtest/main/CURRENT_BEST_STRATEGY.md`
- `https://raw.githubusercontent.com/KazuyaMurayama/deep-research/main/README.md`

ブランチ不明時は `main` → `master` の順で試す。

### 第2選択: GitHub REST API（ディレクトリ一覧・メタ情報が必要なとき）

```
https://api.github.com/repos/KazuyaMurayama/<REPO>/contents/<PATH>?ref=<BRANCH>
```

### 第3選択: リポジトリ一覧の取得（リポジトリ名が不明なとき）

```
https://api.github.com/users/KazuyaMurayama/repos?per_page=100&sort=updated
```

### 第4選択: WebSearch

`site:github.com KazuyaMurayama <キーワード>`

---

## 3. よく参照されるリポジトリ

| 略称 | OWNER/REPO | 代表ファイル |
|---|---|---|
| NASDAQ / バックテスト / ベスト戦略 | `KazuyaMurayama/NASDAQ_backtest` | `CURRENT_BEST_STRATEGY.md` |
| deep-research / DR | `KazuyaMurayama/deep-research` | `README.md`, `file_index.md` |
| フリーランス / compass | `KazuyaMurayama/freelance-compass` | `FILE_INDEX.md` |
| ショッピング / 商品検索 | `KazuyaMurayama/shopping_product_search` | `file_index.md` |

**NASDAQ ベスト戦略質問は特例:** 必ず `CURRENT_BEST_STRATEGY.md` を WebFetch で取得し一次根拠とする。

---

## 4. 取得フロー

1. ユーザー発話からリポジトリ名とファイルパスを特定
2. WebFetch で raw URL を取得
3. **404 の場合:** ブランチを `main` → `master` → `develop` の順で再試行
4. それでも失敗した場合: contents API でパスの存在確認 → ディレクトリなら一覧表示
5. private リポジトリと判定した場合のみ「非公開のため取得不可」と1行返す

---

## 5. エラーハンドリング

| エラー | 対処 |
|---|---|
| 404 | ブランチ違い or パス違い or private の切り分け → §4 のフロー |
| 403 rate limit | `raw.githubusercontent.com` 直叩きに切り替え（rate limit が緩い） |
| タイムアウト | 1回再試行 → 失敗なら raw ↔ API を切り替え |
| バイナリファイル | download_url をユーザーに提示 |

---

## 6. 出典表示

他リポジトリから取得した内容を引用するときは出典 URL を明示する：

> 出典: `https://raw.githubusercontent.com/KazuyaMurayama/<REPO>/main/<PATH>`
