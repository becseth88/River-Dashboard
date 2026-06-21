import streamlit as st

st.set_page_config(page_title="River Protocol", layout="wide", page_icon="🌊")

pages = {
    "Dashboards": [
        st.Page("pages/1_market_overview.py", title="🌊 Market Overview"),
        st.Page("pages/2_coin_explorer.py", title="📈 Coin Explorer"),
    ]
}

pg = st.navigation(pages)
pg.run()
