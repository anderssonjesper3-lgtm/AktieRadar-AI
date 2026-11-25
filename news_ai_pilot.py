"""News-first pilot. Explicitly verified issuer universe required; no orders."""
import asyncio
import re
from datetime import datetime, timezone
from news_scanner import scan_detailed
from multi_engine import analyze_company

POSITIVE = {
    'höjer prognosen': 85, 'raises guidance': 85,
    'höjd prognos': 85, 'raised guidance': 85,
    'erhåller order': 70, 'vinner order': 70, 'receives order': 70,
    'secures order': 70, 'awarded contract': 70, 'tilldelas kontrakt': 70,
    'myndighetsgodkännande': 75, 'regulatory approval': 75,
}
NEGATIVE = ('vinstvarning', 'profit warning', 'nyemission', 'share issue',
            'avsiktsförklaring', 'letter of intent', 'non-binding',
            'icke-bindande', 'order cancellation', 'avbeställning',
            'sänker prognosen', 'lowers guidance', 'not received', 'inte erhållit')

def score_news(item):
    title = item.get('title', '').casefold()
    body = item.get('description', '').casefold()
    if item.get('category') == 'RISKNYHET' or any(x in title+' '+body for x in NEGATIVE):
        return 0, 'Risk eller obindande besked'
    hits = [(score, phrase) for phrase, score in POSITIVE.items()
            if re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)', title)]
    return max(hits, default=(0, 'Ingen tydlig positiv katalysator'))

def explain_news(item, score):
    title = item.get('title', '').casefold()
    if 'prognos' in title or 'guidance' in title:
        return 'Höjd prognos kan innebära högre framtida resultat.', 'Kontrollera marginaler, tidigare prognos och marknadens förväntningar.'
    if any(x in title for x in ('order', 'contract', 'kontrakt')):
        return 'En bindande order kan öka framtida intäkter och orderstock.', 'Kontrollera ordervärde relativt omsättning, leveranstid och lönsamhet.'
    return 'Ett regulatoriskt godkännande kan minska kommersiell osäkerhet.', 'Kontrollera villkor, marknadsstorlek och tid till intäkter.'

def candidate_kind(quote):
    age = quote.get('last_candle_age_minutes')
    signal = quote.get('signal') or {}
    if (not quote.get('error') and quote.get('candles')
            and isinstance(age, (int, float)) and 0 <= age <= 20
            and signal.get('kind') == 'KÖP-KANDIDAT'):
        return 'KÖP-KANDIDAT (FÖRDRÖJD)'
    return 'NYHET-VAKTA'

def news_candidate_kind(quote, published):
    """Require a complete candle starting at or after publication."""
    if candidate_kind(quote) != 'KÖP-KANDIDAT (FÖRDRÖJD)':
        return 'NYHET-VAKTA'
    try:
        latest = max(c['time'] for c in quote['candles'])
        if latest.tzinfo is None or published.tzinfo is None or latest < published:
            return 'NYHET-VAKTA'
    except (KeyError, TypeError, ValueError, AttributeError):
        return 'NYHET-VAKTA'
    return 'KÖP-KANDIDAT (FÖRDRÖJD)'


def smart_exit(entry, peak, current, stop_pct=1.0, trail_pct=1.0):
    if min(entry, peak, current, stop_pct, trail_pct) <= 0 or peak < entry:
        raise ValueError('Ogiltiga priser eller riskgränser')
    if current <= entry * (1 - stop_pct / 100):
        return 'STOPP'
    if peak >= entry * 1.02 and current <= peak * (1 - trail_pct / 100):
        return 'SMART EXIT'
    return 'BEHÅLL'

def simulated_result(entry, exit_price, quantity, fee=0, slippage_pct=0):
    if min(entry, exit_price, quantity) <= 0 or min(fee, slippage_pct) < 0 or slippage_pct >= 100:
        raise ValueError('Ogiltiga affärsvärden')
    cost = entry * quantity * (1 + slippage_pct / 100) + fee
    proceeds = exit_price * quantity * (1 - slippage_pct / 100) - fee
    return {'net_sek': round(proceeds - cost, 2),
            'net_pct': round(100 * (proceeds - cost) / cost, 2)}

async def run_news_pilot(config, now=None, fetch=None, quote=None, max_age_hours=24):
    now = now or datetime.now(timezone.utc)
    eligible = [c for c in config['companies']
                if c.get('segment') in ('Mid Cap', 'Small Cap')
                and c.get('segment_verified') is True]
    matches, failures, diagnostics = scan_detailed(
        {'companies': eligible, 'shared_feeds': config.get('shared_feeds', [])}, now=now, fetch=fetch, max_age_hours=max_age_hours)
    companies = {c['name']: c for c in eligible}
    candidates = {}
    for item in matches:
        score, reason = score_news(item)
        if score < 70:
            continue
        key = (item['company'], ' '.join(item['title'].casefold().split()))
        if key not in candidates or item['published'] < candidates[key]['published']:
            candidates[key] = dict(item, score=score, reason=reason)
    quotes = {}
    for item in sorted(candidates.values(), key=lambda x: x['score'], reverse=True):
        name = item['company']
        if name not in quotes:
            # Avoid a second news fetch. Existing engine checks price availability.
            company = dict(companies[name], feeds=[])
            try:
                quotes[name] = await (quote or analyze_company)(company, now)
            except Exception as exc:
                quotes[name] = {'candles': [], 'error': type(exc).__name__}
        q = quotes[name]
        item['quote'] = q
        item['kind'] = news_candidate_kind(q, item['published'])
        item['economic_case'], item['risk'] = explain_news(item, item['score'])
    return {'candidates': list(candidates.values()), 'eligible_count': len(eligible),
            'failures': failures, 'diagnostics': diagnostics, 'quote_count': len(quotes)}


def update_paper_journal(journal, candidates, observations, fee=0, slippage_pct=0.1):
    """Update caller-owned state; delayed paper observations only."""
    import math
    positions = journal.setdefault('positions', {})
    closed = journal.setdefault('closed', [])
    seen = journal.setdefault('seen', [])
    events = []
    for name, q in observations.items():
        p = positions.get(name)
        if not p or q.get('error'):
            continue
        for candle in sorted(q.get('candles', []), key=lambda c: c['time']):
            stamp = candle['time'].isoformat()
            price = float(candle['close'])
            if stamp <= p['last_time'] or not math.isfinite(price) or price <= 0:
                continue
            p['last_time'] = stamp
            p['peak'] = max(p['peak'], price)
            decision = smart_exit(p['entry'], p['peak'], price)
            if decision != 'BEHÅLL':
                trade = dict(p, exit_price=price, exit_time=stamp, exit_reason=decision,
                             **simulated_result(p['entry'], price, p['quantity'], fee, slippage_pct))
                closed.append(trade)
                del positions[name]
                events.append(dict(company=name, kind=decision, time=stamp))
                break
    for item in candidates:
        name = item['company']
        if item['kind'] != 'KÖP-KANDIDAT (FÖRDRÖJD)' or name in positions or item['id'] in seen:
            continue
        q = item['quote']
        if news_candidate_kind(q, item.get('published')) != item['kind']:
            continue
        candle = max(q['candles'], key=lambda c: c['time'])
        price = float(candle['close'])
        if not math.isfinite(price) or price <= 0 or price > 5000:
            continue
        stamp = candle['time'].isoformat()
        positions[name] = dict(company=name, entry=price, peak=price, quantity=int(5000 // price),
                               last_time=stamp, entry_time=stamp, news_id=item['id'])
        seen.append(item['id'])
        events.append(dict(company=name, kind='SIMULERAT KÖP', time=stamp))
    return events


def assess_impact(item):
    """Conservative headline-based assessment; not a price forecast."""
    title = item.get('title', '').casefold()
    rules = [
        (('vinstvarning', 'profit warning', 'sänker prognosen', 'lowers guidance'), 'Negativ', 'Hög', 'Lägre förväntat resultat kan minska värderingen.', 'Kontrollera prognosändringens storlek.'),
        (('nyemission', 'share issue', 'rights issue'), 'Blandad', 'Hög', 'Nytt kapital stärker likviditeten men kan späda ut ägandet.', 'Kontrollera emissionsvillkor och kapitalbehov.'),
        (('avsiktsförklaring', 'letter of intent', 'non-binding', 'icke-bindande'), 'Osäker', 'Medel', 'Möjlig framtida affär, ännu inte säkerställda intäkter.', 'Kontrollera bindande avtal.'),
    ]
    for phrases, direction, importance, case, risk in rules:
        if any(p in title for p in phrases):
            return dict(direction=direction, importance=importance, economic_case=case, risk=risk)
    score, reason = score_news(item)
    if score >= 70:
        case, risk = explain_news(item, score)
        return dict(direction='Positiv', importance='Möjligen hög', economic_case=case, risk=risk)
    return dict(direction='Oklar', importance='Ej fastställd', economic_case='Rubriken räcker inte för att fastställa ekonomisk påverkan.', risk='Läs originalmeddelandet och kontrollera finansiella uppgifter.')

def run_news_only(config, now=None, fetch=None, max_age_hours=24):
    eligible = [c for c in config['companies'] if c.get('segment_verified') is True
                and c.get('segment') in ('Mid Cap', 'Small Cap')]
    matches, failures, diagnostics = scan_detailed(
        {'companies': eligible, 'shared_feeds': config.get('shared_feeds', [])}, now=now, fetch=fetch, max_age_hours=max_age_hours)
    unique = {}
    for item in matches:
        key = (item['company'], ' '.join(item['title'].casefold().split()))
        if key not in unique:
            unique[key] = dict(item, **assess_impact(item))
    return dict(items=sorted(unique.values(), key=lambda x: x['published'], reverse=True),
                eligible_count=len(eligible), failures=failures, diagnostics=diagnostics,
                duplicates=len(matches)-len(unique), quote_count=0)
