"""AktieRadar AI 6.0 dashboard. Market data never synthesized."""
import asyncio
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from multi_engine import companies, analyze_all
from news_scanner import scan, scan_detailed
from order_analysis import parse_order_amount, order_ratio
from news_analysis import analyze_news
from news_history import update_history, load_history
from test_avanza_forbattrad import calculate_ema, calculate_rsi, calculate_macd, SWEDEN
from performance import load_journal, record_signal, update_open_trades, summary as journal_summary, trades_csv
from aktieradar_telegram import market_session
from test_avanza_forbattrad import MAX_AGE_MINUTES

st.set_page_config(page_title='AktieRadar AI 6.0',page_icon='📡',layout='wide')
st.markdown('''<style>
.stApp{background:#0c1525;color:#edf3ff}div[data-testid="stMetric"]{background:#17253b;border:1px solid #293a51;border-radius:14px;padding:16px}
div.stButton>button{background:#17253b;color:#f3f7ff !important;border:1px solid #30435c;border-radius:12px;min-height:56px;width:100%;text-align:left;font-weight:600}\n.stButton>button p,.stButton>button span,.stButton>button div{color:#f3f7ff !important;opacity:1 !important}\n.stButton>button:disabled{color:#dce7f5 !important;opacity:.85}
div.stButton>button:hover{background:#244e58;color:#f7fbff;border-color:#55e0c4}
div.stDownloadButton>button,div.stLinkButton>a,div.stFormSubmitButton>button{color:#f3f7ff !important}
div.stDownloadButton>button p,div.stLinkButton>a p,div.stFormSubmitButton>button p{color:#f3f7ff !important;opacity:1 !important}
div[data-testid="stBaseButton-secondary"],div[data-testid="stBaseButton-primary"]{color:#f3f7ff !important}

/* Consistent high-contrast text throughout AktieRadar 6.0 */
.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricValue"],
.stApp [data-testid="stMetricDelta"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stExpander"] summary,
.stApp [data-testid="stExpander"] summary p {
    color: #f3f7ff !important;
    opacity: 1 !important;
}
.stApp div.stButton > button,
.stApp div.stButton > button *,
.stApp div.stDownloadButton > button,
.stApp div.stDownloadButton > button * {
    color: #f3f7ff !important;
    opacity: 1 !important;
}
.stApp div[data-testid="stDataFrame"] { color-scheme: dark; }
.stApp a { color: #91e9ff !important; }
.stApp a:hover { color: #d1f8ff !important; }
.stApp input, .stApp textarea, .stApp select {
    color: #f3f7ff !important;
}

/* Restore legible dark foreground on Streamlit's pale alert backgrounds. */
.stApp div[data-testid="stAlert"],
.stApp div[data-testid="stAlert"] p,
.stApp div[data-testid="stAlert"] span,
.stApp div[data-testid="stAlert"] li,
.stApp div[data-testid="stAlert"] strong,
.stApp div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
    color: #17253b !important;
    opacity: 1 !important;
}
.stApp div[data-testid="stAlert"] a { color: #125a83 !important; }
</style>''',unsafe_allow_html=True)
st.title('📡 AktieRadar AI 6.0')
st.caption('MARKNADSÖVERSIKT · 10 AKTIER · FEMMINUTERSLJUS · NYHETER · SIGNALJOURNAL · DATAKONTROLL')
st_autorefresh(interval=300_000, key='aktieradar_5min_refresh')
st.warning('Analysverktyg – inga handelsråd eller automatiska köp. Kurser kan vara fördröjda.')
watchlist=companies()
@st.cache_data(ttl=240,show_spinner=False)
def market_snapshot():return asyncio.run(analyze_all())
@st.cache_data(ttl=60,show_spinner=False)
def news_snapshot():return scan_detailed({'companies':companies()}, max_age_hours=24*30)
st.caption('🟢 Skarp RSS-inhämtning är aktiv i appen när källorna svarar. Historisk import är separat och skickar inga Telegram-larm.')
if st.button('🗂️ Importera tillgängliga nyheter från senaste 30 dagarna (utan larm)', key='historical_import'):
    with st.spinner('Läser tillgängliga RSS-poster och sparar historik...'):
        try:
            older, history_failures, _ = scan_detailed({'companies': companies()}, max_age_hours=24*30)
            before = len(load_history())
            stored = update_history(older)
            st.success(f'Historisk import klar: {len(older)} matchande RSS-poster, {len(stored)-before} nya arkivposter.')
            if history_failures:
                st.warning('Källor som inte svarade: ' + ', '.join(name for name, _ in history_failures))
            st.info('RSS-flöden innehåller inte nödvändigtvis 30 dagars historik. Inga Telegram-larm skickades.')
        except Exception as exc:
            st.error(f'Historisk import misslyckades: {exc}')
if st.button('🔄 Uppdatera alla datakällor'):
    market_snapshot.clear();news_snapshot.clear();st.rerun()
with st.spinner('Kontrollerar aktier och nyheter...'):
    try:results=market_snapshot()
    except Exception as exc:
        st.error(f'Kursanalysen kunde inte starta: {exc}');st.stop()
    try:
        articles,failures,news_diagnostics=news_snapshot()
        news_archive=update_history(articles)
    except Exception as exc:
        articles,failures,news_diagnostics=[],[('Nyhetsbevakning',str(exc))],[]
        try: news_archive=update_history([])
        except Exception: news_archive=[]
by_name={r['company']:r for r in results}
ready=sum(bool(r.get('candles')) and not r.get('error') for r in results)
buys=sum(bool(r['signal']) and r['signal']['kind']=='KÖP-KANDIDAT' for r in results)
watch=sum(bool(r['signal']) and 'VAKTA' in r['signal']['kind'] for r in results)
a,b,c,d=st.columns(4)
a.metric('Bevakade aktier',len(watchlist));b.metric('Kursdata tillgänglig',f'{ready}/{len(watchlist)}');c.metric('Köpkandidater',buys);d.metric('Vakta',watch)
if any(not c.get('feeds') for c in watchlist):st.warning('Nyhetsbevakning saknar verifierat flöde för: '+', '.join(c['name'] for c in watchlist if not c.get('feeds')))
if failures:st.error('Nyhetskällor med fel: '+', '.join(x[0] for x in failures))
with st.expander('🛰️ Diagnostik för nyhetskällor', expanded=bool(failures)):
    if news_diagnostics:
        st.dataframe(pd.DataFrame(news_diagnostics).rename(columns={
            'feed':'Nyhetsflöde','companies':'Bolag','status':'Status',
            'raw_items':'Råa poster','matched':'Matchade nyheter','error':'Fel'
        }),hide_index=True,use_container_width=True)
        st.caption('Råa poster visar vad källan levererade. Matchade nyheter har passerat bolagsmatchning, datumkontroll och nyhetsfilter.')
    else:
        st.info('Ingen källdiagnostik tillgänglig ännu. Tryck på Uppdatera alla datakällor.')
    if articles:
        st.caption(f'{len(articles)} nyheter matchade i aktuell 30-dagars skanning.')
    else:
        st.caption('Inga nyheter har matchat ännu. Kontrollera råa poster och källfel ovan.')
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
st.subheader('📰 Nyheter och order')
items=[a for a in news_archive if a.get('company')==selected]
if not items:
    st.caption('Inga arkiverade nyheter för aktien ännu. Kontrollera nyhetskällediagnostiken ovan för att se om flödet svarar och levererar poster.')
    if st.toggle('🎨 Visa nyhetsanalys – designexempel', key='news_design_demo'):
        with st.container(border=True):
            st.markdown('**DEMO – INTE EN VERKLIG NYHET**')
            st.markdown('### Exempelbolaget tecknar ett nytt leveransavtal')
            st.caption('Påhittad rubrik · riktig källa och tid visas när nyheter hämtats')
            st.info('Nyhetsbedömning: PRELIMINÄRT POSITIV · invänta kurs- och volymbekräftelse')
            st.write('Framåthypotes: Positivt momentum är möjligt om marknaden bekräftar nyheten med stigande kurs och volym.')
            st.caption('Historisk träffsäkerhet kan inte beräknas utan verifierade kursdata.')
else:
    items=sorted(items, key=lambda x: x.get('published') or '', reverse=True)
    latest=items[0]
    st.markdown('**SENASTE NYHET**')
    st.markdown(f"**{latest['category']}** · [{latest['title']}]({latest['url']})")
    st.caption(f"Publicerad: {latest.get('published') or 'Okänt datum'} · Källa: {latest.get('url','').split('/')[2] if latest.get('url') else 'Okänd'}")
    latest_analysis=analyze_news(latest,c)
    st.write(f"Nyhetsbedömning: **{latest_analysis['view']}** · {latest_analysis['impact']}")
    st.write(latest_analysis['forward_hypothesis'])
    if len(items)>1:
        with st.expander(f"🗂️ Nyhetshistorik ({len(items)-1} äldre nyheter)"):
            for article in items[1:]:
                st.markdown(f"**{article.get('published') or 'Publiceringstid saknas'}** · [{article['title']}]({article['url']})")
                analysis=analyze_news(article,c)
                st.caption(f"{analysis['view']} · {analysis['impact']}")
    if st.button("🧪 Testa senaste nyhetens framåthypotes", key="historical_news_test"):
        st.session_state["historical_news_result"] = {
            "company": selected, "news_id": latest.get("id"),
            "analysis": latest_analysis,
        }
    previous=st.session_state.get("historical_news_result")
    if previous and previous.get("company")==selected and previous.get("news_id")==latest.get("id"):
        st.info("Framåthypotesen är beräknad utifrån nyhetens rubrik och RSS-beskrivning. "
                "Verkligt historiskt kursutfall är ännu inte verifierat – detta är inte ett färdigt backtest.")
        st.json({k:str(v) for k,v in previous["analysis"].items() if k != "url"})
    st.caption("Historikens beständighet beror på värdplattformens lagring. Exportera eller anslut beständig lagring innan den används som långtidsarkiv.")
with st.expander('🛠️ Kontrollcentral – alla aktier'):
    st.dataframe(pd.DataFrame([{'Bolag':x['company'],'Avanza-ID':next((c.get('order_book_id') for c in watchlist if c['name']==x['company']),None),'5-minutersljus':len(x['candles']),'Luckor':x.get('gaps'),'Signal':x['signal']['kind'] if x['signal'] else '–','Datastatus':x['error'] or x['status']} for x in results]),hide_index=True,use_container_width=True)
    st.caption('ID:n verifieras separat med verify_sources.py. Streamlit uppdateras vid omladdning; schemalagda jobb körs separat.')

# Persistent paper-trade journal (no real orders).
journal_error = None
try:
    current_prices = {}
    journal_now = datetime.now(SWEDEN)
    if market_session(journal_now):
        for row in results:
            if row.get('candles') and not row.get('error'):
                bar = row['candles'][-1]
                bar_time = bar['time']
                if bar_time.tzinfo is None:
                    bar_time = bar_time.replace(tzinfo=SWEDEN)
                age = (journal_now - (bar_time + pd.Timedelta(minutes=5))).total_seconds() / 60
                if bar_time.date() == journal_now.date() and 0 <= age <= MAX_AGE_MINUTES:
                    current_prices[row['ticker']] = float(bar['close'])
    update_open_trades(current_prices)
    for company, result in zip(watchlist, results):
        if result.get('signal') and not result.get('error'):
            record_signal(company['name'], company['ticker'], result['signal'])
    journal = load_journal()
except Exception as exc:
    journal_error = str(exc)
    journal = {'version': 1, 'events': [], 'trades': []}

st.divider()
st.subheader('📒 Signaljournal och simulerade affärer')
st.caption('Pappershandel – inga riktiga köp eller sälj. Standard: 5 000 kr, mål +2 %, stop -1 %, courtage 0,25 % (minst 1 kr) och slippage 0,10 % per sida. Endast färdiga staplar används.')
if journal_error:
    st.error('Signaljournalen kunde inte uppdateras: ' + journal_error)
else:
    stats = journal_summary(journal)
    x1, x2, x3, x4, x5 = st.columns(5)
    x1.metric('Simulerade affärer', stats['total_trades'])
    x2.metric('Öppna', stats['open_trades'])
    x3.metric('Avslutade', stats['closed_trades'])
    x4.metric('Träffsäkerhet', str(round(stats['win_rate_pct'], 1)) + '%')
    x5.metric('Realiserat netto', str(round(stats['realized_pnl_sek'], 2)) + ' kr')
    if journal['trades']:
        trades = pd.DataFrame(journal['trades'])
        st.dataframe(trades.sort_values('entry_time', ascending=False), use_container_width=True, hide_index=True)
        closed = trades[trades['status'] == 'CLOSED'].copy()
        if not closed.empty:
            closed['entry_time'] = pd.to_datetime(closed['entry_time'])
            closed = closed.sort_values('entry_time')
            closed['Kumulativt netto (kr)'] = closed['pnl_sek'].astype(float).cumsum()
            st.line_chart(closed.set_index('entry_time')['Kumulativt netto (kr)'])
        st.download_button('Exportera affärer (CSV)', data=trades_csv(journal), file_name='aktieradar_signaljournal.csv', mime='text/csv')
    else:
        st.info('Inga KÖP-KANDIDATER har ännu registrerats.')
    st.caption('Signaljournalen sparas i signal_journal.json. Exportera regelbundet om driftmiljön saknar beständig lagring.')
