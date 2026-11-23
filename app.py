"""AktieRadar AI 6.0 dashboard. Market data never synthesized."""
import asyncio
from datetime import datetime, timezone
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import importlib
import multi_engine
importlib.reload(multi_engine)
from multi_engine import companies
from news_scanner import scan, scan_detailed
from order_analysis import parse_order_amount, order_ratio
from news_analysis import analyze_news
from news_momentum import evaluate_news_momentum
from news_history import update_history, load_history
from test_avanza_forbattrad import calculate_ema, calculate_rsi, calculate_macd, SWEDEN
from performance import load_journal, record_signal, update_open_trades, evaluate_smart_exit, summary as journal_summary, trades_csv
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
if st.button('₿ Öppna KryptoRadar – Bitcoin, Ethereum och Solana', key='open_kryptoradar'):
    st.switch_page('pages/KryptoRadar.py')
st.caption('10 AKTIER · AVANZA MED UPP TILL 20 MIN FÖRDRÖJNING · MOMENTUM · NYHETER · SIGNALJOURNAL')
st_autorefresh(interval=300_000, key='aktieradar_5min_refresh')
st.warning('Analysverktyg – inga handelsråd eller automatiska köp. Kurser kan vara fördröjda.')
if not market_session(datetime.now(SWEDEN)):
    st.info('⏰ Börsen är stängd just nu. Tekniska signaler kan saknas eller visas som gamla tills nya verifierade femminutersstaplar finns efter öppning. Historik ska inte raderas.')
watchlist=companies()
@st.cache_data(ttl=90,show_spinner=False)
def market_snapshot_v3():return asyncio.run(multi_engine.analyze_all())
@st.cache_data(ttl=60,show_spinner=False)
def news_snapshot():return scan_detailed({'companies':companies()}, max_age_hours=24*30)
st.caption('Nyheter hämtas från bolagens officiella press- och investerarsidor. Historisk import skickar inga larm.')
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
    market_snapshot_v3.clear();news_snapshot.clear();st.rerun()
with st.spinner('Kontrollerar aktier och nyheter...'):
    try:results=market_snapshot_v3()
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
fresh=sum(bool(r.get('data_fresh')) and not r.get('error') for r in results)
buys=sum(bool(r['signal']) and r['signal']['kind']=='KÖP-KANDIDAT' for r in results)
watch=sum(bool(r['signal']) and 'VAKTA' in r['signal']['kind'] for r in results)
a,b,c,d=st.columns(4)
a.metric('Bevakade aktier',len(watchlist));b.metric('Kursdata finns',f'{ready}/{len(watchlist)}',help=f'{fresh}/{len(watchlist)} aktier har avslut inom senaste 20 minuterna. Äldre observerade ljus visas också.');c.metric('Köpkandidater',buys);d.metric('Vakta',watch)
if ready == 0:
    st.info('Inga observerade kursljus har hämtats ännu. Kontrollera att datakällan svarar.')
elif fresh == 0:
    st.caption('Historiska kursljus finns, men inga av de senaste avsluten är verifierat inom 20 minuter. Analysen visar tillgänglig historik utan nya köpsignaler.')
if any(not c.get('feeds') for c in watchlist):st.warning('Nyhetsbevakning saknar verifierat flöde för: '+', '.join(c['name'] for c in watchlist if not c.get('feeds')))
if failures:st.error('Nyhetskällor med fel: '+', '.join(x[0] for x in failures))
st.subheader('🧭 Nyhet → momentum → signal')
st.caption('En positiv bolagsnyhet sätter aktien under bevakning. KÖP-KANDIDAT kräver bekräftade observerade kursljus och volym. Ingen order läggs.')
news_signal_rows = []
for company in watchlist:
    result = by_name.get(company['name'], {})
    assessment = evaluate_news_momentum(company, articles, result.get('candles') or [], now=datetime.now(SWEDEN))
    news_signal_rows.append({
        'Aktie': company['name'],
        'Nyhetsmomentum': assessment['kind'],
        'Reaktion %': assessment.get('move_pct'),
        'Datans ålder (min)': assessment.get('age_minutes'),
        'Bedömning': assessment.get('reason'),
    })
st.dataframe(pd.DataFrame(news_signal_rows), hide_index=True, use_container_width=True)
st.caption('Fördröjda ljus kan ge en sen signal. Kontrollera aktuell kurs och spread i Avanza; simulering använder inte den gamla ljuskursen som exekvering.')
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
news_assessment = evaluate_news_momentum(c, articles, r.get('candles') or [], now=datetime.now(SWEDEN))
if news_assessment.get('news'):
    st.info('Nyhetsmomentum: ' + news_assessment['kind'] + ' · ' + news_assessment['reason'])
    if news_assessment.get('move_pct') is not None:
        st.caption(f"Observerad reaktion efter nyheten: {news_assessment['move_pct']:+.2f} % · Datans ålder: {news_assessment.get('age_minutes', 'okänd')} min")

if r.get('last_trade_time'):
    st.caption(f"Senaste faktiska avslut: {r['last_trade_time']} · Ålder: {r.get('data_age_minutes')} minuter")
if r.get('data_reason'):
    st.warning('Datakontroll: ' + r['data_reason'] + '. Ingen ny köpsignal ges från denna kurs.')
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
    st.caption(f"Senaste färdiga ljus: {df.time.iloc[-1]} · Antal: {len(df)} · Observerade femminutersljus (gles handel tillåts)")
else:st.caption('Inga observerade femminutersljus att visa ännu.')
st.subheader('📰 Senaste bolagsnyheter och analys')
selected_source = next((x for x in c.get('feeds', []) if x.startswith('https://')), None)
if selected_source:
    st.caption('Officiell nyhetskälla för ' + selected + ': ' + selected_source)
    st.markdown(f'[Öppna bolagets officiella nyhetssida]({selected_source})')
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
# Persistent paper-trade journal (no real orders).
journal_error = None
try:
    import importlib
    import journal_store
    importlib.reload(journal_store)  # Streamlit hot reload can retain the older module in sys.modules
    import os
    try:
        token = st.secrets.get('AKTIERADAR_JOURNAL_TOKEN')
        repo = st.secrets.get('AKTIERADAR_JOURNAL_REPO')
    except Exception:
        token, repo = None, None
    if token:
        os.environ['AKTIERADAR_JOURNAL_TOKEN'] = token
    if repo:
        os.environ['AKTIERADAR_JOURNAL_REPO'] = repo
    os.environ.setdefault('AKTIERADAR_JOURNAL_REPO', 'anderssonjesper3-lgtm/AktieRadar-AI')
    journal = journal_store.read_public_snapshot()
except Exception as exc:
    journal_error = str(exc)
    journal = {'version': 1, 'events': [], 'trades': []}

st.divider()
st.subheader('📒 Signaljournal och simulerade affärer')
st.caption('Pappershandel – inga riktiga köp eller sälj. Standard: 5 000 kr, stop-loss -1 % och teknisk SÄLJ-signal. Ingen automatisk vinsthemtagning vid +2 %. Courtage 0,25 % (minst 1 kr) och slippage 0,10 % per sida. Endast färdiga staplar används.')
if journal_error:
    st.error('Signaljournalen kunde inte läsas (ingen historik har raderats): ' + journal_error)
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
        if 'exit_signal_status' not in trades.columns:
            trades['exit_signal_status'] = trades['status'].map(lambda x: 'AVSLUTAD' if x == 'CLOSED' else 'BEHÅLL – inväntar signal')
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
    st.caption('Öppna affärer följs tills teknisk SÄLJ-KANDIDAT bekräftas eller stop-loss -1 % nås. +2 % är endast en resultatnivå, inte en säljordernivå.')
    st.caption('Journalen läses från GitHub och uppdateras endast av den schemalagda roboten. Appen gör inga egna simulerade affärer.')
