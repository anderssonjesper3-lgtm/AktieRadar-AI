import asyncio
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_pilot

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
        st.caption(f"Publicerad: {item['published']} · VAKTA · Regelpoäng {item['score']}/100 (ej sannolikhet)")
        st.write(item['reason'])
        q = item['quote']
        if q.get('error') or not q.get('candles'):
            st.warning(q.get('error') or 'Kursdata saknas')
        else:
            df = pd.DataFrame(q['candles']).sort_values('time').set_index('time')
            st.caption(f"Avanza · Senaste ljus: {df.index[-1]} · Ålder: {q.get('last_candle_age_minutes', 'okänd')} min")
            st.line_chart(df['close'])
            st.bar_chart(df['volume'])
        st.caption('Smart Exit ej verifierad. Ingen köp- eller säljnotis från fördröjd kurs.')
with st.expander('Källkontroll'):
    st.dataframe(pd.DataFrame(result['diagnostics']))
st.caption('Kontroll vid öppning/omladdning; cache 5 minuter. Automatisk bakgrundsbevakning ännu ej ansluten.')
