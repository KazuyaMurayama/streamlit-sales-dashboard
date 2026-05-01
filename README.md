# Streamlit Sales Dashboard — 売上・営業KPIダッシュボード

> Streamlit で構築したリアルタイム売上・営業KPI管理ダッシュボードです。

## 📋 概要

Streamlit で構築したリアルタイム売上・営業KPI管理ダッシュボードです。売上推移・目標達成率・顧客別分析・担当者別実績をインタラクティブに可視化します。

## ✨ 主な機能

- 売上・受注・パイプラインのリアルタイム可視化
- 目標vs実績の達成率トラッキング
- 顧客セグメント別・担当者別ドリルダウン分析
- 前年同期比・移動平均トレンド表示
- CSV/Excelデータの自動取込・更新

## 🛠️ 技術スタック

| カテゴリ | 技術・ライブラリ |
|----------|----------------|
| 言語 | Python 3.10+ |
| UI | Streamlit |
| 可視化 | plotly, altair |
| データ処理 | pandas |
| データソース | CSV / Google Sheets |

## 🚀 セットアップ

### 前提条件

- Python 3.9 以上
- APIキー（Claude / OpenAI 等）を `.env` ファイルに設定

### インストール

```bash
git clone https://github.com/KazuyaMurayama/streamlit-sales-dashboard.git
cd streamlit-sales-dashboard
pip install -r requirements.txt
```

### 環境設定

```bash
cp .env.example .env
# .env ファイルに必要なAPIキーを設定
```

## 💻 使い方

```bash
streamlit run dashboard.py
```

## 👨‍💻 開発者情報

**男座員也（Kazuya Oza / おざ かずや）**

| | |
|---|---|
| GitHub | [@KazuyaMurayama](https://github.com/KazuyaMurayama) |
| 専門領域 | データサイエンス・生成AIコンサルタント |
| 主要スキル | Python, LightGBM, LangChain, RAG, Streamlit, React, TypeScript |
| 事業 | AIコンサルティング（月単価目標300万円）/ SaaS開発 / 定量投資 |

## 📄 ライセンス

© 2025 男座員也（Kazuya Oza）. All rights reserved.

---

> このリポジトリは **男座員也（Kazuya Oza）** が開発・管理しています。
> 命名・ドキュメント等での表記は必ず **男座員也** または **Kazuya Oza** を使用してください。
