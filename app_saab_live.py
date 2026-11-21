"""AktieRadar AI – Streamlit-vy för Saab B med Avanza-data.

Kräver test_avanza_forbattrad.py i samma katalog och paket fastmcp, avanza-mcp.
Visar inga syntetiska kurser eller automatiska handelsorder.
"""
import asyncio
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from test_avanza_forbattrad import (
    SWEDEN, LOOKBACK, MAX_AGE_MINUTES, build_candles,
    calculate_ema, calculate_rsi, calculate_macd, calculate_relative_volume,
    calculate_signal_scores, check_buy_signal, consecutive_count,
    detect_candlestick_patterns, fetch_points,
)

st.set_page_config(page_title="AktieRadar AI – Saab B", page_icon="📈", layout="wide")
st.title("📈 AktieRadar AI – Saab B")
st.caption("Avanza-kursdata • femminutersstaplar • indikativa VAKTA/KÖP-kandidater • ingen orderläggning")
st.warning("Börshelgdagar och eventuell fördröjning i Avanzas kursdata verifieras inte. Använd inte signalerna som handelsrekommendationer.")

@st.cache_data(ttl=60, show_spinner=False)
def get_data():
    # Cache begränsar antalet anrop. Ny hämtning sker vid omkörning efter TTL.
    return asyncio.run(fetch_points())

if st.button("🔄 Uppdatera kursdata"):
    get_data.clear()
    st.rerun()

try:
    with st.spinner("Hämtar Saab B från Avanza..."):
        points, raw_count = get_data()
    candles, gaps = build_candles(points)
except Exception as exc:
    st.error(f"Avanza-data kunde inte hämtas: {exc}")
    st.info("Inga signaler visas när datakällan inte fungerar.")
    st.stop()

if not candles:
    st.error("Inga kompletta femminutersstaplar tillgängliga. Signaler blockerade.")
    st.stop()

closes = [c["close"] for c in candles]
ema9 = calculate_ema(closes, 9)
ema21 = calculate_ema(closes, 21)
rsi14 = calculate_rsi(closes, 14)
_, _, macd_hist = calculate_macd(closes)
relative_volume = calculate_relative_volume(candles)
patterns = detect_candlestick_patterns(candles)
scores = calculate_signal_scores(candles, ema9, ema21, rsi14, macd_hist, relative_volume, patterns)

now = datetime.now(SWEDEN)
last = candles[-1]
last_end = last["time"] + timedelta(minutes=5)
completed = now >= last_end
age = (now - last_end).total_seconds() / 60
same_day = last["time"].date() == now.date()
normal_hours = now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) < (17, 30)
continuous = consecutive_count(candles)
quality_ok = continuous >= LOOKBACK
latest_score = scores[-1]["score"] if scores and scores[-1] is not None else None
status = check_buy_signal(latest_score, quality_ok)
if not completed:
    status = "BLOCKERAD – STAPEL EJ FÄRDIG"
if not same_day or age > MAX_AGE_MINUTES or age < 0:
    status = "BLOCKERAD – GAMMAL ELLER OGILTIG KURSDATA"
if not normal_hours:
    status = "BLOCKERAD – UTANFÖR NORMAL HANDELSTID"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Senaste kurs (kr)", f'{last["close"]:.2f}')
col2.metric("Senaste poäng", str(latest_score) if latest_score is not None else "Saknas")
col3.metric("Relativ volym", f"{relative_volume[-1]:.2f}×" if relative_volume[-1] is not None else "Saknas")
col4.metric("Sammanhängande staplar", f"{continuous}/{LOOKBACK}")

if status.startswith("BLOCKERAD"):
    st.error(f"🛡️ {status}")
elif status.startswith("KOP"):
    st.warning(f"🔎 {status} – endast analyskandidat")
elif status.startswith("VAKTA"):
    st.info(f"👀 {status}")
else:
    st.info(f"Signalstatus: {status}")

st.caption(
    f"Datakälla: Avanza, Saab B (orderbok 5401) • Senaste kompletta stapel: "
    f"{last['time'].strftime('%Y-%m-%d %H:%M')} svensk tid • "
    f"{len(candles)} kompletta staplar • {len(gaps)} ofullständiga perioder • "
    f"{raw_count} hämtade minutposter"
)
if not same_day:
    st.warning("Senaste kursdata kommer från en tidigare dag. Ingen aktuell signal tillåts.")
elif not quality_ok:
    st.warning("För få sammanhängande staplar för relativ volym. Signaler blockeras tills datakvaliteten räcker.")

st.subheader("Saab B – kurs och EMA")
chart_data = pd.DataFrame({
    "Kurs": closes,
    "EMA 9": ema9,
    "EMA 21": ema21,
}, index=pd.DatetimeIndex([c["time"] for c in candles], name="Tid"))
st.line_chart(chart_data, use_container_width=True)

with st.expander("🔍 Indikatorer och datakvalitet"):
    st.write({
        "RSI 14": round(rsi14[-1], 2) if rsi14[-1] is not None else "saknas",
        "MACD-histogram": round(macd_hist[-1], 4) if macd_hist[-1] is not None else "saknas",
        "Senaste stapelns tidsperiod avslutad": completed,
        "Kursdata från idag": same_day,
        "Ålder från stapelns slut (minuter)": round(age, 1),
        "Normal handelstid": normal_hours,
        "Datakvalitet godkänd": quality_ok,
    })
    st.caption("Normal handelstid är en förenklad veckodagskontroll, inte en verifierad börskalender.")

st.subheader("Historiska poäng – endast analys")
rows = []
for i, item in enumerate(scores):
    if item is not None and item["score"] >= 50:
        rows.append({
            "Tid": item["time"], "Kurs": candles[i]["close"],
            "Poäng": item["score"], "Orsaker": ", ".join(item["reasons"]),
            "21 sammanhängande": i >= 20 and all(
                (candles[j]["time"] - candles[j-1]["time"]).total_seconds() == 300
                for j in range(i-19, i+1)
            ),
        })
if rows:
    st.dataframe(pd.DataFrame(rows).iloc[::-1], use_container_width=True, hide_index=True)
else:
    st.info("Inga historiska poäng på minst 50 i de hämtade uppgifterna.")
st.caption("Historiska poäng är inte verifierade köp-/säljlarm. Ingen automatisk handel sker.")
