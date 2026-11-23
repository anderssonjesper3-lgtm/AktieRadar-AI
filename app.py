"""AktieRadar 5.0 dashboard. Market data never synthesized."""
import asyncio
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from multi_engine import companies, analyze_all
from news_scanner import scan
from test_avanza_forbattrad import calculate_ema, calculate_rsi, calculate_macd, SWEDEN

st.set_page_config(page_title='AktieRadar AI 5.0',page_icon='📡',layout='wide')
st.markdown('''<style>
.stApp{background:#0c1525;color:#edf3ff}div[data-testid="stMetric"]{background:#17253b;border:1px solid #293a51;border-radius:14px;padding:16px}
div.stButton>button{background:#17253b;color:#f3f7ff !important;border:1px solid #30435c;border-radius:12px;min-height:56px;width:100%;text-align:left;font-weight:650}\n.stButton>button p,.stButton>button span,.stButton>button div{color:#f3f7ff !important;opacity:1 !important}\n.stButton>button:disabled{color:#dce7f5 !important;opacity:.9}\n.stDownloadButton>button,.stDownloadButton>button p{color:#f3f7ff !important}
div.stButton>button:hover{background:#244e58;color:white;border-color:#55e0c4}
</style>''',unsafe_allow_html=True)
st.title('📡 AktieRadar AI 5.0')
st.caption('MARKNADSÖVERSIKT · 10 AKTIER · FEMMINUTERSLJUS · MOMENTUM · VOLYM · NYHETER')
st.warning('Analysverktyg – inga handelsråd eller automatiska köp. Kurser kan vara fördröjda.')
watchlist=companies()
@st.cache_data(ttl=120,show_spinner=False)
def market_snapshot():return asyncio.run(analyze_all())
@st.cache_data(ttl=180,show_spinner=False)
def news_snapshot():return scan({'companies':companies()})
if st.button('🔄 Uppdatera alla datakällor'):
    market_snapshot.clear();news_snapshot.clear();st.rerun()
with st.spinner('Kontrollerar aktier och nyheter...'):
    try:results=market_snapshot()
    except Exception as exc:
        st.error(f'Kursanalysen kunde inte starta: {exc}');st.stop()
    try:articles,failures=news_snapshot()
    except Exception as exc:articles,failures=[],[('Nyhetsbevakning',str(exc))]
by_name={r['company']:r for r in results}
ready=sum(bool(r.get('candles')) and not r.get('error') for r in results)
buys=sum(bool(r['signal']) and r['signal']['kind']=='KÖP-KANDIDAT' for r in results)
watch=sum(bool(r['signal']) and 'VAKTA' in r['signal']['kind'] for r in results)
a,b,c,d=st.columns(4)
a.metric('Bevakade aktier',len(watchlist));b.metric('Kursdata tillgänglig',f'{ready}/{len(watchlist)}');c.metric('Köpkandidater',buys);d.metric('Vakta',watch)
if not any(c.get('feeds') for c in watchlist):st.warning('Nyhetsanalysen är ännu inte ansluten: samtliga 10 aktier saknar konfigurerade RSS-flöden.')
if ready == 0:
    st.error('0/10: Ingen aktie har användbara kursstaplar. Se felorsaker i kontrollcentralen. Det är ett anslutningsproblem, inte en negativ marknadssignal.')
if failures:st.error('Nyhetskällor med fel: '+', '.join(x[0] for x in failures))
st.subheader('📊 Avanza – fördröjd marknadsanalys')
st.caption('5-minutersljus · momentum · relativ volym · nyhetsbevakning · högst 20 minuters ålder under handelstid.')
st.info('Kandidater är informationssignaler, inte order. Kontrollera aktuell kurs i Avanza före köp eller försäljning.')
st.subheader('🎯 Välj aktie')
if 'selected_stock' not in st.session_state:st.session_state.selected_stock=watchlist[0]['name']
ordered=sorted(watchlist,key=lambda c: {'KÖP-KANDIDAT':0,'VAKTA':1,'MORGON-VAKTA':2}.get((by_name.get(c['name']) or {}).get('signal',{}).get('kind') if (by_name.get(c['name']) or {}).get('signal') else '',3))
for i in range(0,len(ordered),5):
    cols=st.columns(5)
    for col,c in zip(cols,ordered[i:i+5]):
        r=by_name.get(c['name'],{});s=r.get('signal');status=s['kind'] if s else ('DATA SAKNAS' if r.get('error') else 'AVVAKTA')
        if col.button(f"{c['name']}\n\n{status}",key='stock_'+c['ticker']):st.session_state.selected_stock=c['name']
selected=st.session_state.selected_stock
c=next(c for c in watchlist if c['name']==selected);r=by_name[selected]
st.divider();st.subheader(f"📊 {selected} · {c['ticker']}")
st.write('Datastatus:',r.get('error') or r['status'])
st.caption('Nyhetsstatus: '+r.get('news_status','ej kontrollerad'))
if r.get('signal'):
    s=r['signal'];st.info(f"{s['kind']} · {s['score'] if s['score'] is not None else 'Poäng saknas'} · {', '.join(map(str,s['reasons']))}")
if r['candles']:
    df=pd.DataFrame(r['candles']).sort_values('time');close=df['close'].tolist()
    df['EMA 9']=calculate_ema(close,9);df['EMA 21']=calculate_ema(close,21)
    fig=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=.05,row_heights=[.65,.18,.17],subplot_titles=('5-minutersljus','Volym','RSI 14'))
    fig.add_trace(go.Candlestick(x=df.time,open=df.open,high=df.high,low=df.low,close=df.close,name='OHLC'),row=1,col=1)
    fig.add_trace(go.Scatter(x=df.time,y=df['EMA 9'],name='EMA 9',line=dict(color='#f5c76b')),row=1,col=1)
    fig.add_trace(go.Scatter(x=df.time,y=df['EMA 21'],name='EMA 21',line=dict(color='#4c91e8')),row=1,col=1)
    fig.add_trace(go.Bar(x=df.time,y=df.volume,name='Volym',marker_color='#4ba3a5'),row=2,col=1)
    fig.add_trace(go.Scatter(x=df.time,y=calculate_rsi(close,14),name='RSI 14',line=dict(color='#b58bea')),row=3,col=1)
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0c1525',plot_bgcolor='#0c1525',height=650,xaxis_rangeslider_visible=False,margin=dict(l=10,r=10,t=55,b=10))
    st.plotly_chart(fig,use_container_width=True)
    macd,signal,hist=calculate_macd(close)
    st.caption(f"MACD histogram (senaste): {hist[-1]:.4f}" if hist and hist[-1] is not None else 'MACD: otillräcklig historik')
    st.caption(f"Senaste färdiga ljus: {df.time.iloc[-1]} · Ålder: {r.get('last_candle_age_minutes','okänt')} min · Antal: {len(df)} · Luckor: {r.get('gaps','okänt')}")
else:st.warning('Ingen verifierad komplett femminutersstapel att visa.')
st.subheader('📰 Nyheter och nyhetssignaler')
items=[a for a in articles if a['company']==selected]
if not items:st.caption('Inga verifierat inlästa nyheter i anslutna flöden.')
for a in items:
    st.markdown(f"**{a['category']}** · [{a['title']}]({a['url']})")
    st.caption('Nyheten är en bevakningssignal, inte ett verifierat köp- eller säljbeslut.')
with st.expander('🛠️ Kontrollcentral – alla aktier'):
    st.dataframe(pd.DataFrame([{'Bolag':x['company'],'Avanza-ID':next((c.get('order_book_id') for c in watchlist if c['name']==x['company']),None),'5-minutersljus':len(x['candles']),'Luckor':x.get('gaps'),'Signal':x['signal']['kind'] if x['signal'] else '–','Datastatus':x['error'] or x['status']} for x in results]),hide_index=True,use_container_width=True)
    st.caption('ID:n verifieras separat med verify_sources.py. Streamlit uppdateras vid omladdning; schemalagda jobb körs separat.')
