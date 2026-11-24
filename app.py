import asyncio
from multi_engine import analyze_company
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_pilot, smart_exit, simulated_result, update_paper_journal

st.set_page_config(page_title='AktieRadar News AI', page_icon='📡', layout='wide')
st.title('📡 AktieRadar News AI')
st.caption('Mid Cap & Small Cap · Nyheter först · Fördröjd kursdata')
st.warning('Prototyp. Kontrollera aktuell kurs hos mäklaren. Inga automatiska order.')
@st.cache_data(ttl=300, show_spinner=False)
def snapshot():
    return asyncio.run(run_news_pilot(load_config()))
if st.button('Uppdatera nyhetsradar'):
    snapshot.clear()
    st.rerun()
try:
    with st.spinner('Kontrollerar nyhetskällor'):
        result = snapshot()
except Exception as exc:
    st.error(f'Nyhetskontroll misslyckades: {type(exc).__name__}')
    st.stop()
a,b,c = st.columns(3)
a.metric('Verifierat segment i listan', result['eligible_count'])
b.metric('Intressanta nyheter', len(result['candidates']))
c.metric('Aktier med begärd kursdata', result['quote_count'])
config = load_config()
covered = sum(bool(c.get('feeds')) for c in config['companies'] if c.get('segment_verified') and c.get('segment') in ('Mid Cap', 'Small Cap'))
st.caption(f'Konfigurerade nyhetskällor: {covered}/{result["eligible_count"]} verifierade bolag')
if not config.get('universe_complete'):
    st.warning('Bolagslistan är ofullständig; siffrorna avser endast pilotlistan.')
if not result['eligible_count']:
    st.warning('Bolagsuniversum ännu inte verifierat. Ingen aktiv bevakning.')
elif result['failures']:
    st.warning('Vissa nyhetskällor kunde inte läsas. Bevakningen är ofullständig.')
elif not result['candidates']:
    st.info('Inga nyheter passerade filtret vid senaste kontrollen.')
for item in result['candidates']:
    with st.container(border=True):
        st.subheader(item['company'])
        st.write(item['title'])
        st.link_button('Originalkälla', item['url'])
        st.caption(f"Publicerad: {item['published']} · {item['kind']} · Regelpoäng {item['score']}/100 (ej sannolikhet)")
        st.write(item['reason'])
        st.markdown('**Ekonomisk betydelse**')
        st.write(item['economic_case'])
        st.markdown('**Risk att kontrollera**')
        st.write(item['risk'])
        st.caption('Regelbaserad bedömning, inte verifierad AI-analys av hela pressmeddelandet.')
        q = item['quote']
        if q.get('error') or not q.get('candles'):
            st.warning(q.get('error') or 'Kursdata saknas')
        else:
            df = pd.DataFrame(q['candles']).sort_values('time').set_index('time')
            st.caption(f"Avanza · Senaste ljus: {df.index[-1]} · Ålder: {q.get('last_candle_age_minutes', 'okänd')} min")
            st.line_chart(df['close'])
            st.bar_chart(df['volume'])
        st.caption('Endast analyskandidat. Kontrollera aktuell kurs; ingen automatisk order.')
with st.expander('Källkontroll'):
    st.dataframe(pd.DataFrame(result['diagnostics']))
st.caption('Kontroll vid öppning/omladdning; cache 5 minuter. Automatisk bakgrundsbevakning ännu ej ansluten.')

with st.expander('Smart Exit och simulerad affär'):
    st.caption('Manuell kalkyl, inte automatisk journal. Använd observerade priser.')
    entry = st.number_input('Ingångskurs', min_value=0.01, value=100.0)
    peak = st.number_input('Högsta observerade kurs sedan köp', min_value=0.01, value=100.0)
    current = st.number_input('Aktuell observerad kurs', min_value=0.01, value=100.0)
    qty = st.number_input('Antal aktier', min_value=1, value=50)
    fee = st.number_input('Courtage per sida (kr)', min_value=0.0, value=0.0)
    slip = st.number_input('Slippage per sida (%)', min_value=0.0, max_value=10.0, value=0.1)
    if peak >= max(entry, current):
        st.write(smart_exit(entry, peak, current))
        net = simulated_result(entry, current, qty, fee, slip)
        st.metric('Simulerat netto (kr)', net['net_sek'])
        st.metric('Simulerat netto (%)', net['net_pct'])
    else:
        st.warning('Högsta kurs måste vara minst ingångskurs och aktuell kurs.')

st.subheader('Simulerad signaljournal')
st.caption('Experimentell sessionsjournal · 5 000 kr per position · fördröjda observationer. Nollställs när sessionen försvinner.')
journal = st.session_state.setdefault('paper_journal', {})
observations = {item['company']: item['quote'] for item in result['candidates']}
async def follow_positions():
    config = {c['name']: c for c in load_config()['companies']}
    for name in journal.get('positions', {}):
        if name not in observations and name in config:
            observations[name] = await analyze_company(dict(config[name], feeds=[]))
asyncio.run(follow_positions())
events = update_paper_journal(journal, result['candidates'], observations)
for event in events:
    st.info(f"{event['company']}: {event['kind']} · {event['time']}")
closed = journal.get('closed', [])
st.metric('Simulerat netto (kr)', round(sum(t['net_sek'] for t in closed), 2))
st.metric('Avslutade affärer', len(closed))
if closed:
    st.dataframe(pd.DataFrame(closed))
if journal.get('positions'):
    st.dataframe(pd.DataFrame(journal['positions'].values()))
