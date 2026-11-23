"""AktieRadar AI 3.2 — Saab B monitoring, never places trades.

Requires existing test_avanza_forbattrad.py unchanged.
GitHub repository Actions variable stores a *pre-send reservation* to minimize duplicate alerts.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from test_avanza_forbattrad import (
    SWEDEN, LOOKBACK, MAX_AGE_MINUTES, fetch_points, build_candles,
    calculate_ema, calculate_rsi, calculate_macd, calculate_relative_volume,
    detect_candlestick_patterns, calculate_signal_scores, consecutive_count,
    check_buy_signal,
)

VERSION = '4.0'
STATE_VARIABLE = 'AKTIERADAR_SIGNAL_HISTORY'
COOLDOWN_MINUTES = int(os.getenv('AKTIERADAR_COOLDOWN_MINUTES', '30'))
MAX_EVENTS = 100


def easter_sunday(year):
    """Gregorian computus, used only for conservative Swedish closure checks."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    from datetime import date
    return date(year, month, day)


def market_session(now):
    """Conservative closures; not a substitute for the official exchange calendar."""
    from datetime import date, timedelta as td
    now = now.astimezone(SWEDEN) if now.tzinfo else now
    d = now.date()
    if d.weekday() >= 5:
        return False
    easter = easter_sunday(d.year)
    # Good Friday, Easter Monday, Ascension Day and Maundy Thursday (skip early close).
    if d in {easter - td(days=2), easter + td(days=1),
             easter + td(days=39), easter - td(days=3)}:
        return False
    # Swedish fixed public holidays and conservatively excluded early-close eves.
    if (d.month, d.day) in {(1, 1), (1, 5), (1, 6), (5, 1), (6, 6),
                            (12, 24), (12, 25), (12, 26), (12, 31), (4, 30)}:
        return False
    # Midsummer Eve (Friday June 19–25).
    if d.month == 6 and d.weekday() == 4 and 19 <= d.day <= 25:
        return False
    return (9, 0) <= (now.hour, now.minute) < (17, 30)


def morning_signal(candles, continuous):
    if not (6 <= continuous < LOOKBACK):
        return False
    recent = candles[-6:]
    avg = sum(c['volume'] for c in recent[:-1]) / 5
    return (avg > 0 and recent[-1]['volume'] / avg >= 1.5
            and recent[-1]['close'] > recent[-4]['close']
            and recent[-1]['close'] > recent[-1]['open'])


def classify(candles, now):
    if not market_session(now):
        return None, 'Utanför tillåten handelstid / börshelgdag'
    if not candles:
        return None, 'Inga kompletta staplar'
    last = candles[-1]
    end = last['time'] + timedelta(minutes=5)
    age = (now - end).total_seconds() / 60
    if last['time'].date() != now.date() or not 0 <= age <= MAX_AGE_MINUTES:
        return None, 'För gammal, framtida eller ofullständig kursdata'
    continuous = consecutive_count(candles)
    if morning_signal(candles, continuous):
        return {'kind': 'MORGON-VAKTA', 'time': last['time'], 'close': last['close'],
                'score': None, 'reasons': ['Prisuppgång', 'Grön 5-minutersstapel',
                                          'Volymökning minst 1,5 gånger']}, 'Morgonbevakning'
    if continuous < 6:
        return None, f'För få sammanhängande senaste staplar ({continuous}/6)'
    # Technical indicators can use older completed candles across small gaps.
    # Never invent missing prices or volume; buy needs verified recent volume.
    closes = [c['close'] for c in candles]
    ema9, ema21 = calculate_ema(closes, 9), calculate_ema(closes, 21)
    rsi = calculate_rsi(closes, 14)
    _, _, hist = calculate_macd(closes)
    rv = calculate_relative_volume(candles)
    patterns = detect_candlestick_patterns(candles)
    scores = calculate_signal_scores(candles, ema9, ema21, rsi, hist, rv, patterns)
    current = scores[-1] if scores else None
    if current is None:
        return None, 'Indikatorerna saknar tillräcklig historik'
    status = check_buy_signal(current['score'], True)
    if status.startswith('KOP') and not current.get('volume_verified', False):
        kind = 'VAKTA'
        current = dict(current, reasons=list(current['reasons']) + ['Volym ej verifierad – köp blockerat'])
    elif status.startswith('KOP') and continuous < LOOKBACK:
        kind = 'VAKTA'
        current = dict(current, reasons=list(current['reasons']) + ['Kort sammanhängande historik – köp blockerat'])
    elif status.startswith('KOP'):
        kind = 'KÖP-KANDIDAT'
    elif status.startswith('VAKTA'):
        kind = 'VAKTA'
    else:
        return None, f'AVVAKTA ({current["score"]}/100)'
    return {'kind': kind, 'time': last['time'], 'close': last['close'],
            'score': current['score'], 'reasons': current['reasons']}, status


def github_api(method, suffix='', payload=None, allow_404=False):
    token, repo = os.getenv('GH_TOKEN'), os.getenv('GITHUB_REPOSITORY')
    if not token or not repo or '/' not in repo:
        raise RuntimeError('GitHub-behörighet saknas; LIVE stoppas')
    url = f'https://api.github.com/repos/{repo}/actions/variables{suffix}'
    headers = {'Authorization': f'Bearer {token}',
               'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'AktieRadar-AI-3.2'}
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except HTTPError as exc:
        if exc.code == 404 and allow_404:
            return None
        raise RuntimeError(f'GitHub-historik HTTP {exc.code}; LIVE stoppas') from None
    except Exception:
        raise RuntimeError('GitHub-historik kunde inte nås; LIVE stoppas') from None


def validate_state(raw):
    if not isinstance(raw, dict) or raw.get('version') != 4 or not isinstance(raw.get('events'), list):
        raise RuntimeError('Ogiltigt historikformat; LIVE stoppas')
    for e in raw['events']:
        if (not isinstance(e, dict) or not all(isinstance(e.get(k), str)
            for k in ('id', 'kind', 'time', 'status')) or e['status'] not in ('reserved', 'sent')):
            raise RuntimeError('Skadad signalhistorik; LIVE stoppas')
    return raw


def read_state(create=False, migrate=False):
    result = github_api('GET', '/' + STATE_VARIABLE, allow_404=True)
    if result is None:
        if not create:
            raise RuntimeError('Historikvariabeln saknas; kör state-check först')
        initial = {'version': 4, 'events': []}
        github_api('POST', '', {'name': STATE_VARIABLE,
                                'value': json.dumps(initial, separators=(',', ':'))})
        result = github_api('GET', '/' + STATE_VARIABLE)
    try:
        parsed = json.loads(result['value'])
        if migrate and parsed.get('version') == 3 and isinstance(parsed.get('events'), list):
            upgraded = {'version': 4, 'events': [dict(e, status='sent') for e in parsed['events']]}
            validate_state(upgraded)
            return upgraded
        return validate_state(parsed)
    except (KeyError, ValueError, TypeError, AttributeError):
        raise RuntimeError('Historiken kunde inte tolkas; LIVE stoppas') from None


def write_state(state):
    validate_state(state)
    value = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    if len(value.encode('utf-8')) > 40000:
        raise RuntimeError('Historiken för stor; LIVE stoppas')
    github_api('PATCH', '/' + STATE_VARIABLE, {'name': STATE_VARIABLE, 'value': value})
    # Verify round-trip, including state updates.
    if read_state() != state:
        raise RuntimeError('Historikens skrivning kunde inte verifieras; LIVE stoppas')


def state_check():
    """Safe off-hours read/write/verify without sending any Telegram message."""
    state = read_state(create=True, migrate=True)
    write_state(state)
    print('STATE CHECK OK: GitHub-variabeln kan läsas, skrivas och verifieras.')


def should_notify(signal, events):
    event_id = f"SAAB-B:{signal['kind']}:{signal['time'].isoformat()}"
    for e in events:
        if e['id'] == event_id:
            return False, 'Samma stapel är redan reserverad/skickad', event_id
    for e in reversed(events):
        if e['kind'] != signal['kind']:
            continue
        try:
            prior = datetime.fromisoformat(e['time'])
            minutes = (signal['time'] - prior).total_seconds() / 60
        except (ValueError, TypeError):
            raise RuntimeError('Historikens tidsstämpel är felaktig; LIVE stoppas') from None
        if 0 <= minutes < COOLDOWN_MINUTES:
            return False, f'Samma signaltyp inom {COOLDOWN_MINUTES} minuter', event_id
    return True, 'Ny signal', event_id


def telegram_send(message):
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError('Telegram Secrets saknas')
    body = urlencode({'chat_id': chat_id, 'text': message}).encode('utf-8')
    req = Request(f'https://api.telegram.org/bot{token}/sendMessage', data=body, method='POST')
    try:
        with urlopen(req, timeout=20) as response:
            result = json.load(response)
    except Exception:
        raise RuntimeError('Telegram kunde inte nås; kontrollera Secrets') from None
    if not result.get('ok'):
        raise RuntimeError('Telegram avvisade meddelandet')


def format_message(signal):
    symbol = '🟢' if signal['kind'] == 'KÖP-KANDIDAT' else '🟡'
    score = f"{signal['score']}/100" if signal['score'] is not None else 'Ej beräknad (morgon)'
    return (f"{symbol} AktieRadar AI {VERSION} – {signal['kind']} | Saab B\n"
            f"Stapel: {signal['time']:%Y-%m-%d %H:%M} svensk tid\n"
            f"Kurs vid stapel: {signal['close']:.2f} kr\nPoäng: {score}\n"
            f"Orsaker: {', '.join(map(str, signal['reasons']))}\n"
            f"Nyhetsstatus: {signal.get('news_status', 'ej kontrollerad')}\n"
            'Analys, inte handelsråd. Kontrollera aktuell kurs och spread före beslut.')


def process_live(signal):
    state = read_state()  # fail closed if state-check has not initialized it
    notify, reason, event_id = should_notify(signal, state['events'])
    print('Dubblettkontroll:', reason)
    if not notify:
        return
    # Reserve BEFORE sending. A failure after reservation may mean a missed alert,
    # but prevents automatic duplicate alerts after an ambiguous Telegram failure.
    state['events'].append({'id': event_id, 'kind': signal['kind'],
                            'time': signal['time'].isoformat(), 'status': 'reserved'})
    state['events'] = state['events'][-MAX_EVENTS:]
    write_state(state)
    telegram_send(format_message(signal))
    state['events'][-1]['status'] = 'sent'
    write_state(state)
    print('Telegram skickat och markerat som sent.')


def news_context_for_saab(config=None, now=None, fetch=None):
    """Return *unverified* recent headline context for Saab; never a buy trigger alone.

    The company-specific feeds must be configured and validated separately.
    A feed outage cannot be interpreted as 'no bad news'.
    """
    from news_scanner import load_config, scan
    config = config if config is not None else load_config()
    now = now or datetime.now(timezone.utc)
    scoped = {'companies': [c for c in config['companies'] if c['name'] == 'Saab B']}
    if not scoped['companies'] or not scoped['companies'][0].get('feeds'):
        return {'status': 'ej ansluten', 'positive': [], 'risk': []}
    matches, failures = scan(scoped, now=now, fetch=fetch)
    if failures:
        return {'status': 'källfel', 'positive': [], 'risk': []}
    # Freshness is shorter than general 24h news monitoring, for intraday context.
    fresh = [m for m in matches if timedelta(0) <= now - m['published'] <= timedelta(hours=6)]
    return {'status': 'kontrollerad rubrikbevakning',
            'positive': [m for m in fresh if m['category'] == 'ORDER/AVTAL – GRANSKA'],
            'risk': [m for m in fresh if m['category'] == 'RISKNYHET']}


def enrich_signal_with_news(signal, context):
    """Informational context, NOT an additional statistical buy probability.

    Risk headlines stop the automated buy-candidate notification pending manual review.
    Positive headlines never promote a VAKTA to a buy candidate.
    """
    result = dict(signal)
    result['news_status'] = context['status']
    result['news_positive'] = len(context['positive'])
    result['news_risk'] = len(context['risk'])
    if result['kind'] == 'KÖP-KANDIDAT' and context['risk']:
        result['kind'] = 'VAKTA-RISKGRANSKNING'
        result['reasons'] = list(result['reasons']) + ['Ny riskrubrik: granska originalkällan']
    elif context['positive']:
        result['reasons'] = list(result['reasons']) + ['Ny order/avtalsrubrik: ej verifierad']
    return result


def process_news(dry_run=False):
    """Send announcement WATCH notices, separate from technical buy candidates."""
    from news_scanner import load_config, scan
    config = load_config()
    feeds = sum(len(c.get('feeds', [])) for c in config['companies'])
    if not feeds:
        print('NYHETSVAKTA ej aktiverad: lägg till verifierade RSS/Atom-URL:er i news_watchlist.json.')
        return
    matches, failures = scan(config)
    print(f'Nyhetskandidater: {len(matches)}; flödesfel: {len(failures)}')
    if failures:
        print('Flöden med fel:', ', '.join(name for name, _ in failures))
        # Fail closed rather than silently missing critical data.
        raise RuntimeError('Ett eller flera nyhetsflöden kunde inte läsas')
    if dry_run:
        for match in matches:
            print('NYHET-VAKTA:', match['company'], match['title'])
        return
    if not matches:
        return
    state = read_state()
    for match in matches:
        if any(e['id'] == match['id'] for e in state['events']):
            continue
        event = {'id': match['id'], 'kind': 'NYHET-VAKTA',
                 'time': match['published'].isoformat(), 'status': 'reserved'}
        state['events'].append(event)
        state['events'] = state['events'][-MAX_EVENTS:]
        write_state(state)
        telegram_send('📰 AktieRadar – NYHET-VAKTA (inte köpsignal)\n'
                      f"Bolag: {match['company']}\nKategori: {match['category']}\n"
                      f"Rubrik: {match['title']}\nKälla: {match['url']}\n"
                      'Kontrollera originalmeddelande, ordervärde, omsättning, kurs och spread.')
        event['status'] = 'sent'
        write_state(state)
        print('Nyhetsnotis skickad:', match['id'])


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--test', action='store_true')
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--state-check', action='store_true')
    group.add_argument('--news-scan', action='store_true', help='Nyhetsbevakning utan köporder')
    group.add_argument('--news-dry-run', action='store_true', help='Testa nyhetsflöden utan notis')
    args = parser.parse_args()
    if args.test:
        telegram_send(f'🔔 AktieRadar AI {VERSION}: Telegram fungerar! (TEST, ingen börssignal)')
        print('TEST OK')
        return
    if args.state_check:
        state_check()
        return
    if args.news_scan or args.news_dry_run:
        process_news(dry_run=args.news_dry_run)
        return
    now = datetime.now(SWEDEN)
    if not market_session(now):
        print('Ingen bevakning: stängt, helgdag eller utanför ordinarie tid.')
        return
    points, count = asyncio.run(fetch_points())
    candles, gaps = build_candles(points)
    signal, status = classify(candles, now)
    print(f'Minutposter: {count}, kompletta staplar: {len(candles)}, luckor: {len(gaps)}')
    print('Status:', status)
    if not signal:
        return
    context = news_context_for_saab()
    signal = enrich_signal_with_news(signal, context)
    if args.dry_run:
        print('DRY RUN – ingen notis och ingen historikändring.\n' + format_message(signal))
        return
    process_live(signal)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Fel: {exc}', file=sys.stderr)
        sys.exit(1)
