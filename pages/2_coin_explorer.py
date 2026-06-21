import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timezone, timedelta

PARQUET_PATH = "data/public_history.parquet"

st.title("📈 Historical Coin Explorer")
st.markdown("Deep dive into the specific kinematic history of any asset over the last year.")

@st.cache_data(ttl=300)
def get_all_symbols():
    try:
        df = pd.read_parquet(PARQUET_PATH, columns=['symbol'])
        return sorted(df['symbol'].unique().tolist())
    except:
        return []

@st.cache_data(ttl=300)
def fetch_coin_history(symbol, days_back):
    try:
        df_all = pd.read_parquet(PARQUET_PATH)
    except:
        return pd.DataFrame()
        
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)
    
    df = df_all[(df_all['symbol'] == symbol) & (df_all['open_time'] >= start_ms)].copy()
    df = df.sort_values('open_time')
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        
        # Calculate Rolling River Kinematics (24H window for compression)
        df['rolling_high'] = df['high'].rolling(window=24, min_periods=1).max()
        df['rolling_low'] = df['low'].rolling(window=24, min_periods=1).min()
        df['rolling_vol'] = df['quote_volume'].rolling(window=24, min_periods=1).sum()
        
        epsilon = 1e-9
        df['compression'] = (df['rolling_high'] - df['rolling_low']) / (df['close'] + epsilon)
        df['the_trap'] = df['rolling_vol'] / ((df['compression']**2) + epsilon)
        
        # Wick Absorption (Close relative to High-Low spread)
        df['spread'] = df['high'] - df['low']
        df['wick_absorption'] = np.where(df['spread'] > 0, (df['close'] - df['low']) / df['spread'], 0.5)
        
    return df

symbols = get_all_symbols()
default_coin_idx = symbols.index("BTCUSDT") + 1 if "BTCUSDT" in symbols else 0
selected_coin = st.selectbox("Search for a specific coin:", [""] + symbols, index=default_coin_idx)

if selected_coin:
    # Time Period Selector
    time_periods = {
        "1 Year": 365,
        "6 Months": 180,
        "3 Months": 90,
        "1 Month": 30,
        "2 Weeks": 14,
        "1 Week": 7,
        "1 Day": 1
    }
    
    default_period_idx = list(time_periods.keys()).index("1 Week")
    selected_period = st.radio("Select Time Period:", list(time_periods.keys()), horizontal=True, index=default_period_idx)
    days_back = time_periods[selected_period]
    
    with st.spinner(f"Loading {selected_period} history for {selected_coin}..."):
        df = fetch_coin_history(selected_coin, days_back)
        
        if df.empty:
            st.warning(f"No data found for {selected_coin} in the last {selected_period}.")
        else:
            # Create a Massive 4-Row Subplot
            fig = make_subplots(
                rows=4, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.05,
                row_heights=[0.4, 0.2, 0.2, 0.2],
                subplot_titles=(f"Price Action", "Turnover (Hourly USD Volume)", "The Trap Score (Log)", "Wick Absorption (Buyer Defense)")
            )
            
            # Row 1: Candlestick Price
            fig.add_trace(
                go.Candlestick(
                    x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    name="Price", increasing_line_color='#00FFAA', decreasing_line_color='#FF3366'
                ), row=1, col=1
            )
            
            # Row 2: Turnover (Volume)
            fig.add_trace(
                go.Bar(
                    x=df['date'], y=df['quote_volume'], name="Volume", marker_color='#00E5FF', opacity=0.8
                ), row=2, col=1
            )
            
            # Row 3: The Trap Score
            df['trap_log'] = np.log10(df['the_trap'] + 1)
            fig.add_trace(
                go.Scatter(
                    x=df['date'], y=df['trap_log'], name="Trap Score (Log)",
                    line=dict(color='#FFAA00', width=2), fill='tozeroy', fillcolor='rgba(255, 170, 0, 0.1)'
                ), row=3, col=1
            )
            
            # Row 4: Wick Absorption
            fig.add_trace(
                go.Scatter(
                    x=df['date'], y=df['wick_absorption'], name="Wick Absorption",
                    mode='markers', marker=dict(size=4, color=df['wick_absorption'], colorscale='RdYlGn', showscale=False)
                ), row=4, col=1
            )
            # Add 0.5 threshold line for Wick Absorption
            fig.add_hline(y=0.5, line_dash="dash", line_color="gray", opacity=0.5, row=4, col=1)
            
            # Formatting
            fig.update_layout(
                height=1000,
                template="plotly_dark",
                showlegend=False,
                xaxis_rangeslider_visible=False,
                hovermode="x unified"
            )
            
            # Y-Axis Formatting
            fig.update_yaxes(title_text="Price ($)", row=1, col=1)
            fig.update_yaxes(title_text="Volume", row=2, col=1)
            fig.update_yaxes(title_text="Trap Heat", row=3, col=1)
            fig.update_yaxes(title_text="Defense (>0.5)", range=[-0.1, 1.1], row=4, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
