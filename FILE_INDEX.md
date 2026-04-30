# FILE_INDEX.md — streamlit-sales-dashboard

> **新セッション開始時に必ずこのファイルを読む。**
> ファイル追加・削除・移動時は必ずこのファイルを更新すること。
> 最終更新: 2026-04-30

## 概要
StreamlitによるシンプルなECサイト売上分析ダッシュボード。CSVデータ読み込みによるインタラクティブ可視化。

**スタック:** Python, Streamlit, Pandas

---

## 📋 最初に読むべきファイル

| 優先度 | ファイル | 内容 |
|---|---|---|
| ★★★ | `my_dashboard.py` | Streamlit ダッシュボードメインファイル |
| ★★ | `requirements.txt` | Python依存関係 |
| ★★ | `sales_data.csv` | 売上データ（基本） |
| ★★ | `sales_data_extended.csv` | 売上データ（拡張） |

---

## 🗂️ ディレクトリ構造

```
streamlit-sales-dashboard/
├── my_dashboard.py              ← Streamlitダッシュボード
├── requirements.txt
├── sales_data.csv               ← 売上データ（基本）
└── sales_data_extended.csv      ← 売上データ（拡張）
```

---

## 📑 全ファイル一覧

| パス | 種別 | 説明 |
|---|---|---|
| `my_dashboard.py` | Python | Streamlit売上分析ダッシュボード |
| `requirements.txt` | 設定 | Python依存関係（Streamlit, Pandas等） |
| `sales_data.csv` | データ | 売上データ（基本版） |
| `sales_data_extended.csv` | データ | 売上データ（拡張版） |

---

## 🔖 ファイル更新ルール

1. 新ファイル追加時: 該当セクションに1行追加
2. ファイル削除・移動時: 該当行を削除または更新
3. 更新後: `git add FILE_INDEX.md && git commit -m "docs: FILE_INDEX.md更新"`
