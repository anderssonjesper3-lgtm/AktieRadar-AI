"""Shared 5-minute technical engine. No synthetic signals or trading orders."""
import asyncio
from datetime import datetime
from news_scanner import load_config
from test_avanza_forbattrad import SWEDEN, fetch_points, build_candles
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
    result = {'company':c['name'], 'ticker':c.get('ticker',''), 'status':'DATA SAKNAS', 'signal':None, 'candles':[], 'error':error}
    if error:
        return result
    try:
        points, _ = await fetch_points(order_book_id=str(c['order_book_id']))
        candles, gaps = build_candles(points)
        signal, status = classify(candles, now)
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
