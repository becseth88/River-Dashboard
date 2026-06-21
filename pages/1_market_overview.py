import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
import numpy as np
from datetime import datetime, timezone, timedelta

# --- Config & Setup ---
st.set_page_config(page_title="River Protocol: Market Overview", layout="wide", page_icon="🌊")
PARQUET_PATH = "data/public_history.parquet"

# --- Educational Data Dictionary ---
with st.expander("📚 River Protocol: Kinematics Glossary & Math"):
    st.markdown("""
    **Domain 1: Exchange Kinematics (Physical Laws)**
    - **Compression**: `(24H High - 24H Low) / Current Price`. Measures how tight the price is coiled. Values below 2% indicate massive tension.
    - **Turnover**: `24H USD Trading Volume`. Represents the kinetic energy flowing through the asset.
    - **The Trap**: `Turnover / Compression²`. The core metric. Identifies "boredom" - coins with massive volume but artificially constrained price action (a coiled spring).
    - **Wick Absorption (BP)**: `(Close - Low) / (High - Low)`. Measures institutional buying. If a coin dumps but closes near the top of the candle, buyers "absorbed" the selling pressure. (>0.5 is bullish).
    - **G-Force (Acceleration)**: Live `15m` Volume (or `1H` in Historical Mode) compared to its 24H rolling average. Measures if volume is suddenly accelerating *right now*.
    """)

# --- Sidebar: Data Engine ---
st.sidebar.header("⚙️ Data Engine")
mode = st.sidebar.radio("Dashboard Mode", ["Live (Binance API)", "Historical (Parquet)"])

target_time_ms = None
if mode == "Historical (Parquet)":
    st.sidebar.markdown("Select a specific moment in time to travel back to:")
    sel_date = st.sidebar.date_input("Date", value=datetime.now().date() - timedelta(days=1))
    sel_time = st.sidebar.time_input("Time", value=datetime.now().time())
    
    dt = datetime.combine(sel_date, sel_time).replace(tzinfo=timezone.utc)
    target_time_ms = int(dt.timestamp() * 1000)

# --- Data Fetching Functions ---

@st.cache_data(ttl=60)
def fetch_live_snapshot():
    info_res = requests.get("https://api.binance.com/api/v3/exchangeInfo").json()
    usdt_symbols = [s['symbol'] for s in info_res['symbols'] if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']
            
    ticker_res = requests.get("https://api.binance.com/api/v3/ticker/24hr").json()
    df = pd.DataFrame(ticker_res)
    df = df[df['symbol'].isin(usdt_symbols)].copy()
    
    numeric_cols = ['lastPrice', 'highPrice', 'lowPrice', 'quoteVolume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

@st.cache_data(ttl=60)
def fetch_historical_snapshot(target_ms):
    try:
        df_all = pd.read_parquet(PARQUET_PATH)
    except Exception as e:
        st.error(f"Failed to load Parquet: {e}")
        return pd.DataFrame()
        
    start_ms = target_ms - (24 * 60 * 60 * 1000)
    df_window = df_all[(df_all['open_time'] > start_ms) & (df_all['open_time'] <= target_ms)]
    
    if df_window.empty:
        return pd.DataFrame()
        
    df_agg = df_window.groupby('symbol').agg(
        lowPrice=('low', 'min'),
        highPrice=('high', 'max'),
        quoteVolume=('quote_volume', 'sum')
    ).reset_index()
    
    df_last = df_window.sort_values('open_time').drop_duplicates(subset=['symbol'], keep='last')
    df_last = df_last[['symbol', 'close']].rename(columns={'close': 'lastPrice'})
    
    df = pd.merge(df_agg, df_last, on='symbol')
    return df

@st.cache_data(ttl=60)
def fetch_live_deep_dive(symbols):
    results = []
    my_bar = st.progress(0, text="Running Deep Dive Diagnostics on Filtered Coins...")
    for i, symbol in enumerate(symbols):
        try:
            res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=96").json()
            if not res or len(res) < 2: continue
            last_closed = res[-2]
            current_forming = res[-1]
            high, low, close = float(last_closed[2]), float(last_closed[3]), float(last_closed[4])
            live_vol = float(current_forming[7])
            all_vols = [float(candle[7]) for candle in res[:-1]]
            avg_15m_vol = sum(all_vols) / len(all_vols) if all_vols else 1
            spread = high - low
            bp = (close - low) / spread if spread > 0 else 0.5
            g_force = live_vol / avg_15m_vol if avg_15m_vol > 0 else 0
            results.append({"symbol": symbol, "wick_absorption": bp, "g_force": g_force})
        except:
            pass
        my_bar.progress((i + 1) / len(symbols), text=f"Deep Dive: {symbol}")
        time.sleep(0.05)
    my_bar.empty()
    return pd.DataFrame(results)

@st.cache_data(ttl=60)
def fetch_historical_deep_dive(symbols, target_ms):
    df_all = pd.read_parquet(PARQUET_PATH)
    start_ms = target_ms - (24 * 60 * 60 * 1000)
    df_window = df_all[(df_all['open_time'] > start_ms) & (df_all['open_time'] <= target_ms)]
    df_symbols = df_window[df_window['symbol'].isin(symbols)]
    
    results = []
    for symbol in symbols:
        df_sym = df_symbols[df_symbols['symbol'] == symbol].sort_values('open_time')
        if len(df_sym) < 2: continue
        
        last_row = df_sym.iloc[-1]
        spread = last_row['high'] - last_row['low']
        bp = (last_row['close'] - last_row['low']) / spread if spread > 0 else 0.5
        
        avg_1h_vol = df_sym['quote_volume'].mean()
        g_force = last_row['quote_volume'] / avg_1h_vol if avg_1h_vol > 0 else 0
        
        results.append({"symbol": symbol, "wick_absorption": bp, "g_force": g_force})
    return pd.DataFrame(results)

# --- Main App Execution ---
if mode == "Live (Binance API)":
    st.title("🌊 River Protocol: Live Market Overview")
    st.markdown(f"**Data Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC (Live)")
    with st.spinner("Fetching Live Data..."):
        raw_df = fetch_live_snapshot()
else:
    st.title("⏳ River Protocol: Historical Market Overview")
    st.markdown(f"**Data Timestamp:** {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC (Historical)")
    with st.spinner("Querying Parquet Database..."):
        raw_df = fetch_historical_snapshot(target_time_ms)
        if raw_df.empty:
            st.error("No historical data found for this specific time window. Try a date within the last 1 year.")
            st.stop()

# --- Snapshot Calculations ---
epsilon = 1e-9
raw_df["compression"] = (raw_df["highPrice"] - raw_df["lowPrice"]) / (raw_df["lastPrice"] + epsilon)
raw_df["turnover"] = raw_df["quoteVolume"]
raw_df["the_trap"] = raw_df["turnover"] / ((raw_df["compression"] ** 2) + epsilon)

df = raw_df[['symbol', 'lastPrice', 'turnover', 'compression', 'the_trap']].copy()
df = df.rename(columns={'lastPrice': 'price'})

# --- Filters ---
st.sidebar.header("🎛️ Filters")
min_vol = st.sidebar.slider("Min 24H Volume (USD)", 0, 50000000, 2000000, 500000, format="$%d")
max_comp = st.sidebar.slider("Max Compression (%)", 1.0, 50.0, 15.0, 0.5)

filtered_df = df[(df["turnover"] >= min_vol) & (df["compression"] <= (max_comp / 100.0))].copy()
filtered_df = filtered_df[filtered_df['compression'] >= 0.005] 
filtered_df = filtered_df.sort_values(by="the_trap", ascending=False).reset_index(drop=True)
filtered_df['trap_score_log'] = np.log10(filtered_df['the_trap'] + 1)

# --- Visualizations ---
if not filtered_df.empty:
    all_filtered_symbols = filtered_df['symbol'].tolist()
    if mode == "Live (Binance API)":
        deep_df = fetch_live_deep_dive(all_filtered_symbols)
    else:
        deep_df = fetch_historical_deep_dive(all_filtered_symbols, target_time_ms)
    
    if not deep_df.empty:
        filtered_df = pd.merge(filtered_df, deep_df, on="symbol", how="left")
    else:
        filtered_df["wick_absorption"] = 0.5
        filtered_df["g_force"] = 0.0

    fig = px.scatter(
        filtered_df, x="compression", y="turnover", size="turnover", size_max=60, color="trap_score_log",
        hover_name="symbol", hover_data={"price": ":.4f", "turnover": ":$,.0f", "compression": ":.2%", "wick_absorption": ":.2f", "g_force": ":.2fx", "the_trap": ":.2e", "trap_score_log": False},
        log_y=True, log_x=True, color_continuous_scale="Turbo",
        labels={"compression": "Price Compression (High-Low %)", "turnover": "24H Trading Volume (USD)", "trap_score_log": "Trap Heat"},
        title="Volumetric Compression (The Trap)"
    )
    fig.update_layout(xaxis_tickformat='.1%', coloraxis_colorbar=dict(title="Trap Intensity"))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"### 🔍 The Deep Dive ({len(filtered_df)} Coins)")
    display_df = filtered_df.copy()
    display_df['compression'] = (display_df['compression'] * 100).map("{:.2f}%".format)
    display_df['turnover'] = display_df['turnover'].map("${:,.0f}".format)
    display_df['the_trap'] = display_df['the_trap'].map("{:.2e}".format)
    if 'wick_absorption' in display_df.columns:
        display_df['wick_absorption'] = display_df['wick_absorption'].fillna(0.5).map("{:.2f}".format)
        display_df['g_force'] = display_df['g_force'].fillna(0.0).map("{:.2f}x".format)
    else:
        display_df['wick_absorption'] = "0.50"
        display_df['g_force'] = "0.00x"
    st.dataframe(display_df[['symbol', 'price', 'turnover', 'compression', 'the_trap', 'wick_absorption', 'g_force']], use_container_width=True)
else:
    st.warning("No coins match filters.")

if st.button("🔄 Force Refresh"):
    fetch_live_snapshot.clear()
    fetch_historical_snapshot.clear()
    fetch_live_deep_dive.clear()
    st.rerun()
