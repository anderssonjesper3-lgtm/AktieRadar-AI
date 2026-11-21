"""AktieRadar AI 4.0 – ten-stock market overview; never invents market data."""
import asyncio
from datetime import datetime, timezone
import streamlit as st
import pandas as pd
from multi_engine import companies, analyze_all
from news_scanner import scan
from order_analysis import parse_order_amount, order_ratio

st.set_page_config(page_title='AktieRadar AI 4.0 – Marknadsöversikt', page_icon='📡', layout='wide')
st.title('📡 AktieRadar AI 4.0')
st.caption('MARKNADSÖVERSIKT · 10 BOLAG · NYHETER + MOMENTUM · 5-MINUTERSANALYS')
st.warning('Indikativa bevakningssignaler, inte handelsråd. Ingen automatisk orderläggning. Endast verifierad kursdata används.')
watchlist = companies()
@st.cache_data(ttl=120, show_spinner=False)
def market_snapshot():
    return asyncio.run(analyze_all())
@st.cache_data(ttl=180, show_spinner=False)
def news_snapshot():
    return scan({'companies':companies()})
if st.button('🔄 Uppdatera bevakningen'):
    market_snapshot.clear(); news_snapshot.clear(); st.rerun()
with st.spinner('Kontrollerar kursdata och nyhetsflöden...'):
    results = market_snapshot()
    try:
        articles, failures = news_snapshot()
    except Exception as exc:
        articles, failures = [], [('Nyhetsbevakning',str(exc))]
active = sum(1 for r in results if r['error'] is None)
buy = sum(1 for r in results if r['signal'] and r['signal']['kind']=='KÖP-KANDIDAT')
c1,c2,c3,c4=st.columns(4)
c1.metric('Bolag på listan',len(results)); c2.metric('Kursdata fungerar',active); c3.metric('KÖP-KANDIDAT',buy); c4.metric('Nyheter senaste 24h',len(articles))
if active<len(results):
    st.info(f'{len(results)-active} bolag saknar verifierad kursdatakoppling. De kan INTE få tekniska VAKTA/KÖP-signaler förrän ID och data verifierats.')
if not any(c.get('feeds') for c in watchlist):
    st.info('Nyhetsflöden är ännu inte konfigurerade. Nyhetsrutan visar därför inga faktiska rubriker.')
if failures:
    st.error('Nyhetsflödesfel: '+', '.join(str(f[0]) for f in failures))
st.subheader('📊 Aktieradar')
rows=[]
for r in results:
    signal=r['signal']
    rows.append({'Aktie':r['company'],'Ticker':r['ticker'],'Signal':signal['kind'] if signal else ('DATA SAKNAS' if r['error'] else 'AVVAKTA'), 'Kurs (SEK)':round(signal['close'],2) if signal else None,'Poäng':signal['score'] if signal else None,'Datastatus':r['error'] or r['status']})
st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
selected=st.selectbox('Välj aktie för detaljer', [c['name'] for c in watchlist])
company=next(c for c in watchlist if c['name']==selected)
r=next(x for x in results if x['company']==selected)
st.subheader(selected)
if r['error']:
    st.warning(r['error'])
else:
    st.write('Teknisk bedömning:',r['status'])
    if r['signal']:
        st.write('Orsaker:',', '.join(map(str,r['signal']['reasons'])))
    if r['candles']:
        df=pd.DataFrame(r['candles'])
        st.line_chart(df.set_index('time')['close'])
st.subheader('📰 Order och nyheter')
items=[a for a in articles if a['company']==selected]
if not items:
    st.caption('Inga verifierat inlästa nyheter för bolaget i den aktuella bevakningen.')
for a in items:
    st.markdown(f"**{a['category']}** · [{a['title']}]({a['url']})")
    amount=parse_order_amount(a['title'])
    ratio=order_ratio(amount,company.get('annual_revenue_sek'))
    if amount is not None:
        st.write(f'Identifierat belopp i rubriken: {amount:,.0f} SEK. Kontrollera originalkällan.')
    st.write(f'Ordervärde / årsomsättning: {ratio:.1f} %' if ratio is not None else 'Orderns relativa storlek: kan inte beräknas utan verifierat ordervärde och årsomsättning.')
st.caption('GitHub Actions kör schemalagd analys separat. Streamlit visar en aktuell ögonblicksbild vid omladdning.')
