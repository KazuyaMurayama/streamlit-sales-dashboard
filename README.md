# Streamlit Sales Dashboard — 売上・営業KPIダッシュボード

> Streamlit で構築した売上データ可視化ダッシュボードです。

## 📋 概要

Streamlit で構築した売上データ可視化ダッシュボードです。CSVアップロード（またはデフォルトのサンプルデータ）を読み込み、商品名・エリアでフィルタしながら、主要KPI・月別推移・商品別売上をインタラクティブに確認できます。

## ✨ 実装済み機能

- CSVファイルのアップロード（未指定時は同梱の `sales_data.csv` を使用）
- 商品名・エリアによる絞り込みフィルター
- 主要指標カード表示（総売上・総販売数・平均売上・データ件数）
- 月別売上推移の折れ線グラフ（商品別、matplotlib）
- 商品別売上金額の棒グラフ（matplotlib）
- フィルタリング済みデータのテーブルプレビュー
- フィルタリング済みデータのCSVダウンロード

## 🚧 未実装・構想（README記載のみで実装なし）

以下は将来構想であり、現時点のコードには含まれていません。

- 目標vs実績の達成率トラッキング
- 前年同期比・移動平均トレンド表示
- 顧客セグメント別・担当者別ドリルダウン分析
- Google Sheets連携によるデータ自動取込

## 🛠️ 技術スタック

| カテゴリ | 技術・ライブラリ |
|----------|----------------|
| 言語 | Python 3.10+ |
| UI | Streamlit |
| 可視化 | matplotlib |
| データ処理 | pandas |
| データソース | CSV（ファイルアップロード or ローカルCSV） |

## 🚀 セットアップ

### 前提条件

- Python 3.9 以上
- APIキー等の環境変数は不要（本アプリはCSV読み込みのみで外部API・LLMを呼び出しません）

### インストール

```bash
git clone https://github.com/KazuyaMurayama/streamlit-sales-dashboard.git
cd streamlit-sales-dashboard
pip install -r requirements.txt
```

## 💻 使い方

```bash
streamlit run my_dashboard.py
```

サイドバーからCSVファイルをアップロードするか、未指定のままにするとリポジトリ同梱の `sales_data.csv` が読み込まれます。CSVの必須カラムは `日付, 商品名, エリア, 売上金額, 販売数量` です（`sales_data_extended.csv` も同形式のサンプルとして同梱）。

## 👨‍💻 開発者情報

**男座員也（Kazuya Oza / おざ かずや）**

| | |
|---|---|
| GitHub | [@KazuyaMurayama](https://github.com/KazuyaMurayama) |
| 専門領域 | データサイエンス・生成AIコンサルタント |
| 主要スキル | Python, LightGBM, LangChain, RAG, Streamlit, React, TypeScript |
| 事業 | AIコンサルティング / SaaS開発 / 定量投資 |

## 📄 ライセンス

© 2025 男座員也（Kazuya Oza）. All rights reserved.

---

> このリポジトリは **男座員也（Kazuya Oza）** が開発・管理しています。
> 命名・ドキュメント等での表記は必ず **男座員也** または **Kazuya Oza** を使用してください。
