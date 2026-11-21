"""AktieRadar AI 3.1: Saab B analysis and optional Telegram notifications.

No trading orders. Uses the existing test_avanza_forbattrad.py calculations.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from test_avanza_forbattrad import (
    SWEDEN, LOOKBACK, MAX_AGE_MINUTES, fetch_points, build_candles,
    calculate_ema, calculate_rsi, calculate_macd, calculate_relative_volume,
    detect_candlestick_patterns, calculate_signal_scores, consecutive_count,
    check_buy_signal,
)

COOLDOWN_MINUTES = int(os.getenv('AKTIERADAR_COOLDOWN_MINUTES', '30'))
MAX_STATE_ENTRIES = 100
STATE_VARIABLE = "AKTIERADAR_SIGNAL_HISTORY"


def trading_hours(now):
    return now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) < (17, 30)


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
    if not trading_hours(now):
        return None, 'Utanför ordinarie handelstid'
    if last['time'].date() != now.date() or not (0 <= age <= MAX_AGE_MINUTES):
        return None, 'Gammal, framtida eller ofullständig data'
    continuous = consecutive_count(candles)
    if morning_signal(candles, continuous):
        return {'kind': 'MORGON-VAKTA', 'time': last['time'], 'close': last['close'],
                'score': None, 'reasons': ['Prisuppgång', 'Grön femminutersstapel',
                'Kort volymökning minst 1,5×']}, 'Morgonbevakning'
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


def github_api(method, path, payload=None):
    """Use GitHub Actions repository variables as durable state (not cache)."""
    token = os.environ.get('GH_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo or '/' not in repo:
        raise RuntimeError('GH_TOKEN/GITHUB_REPOSITORY saknas; LIVE stoppas säkert')
    url = f'https://api.github.com/repos/{repo}/actions/variables{path}'
    headers = {'Authorization': f'Bearer {token}',
               'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'AktieRadar-AI'}
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f'GitHub signalhistorik: HTTP {exc.code}; LIVE stoppas') from None
    except Exception:
        raise RuntimeError('GitHub signalhistorik kunde inte nås; LIVE stoppas') from None


def parse_events(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('events'), list):
        raise RuntimeError('Ogiltig signalhistorik; LIVE stoppas')
    return [e for e in raw['events'] if isinstance(e, dict)
            and isinstance(e.get('id'), str) and isinstance(e.get('time'), str)
            and isinstance(e.get('kind'), str)]


def load_state():
    result = github_api('GET', '/' + STATE_VARIABLE)
    if result is None:
        # Create an empty durable record before any real signal can be sent.
        created = github_api('POST', '', {'name': STATE_VARIABLE,
                                          'value': json.dumps({'version': 3, 'events': []})})
        if created is None:
            raise RuntimeError('Kunde inte skapa GitHub signalhistorik')
        print('Ny permanent signalhistorik skapad i GitHub.')
        return []
    try:
        return parse_events(json.loads(result['value']))
    except (KeyError, TypeError, ValueError):
        raise RuntimeError('GitHub signalhistorik är skadad; LIVE stoppas') from None


def save_state(events):
    payload = json.dumps({'version': 3, 'events': events[-MAX_STATE_ENTRIES:]},
                         ensure_ascii=False, separators=(',', ':'))
    if len(payload.encode('utf-8')) > 40000:
        raise RuntimeError('Signalhistoriken är för stor; LIVE stoppas')
    result = github_api('PATCH', '/' + STATE_VARIABLE,
                        {'name': STATE_VARIABLE, 'value': payload})
    if result is None:
        raise RuntimeError('Signalhistoriken saknas vid sparning')


def should_notify(signal, events):
    """Suppress same-bar duplicates and repeat notifications of same category for a cooldown."""
    event_id = f"SAAB-B:{signal['kind']}:{signal['time'].isoformat()}"
    if any(e['id'] == event_id for e in events):
        return False, 'Samma signalstapel har redan skickats', event_id
    current_time = signal['time']
    for event in reversed(events):
        if event.get('kind') != signal['kind']:
            continue
        try:
            previous = datetime.fromisoformat(event['time'])
            minutes = (current_time - previous).total_seconds() / 60
            if 0 <= minutes < COOLDOWN_MINUTES:
                return False, f'Samma signaltyp inom {COOLDOWN_MINUTES} minuter', event_id
        except ValueError:
            continue
    return True, 'Ny signal', event_id


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
    except Exception:
        raise RuntimeError('Telegram-anropet misslyckades; kontrollera Secrets och anslutning') from None
    if not result.get('ok'):
        raise RuntimeError('Telegram avvisade meddelandet')


def format_message(signal):
    kind = signal['kind']
    symbol = '🟢' if kind == 'KÖP-KANDIDAT' else '🟡'
    when = signal['time'].strftime('%Y-%m-%d %H:%M')
    score = (f"\nPoäng: {signal['score']}/100" if signal['score'] is not None
             else '\nPoäng: inte beräknad (morgonläge)')
    reasons = ', '.join(map(str, signal['reasons'])) if signal['reasons'] else 'Se appen'
    return (f'{symbol} AktieRadar AI 3.1 – {kind} | Saab B\n'
            f'Tid: {when} svensk tid (stapelns start)\n'
            f'Kurs: {signal["close"]:.2f} kr{score}\n'
            f'Orsaker: {reasons}\n'
            'Indikativ analys, inte handelsråd. Kontrollera aktuell kurs före beslut.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Skicka endast Telegram-test')
    parser.add_argument('--dry-run', action='store_true', help='Analysera utan Telegram')
    args = parser.parse_args()
    if args.test and args.dry_run:
        parser.error('--test och --dry-run kan inte kombineras')
    if args.test:
        telegram_send('🔔 AktieRadar AI 3.1: Telegram fungerar! (Test, ingen börssignal)')
        print('Testmeddelande skickat.')
        return
    now = datetime.now(SWEDEN)
    if not trading_hours(now):
        print('Ingen bevakning: utanför normal handelstid.')
        return
    points, count = asyncio.run(fetch_points())
    candles, gaps = build_candles(points)
    signal, status = classify(candles, now)
    print(f'Minutposter: {count}, kompletta staplar: {len(candles)}, luckor: {len(gaps)}')
    print('Status:', status)
    if not signal:
        return
    # Dry-run must not require GitHub write permissions or modify persistent history.
    events = [] if args.dry_run else load_state()
    notify, reason, event_id = should_notify(signal, events)
    print('Dubblettkontroll:', reason)
    if not notify:
        return
    if args.dry_run:
        print('DRY RUN – inget Telegram skickas.\n' + format_message(signal))
        return
    telegram_send(format_message(signal))
    events.append({'id': event_id, 'kind': signal['kind'], 'time': signal['time'].isoformat()})
    save_state(events)
    print('Telegram-notis skickad; permanent signalhistorik sparad i GitHub.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Fel: {exc}', file=sys.stderr)
        sys.exit(1)
