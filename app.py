import pandas as pd
import streamlit as st
from news_scanner import load_config
from news_ai_pilot import run_news_only, deduplicate_news
from news_monitor import interval_minutes
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title='MidCap News', page_icon='📈', layout='wide')
st.markdown("""<style>
.stApp, [data-testid="stHeader"] {background:#0B1424;color:#F1F5F9;}
.stApp p,.stApp label,.stApp h1,.stApp h2,.stApp h3 {color:#F1F5F9;}
[data-testid="stCaptionContainer"] p {color:#B9C9DB !important;}
[data-testid="stMetric"] {background:#17263B;border:1px solid #263B50;border-radius:14px;padding:14px;}
[data-testid="stMetricValue"] {color:#26D9C7 !important;font-weight:700;}
[data-testid="stMetricLabel"] * {color:#CBD5E1 !important;}
[data-testid="stExpander"] details {background:#17263B;border:1px solid #263B50;border-radius:12px;}
[data-testid="stExpander"] summary {padding:14px;color:#F1F5F9;}
[data-testid="stExpander"] summary p {color:#F1F5F9;font-weight:600;}
.stButton button,.stLinkButton a {background:#26D9C7;color:#0B1424;border:0;border-radius:10px;}
.stButton button p,.stLinkButton a p {color:#0B1424;font-weight:600;}
[data-testid="stAlert"] {background:#23364b !important;}
[data-testid="stAlert"] * {color:#F1F5F9 !important;}
.brand {display:flex;align-items:center;gap:14px;margin:8px 0 20px;}
.brand-name {font-size:clamp(24px,5vw,38px);font-weight:800;letter-spacing:1px;color:#26D9C7;}
.brand-sub {color:#CBD5E1;font-size:14px;}
.brand-status {color:#26D9C7;font-size:12px;letter-spacing:1.5px;font-weight:600;}
</style>
<div class="brand"><svg width="52" height="52" viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="12" fill="#173A43"/><path d="M6 25 H14 L20 11 L27 36 L34 21 H42" stroke="#26D9C7" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg><div><div class="brand-name">MIDCAP NEWS</div><div class="brand-sub">Svensk börsbevakning</div></div></div>
<div class="brand-status">● NYHETSRADAR</div>
""", unsafe_allow_html=True)
st.caption('Mid Cap · Small Cap · First North')


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
# Only group cross-source reports when the buyer and a distinctive subject match.
import re
def words(s):
    return set(re.findall(r'[^\W_]{4,}', s.casefold())) - {'contract','contracts','framework','agreement','agreements','ramavtal','upphandling','tilldelningsbeslut','services','service','order','awarded'}
def same_deal(ted, press):
    if ted['company'] != press['company'] or press.get('source') == 'TED':
        return False
    if abs((stamp(ted['published'])-stamp(press['published'])).total_seconds()) > 7*86400:
        return False
    buyer = ted.get('procurement_buyer','').strip()
    body = press['title']+' '+press.get('article_text','')
    if not buyer or ';' in buyer or not re.search(r'(?<!\w)'+re.escape(buyer)+r'(?!\w)',body,re.I):
        return False
    subject = ted['title'].split(' – ',1)[-1]
    shared = words(subject) & words(press['title'])
    shared -= words(buyer) | words(ted['company'])
    return len(shared) >= 2 or bool(ted.get('procurement_number') and ted['procurement_number'] in body)
all_items = deduplicate_news(list(merged.values()))
hidden = set()
for ted in [i for i in all_items if i.get('source')=='TED']:
    candidates = [p for p in all_items if same_deal(ted,p)]
    if len(candidates)==1:
        press = candidates[0]
        press.setdefault('related_procurements',[]).append(ted)
        hidden.add(ted['id'])
active = [i for i in all_items if i['id'] not in hidden and (timedelta(0) <= now-stamp(i['published']) < timedelta(hours=24) or any(timedelta(0)<=now-stamp(t['published'])<timedelta(hours=24) for t in i.get('related_procurements',[])))]
result = dict(result,items=active)
config = load_config()
covered = sum(bool(c.get('feeds')) for c in config['companies'] if c.get('segment_verified') and c.get('segment') in ('Mid Cap', 'Small Cap', 'First North'))
a,b,c = st.columns(3)
a.metric('Nyheter · 24 h', len(result['items']))
mid_count = sum(c.get('segment') == 'Mid Cap' and c.get('segment_verified') for c in config['companies'])
small_count = sum(c.get('segment') == 'Small Cap' and c.get('segment_verified') for c in config['companies'])
first_count = sum(c.get('segment') == 'First North' and c.get('segment_verified') for c in config['companies'])
st.caption(f'Mid Cap: {mid_count} · Small Cap: {small_count} · First North: {first_count}')
b.metric('Positiva', sum(i.get('direction') == 'Positiv' for i in result['items']))
c.metric('Hög potential', sum(i.get('direction') == 'Positiv' and (i.get('news_score') or 0) >= 70 for i in result['items']))
st.caption(f"Bevakningslista: {result['eligible_count']} bolag · Gemensamma källor: {len(config.get('shared_feeds', []))} · Hög potential = positiv och minst 70 poäng, inte kursprognos.")
if not config.get('universe_complete'):
    st.caption('Fullständig nyhetstäckning är inte verifierad.')
if result['failures']:
    st.write('⚠️ Källfel: bevakningen är ofullständig.')
if not result['items']:
    st.write('Inga matchade nyheter vid senaste kontrollen.')
st.subheader('Marknadspuls')
st.caption('Endast nyheter publicerade under de senaste 24 timmarna visas här.')
for item in sorted(result['items'], key=lambda x: (x['importance'] in ('Hög','Möjligen hög'), x['published']), reverse=True):
    direction = item.get('direction', 'Oklar')
    marker = {'Positiv':'green', 'Negativ':'red', 'Blandad':'yellow', 'Osäker':'orange', 'Oklar':'gray'}.get(direction, 'gray')
    score = item.get('news_score')
    score_label = f'{score}/100' if score is not None else 'Ej poängsatt'
    with st.expander(f":{marker}[▌] **{item['company']}** · {direction} · :{marker}[{score_label}]", expanded=False):
        st.subheader(item['company'])
        st.markdown('**'+item['title']+'**')
        st.write({'Positiv':'🟢','Negativ':'🔴','Blandad':'🟡','Osäker':'🟠'}.get(item['direction'],'⚪') + ' ' + item['direction'])
        st.caption(f"Publicerad: {stamp(item['published']).astimezone(ZoneInfo('Europe/Stockholm')):%Y-%m-%d %H:%M} svensk tid · {item['direction']} · Betydelse: {item['importance']}")
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
        if item.get('related_procurements'):
            st.markdown('**Samlad affärsinformation**')
            st.caption('Automatisk koppling baserad på beställare och innehåll – kontrollera att det är samma kontrakt. Beloppen summeras inte.')
            for related in sorted(item['related_procurements'],key=lambda x:stamp(x['published'])):
                st.write('TED · '+stamp(related['published']).date().isoformat()+' · '+related['title'])
                st.write(related.get('procurement_text',''))
                st.link_button('Tilldelningsannons · '+related.get('procurement_number',related['id']),related['url'])
            st.write('Pressmeddelande · '+item['title'])
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
