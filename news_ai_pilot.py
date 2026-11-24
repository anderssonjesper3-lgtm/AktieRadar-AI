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

async def run_news_pilot(config, now=None, fetch=None, quote=None, max_age_hours=24):
    now = now or datetime.now(timezone.utc)
    eligible = [c for c in config['companies']
                if c.get('segment') in ('Mid Cap', 'Small Cap')
                and c.get('segment_verified') is True]
    matches, failures, diagnostics = scan_detailed(
        {'companies': eligible}, now=now, fetch=fetch, max_age_hours=max_age_hours)
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
        item['kind'] = 'NYHET-VAKTA'
        item['economic_case'], item['risk'] = explain_news(item, item['score'])
    return {'candidates': list(candidates.values()), 'eligible_count': len(eligible),
            'failures': failures, 'diagnostics': diagnostics, 'quote_count': len(quotes)}
