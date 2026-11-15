import io
import pandas as pd
import streamlit as st
from scanner import demo_ohlcv, scan

st.set_page_config(page_title='AktieRadar AI – Saab B', page_icon='📈', layout='wide')
st.title('📈 AktieRadar AI – Saab B')
st.caption('Version 0.2 • Pine Script v6 → Python • VAKTA och KÖP • Ingen orderläggning')
st.warning('🧪 Standardläget använder SYNTETISKA TESTKURSER – inga verkliga Saab-kurser eller live-signaler.')
with st.sidebar:
    st.header('⚙️ Inställningar')
    threshold = st.slider('Minsta signalpoäng', 1, 100, 70)
    vol_multiplier = st.number_input('Volymökning', min_value=1.0, max_value=10.0, value=1.5, step=0.1)
    show_ema = st.checkbox('Visa EMA', True)
    uploaded = st.file_uploader('Valfri 5-minuters OHLCV-CSV', type=['csv'])
    st.caption('Kolumner: timestamp, open, high, low, close, volume. Tidsstämpel = stapelns start, svensk lokal börstid. Ingen data skickas till Avanza.')

if uploaded:
    try:
        raw = pd.read_csv(uploaded)
        raw.columns = raw.columns.str.strip().str.lower()
        needed = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
        if not needed.issubset(raw.columns):
            raise ValueError('CSV måste ha kolumnerna: ' + ', '.join(sorted(needed)))
        raw['timestamp'] = pd.to_datetime(raw['timestamp'])
        if raw['timestamp'].duplicated().any():
            raise ValueError('Dubbla tidsstämplar finns i filen.')
        data = raw.set_index('timestamp').sort_index()
        if len(data) < 100:
            st.warning('Färre än 100 staplar. Indikatorerna behöver uppvärmningsdata.')
        source = 'UPPLADDAD CSV (kontrollera datakällan och om sista stapeln är stängd)'
    except Exception as e:
        st.error(f'Kunde inte läsa filen: {e}')
        st.stop()
else:
    data = demo_ohlcv()
    source = 'SYNTETISK DEMODATA'

try:
    result = scan(data, threshold=threshold, vol_multiplier=vol_multiplier)
except Exception as e:
    st.error(f'Kunde inte beräkna signalerna: {e}')
    st.stop()

last = result.iloc[-1]
a, b, c, d = st.columns(4)
a.metric('Senaste kurs (kr)', f'{last.close:.2f}')
b.metric('Signalpoäng', f'{int(last.score)}/100')
c.metric('VAKTA-händelser', int(result.watch_alert.sum()))
d.metric('KÖP-händelser', int(result.buy.sum()))
st.caption('Datakälla: **' + source + '**. Antal signaler avser hela inlästa perioden, inte dagens handel.')

st.subheader('Saab B – femminutersgraf')
chart = result[['close']].rename(columns={'close':'Kurs'})
if show_ema:
    chart = chart.join(result[['ema9','ema21']].rename(columns={'ema9':'EMA 9','ema21':'EMA 21'}))
st.line_chart(chart, use_container_width=True)

signals = result.loc[result.watch_alert | result.buy, ['close','score','watch_alert','buy']].copy()
signals['Signal'] = signals.apply(lambda r: 'KÖP' if r['buy'] else 'VAKTA', axis=1)
signals = signals.rename(columns={'close':'Kurs (kr)','score':'Poäng'})[['Signal','Kurs (kr)','Poäng']]
st.subheader('Historiska signaler')
if signals.empty:
    st.info('Inga signaler under den valda perioden. Prova annan CSV eller justera inställningarna.')
else:
    st.dataframe(signals.tail(50).iloc[::-1], use_container_width=True)
    st.download_button('Ladda ner signaler som CSV', signals.to_csv().encode('utf-8'), file_name='saab_signaler.csv', mime='text/csv')

with st.expander('🔍 Originalregler och viktiga skillnader'):
    st.markdown('''**VAKTA:** EMA 9 under EMA 21 men stigande, avstånd högst 0,20 %, stigande RSI, stark volym och grön stapel. VAKTA-larm endast när villkoret blir sant efter att ha varit falskt.

**KÖP:** 20 p bullish engulfing, 15 p hammer, 15 p RSI, 15 p MACD-histogram, 20 p volym, 10 p EMA-trend, 5 p föregående avslutade 15-minuterstrend. KÖP när poängen korsar tröskeln uppåt på avslutad 5-minutersstapel.

**Obs:** VAKTA-etiketten i originalet kan visas på flera staplar; här listas endast larmövergångarna. Exakt TradingView-paritet kan påverkas av dataleverantör, EMA/RSI-startvärden, sessionshantering, aktiesplit och tidsstämplar. 15-minuterstrenden är avsedd att använda föregående avslutade 15-minutersstapel. Ingen automatisk handel eller avkastningsberäkning finns ännu.''')
with st.expander('🧠 Nyhetsanalys – nästa utvecklingssteg'):
    st.write('Här kan vi senare koppla verifierade pressmeddelanden till historiska kursreaktioner. Funktionen är ännu inte aktiv.')
st.caption('Nästa steg: verifiera Saab B-kurser och tillåten datakälla. Endast utbildnings- och analysverktyg.')
