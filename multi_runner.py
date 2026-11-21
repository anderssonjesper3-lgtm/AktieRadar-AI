"""Ten-company alert runner; skips unverified IDs and missing/stale data."""
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from multi_engine import companies, analyze_all
from aktieradar_telegram import market_session, telegram_send, read_state, write_state, COOLDOWN_MINUTES, MAX_EVENTS, process_news, state_check
from test_avanza_forbattrad import SWEDEN
from news_scanner import scan

def should_alert(c, signal, events):
    key = f"{c['ticker']}:{signal['kind']}:{signal['time'].isoformat()}"
    if any(e['id']==key for e in events): return False,key
    for e in events:
        if not e['id'].startswith(c['ticker']+':') or e['kind']!=signal['kind']: continue
        try:
            dt=datetime.fromisoformat(e['time'])
            if 0 <= (signal['time']-dt).total_seconds()/60 < COOLDOWN_MINUTES: return False,key
        except (ValueError,TypeError):
            raise RuntimeError('Felaktig signalhistorik')
    return True,key

def news_for(c, articles, failures, now):
    if not c.get('feeds') or failures:
        return 'Nyhetsstatus okänd',False
    recent=[a for a in articles if a['company']==c['name'] and timedelta(0)<=now-a['published']<=timedelta(hours=6)]
    return ('; '.join(a['category'] for a in recent) or 'Inga matchande rubriker senaste 6h'),any(a['category']=='RISKNYHET' for a in recent)

def run(dry_run=True):
    now=datetime.now(SWEDEN)
    if not market_session(now):
        print('Börsen stängd / handelstid ej verifierad. Inga tekniska notiser.'); return
    config=companies()
    articles,failures=scan({'companies':config})
    if failures: print('Nyhetskällor felar: nyhetsstatus okänd')
    results=asyncio.run(analyze_all(config,now))
    state=None
    for c,r in zip(config,results):
        if r['error']:
            print(c['name'], 'HOPPAS ÖVER:',r['error']); continue
        signal=r['signal']
        print(c['name'],r['status'])
        if not signal or signal['kind'] not in ('VAKTA','MORGON-VAKTA','KÖP-KANDIDAT'):continue
        context,risk=news_for(c,articles,failures,now.astimezone(timezone.utc))
        kind='VAKTA-RISKGRANSKNING' if risk and signal['kind']=='KÖP-KANDIDAT' else signal['kind']
        signal=dict(signal,kind=kind)
        msg=(f"{'🟢' if kind=='KÖP-KANDIDAT' else '🟡'} AktieRadar AI 4.0 – {kind}\n"
             f"Bolag: {c['name']} ({c['ticker']})\n"
             f"Stapel: {signal['time']:%Y-%m-%d %H:%M}\n"
             f"Kurs: {signal['close']:.2f} kr\n"
             f"Poäng: {signal['score'] if signal['score'] is not None else 'ej beräknad'}\n"
             f"Orsaker: {', '.join(map(str,signal['reasons']))}\n"
             f"Nyheter: {context}\n"
             'Inte handelsråd. Kontrollera spread, likviditet och aktuell kurs.')
        if dry_run:
            print('DRY RUN:',msg);continue
        if state is None: state=read_state()
        yes,key=should_alert(c,signal,state['events'])
        if not yes: continue
        event={'id':key,'kind':kind,'time':signal['time'].isoformat(),'status':'reserved'}
        state['events'].append(event);state['events']=state['events'][-MAX_EVENTS:]
        write_state(state)
        telegram_send(msg)
        event['status']='sent';write_state(state)
        print('Telegram skickat:',c['name'],kind)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--state-check',action='store_true');p.add_argument('--news-dry-run',action='store_true');p.add_argument('--news-live',action='store_true');a=p.parse_args()
    if a.state_check:state_check()
    elif a.news_dry_run:process_news(dry_run=True)
    elif a.news_live:process_news(dry_run=False)
    else:run(dry_run=not a.live)
