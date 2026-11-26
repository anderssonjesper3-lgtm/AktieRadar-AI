import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_only, deduplicate_news
from news_monitor import interval_minutes
from datetime import datetime, timezone, timedelta

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
st.caption('Stockholm Mid Cap · Small Cap · First North · Nyhetsradar')


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
from news_followup import load_state, stamp
try:
    stored = load_state()
except (ValueError, OSError):
    stored = {}
now = datetime.now(timezone.utc)
merged = {v['item']['id']:dict(v['item'],published=stamp(v['item']['published'])) for v in stored.values()}
merged.update({i['id']:i for i in result['items']})
active = [i for i in merged.values() if timedelta(0) <= now-stamp(i['published']) < timedelta(hours=24)]
result = dict(result,items=deduplicate_news(active))
config = load_config()
covered = sum(bool(c.get('feeds')) for c in config['companies'] if c.get('segment_verified') and c.get('segment') in ('Mid Cap', 'Small Cap', 'First North'))
a,b,c = st.columns(3)
a.metric('Bolag i bevakningslistan', result['eligible_count'])
mid_count = sum(c.get('segment') == 'Mid Cap' and c.get('segment_verified') for c in config['companies'])
small_count = sum(c.get('segment') == 'Small Cap' and c.get('segment_verified') for c in config['companies'])
first_count = sum(c.get('segment') == 'First North' and c.get('segment_verified') for c in config['companies'])
st.caption(f'Mid Cap: {mid_count} · Small Cap: {small_count} · First North: {first_count}')
b.metric('Gemensamma källor', len(config.get('shared_feeds', [])))
c.metric('Nyheter senaste 24 h', len(result['items']))
if not config.get('universe_complete'):
    st.caption('Fullständig nyhetstäckning är inte verifierad.')
if result['failures']:
    st.write('⚠️ Källfel: bevakningen är ofullständig.')
if not result['items']:
    st.write('Inga matchade nyheter vid senaste kontrollen.')
st.subheader('Senaste nyhetsspår')
st.caption('Endast nyheter publicerade under de senaste 24 timmarna visas här.')
for item in sorted(result['items'], key=lambda x: (x['importance'] in ('Hög','Möjligen hög'), x['published']), reverse=True):
    direction = item.get('direction', 'Oklar')
    marker = {'Positiv':'🟢', 'Negativ':'🔴', 'Blandad':'🟡', 'Osäker':'🟠', 'Oklar':'⚪'}.get(direction, '⚪')
    score = item.get('news_score')
    score_label = f'{score}/100' if score is not None else 'Ej poängsatt'
    with st.expander(f"{marker} {item['company']} · {direction} · {score_label}", expanded=False):
        st.subheader(item['company'])
        st.markdown('**'+item['title']+'**')
        st.write({'Positiv':'🟢','Negativ':'🔴','Blandad':'🟡','Osäker':'🟠'}.get(item['direction'],'⚪') + ' ' + item['direction'])
        st.caption(f"Publicerad: {item['published']} · {item['direction']} · Betydelse: {item['importance']}")
        st.caption('Originaltext: '+('Hämtad' if item.get('article_status')=='ok' else 'Ej tillgänglig eller ej verifierad'))
        st.caption(item.get('analysis_scope', 'Analysomfattning ej verifierad'))
        if item.get('article_chars'):
            st.caption(f"Hämtad text: {item['article_chars']} tecken")
        if item.get('news_type'):
            st.write('Nyhetstyp: ' + item['news_type'])
            if item.get('news_score') is not None:
                st.metric('Nyhetens betydelse (regelbaserad)', str(item['news_score']) + '/100')
            st.write('Tillförlitlighet: ' + item.get('confidence', 'Ej bedömd'))
            st.write('Signal: ' + item.get('analysis_signal', 'AVVAKTA'))
            st.caption('Poängen är inte en sannolikhet för kursuppgång. ' + item.get('surprise', ''))
        st.caption('AI-motor: ' + item.get('ai_status', 'Ej körd'))
        st.markdown('**Vad har hänt?**')
        st.write(item.get('summary_sv','Svensk sammanfattning saknas.'))
        facts = item.get('article_facts',{})
        if facts.get('excerpts'):
            with st.expander('Viktiga uppgifter ur originalnyheten'):
                for excerpt in facts['excerpts']:
                    st.write(excerpt)
                st.caption(facts['note'])
        if item.get('analysis_evidence'):
            with st.expander('Underlag för nyhetsanalysen'):
                for sentence in item['analysis_evidence']:
                    st.write(sentence)
        if item.get('article_text'):
            with st.expander('Hämtad originaltext'):
                st.write(item['article_text'])
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
        st.markdown('**Marknadens reaktion**')
        entry = stored.get(item['id'],{})
        observations = entry.get('observations',{})
        if not observations:
            st.write('Väntar på schemalagd kurskontroll.')
        for slot, obs in sorted(observations.items(),key=lambda pair:int(pair[0])):
            st.write(f"+{slot} min: {obs['status']}")
            if obs['status']=='OK':
                st.write(f"Kursreaktion: {obs['change_pct']:+.2f} % · Relativ volym: {obs['relative_volume']:.2f}×")
                st.write(obs['momentum']+' momentum · '+obs['reaction'])
                st.caption(f"Stapelslut: {obs['bar_end']} · Dataålder vid kontroll: {obs['age_minutes']} min")
        st.link_button('Originalkälla', item['url'])
        st.caption('Regelbaserad bedömning med originalutdrag när tillgängliga, inte kursprognos.')
with st.expander('Källkontroll'):
    st.write(f"Dubbletter: {result['duplicates']}")
    st.dataframe(pd.DataFrame(result['diagnostics']))
    for source in result['diagnostics']:
        st.markdown('**' + source['feed'] + '**')
        st.write(f"Inlästa: {source['raw_items']} · Matchade: {source['matched']}")
        samples = source.get('sample_headlines', [])
        if samples:
            st.dataframe(pd.DataFrame(samples))
st.subheader('Bevakningsschema · svensk tid')
st.table(pd.DataFrame([('Hela dygnet', '5 min')], columns=['Tid', 'Planerat intervall']))
st.caption(f"Planerat intervall just nu: {interval_minutes(datetime.now(timezone.utc))} min. Schemalagd kontroll körs separat. Appens vy uppdateras vid omladdning eller knapptryckning.")
