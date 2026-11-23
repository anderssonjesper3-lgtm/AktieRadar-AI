"""Standalone KryptoRadar Streamlit dashboard; paper trading only."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from kryptoradar.engine import PAIRS, fetch_candles, analyze, paper_trade


st.markdown("""<style>
.stApp { background:#0d1727; color:#f5f9ff; }
.stApp p, .stApp span, .stApp label, .stApp li,
.stApp h1, .stApp h2, .stApp h3,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"],
.stApp [data-testid="stMetricDelta"],
.stApp [data-testid="stSidebar"] p,
.stApp [data-testid="stSidebar"] label { color:#f5f9ff !important; opacity:1 !important; }
div[data-testid="stMetric"] { background:#17253b; border:1px solid #30445f; padding:14px; border-radius:12px; }
.stApp div.stButton > button, .stApp div.stDownloadButton > button {
 background:#213b56; color:#ffffff !important; border:1px solid #6d91b1; font-weight:650;
}
.stApp div.stButton > button *, .stApp div.stDownloadButton > button * { color:#ffffff !important; }
.stApp div.stButton > button:hover, .stApp div.stDownloadButton > button:hover { background:#305879; }
.stApp div[data-testid="stAlert"], .stApp div[data-testid="stAlert"] * {
 color:#17253b !important; opacity:1 !important;
}
.stApp a { color:#a9eaff !important; }
</style>""", unsafe_allow_html=True)
st.title("₿ KryptoRadar")
st.caption("BTC · ETH · SOL | KRAKEN | STÄNGDA 1-MINUTSLJUS | INGA NYHETER")
st.warning("Experimentell analys och fiktiva affärer. Inga riktiga köp eller säljordrar. Kryptomarknaden innebär hög risk.")
st_autorefresh(interval=60_000, key="crypto_refresh")
st.sidebar.header("Simulering")
stake = st.sidebar.number_input("Belopp per fiktiv affär (USD)", min_value=100, value=1000, step=100)
fee = st.sidebar.number_input("Courtage per sida (%)", min_value=0.0, value=0.25, step=0.05)
slip = st.sidebar.number_input("Slippage per sida (%)", min_value=0.0, value=0.10, step=0.05)
auto = st.sidebar.checkbox("Registrera fiktiva affärer automatiskt", value=False)
st.sidebar.caption("Journalen lagras i appens lokala filsystem. På molnhosting kan den försvinna vid omstart.")
path = Path(__file__).parent / "paper_journal.json"
try:
    journal = json.loads(path.read_text()) if path.exists() else []
except (OSError, ValueError):
    journal = []
if st.sidebar.button("Uppdatera"):
    st.cache_data.clear()
@st.cache_data(ttl=50, show_spinner=False)
def snapshot(pair):
    return analyze(fetch_candles(pair))
for name, pair in PAIRS.items():
    st.subheader(name + " · " + pair)
    try:
        s = snapshot(pair)
    except Exception as exc:
        st.error("Ingen verifierad aktuell data: " + str(exc))
        continue
    a,b,c,d = st.columns(4)
    a.metric("Signal",s["status"])
    b.metric("Pris (USD)",f'{s["price"]:,.4f}')
    c.metric("RSI",f'{s["rsi"]:.1f}')
    d.metric("Volym mot 20 ljus",f'{s["volume_ratio"]:.2f}×')
    st.caption("Senaste stängda ljus: " + s["timestamp"] + " UTC · Datakälla: Kraken")
    frame = s["frame"].set_index("timestamp")
    st.line_chart(frame[["close","ema9","ema21"]].tail(120))
    if auto:
        before = len(journal)
        paper_trade(journal,pair,s,fee,slip,stake)
        if len(journal) != before:
            try:
                path.write_text(json.dumps(journal, indent=2))
            except OSError as exc:
                st.error("Journalen kunde inte sparas: " + str(exc))
st.subheader("Fiktiv handelsjournal")
if journal:
    trades = pd.DataFrame(journal)
    st.dataframe(trades, use_container_width=True, hide_index=True)
    st.metric("Realiserat resultat (USD)",f'{trades["pnl"].dropna().sum():,.2f}')
    st.download_button("Ladda ner journal som CSV", trades.to_csv(index=False), "kryptoradar_journal.csv", "text/csv")
else:
    st.info("Inga simulerade affärer ännu. Aktivera registrering i sidomenyn.")
