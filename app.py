import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_only
from news_monitor import interval_minutes
from datetime import datetime, timezone

st.set_page_config(page_title='AktieRadar News AI', page_icon='📡', layout='wide')
st.markdown("""<style>
.stApp {background:#101b2b;color:#f1f5f9;}
[data-testid="stHeader"] {background:#101b2b;}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3,[data-testid="stMetricValue"],[data-testid="stMetricLabel"] {color:#f1f5f9;}
[data-testid="stCaptionContainer"] p {color:#cbd5e1;}
.stButton button,.stLinkButton a {background:#e2e8f0;color:#10243b;border-radius:10px;}
.stButton button p,.stLinkButton a p {color:#10243b;}
[data-testid="stAlert"] {background:#23364b !important;color:#f1f5f9 !important;}
[data-testid="stAlert"] * {color:#f1f5f9 !important;}
[data-testid="stCaptionContainer"] p {color:#d1dbe8 !important;}
</style>""", unsafe_allow_html=True)
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
b.metric('Gemensamma källor', len(config.get('shared_feeds', [])))
c.metric('Nyheter senaste 24 h', len(result['items']))
if not config.get('universe_complete'):
    st.warning('Ofullständig bolagstäckning. Gemensam Cision-källa är experimentell.')
if result['failures']:
    st.warning('Källfel: bevakningen är ofullständig.')
if not result['items']:
    st.info('Inga matchade nyheter vid senaste kontrollen.')
st.subheader('Senaste nyhetsspår')
for item in sorted(result['items'], key=lambda x: (x['importance'] in ('Hög','Möjligen hög'), x['published']), reverse=True):
    with st.container(border=True):
        st.subheader(item['company'])
        st.markdown('**'+item['title']+'**')
        st.write({'Positiv':'🟢','Negativ':'🔴','Blandad':'🟡','Osäker':'🟡'}.get(item['direction'],'⚪') + ' ' + item['direction'])
        st.caption(f"Publicerad: {item['published']} · {item['direction']} · Betydelse: {item['importance']}")
        st.markdown('**Ekonomisk påverkan**')
        st.write(item['economic_case'])
        st.markdown('**Risk att kontrollera**')
        st.write(item['risk'])
        profile = item.get('company_profile', {})
        if profile:
            st.markdown('**Bolagsinformation**')
            for key, label in [('totalRevenue','Omsättning'),('marketCap','Börsvärde'),('totalCash','Kassa'),('totalDebt','Skulder')]:
                value = profile.get(key)
                if isinstance(value,(int,float)):
                    currency = profile.get('currency' if key=='marketCap' else 'financialCurrency') or 'valuta okänd'
                    st.write(f'{label}: {value/1e6:,.1f} miljoner {currency}')
            if profile.get('industry'):
                st.write(profile['industry'])
            if profile.get('source'):
                st.link_button('Bolagsdata · Yahoo Finance',profile['source'])
            if profile.get('status') != 'ok':
                st.caption('Bolagsdata saknas eller är ofullständig.')
            comparison = item.get('order_comparison')
            if comparison:
                st.write(f"Belopp relativt omsättning: {comparison['revenue_ratio_pct']} %")
                st.caption(comparison['note'])
        st.link_button('Originalkälla', item['url'])
        st.caption('Regelbaserad rubrikbedömning, inte kursprognos.')
with st.expander('Källkontroll'):
    st.write(f"Dubbletter: {result['duplicates']}")
    st.dataframe(pd.DataFrame(result['diagnostics']))
st.subheader('Bevakningsschema · svensk tid')
st.table(pd.DataFrame([('07.00–09.30', '5 min'), ('09.30–16.30', '10 min'), ('16.30–18.00', '5 min'), ('18.00–07.00', '15 min')], columns=['Tid', 'Intervall']))
st.caption(f"Planerat intervall just nu: {interval_minutes(datetime.now(timezone.utc))} min. Schemalagd kontroll körs separat. Appens vy uppdateras vid omladdning eller knapptryckning.")
