import streamlit as st
import pandas as pd
from binance.client import Client
from dotenv import load_dotenv
import os
from datetime import datetime
import altair as alt
import pytz
import time
import requests
import hmac
import hashlib

# ตั้งค่าเพจ (ต้องตั้งก่อนเรียกใช้งาน streamlit อื่นๆ)
st.set_page_config(page_title="Combined Trade Dashboard", layout="wide")

# ------ Dark mode & responsive style ------
dark_mode_css = """
<style>
    /* Background and text */
    .reportview-container {
        background-color: #0E1117;
        color: white;
    }
    h1, h2, h3, h4 {
        color: white;
    }
    /* Table header */
    .css-1d391kg th {
        background-color: #262730 !important;
        color: white !important;
    }
    /* Table rows */
    .css-1d391kg td {
        background-color: #1A1D26 !important;
        color: white !important;
    }
    /* Metric boxes */
    .stMetric > div {
        background-color: #1A1D26;
        border-radius: 10px;
        padding: 10px;
        color: white;
    }

    /* Responsive tweaks */
    @media (max-width: 768px) {
        .stMetric > div {
            font-size: 14px;
            padding: 6px;
        }
        h1, h2, h3 {
            font-size: 18px;
        }
    }
</style>
"""
st.markdown(dark_mode_css, unsafe_allow_html=True)

# โหลด API key จาก .env
load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
client = Client(API_KEY, API_SECRET)

# สร้าง 2 tabs
tab1, tab2 = st.tabs(["BTC/USDT Trades", "USDT/THB Trades"])

# ---------- Tab 1: BTC/USDT Dashboard ----------
with tab1:
    st.title("💹 BTC/USDT Trade Dashboard")

    price_placeholder = st.empty()

    def show_live_price():
        try:
            ticker = client.get_symbol_ticker(symbol="BTCUSDT")
            current_price = float(ticker['price'])
            price_placeholder.metric("BTC/USDT", f"{current_price:.2f} USDT")
            return current_price
        except Exception as e:
            price_placeholder.error(f"Error: {e}")
            return None

    current_price = show_live_price()

    # ดึงข้อมูลการเทรด BTCUSDT
    try:
        trades = client.get_my_trades(symbol="BTCUSDT")
        df = pd.DataFrame(trades)

        if df.empty:
            st.info("❗ ไม่มีประวัติการเทรด BTCUSDT")
            st.stop()

        bangkok_tz = pytz.timezone("Asia/Bangkok")
        df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True).dt.tz_convert(bangkok_tz).dt.tz_localize(None)

        # แปลงข้อมูลชนิดตัวเลข
        df["price"] = df["price"].astype(float)
        df["qty"] = df["qty"].astype(float)
        df["quoteQty"] = df["quoteQty"].astype(float)
        df["commission"] = df["commission"].astype(float)

        # แปลง isBuyer เป็น BUY / SELL
        df["side"] = df["isBuyer"].apply(lambda x: "BUY" if x else "SELL")

        # ลบข้อมูลซ้ำ
        df.drop_duplicates(subset=["orderId", "time", "qty", "price"], inplace=True)

        # เลือกคอลัมน์และตั้งชื่อใหม่
        df = df[["time", "side", "price", "qty", "quoteQty", "commission", "commissionAsset"]]
        df.rename(columns={
            "time": "Date",
            "price": "Price (USDT)",
            "qty": "BTC Amount",
            "quoteQty": "Total (USDT)",
            "commission": "Fee",
            "commissionAsset": "Fee Asset",
            "side": "Type"
        }, inplace=True)

        st.subheader(f"📊 สรุปผลรวม ({df['Date'].min().date()} - {df['Date'].max().date()})")

        buy = df[df["Type"] == "BUY"]
        total_buy_usdt = buy["Total (USDT)"].sum()
        total_buy_btc = buy["BTC Amount"].sum()
        total_fee = df["Fee"].sum()
        avg_cost = total_buy_usdt / total_buy_btc if total_buy_btc > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("จำนวน BTC ซื้อ", f"{total_buy_btc:.6f}")
        col2.metric("ซื้อรวม (USDT)", f"{total_buy_usdt:.2f}")
        col3.metric("ต้นทุนเฉลี่ย (USDT)", f"{avg_cost:.2f}")
        col4.metric("ค่าธรรมเนียมรวม", f"{total_fee:.6f} {df['Fee Asset'].iloc[0]}")

        if current_price:
            profit_loss = (current_price - avg_cost) * total_buy_btc
            st.metric("💰 กำไร/ขาดทุน (USDT)", f"{profit_loss:.2f} USDT")

        st.markdown("### 📈 กราฟราคาซื้อขาย")

        df["Date Only"] = df["Date"].dt.date
        price_chart = df.groupby(["Date Only", "Type"]).agg({
            "Price (USDT)": "mean",
            "BTC Amount": "sum"
        }).reset_index()

        line = alt.Chart(price_chart).mark_line(point=True).encode(
            x="Date Only:T",
            y="Price (USDT):Q",
            color="Type:N",
            tooltip=["Date Only", "Type", "Price (USDT)", "BTC Amount"]
        )

        avg_line = alt.Chart(pd.DataFrame({
            "Date Only": [price_chart["Date Only"].min(), price_chart["Date Only"].max()],
            "Avg Cost": [avg_cost, avg_cost]
        })).mark_line(strokeDash=[6, 3], color="orange").encode(
            x="Date Only:T",
            y="Avg Cost:Q"
        ).properties(title="ต้นทุนเฉลี่ย")

        st.altair_chart(line + avg_line, use_container_width=True)

        st.markdown("### 📅 เลือกช่วงวันที่")
        min_date = df["Date"].min().date()
        max_date = df["Date"].max().date()
        start_date = st.date_input("เริ่ม", min_value=min_date, max_value=max_date, value=min_date)
        end_date = st.date_input("ถึง", min_value=min_date, max_value=max_date, value=max_date)

        mask = (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)
        filtered_df = df[mask]

        st.markdown("### 📋 รายการซื้อขาย BTC/USDT")
        st.dataframe(filtered_df.sort_values("Date", ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")

# ---------- Tab 2: USDT/THB Trades Dashboard ----------
with tab2:
    st.title("💱 USDT/THB Trades Dashboard")

    API_KEY_USDTTHB = os.getenv("API_KEY_USDTTHB") or API_KEY
    API_SECRET_USDTTHB = os.getenv("API_SECRET_USDTTHB") or API_SECRET
    BASE_URL = 'https://api.binance.th'

    def get_all_orders(symbol):
        timestamp = int(time.time() * 1000)
        query_string = f'symbol={symbol}&timestamp={timestamp}'

        signature = hmac.new(
            API_SECRET_USDTTHB.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        url = f'{BASE_URL}/api/v1/allOrders?{query_string}&signature={signature}'

        headers = {
            'X-MBX-APIKEY': API_KEY_USDTTHB
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error {response.status_code}: {response.text}")
            return None

    def format_orders_to_table(orders):
        rows = []
        total_qty = 0.0
        total_cost = 0.0
        total_fee = 0.0

        min_timestamp = None
        max_timestamp = None

        for order in orders:
            if order['status'] != 'FILLED':
                continue

            ts = order['time']
            if min_timestamp is None or ts < min_timestamp:
                min_timestamp = ts
            if max_timestamp is None or ts > max_timestamp:
                max_timestamp = ts

            timestamp = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
            quantity = float(order['origQty'])

            # ราคาอาจ 0 ให้ลองใช้ cumulativeQuoteQty แทน
            if float(order.get('price', 0)) > 0:
                price = float(order['price'])
            else:
                quote_qty = order.get('cumulativeQuoteQty') or order.get('cummulativeQuoteQty') or 0
                if quote_qty and quantity > 0:
                    price = float(quote_qty) / quantity
                else:
                    price = 0

            fee = quantity * 0.0025  # สมมติค่าธรรมเนียม 0.25%
            total = quantity * price

            total_qty += quantity
            total_cost += total
            total_fee += fee

            rows.append({
                'วันที่': timestamp,
                'ประเภท': order['side'],
                'ราคา': price,
                'จำนวน': quantity,
                'รวม': total,
                'ค่าธรรมเนียม': fee
            })

        return pd.DataFrame(rows), total_qty, total_cost, total_fee, min_timestamp, max_timestamp

    orders = get_all_orders('USDTTHB')

    if orders:
        df_orders, total_qty, total_cost, total_fee, min_ts, max_ts = format_orders_to_table(orders)

        if df_orders.empty:
            st.info("❗ ไม่มีประวัติการเทรด USDT/THB")
            st.stop()

        min_date = datetime.fromtimestamp(min_ts / 1000).date() if min_ts else None
        max_date = datetime.fromtimestamp(max_ts / 1000).date() if max_ts else None

        st.subheader(f"สรุป ({min_date} - {max_date})")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("จำนวน USDT ซื้อ", f"{total_qty:.4f}")
        col2.metric("ซื้อรวม (THB)", f"{total_cost:.2f}")
        avg_cost = total_cost / total_qty if total_qty > 0 else 0
        col3.metric("ต้นทุนเฉลี่ย (THB)", f"{avg_cost:.2f}")
        col4.metric("ค่าธรรมเนียมรวม (THB)", f"{total_fee:.4f}")

        st.markdown("### รายการซื้อขาย USDT/THB")
        st.dataframe(df_orders.sort_values(by='วันที่', ascending=False), use_container_width=True)

        st.markdown("### เลือกช่วงวันที่")
        start_date = st.date_input("เริ่ม", min_value=min_date, max_value=max_date, value=min_date)
        end_date = st.date_input("ถึง", min_value=min_date, max_value=max_date, value=max_date)

        filtered_orders = df_orders[
            (pd.to_datetime(df_orders['วันที่']).dt.date >= start_date) &
            (pd.to_datetime(df_orders['วันที่']).dt.date <= end_date)
        ]
        st.dataframe(filtered_orders.sort_values(by='วันที่', ascending=False), use_container_width=True)

