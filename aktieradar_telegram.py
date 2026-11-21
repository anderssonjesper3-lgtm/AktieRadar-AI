"""AktieRadar AI: Saab B -> Telegram. No trading orders."""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from test_avanza_forbattrad import (
    SWEDEN, LOOKBACK, MAX_AGE_MINUTES, fetch_points, build_candles,
    calculate_ema, calculate_rsi, calculate_macd, calculate_relative_volume,
    detect_candlestick_patterns, calculate_signal_scores, consecutive_count,
    check_buy_signal,
)

STATE_PATH = Path(os.getenv('AKTIERADAR_STATE_FILE', 'telegram_signal_state.json'))


def morning_signal(candles, continuous):
    if not (6 <= continuous < LOOKBACK):
        return False
    recent = candles[-6:]
    volumes = [c['volume'] for c in recent[:-1]]
    avg = sum(volumes) / len(volumes)
    return (avg > 0 and recent[-1]['volume'] / avg >= 1.5
            and recent[-1]['close'] > recent[-4]['close']
            and recent[-1]['close'] > recent[-1]['open'])


def classify(candles, now):
    if not candles:
        return None, 'Inga kompletta staplar'
    last = candles[-1]
    end = last['time'] + timedelta(minutes=5)
    age = (now - end).total_seconds() / 60
    if now.weekday() >= 5 or not ((9, 0) <= (now.hour, now.minute) < (17, 30)):
        return None, 'Utanför ordinarie handelstid'
    if last['time'].date() != now.date() or not (0 <= age <= MAX_AGE_MINUTES):
        return None, 'Gammal, framtida eller ofullständig data'
    continuous = consecutive_count(candles)
    if morning_signal(candles, continuous):
        return {'kind': 'MORGON-VAKTA', 'time': last['time'], 'close': last['close'], 'score': None,
                'reasons': ['Prisuppgång', 'Grön femminutersstapel', 'Kort volymökning minst 1,5×']}, 'Morgonbevakning'
    if continuous < LOOKBACK:
        return None, f'För få sammanhängande staplar ({continuous}/{LOOKBACK})'
    closes = [c['close'] for c in candles]
    ema9, ema21 = calculate_ema(closes, 9), calculate_ema(closes, 21)
    rsi = calculate_rsi(closes, 14)
    _, _, hist = calculate_macd(closes)
    rv = calculate_relative_volume(candles)
    patterns = detect_candlestick_patterns(candles)
    scores = calculate_signal_scores(candles, ema9, ema21, rsi, hist, rv, patterns)
    current = scores[-1] if scores else None
    if current is None:
        return None, 'Indikatorer saknas (MACD kräver längre historik)'
    status = check_buy_signal(current['score'], True)
    if status.startswith('KOP'):
        kind = 'KÖP-KANDIDAT'
    elif status.startswith('VAKTA'):
        kind = 'VAKTA'
    else:
        return None, f'AVVAKTA ({current["score"]}/100)'
    return {'kind': kind, 'time': last['time'], 'close': last['close'],
            'score': current['score'], 'reasons': current['reasons']}, status


def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        return set(data.get('sent', []))
    except (OSError, ValueError, TypeError):
        return set()


def save_state(sent):
    STATE_PATH.write_text(json.dumps({'sent': sorted(sent)[-300:]}, ensure_ascii=False), encoding='utf-8')


def telegram_send(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError('TELEGRAM_BOT_TOKEN eller TELEGRAM_CHAT_ID saknas i GitHub Secrets')
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    body = urlencode({'chat_id': chat_id, 'text': message}).encode('utf-8')
    req = Request(url, data=body, method='POST')
    try:
        with urlopen(req, timeout=20) as response:
            result = json.load(response)
    except Exception as exc:
        # Never print token-bearing URL or raw HTTP error details.
        raise RuntimeError('Telegram-anropet misslyckades; kontrollera botnyckel, chatt-ID och anslutning') from None
    if not result.get('ok'):
        raise RuntimeError('Telegram avvisade meddelandet')


def format_message(signal):
    kind = signal['kind']
    symbol = '🟢' if kind == 'KÖP-KANDIDAT' else '🟡'
    when = signal['time'].strftime('%Y-%m-%d %H:%M')
    score = f"\nPoäng: {signal['score']}/100" if signal['score'] is not None else '\nPoäng: inte beräknad (morgonläge)'
    reasons = ', '.join(signal['reasons']) if signal['reasons'] else 'Se appen'
    return (f'{symbol} AktieRadar AI – {kind} | Saab B\n'
            f'Tid: {when} svensk tid (stapelns start)\n'
            f'Kurs: {signal["close"]:.2f} kr{score}\n'
            f'Orsaker: {reasons}\n'
            'Indikativ analys, inte handelsråd. Kontrollera kursen före beslut.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Send only a connectivity test')
    parser.add_argument('--dry-run', action='store_true', help='Analyze without sending Telegram')
    args = parser.parse_args()
    if args.test:
        telegram_send('🔔 AktieRadar AI 3.0: Telegram-kopplingen fungerar! (Test, ingen börssignal)')
        print('Testmeddelande skickat.')
        return
    now = datetime.now(SWEDEN)
    # Do not call data provider outside weekday trading hours.
    if now.weekday() >= 5 or not ((9, 0) <= (now.hour, now.minute) < (17, 30)):
        print('Ingen bevakning: utanför normal handelstid.')
        return
    points, count = asyncio.run(fetch_points())
    candles, gaps = build_candles(points)
    signal, status = classify(candles, now)
    print(f'Minutposter: {count}, kompletta staplar: {len(candles)}, luckor: {len(gaps)}')
    print('Status:', status)
    if not signal:
        return
    event_id = f"SAAB-B:{signal['kind']}:{signal['time'].isoformat()}"
    sent = load_state()
    if event_id in sent:
        print('Dubblett stoppad:', event_id)
        return
    print('Ny kandidat:', event_id)
    if args.dry_run:
        print('DRY RUN – inget Telegram skickas.\n' + format_message(signal))
        return
    telegram_send(format_message(signal))
    sent.add(event_id)
    save_state(sent)
    print('Telegram-notis skickad; dubblettstatus sparad.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Fel: {exc}', file=sys.stderr)
        sys.exit(1)
