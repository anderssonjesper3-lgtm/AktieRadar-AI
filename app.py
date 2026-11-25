import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_only

st.set_page_config(page_title='AktieRadar News AI', page_icon='📡', layout='wide')
st.title('📡 AktieRadar News AI')
st.caption('Stockholm Mid Cap & Small Cap · Nyhetspilot')
st.info('Nyheter och ekonomisk bedömning. Ingen kursinsamling eller handel i denna version.')

@st.cache_data(ttl=300, show_spinner=False)
def snapshot():
    return run_news_only(load_config())

if st.button('Uppdatera nyhetsradar'):
    snapshot.clear()
    st.rerun()
try:
    with st.spinner('Kontrollerar nyhetskällor'):
        result = snapshot()
except Exception as exc:
    st.error(f'Nyhetskontroll misslyckades: {type(exc).__name__}')
    st.stop()
config = load_config()
covered = sum(bool(c.get('feeds')) for c in config['companies'] if c.get('segment_verified') and c.get('segment') in ('Mid Cap', 'Small Cap'))
a,b,c = st.columns(3)
a.metric('Bolag i pilotlistan', result['eligible_count'])
b.metric('Bolag med källa', covered)
c.metric('Nyheter senaste 24 h', len(result['items']))
if not config.get('universe_complete'):
    st.warning('Ofullständig bolagstäckning. Gemensamma nyhetskällor ännu inte anslutna.')
if result['failures']:
    st.warning('Källfel: bevakningen är ofullständig.')
if not result['items']:
    st.info('Inga matchade nyheter vid senaste kontrollen.')
for item in result['items']:
    with st.container(border=True):
        st.subheader(item['company'])
        st.write(item['title'])
        st.caption(f"Publicerad: {item['published']} · {item['direction']} · Betydelse: {item['importance']}")
        st.markdown('**Ekonomisk påverkan**')
        st.write(item['economic_case'])
        st.markdown('**Risk att kontrollera**')
        st.write(item['risk'])
        st.link_button('Originalkälla', item['url'])
        st.caption('Regelbaserad rubrikbedömning, inte kursprognos.')
with st.expander('Källkontroll'):
    st.write(f"Dubbletter: {result['duplicates']}")
    st.dataframe(pd.DataFrame(result['diagnostics']))
st.caption('Uppdatering vid öppning eller knapptryckning. Cache 5 minuter; ingen bakgrundsbevakning ännu.')
