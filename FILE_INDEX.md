# FILE_INDEX — streamlit-sales-dashboard

> ⚠️ このファイルは手動生成です（2026-07-16 全量同期）。

| 項目 | 値 |
|---|---|
| リポジトリ | KazuyaMurayama/streamlit-sales-dashboard |
| ブランチ | main |
| 総ファイル数 | 30 |
| 最終更新日 | 2026-07-16 |
| 管理者 | 男座員也（Kazuya Oza） |

---

## カテゴリ別サマリー

| カテゴリ | ファイル数 |
|---|---|
| Documentation | 5 |
| Code | 1 |
| Data | 2 |
| Config | 3 |
| Claude運用（`.claude/`・`.github/`） | 19 |

---

## ディレクトリ構成

```
.
├── .claude/
│   ├── cross-repo.md
│   ├── hooks/
│   │   ├── md_table_check.py
│   │   ├── post_bash_guard.py
│   │   ├── pre_md_table_guard.py
│   │   ├── pre_write_guard.py
│   │   └── session_guard.py
│   ├── quality-rules.md
│   ├── settings.json
│   ├── skills/
│   │   ├── branch-cleanup/SKILL.md
│   │   ├── mermaid-agents365/SKILL.md
│   │   ├── mermaid-agents365/reference/CLASS-ER.md
│   │   ├── mermaid-agents365/reference/FLOWCHART.md
│   │   ├── mermaid-agents365/reference/OTHER-TYPES.md
│   │   ├── mermaid-agents365/reference/SEQUENCE.md
│   │   ├── sp-brainstorming/SKILL.md
│   │   ├── sp-executing-plans/SKILL.md
│   │   ├── sp-verification-before-completion/SKILL.md
│   │   └── sp-writing-plans/SKILL.md
│   └── visual-rules.md
├── .github/
│   └── workflows/md-table-lint.yml
├── .gitignore
├── CLAUDE.md
├── FILE_INDEX.md
├── my_dashboard.py
├── README.md
├── requirements.txt
├── sales_data_extended.csv
├── sales_data.csv
├── tasks.md
└── Timeout_Prevention.md
```

---

## ファイル詳細

### Documentation (5件)

| ファイル | サイズ | 説明 |
|---|---|---|
| `CLAUDE.md` | 15.7 KB | Claude Code プロジェクト設定・命名ルール |
| `FILE_INDEX.md` | 1.9 KB | （このファイル）全ファイルインデックス |
| `README.md` | 3.2 KB | リポジトリ概要・セットアップ手順・実装済み機能一覧 |
| `tasks.md` | 2.2 KB | タスク管理・セッション履歴 |
| `Timeout_Prevention.md` | 5.0 KB | タイムアウト対策ガイド |

### Code (1件)

| ファイル | サイズ | 説明 |
|---|---|---|
| `my_dashboard.py` | 3.9 KB | Streamlit 売上ダッシュボード本体（CSV読込・フィルター・KPI表示・matplotlibグラフ） |

### Data (2件)

| ファイル | サイズ | 説明 |
|---|---|---|
| `sales_data_extended.csv` | 2.7 KB | CSV サンプルデータ（拡張版） |
| `sales_data.csv` | 726 B | CSV サンプルデータ（デフォルト読込対象） |

### Config (3件)

| ファイル | サイズ | 説明 |
|---|---|---|
| `.gitignore` | 422 B | Git 除外設定 |
| `requirements.txt` | 53 B | Python 依存パッケージリスト（streamlit, pandas, matplotlib） |
| `.github/workflows/md-table-lint.yml` | 374 B | MDテーブル整形チェック用 GitHub Actions |

### Claude運用 `.claude/`（19件）

| ファイル | サイズ | 説明 |
|---|---|---|
| `.claude/cross-repo.md` | 3.6 KB | 横断リポジトリ運用メモ |
| `.claude/quality-rules.md` | 3.1 KB | 品質ルール |
| `.claude/settings.json` | 856 B | Claude Code 設定 |
| `.claude/visual-rules.md` | 4.0 KB | 図表・視覚化ルール |
| `.claude/hooks/md_table_check.py` | 8.8 KB | MDテーブルチェックフック |
| `.claude/hooks/post_bash_guard.py` | 1.4 KB | Bash実行後ガードフック |
| `.claude/hooks/pre_md_table_guard.py` | 4.7 KB | MDテーブル事前ガードフック |
| `.claude/hooks/pre_write_guard.py` | 1.6 KB | 書き込み前ガードフック |
| `.claude/hooks/session_guard.py` | 2.4 KB | セッションガードフック |
| `.claude/skills/branch-cleanup/SKILL.md` | 6.6 KB | ブランチ整理スキル |
| `.claude/skills/mermaid-agents365/SKILL.md` | 7.6 KB | Mermaid図生成スキル |
| `.claude/skills/mermaid-agents365/reference/CLASS-ER.md` | 2.1 KB | Mermaid参照（クラス/ER図） |
| `.claude/skills/mermaid-agents365/reference/FLOWCHART.md` | 1.6 KB | Mermaid参照（フローチャート） |
| `.claude/skills/mermaid-agents365/reference/OTHER-TYPES.md` | 2.0 KB | Mermaid参照（その他図種） |
| `.claude/skills/mermaid-agents365/reference/SEQUENCE.md` | 1.7 KB | Mermaid参照（シーケンス図） |
| `.claude/skills/sp-brainstorming/SKILL.md` | 10.5 KB | ブレインストーミングスキル |
| `.claude/skills/sp-executing-plans/SKILL.md` | 2.5 KB | 計画実行スキル |
| `.claude/skills/sp-verification-before-completion/SKILL.md` | 4.2 KB | 完了前検証スキル |
| `.claude/skills/sp-writing-plans/SKILL.md` | 6.1 KB | 計画作成スキル |

---

_手動生成・全量同期: 2026-07-16 | 管理者: 男座員也（Kazuya Oza）_
