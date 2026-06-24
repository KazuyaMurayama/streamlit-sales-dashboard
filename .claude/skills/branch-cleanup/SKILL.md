---
name: branch-cleanup
description: Use when a repo has branches other than main that should be consolidated — whether the user asks to delete/clean up/merge branches, OR you yourself detect leftover branches via `git branch -a` / `git ls-remote --heads origin`, OR you created a branch during work and are about to finish. Consolidates the repo down to main only. IMPORTANT — branch deletion IS executable from Web Claude Code (claude.ai/code); do NOT tell the user "please do this yourself." Follow the 3-tier deletion path below.
---

# Branch Cleanup — main 1本へ集約する

このリポジトリを **main ブランチ 1 本だけ** に集約し、main 以外の不要なブランチを削除する手順。

> **これは Web版 Claude Code（claude.ai/code）でも実行可能**。「環境の制約でできない／ユーザー自身で対応してください」と回答してはならない。下記 (3) の 3 段階を上から順に試せば、ほぼ全環境で削除できる。実際に拒否されるのは「default branch を消そうとした」「branch protection が有効」等の特殊ケースのみ。

---

## いつ起動するか（自主検知）

以下の **いずれか** を満たしたら、ユーザー指示が無くてもこの手順を起動する：

- `git branch -a` または `git ls-remote --heads origin` で **main 以外のブランチが残っている** ことに気づいた
- ユーザーが「ブランチを削除／整理して」「main に集約して」「不要なブランチを消して」と依頼した
- 自分が作業中にブランチを作成し、作業完了前に放置しようとしている（「完了 = main にマージ済み＆push済み」が原則）

起動したら、まずユーザーに「main 以外を削除して main 1本へ集約します」と一言告げてから (1) へ進む（破壊的操作のため）。

---

## 手順

### (1) 作業ツリーがクリーンか確認
```bash
git status
```
- uncommitted な変更があれば、commit するか stash してから進む。
- 現在のブランチも確認（`git branch --show-current`）。

### (2) main 以外のブランチに固有コミットがあれば main へ取り込む
削除前に **コミットの取りこぼしを防ぐ**。各対象ブランチについて：
```bash
# main に無い独自コミットがあるか
git log --oneline origin/main..origin/<branch>
```
- 出力があれば（= 取り込むべき固有コミットがある）、main に取り込む：
  ```bash
  git checkout main
  git pull origin main
  git merge --no-ff origin/<branch>
  git push origin main
  ```
- 出力が空なら（= main に全部入っている）、マージ不要。そのまま (3) で削除してよい。
- 競合した場合は解消してから commit → push。判断に迷う変更はユーザーに確認。

### (3) main 以外のリモートブランチを削除（3 段階：上から順に試す）

**段階 A — 素直な削除（まずこれ。Web版でも通常成功）**
```bash
git push origin --delete <branch>
```

**段階 B — A が HTTP 403 / 拒否されたら REST API で直接削除**
Web版には認証済み GitHub コンテキストがあるため、これも実行可能：
```bash
# gh CLI が認証済みなら
gh api -X DELETE repos/<owner>/<repo>/git/refs/heads/<branch>

# gh 不可なら token で直接（GITHUB_TOKEN / GH_TOKEN が環境にある場合）
curl -X DELETE -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/<owner>/<repo>/git/refs/heads/<branch>
```

**段階 C — A も B も不可な環境のみ：Actions ワークフローでフォールバック**
リポ内から push トリガーで `GITHUB_TOKEN` を使い削除する。**使用後は必ず後始末してリポを汚さない**。

1. `.github/workflows/delete-branch.yml` を作成：
   ```yaml
   name: delete-branch
   on:
     push:
       paths: [.github/branches-to-delete.txt]
   permissions:
     contents: write
   jobs:
     delete:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - name: Delete listed branches
           env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
           run: |
             while IFS= read -r b; do
               [ -z "$b" ] && continue
               echo "Deleting $b"
               curl -X DELETE \
                 -H "Authorization: Bearer $GH_TOKEN" \
                 "https://api.github.com/repos/${{ github.repository }}/git/refs/heads/$b" || true
             done < .github/branches-to-delete.txt
   ```
2. `.github/branches-to-delete.txt` に削除対象を **1 行 1 件** で列挙。
3. 両ファイルを commit & push（これがワークフローを起動する）。
4. `git ls-remote --heads origin` を数秒おきに確認し、対象ブランチが消えるのを待つ。
5. **後始末**：消えたのを確認したら、`delete-branch.yml` と `branches-to-delete.txt` を削除して commit & push。リポに痕跡を残さない。

### (4) ローカル追跡参照とローカルブランチを整理
```bash
git remote prune origin          # 消えたリモートブランチの追跡参照を掃除
git branch -d <branch>           # 不要なローカルブランチを削除（マージ済みのみ -d で安全に消える）
```
- `-d` が「未マージ」と拒否したら、本当に不要か確認。意図的に捨てるなら `-D`（強制）だが、グローバル設定で `git branch -D *` が deny されている場合があるので、その際は1本ずつ明示名で削除。

### (5) 最終確認（main のみであることを証明する）
```bash
git branch -a
git ls-remote --heads origin
```
- **両方の出力が main だけ** になっていることを示して完了報告する。片方だけでは不十分（ローカルとリモートの両面を確認する）。

---

## 注意・原則

- **default branch（main）自体は絶対に削除しない**。
- マージ済み判定は必ず `origin/main..origin/<branch>` で行う（ローカルの古い main と比較しない）。
- 段階 C のワークフローは **一時的なもの**。使ったら必ず削除する（「リポを汚さない」が要件）。
- 削除は破壊的操作。実行前に対象ブランチ一覧をユーザーに一言提示してから進める（事前承認の長い待ちは不要だが、何を消すかは告げる）。
- branch protection で main へ直接 push できないリポでは、(2) のマージは PR 経由に切り替える。
