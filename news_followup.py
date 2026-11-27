import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import re
import pandas as pd

STATE = Path(__file__).with_name('news_followup_state.json')
SLOTS = (20,35,50,65,80)

def stamp(value):
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc)

def load_state(path=STATE):
    return json.loads(path.read_text()) if path.exists() else {}

def quotes(ticker, interval):
    import yfinance as yf
    return yf.Ticker(ticker).history(period='5d', interval=interval, auto_adjust=False, timeout=10)

def observe(frame, published, now, minutes):
    if frame.empty or frame.index.tz is None:
        return {'status':'Kursdata saknas'}
    frame = frame.sort_index().dropna(subset=['Close','Volume'])
    ends = frame.index + pd.Timedelta(minutes=minutes)
    frame = frame.loc[ends <= now]
    ends = frame.index + pd.Timedelta(minutes=minutes)
    before = frame.loc[ends <= published]
    after = frame.loc[frame.index >= published]
    if before.empty or after.empty:
        return {'status':'Väntar på stapel efter nyheten'}
    end = after.index[-1] + pd.Timedelta(minutes=minutes)
    age = (now-end).total_seconds()/60
    if age > 40:
        return {'status':'För gammal kursdata','age_minutes':round(age,1)}
    close = frame.Close
    baseline = float(before.Close.iloc[-1])
    normal = float(before.Volume.tail(20).mean())
    if baseline <= 0 or normal <= 0 or len(close)<21:
        return {'status':'Otillräcklig historik'}
    ema9 = close.ewm(span=9,adjust=False).mean()
    ema21 = close.ewm(span=21,adjust=False).mean()
    change = (float(after.Close.iloc[-1])/baseline-1)*100
    relative = float(after.Volume.iloc[-1])/normal
    return {'status':'OK','bar_end':end.isoformat(),'age_minutes':round(age,1),
            'interval_minutes':minutes,'change_pct':round(change,2),'relative_volume':round(relative,2),
            'momentum':'Positivt' if ema9.iloc[-1]>ema21.iloc[-1] else 'Svagt',
            'reaction':'Positiv reaktion' if change>0 and relative>=1.5 and ema9.iloc[-1]>ema21.iloc[-1] else 'Ingen tydlig positiv bekräftelse'}

def advance(state, items, config, now, fetch=quotes):
    state = {k:v for k,v in state.items() if now-stamp(v['first_seen']) < timedelta(days=7)}
    companies = {c['name']:c for c in config['companies']}
    for item in items:
        if now-stamp(item['published']) >= timedelta(hours=24):
            continue
        key = item['id']
        if key not in state:
            state[key] = {'first_seen':now.isoformat(),'item':json.loads(json.dumps(item,default=str,ensure_ascii=False)), 'observations':{}}
    cache = {}
    for entry in state.values():
        item = entry['item']
        if now-stamp(entry['first_seen']) >= timedelta(hours=24):
            continue
        elapsed = (now-stamp(entry['first_seen'])).total_seconds()/60
        due = [s for s in SLOTS if s<=elapsed and entry['observations'].get(str(s), {}).get('status') not in ('OK', 'Kontrolltillfälle missat')]
        if not due:
            continue
        # Retry missing observations; do not label a current quote as an earlier observation.
        slot = due[-1]
        ticker = companies.get(item['company'],{}).get('ticker','').replace(' ','-')
        result = {'status':'Börssymbol saknas'}
        if re.fullmatch(r'[A-Za-z0-9-]+',ticker):
            for interval, minutes in [('5m',5),('15m',15)]:
                try:
                    key = (ticker,interval)
                    if key not in cache:
                        cache[key] = fetch(ticker+'.ST',interval)
                    result = observe(cache[key],stamp(item['published']),now,minutes)
                    if result['status']=='OK':
                        break
                except Exception as exc:
                    result = {'status':'Kursfel: '+type(exc).__name__}
        entry['observations'][str(slot)] = dict(result,checked_at=now.isoformat())
        if result['status'] == 'OK':
            for s in due[:-1]:
                entry['observations'][str(s)] = {'status':'Kontrolltillfälle missat'}
    return state

def save_state(state,path=STATE):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)
