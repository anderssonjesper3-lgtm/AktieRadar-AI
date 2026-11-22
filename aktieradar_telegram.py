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
    """Early watch-only setup using observed bars; no wall-clock continuity required."""
    if continuous < 6:
        return False
    recent = candles[-6:]
    baseline = [bar['volume'] for bar in recent[:-1] if bar.get('volume', 0) > 0]
    if len(baseline) < 3:
        return False
    avg = sum(baseline) / len(baseline)
    current = recent[-1]
    return (avg > 0 and current['volume'] / avg >= 1.5
            and current['close'] > recent[-4]['close']
            and current['close'] > current['open'])


def classify(candles, now):
    # Count observed traded bars, never require wall-clock adjacency.
    if not candles:
        return None, 'DATA SAKNAS - inga observerade staplar'
    observed = consecutive_count(candles)
    if not market_session(now):
        return None, 'Utanför tillåten handelstid / börshelgdag'
    last = candles[-1]
    end = last.get('last_trade_time', last['time'] + timedelta(minutes=5))
    age = (now - end).total_seconds() / 60
    if end.date() != now.date() or not 0 <= age <= MAX_AGE_MINUTES:
        return None, 'DATA FÖR GAMMAL - senaste faktiska avslutet är inte aktuellt'

    # Early observations may create WATCH only. Full technical BUY scoring waits
    # until EMA21, RSI14, MACD signal and a volume baseline are all computable.
    if morning_signal(candles, observed):
        return {'kind': 'MORGON-VAKTA', 'time': last['time'], 'close': last['close'],
                'score': None, 'reasons': ['Prisuppgång', 'Grön 5-minutersstapel',
                                          'Volymökning mot tidigare observerade staplar']}, \
               f'Morgonbevakning ({observed} observerade staplar)'
    closes = [bar['close'] for bar in candles]
    ema9, ema21 = calculate_ema(closes, 9), calculate_ema(closes, 21)
    rsi = calculate_rsi(closes, 14)
    _, _, hist = calculate_macd(closes)
    rv = calculate_relative_volume(candles)
    patterns = detect_candlestick_patterns(candles)
    scores = calculate_signal_scores(candles, ema9, ema21, rsi, hist, rv, patterns)
    current = scores[-1] if scores else None
    if current is None:
        return None, (f'INDIKATORER BYGGER HISTORIK ({observed} observerade staplar; '
                      'köpsignal kräver tillräcklig EMA/RSI/MACD/volymhistorik)')
    status = check_buy_signal(current['score'], True)
    if status.startswith('KOP'):
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


def should_notify(signal, events, ticker='SAAB B'):
    event_id = f"{ticker}:{signal['kind']}:{signal['time'].isoformat()}"
    for e in events:
        if e['id'] == event_id:
            return False, 'Samma stapel är redan reserverad/skickad', event_id
    for e in reversed(events):
        if e['kind'] != signal['kind'] or not e['id'].startswith(f'{ticker}:'):
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
    kind = signal['kind']
    symbol = '🟢' if kind == 'KÖP-KANDIDAT' else ('🔴' if 'SÄLJ' in kind else '🟡')
    score_value = signal.get('score')
    score = f"{score_value}/100" if score_value is not None else 'Ej beräknad'
    company = signal.get('company', 'Saab B')
    ticker = signal.get('ticker', 'SAAB B')
    return (f"{symbol} AktieRadar AI {VERSION} – {kind} | {company} ({ticker})\\n"
            f"Tid: {signal['time']:%Y-%m-%d %H:%M} svensk tid\\n"
            f"Kurs: {signal['close']:.2f} kr\\nPoäng: {score}\\n"
            f"Orsaker: {', '.join(map(str, signal.get('reasons', [])))}\\n"
            f"Nyhetsstatus: {signal.get('news_status', 'ej kontrollerad')}\\n"
            'Pappersanalys, inte handelsråd. Kontrollera aktuell kurs och spread före beslut.')

def process_live(signal):
    state = read_state(create=True, migrate=True)  # initialize or migrate legacy signal history safely
    ticker = signal.get('ticker', 'SAAB B')
    notify, reason, event_id = should_notify(signal, state['events'], ticker)
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
    now_local = datetime.now(SWEDEN)
    if not market_session(now_local):
        print('Ingen nyhetsskanning: utanför svensk börshandel eller börshelgdag.')
        return
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


def process_multi_live(dry_run=False):
    """Run the shared 10-company technical/news/exit pipeline."""
    from multi_engine import analyze_all, companies
    from news_scanner import scan
    from news_analysis import analyze_news
    from performance import record_signal, update_open_trades, load_journal
    now = datetime.now(SWEDEN)
    if not market_session(now):
        print('Ingen tiobolagskörning: börsen stängd.')
        return
    watchlist = companies()
    technical = asyncio.run(analyze_all(watchlist, now=now))
    articles, failures = scan({'companies': watchlist}, now=now.astimezone(timezone.utc))
    if failures:
        raise RuntimeError('Nyhetskällfel – köpbeslut blockeras: ' + ', '.join(x[0] for x in failures))
    by_ticker = {c['ticker']: c for c in watchlist}
    news_by_ticker = {c['ticker']: [] for c in watchlist}
    for article in articles:
        company = next((c for c in watchlist if c['name'] == article['company']), None)
        if company:
            news_by_ticker[company['ticker']].append(analyze_news(article, company))
    prices, candles_by_ticker = {}, {}
    for result in technical:
        ticker = result.get('ticker')
        if result.get('error') or not result.get('candles'):
            print('BLOCKERAD:', ticker, result.get('error') or result.get('status'))
            continue
        candles = result['candles']; last = candles[-1]
        prices[ticker] = float(last['close']); candles_by_ticker[ticker] = candles
        signal = result.get('signal')
        if signal:
            company = by_ticker[ticker]
            signal = dict(signal, company=company['name'], ticker=ticker)
            analyses = news_by_ticker.get(ticker, [])
            risks = [n for n in analyses if n['view'] == 'NEGATIV']
            positives = [n for n in analyses if n['view'] in ('POSITIV','PRELIMINÄRT POSITIV')]
            signal['news_status'] = f'{len(analyses)} analyserade nyheter'
            if risks and signal['kind'] == 'KÖP-KANDIDAT':
                signal['kind'] = 'VAKTA-RISKGRANSKNING'
                signal['reasons'] = list(signal.get('reasons', [])) + ['Negativ bolagsnyhet – manuell granskning']
            elif positives:
                signal['reasons'] = list(signal.get('reasons', [])) + ['Positiv nyhet – teknisk bekräftelse krävs']
            print('SIGNAL:', ticker, signal['kind'], signal['score'], signal['news_status'])
            if not dry_run:
                record_signal(company['name'], ticker, signal)
                process_live(signal)
    if not dry_run:
        before = load_journal()
        closed = update_open_trades(prices, candles_by_ticker=candles_by_ticker, now=now)
        after = load_journal()
        print('Simulerade affärer stängda:', closed)
        before_ids = {t.get('id') for t in before.get('trades', []) if t.get('status') == 'CLOSED'}
        for trade in after.get('trades', []):
            if trade.get('status') == 'CLOSED' and trade.get('id') not in before_ids:
                exit_signal = {
                    'kind': 'SÄLJ',
                    'company': trade.get('company', trade.get('ticker')),
                    'ticker': trade['ticker'],
                    'time': now,
                    'close': float(trade.get('exit_price') or prices.get(trade['ticker'], 0)),
                    'score': None,
                    'reasons': [trade.get('exit_reason') or 'Smart Exit'] + trade.get('exit_signal_reasons', []),
                    'news_status': 'positionsbevakning'
                }
                process_live(exit_signal)
    else:
        print('DRY RUN – journal/Telegram ändrades inte.')


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--test', action='store_true')
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--state-check', action='store_true')
    group.add_argument('--multi-live', action='store_true', help='Gemensam tiobolagsmotor, Telegram och journal')
    group.add_argument('--multi-dry-run', action='store_true', help='Testa tiobolagsmotor utan journal eller Telegram')
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
    if args.multi_live or args.multi_dry_run:
        process_multi_live(dry_run=args.multi_dry_run)
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
