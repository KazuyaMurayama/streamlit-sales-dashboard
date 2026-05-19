# Quality Rules — 品質ガードレール

> このファイルは **ファイル生成前・push前・成果物報告前** に必ず参照し、適用する。

---

## ルール1: ブランチ衛生（自動マージ）

### 原則
**新規ブランチを作らない。** ファイルは常に `main`（または `master`）に直接コミットする。
- GitHub Contents API: `branch` パラメータに必ず `main` を指定する
- ローカル作業開始前: `git rev-parse --abbrev-ref HEAD` を確認し、main/master 以外なら即 `git checkout main && git pull`

### ブランチが存在してしまった場合の即時マージフロー（ユーザー指示不要）

**ローカル環境:**
1. `git checkout main && git pull origin main`
2. `git merge <branch> --ff-only`（衝突時のみユーザー確認）
3. `git push origin main`
4. `git branch -d <branch>` → `git push origin --delete <branch>`
5. マージ完了後にのみ成果物URLを生成する（`/blob/main/...` 形式）

**Web版/API環境:**
1. `gh api -X POST /repos/{owner}/{repo}/merges -f base=main -f head=<branch>`
2. `gh api -X DELETE /repos/{owner}/{repo}/git/refs/heads/<branch>`
3. 失敗（コンフリクト）時のみユーザーに状況を1行報告し指示を仰ぐ

**トリガー（以下いずれかで自動発動）:**
- ファイル新規作成・更新の直後（3列表生成の前）
- セッション開始時に main/master 以外のブランチを検出した時

---

## ルール2: リサーチ・ファクトチェック

### 適用スコープ（CLAUDE.md の `Repo type:` で判定）

| Repo type | 発動条件 |
|---|---|
| research | 外部情報を含む成果物は常時チェック |
| app | WebFetch/WebSearch を使った成果物のみ |
| mixed | 外部情報の引用・分析を含む成果物のみ |

未宣言の場合は `mixed` として扱う。迷ったら「適用する側」に倒す。

### 必須チェック2項目（push 前の固定工程）

#### (a) URL 実在確認
- 成果物内の **全外部URL** に WebFetch を実行し HTTP 200 + 本文を確認する
- 確認できないURL（404・タイムアウト・内容不一致）は引用から削除する
- 確認済みURLには取得日を付記: `（確認: YYYY-MM-DD）`

#### (b) 飛躍なし表現チェック
- **引用**: ソース原文を `>` ブロックで明示 ＋ URL 記載
- **要約**: `（出典: URL）` を付記。ソースにない属性・数値を追加しない
- **推論**: 「考えられる」「推定される」「と思われる」等のヘッジ語を必須とする。出典なしの断定禁止
- 数値（%・金額・件数）は必ず出典URL とセット。出典なしの数値は推論格下げまたは削除

### チェック不合格時の扱い
1. 違反箇所をリストアップし修正案を提示する
2. ユーザーの確認後に push（自動 push しない）
3. 違反なしなら通常の成果物報告フローへ
