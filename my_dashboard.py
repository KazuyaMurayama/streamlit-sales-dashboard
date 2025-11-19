import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ページ設定
st.set_page_config(
    page_title="売上ダッシュボード",
    page_icon="📊",
    layout="wide"
)

# タイトル
st.title("📊 売上分析ダッシュボード")
st.markdown("---")

# データ読み込み
@st.cache_data
def load_data(file):
    if file is not None:
        df = pd.read_csv(file)
    else:
        df = pd.read_csv("sales_data.csv")  # デフォルトファイル
    
    df['日付'] = pd.to_datetime(df['日付'])
    df['年月'] = df['日付'].dt.strftime('%Y-%m')
    return df

# サイドバー：ファイルアップロード
st.sidebar.header("📁 データ設定")

uploaded_file = st.sidebar.file_uploader(
    "CSVファイルをアップロード",
    type=['csv'],
    help="売上データのCSVファイルを選択してください"
)

# データ読み込みを実行
df = load_data(uploaded_file)



# サイドバー：フィルター設定
st.sidebar.header("🔍 フィルター設定")

# TODO: 商品フィルター
selected_products = st.sidebar.multiselect(
    "商品を選択",
    options=df['商品名'].unique(),
    default=df['商品名'].unique()
)

# TODO: エリアフィルター
selected_areas = st.sidebar.multiselect(
    "エリアを選択",
    options=df['エリア'].unique(),
    default=df['エリア'].unique()
)

# TODO: データフィルタリング
filtered_df = df[
    (df['商品名'].isin(selected_products)) & 
    (df['エリア'].isin(selected_areas))
]

# メイン表示エリア
# TODO: KPIメトリクスを表示
st.subheader("📈 主要指標")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("総売上", f"¥{filtered_df['売上金額'].sum():,.0f}")

with col2:
    st.metric("総販売数", f"{filtered_df['販売数量'].sum():,.0f}個")

with col3:
    st.metric("平均売上", f"¥{filtered_df['売上金額'].mean():,.0f}")

with col4:
    st.metric("データ件数", f"{len(filtered_df)}件")

st.markdown("---")

# タブを作成
tab1, tab2 = st.tabs(["📈 時系列分析", "📊 商品別分析"])

with tab1:
    st.subheader("月別売上推移")
    
    # 月別集計
    monthly_sales = filtered_df.groupby(['年月', '商品名'])['売上金額'].sum().reset_index()
    
    # 折れ線グラフ
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for product in monthly_sales['商品名'].unique():
        product_data = monthly_sales[monthly_sales['商品名'] == product]
        ax.plot(product_data['年月'], product_data['売上金額'], 
               marker='o', label=product, linewidth=2)
    
    ax.set_xlabel('月')
    ax.set_ylabel('売上金額 (円)')
    ax.set_title('月別売上推移（商品別）')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    
    st.pyplot(fig)

with tab2:
    st.subheader("商品別売上金額")
    
    # 商品別集計
    product_sales = filtered_df.groupby('商品名')['売上金額'].sum().reset_index()
    
    # 棒グラフ
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(product_sales['商品名'], product_sales['売上金額'],
                  color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
    
    ax.set_xlabel('商品名')
    ax.set_ylabel('売上金額 (円)')
    ax.set_title('商品別売上金額')
    
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'¥{height:,.0f}',
               ha='center', va='bottom')
    
    st.pyplot(fig)

# データプレビュー
st.markdown("---")
st.subheader("📊 フィルタリング済みデータ")
st.dataframe(filtered_df)
st.write(f"表示件数: {len(filtered_df)}件")


# CSVダウンロードボタン
csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    label="📥 CSVをダウンロード",
    data=csv,
    file_name="filtered_sales_data.csv",
    mime="text/csv"
)