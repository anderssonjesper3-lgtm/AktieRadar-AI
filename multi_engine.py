"""Shared 5-minute technical engine. No synthetic signals or trading orders."""
import asyncio
from datetime import datetime, timedelta
from news_scanner import load_config
from test_avanza_forbattrad import SWEDEN, MAX_AGE_MINUTES, fetch_points, build_candles
from aktieradar_telegram import classify, enrich_signal_with_news

def companies():
    return load_config()['companies']

def validate_company(c):
    if not c.get('order_book_id') or not str(c['order_book_id']).isdigit():
        return 'Avanza-ID ej verifierat'
    return None

async def analyze_company(c, now=None):
    now = now or datetime.now(SWEDEN)
    error = validate_company(c)
    result = {'company':c['name'], 'ticker':c.get('ticker',''), 'status':'DATA SAKNAS', 'signal':None, 'candles':[], 'error':error, 'data_age_minutes':None, 'last_trade_time':None, 'data_fresh':False, 'data_reason':None, 'raw_points':0, 'last_bar_time':None}
    if error:
        return result
    try:
        points, _ = await fetch_points(order_book_id=str(c['order_book_id']))
        candles, gaps = build_candles(points)
        result['raw_points'] = len(points)
        if candles:
            result['last_bar_time'] = candles[-1]['time'].isoformat()
        signal, status = classify(candles, now)
        if candles:
            last = candles[-1]
            last_trade = last.get('last_trade_time', last['time'] + timedelta(minutes=5))
            age = (now - last_trade).total_seconds() / 60
            fresh = last_trade.date() == now.date() and 0 <= age <= MAX_AGE_MINUTES
            if not fresh:
                signal = None
                status = 'DATA FÖR GAMMAL – senaste faktiska avslutet är inte aktuellt'
            reason = ('Senaste avslut är äldre än 15 minuter; kan bero på låg handel eller fördröjd källa' if age > MAX_AGE_MINUTES else 'Ingen verifierad aktuell handel idag' if last_trade.date() != now.date() else 'Tidsstämpel ligger i framtiden' if age < 0 else None)
            result.update(data_age_minutes=round(age, 1), last_trade_time=last_trade.isoformat(), data_fresh=fresh, data_reason=reason)
        result.update(status=status, signal=signal, candles=candles, error=None, gaps=len(gaps))
    except Exception as exc:
        result['error'] = f'Kursdata kunde inte verifieras: {exc}'
    return result

async def analyze_all(config=None, now=None):
    selected = config or companies()
    # Sequential to avoid overwhelming upstream provider; errors isolated per company.
    return [await analyze_company(c, now) for c in selected]

def notification_key(company, signal):
    return f"{company['ticker']}:{signal['kind']}:{signal['time'].isoformat()}"
