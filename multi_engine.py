"""Shared 5-minute technical engine. No synthetic signals or trading orders."""
import asyncio
from datetime import datetime, timedelta, timezone
from news_scanner import load_config, scan
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
        result.update(status=status, signal=signal, candles=candles, error=None, gaps=len(gaps),
                      source='Avanza', delay_limit_minutes=20)
        if candles:
            result['last_candle_age_minutes'] = round(
                (now - (candles[-1]['time'] + timedelta(minutes=5))).total_seconds() / 60, 1)
        # Headlines can create WATCH context only, never a standalone buy signal.
        if c.get('feeds'):
            matches, failures = scan({'companies': [c]}, now=now.astimezone(timezone.utc))
            result['news_count'] = len(matches)
            result['news_errors'] = len(failures)
            if failures:
                result['news_status'] = 'Nyhetskälla kunde inte verifieras'
            elif matches:
                recent = [m for m in matches if
                          timedelta(0) <= now.astimezone(timezone.utc) - m['published'] <= timedelta(hours=6)]
                result['news_status'] = f'{len(recent)} nyheter senaste 6 timmarna'
                risks = [m for m in recent if m['category'] == 'RISKNYHET']
                positive = [m for m in recent if m['category'] == 'ORDER/AVTAL – GRANSKA']
                if risks and signal and signal['kind'] == 'KÖP-KANDIDAT':
                    signal = dict(signal, kind='VAKTA-RISKGRANSKNING',
                                  reasons=list(signal['reasons']) + ['Risknyhet: kontrollera originalkälla'])
                elif positive and signal and signal['kind'].startswith('VAKTA'):
                    signal = dict(signal, reasons=list(signal['reasons']) + ['Relevant nyhet: granska originalkälla'])
                elif positive and not signal and candles and result['last_candle_age_minutes'] <= 20 and result['last_candle_age_minutes'] >= 0:
                    signal = {'kind':'NYHET-VAKTA','time':candles[-1]['time'],
                              'close':candles[-1]['close'],'score':None,
                              'reasons':['Ny order/avtalsrubrik – verifiera originalnyheten och kursreaktionen']}
                result['signal'] = signal
            else:
                result['news_status'] = 'Inga matchande nyheter'
        else:
            result['news_status'] = 'Nyhetsflöde ej anslutet'
    except Exception as exc:
        result['error'] = f'Kursdata kunde inte verifieras: {exc}'
    return result

async def analyze_all(config=None, now=None):
    selected = config or companies()
    # Sequential to avoid overwhelming upstream provider; errors isolated per company.
    return [await analyze_company(c, now) for c in selected]

def notification_key(company, signal):
    return f"{company['ticker']}:{signal['kind']}:{signal['time'].isoformat()}"
