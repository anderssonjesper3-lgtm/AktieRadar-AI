"""AktieRadar AI – Streamlit-vy för Saab B med Avanza-data.

Kräver test_avanza_forbattrad.py i samma katalog och paket fastmcp, avanza-mcp.
Visar inga syntetiska kurser eller automatiska handelsorder.
"""
import asyncio
from datetime import datetime, timedelta

import pandas as pd
import altair as alt
import streamlit as st

from test_avanza_forbattrad import (
    SWEDEN, LOOKBACK, MAX_AGE_MINUTES, build_candles,
    calculate_ema, calculate_rsi, calculate_macd, calculate_relative_volume,
    calculate_signal_scores, check_buy_signal, consecutive_count,
    detect_candlestick_patterns, fetch_points,
)

st.set_page_config(page_title="AktieRadar AI – Saab B", page_icon="📈", layout="wide")
st.title("📈 AktieRadar AI – Saab B")
st.caption("AKTIERADAR 2.2 · SIGNALDIAGNOSTIK")
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
# Den sista historiskt beräkningsbara poängen är ENDAST för analys.
last_valid = next((item for item in reversed(scores) if item is not None), None)
# Hitta den senaste verkliga tidsluckan, utan att fylla den med påhittade kurser.
last_gap = next((
    (candles[i-1]["time"], candles[i]["time"])
    for i in range(len(candles)-1, 0, -1)
    if candles[i]["time"] - candles[i-1]["time"] != timedelta(minutes=5)
), None)
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
plot = chart_data.reset_index().melt(id_vars="Tid", var_name="Serie", value_name="Pris")
plot = plot.dropna(subset=["Pris"])
chart = (
    alt.Chart(plot)
    .mark_line(strokeWidth=2)
    .encode(
        x=alt.X("Tid:T", title="Svensk tid", axis=alt.Axis(format="%H:%M", labelOverlap=True)),
        y=alt.Y("Pris:Q", title="Kurs (kr)", scale=alt.Scale(zero=False)),
        color=alt.Color("Serie:N", title="Linje", scale=alt.Scale(
            domain=["Kurs", "EMA 9", "EMA 21"],
            range=["#18a999", "#f59e0b", "#6478d3"]
        )),
        tooltip=[alt.Tooltip("Tid:T", format="%Y-%m-%d %H:%M"), "Serie:N", alt.Tooltip("Pris:Q", format=".2f")],
    )
    .properties(height=400)
    .interactive()
)
st.altair_chart(chart, use_container_width=True)
st.caption("Diagrammet anpassar prisskalan efter Saab-kursen. Linjerna avser historiska, färdigbyggda femminutersstaplar.")

st.subheader("🔎 Signaldiagnostik – varför saknas poäng?")
if last_valid is not None:
    st.caption(
        f"Senaste historiskt beräknade poäng: {last_valid['score']}/100 "
        f"kl. {last_valid['time'].strftime('%Y-%m-%d %H:%M')} svensk tid. "
        "Detta är INTE en aktuell signal."
    )
else:
    st.caption("Ingen historisk stapel har tillräckliga indikatorer för en fullständig poäng.")
if last_gap:
    previous_time, next_time = last_gap
    st.info(
        f"Senaste avbrott mellan kompletta staplar: "
        f"{previous_time.strftime('%Y-%m-%d %H:%M')} och "
        f"{next_time.strftime('%Y-%m-%d %H:%M')}. "
        "Avbrutna perioder hoppas över; vi skapar inte påhittade kurser."
    )
if continuous < LOOKBACK:
    st.progress(min(continuous / LOOKBACK, 1.0), text=f"{continuous} av {LOOKBACK} sammanhängande femminutersstaplar")
    st.caption(
        f"Om kommande staplar är kompletta krävs minst {LOOKBACK - continuous} "
        "ytterligare staplar innan just kontinuitetskravet uppfylls. "
        "Efter natt/helg börjar denna sammanhängande följd om från början."
    )
else:
    st.success("Kontinuitetskravet för relativ volym är uppfyllt.")
st.subheader("🛡️ Varför visas denna signalstatus?")
if not normal_hours:
    st.info("Utanför normal handelstid. Inga aktuella signaler tillåts.")
elif not same_day:
    st.warning("Senaste stapeln är från en annan handelsdag.")
elif not completed:
    st.warning("Den senaste stapelns tidsperiod har ännu inte avslutats.")
elif age > MAX_AGE_MINUTES or age < 0:
    st.warning(f"Kursdata är inte tillräckligt färska (ålder från stapelslut: {age:.1f} minuter).")
elif not quality_ok:
    st.warning(f"Endast {continuous} sammanhängande femminutersstaplar. Minst {LOOKBACK} behövs.")
elif latest_score is None:
    st.warning("Någon indikator saknas. Ingen poäng eller signal kan beräknas.")
else:
    st.success("Grundkontrollerna är godkända. Signalen är fortfarande en analyskandidat, inte ett handelsråd.")

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
