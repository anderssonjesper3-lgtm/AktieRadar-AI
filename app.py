"""AktieRadar 5.0 dashboard. Market data never synthesized."""
import asyncio
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from multi_engine import companies, analyze_all
from news_scanner import scan
from order_analysis import parse_order_amount, order_ratio
from test_avanza_forbattrad import calculate_ema, calculate_rsi, calculate_macd, SWEDEN

st.set_page_config(page_title='AktieRadar AI 5.0',page_icon='📡',layout='wide')
st.markdown('''<style>
.stApp{background:#0c1525;color:#edf3ff}div[data-testid="stMetric"]{background:#17253b;border:1px solid #293a51;border-radius:14px;padding:16px}
div.stButton>button{background:#17253b;color:#f3f7ff !important;border:1px solid #30435c;border-radius:12px;min-height:56px;width:100%;text-align:left;font-weight:650}\n.stButton>button p,.stButton>button span,.stButton>button div{color:#f3f7ff !important;opacity:1 !important}\n.stButton>button:disabled{color:#dce7f5 !important;opacity:.9}\n.stDownloadButton>button,.stDownloadButton>button p{color:#f3f7ff !important}
div.stButton>button:hover{background:#244e58;color:white;border-color:#55e0c4}
</style>''',unsafe_allow_html=True)
st.title('📡 AktieRadar AI 5.0')
st.caption('MARKNADSÖVERSIKT · 10 AKTIER · FEMMINUTERSLJUS · NYHETER · DATAKONTROLL')
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
if not any(c.get('feeds') for c in watchlist):st.info('Nyhetsflöden är inte anslutna. Inga nyheter har verifierats.')
if failures:st.error('Nyhetskällor med fel: '+', '.join(x[0] for x in failures))
st.subheader('📡 Realtidsmotor – integrationsstatus')
with st.container(border=True):
    st.warning('Experimentell integration. Ingen verifierad strömmande realtidskälla är ansluten ännu.')
    m1,m2,m3=st.columns(3)
    m1.metric('Dataleverantör','Avanza historik')
    m2.metric('Streaming','Ej ansluten')
    m3.metric('Realtid verifierad','Nej')
    st.caption('Den befintliga kursanalysen körs separat. Gröna enhetstester är inte ett bevis på livekurser.')
    with st.expander('🔍 Diagnostik och nästa steg'):
        st.write('Avanza SSE: experimentell brygga skapad, kräver autentiserad session och separat drift.')
        st.write('Alternativ minutdatamotor: implementerad och enhetstestad, men inte ansluten till API.')
        st.write('Signaler från ny strömningsmotor: avstängda tills kurskälla, tidsstämplar och licens är verifierade.')
# Optional public-source diagnostic; not an input to trading signals.
with st.expander('🧪 Saab B – experimentell kurskontroll (Yahoo, endast diagnostik)'):
    st.caption('Kursen hämtas på begäran. Ingen realtids- eller handelslicens verifierad. Inte kopplad till VAKTA/KÖP.')
    if st.button('🔎 Kontrollera senaste Saab B-kurs', key='yahoo_probe_button'):
        try:
            import json
            import urllib.request
            from datetime import datetime, timezone
            req=urllib.request.Request('https://query1.finance.yahoo.com/v8/finance/chart/SAAB-B.ST?interval=1m&range=1d',headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=12) as response:
                payload=json.load(response)
            chart=(payload.get('chart',{}).get('result') or [])[0]
            meta=chart.get('meta',{})
            stamps=chart.get('timestamp') or []
            closes=(chart.get('indicators',{}).get('quote') or [{}])[0].get('close') or []
            valid=[(t,p) for t,p in zip(stamps,closes) if isinstance(p,(int,float)) and p>0]
            if meta.get('symbol')!='SAAB-B.ST' or meta.get('currency')!='SEK' or not valid:
                raise ValueError('Instrument, valuta eller kursdata kunde inte verifieras')
            t,price=valid[-1]
            observed=datetime.fromtimestamp(t,timezone.utc)
            age=(datetime.now(timezone.utc)-observed).total_seconds()
            st.metric('Senaste observerade Saab B-kurs',f'{price:.2f} kr')
            # Visual-only preview of real observed minute candles; never enter the signal engine.
            minute_rows=[]
            q=(chart.get('indicators',{}).get('quote') or [{}])[0]
            for idx,ts in enumerate(stamps):
                try:
                    o,h,l,cl,v=(q.get(k) or [])[idx] for k in ('open','high','low','close','volume')
                    if all(isinstance(z,(int,float)) and z>0 for z in (o,h,l,cl)):
                        minute_rows.append({'time':datetime.fromtimestamp(ts,timezone.utc),'open':o,'high':h,'low':l,'close':cl,'volume':v or 0})
                except (IndexError,TypeError):
                    continue
            if minute_rows:
                minute_df=pd.DataFrame(minute_rows).set_index('time').sort_index()
                # Exclude the currently forming 5-minute bar; incomplete periods must not be scored.
                five=minute_df.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
                counts=minute_df['close'].resample('5min').count()
                five=five[counts==5].dropna()
                st.caption(f'Faktiska minutposter: {len(minute_df)} · Kompletta femminutersstaplar: {len(five)}')
                if not five.empty:
                    preview=go.Figure(go.Candlestick(x=five.index,open=five.open,high=five.high,low=five.low,close=five.close,name='Saab B – observationsdata'))
                    preview.update_layout(template='plotly_dark',height=360,xaxis_rangeslider_visible=False,margin=dict(l=10,r=10,t=20,b=10))
                    st.plotly_chart(preview,use_container_width=True)
                    st.caption('Förhandsvisning – inte ansluten till automatisk signalgenerering.')
            st.write(f'Källtidsstämpel (UTC): {observed.isoformat()} · Ålder: {age:.1f} sekunder')
            st.warning('Experimentell källa. Tidsstämpelns ålder bevisar inte exekverbar börskurs eller tillåten användning för handel.')
        except Exception as exc:
            st.error(f'Kurskontroll misslyckades: {type(exc).__name__}: {exc}')
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
    st.caption(f"Senaste färdiga ljus: {df.time.iloc[-1]} · Antal: {len(df)} · Luckor: {r.get('gaps','okänt')}")
else:st.warning('Ingen verifierad komplett femminutersstapel att visa.')
st.subheader('📰 Förhandsvisning: nya nyhetsanalysen')
st.caption('DESIGNDEMO · Exempeltext, inte en verklig eller verifierad nyhet. Ingen handelssignal.')
with st.container(border=True):
    st.markdown('**SENASTE NYHET · DEMO**')
    st.markdown('**Exempelbolaget tecknar ett nytt leveransavtal**')
    st.caption('Exempelrubrik · publiceringstid och källa visas här när riktiga data finns')
    st.write('**Nyhetsbedömning:** Möjligen positiv – kräver bekräftelse från kurs och volym.')
    st.write('**Framåthypotes:** Om kursen stiger med högre volym efter publiceringen kan momentum fortsätta. Detta är inte en prognos.')
    if st.button('🧪 Förhandsvisa nyhetstest', key='preview_news_test'):
        st.info('Här ska vi jämföra en tidsstämplad nyhetsbedömning med verifierade historiska kursdata. Testresultat visas först när dessa finns.')
    with st.expander('🗂️ Så kommer nyhetshistoriken att visas'):
        st.caption('Äldre verifierade nyheter listas med datum, källa och bedömning. Inga exempel presenteras som verkliga nyheter.')
st.caption('Detta är en visuell förhandsvisning i 5.0. Den fullständiga nyhetsmotorn utvecklas separat i 6.0.')
st.subheader('📰 Nyheter och order')
items=[a for a in articles if a['company']==selected]
if not items:st.caption('Inga verifierat inlästa nyheter i anslutna flöden.')
for a in items:
    st.markdown(f"**{a['category']}** · [{a['title']}]({a['url']})")
    amount=parse_order_amount(a['title']);ratio=order_ratio(amount,c.get('annual_revenue_sek'))
    if amount is not None:st.write(f'Belopp upptäckt i rubrik: {amount:,.0f} kr (ej bekräftat ordervärde)')
    st.caption(f'Preliminär beloppskvot: {ratio:.2f} % – kontrollera originaltexten' if ratio is not None else 'Relativ orderstorlek kan inte verifieras')
with st.expander('🛠️ Kontrollcentral – alla aktier'):
    st.dataframe(pd.DataFrame([{'Bolag':x['company'],'Avanza-ID':next((c.get('order_book_id') for c in watchlist if c['name']==x['company']),None),'5-minutersljus':len(x['candles']),'Luckor':x.get('gaps'),'Signal':x['signal']['kind'] if x['signal'] else '–','Datastatus':x['error'] or x['status']} for x in results]),hide_index=True,use_container_width=True)
    st.caption('ID:n verifieras separat med verify_sources.py. Streamlit uppdateras vid omladdning; schemalagda jobb körs separat.')
