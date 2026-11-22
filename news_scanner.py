"""Conservative RSS/Atom announcement scanner. Headlines are WATCH only, never buy signals."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

CONFIG_PATH = Path(__file__).with_name('news_watchlist.json')
KEYWORDS = (
    'order', 'orders', 'beställning', 'beställningar', 'kontrakt', 'contract',
    'avtal', 'agreement', 'ramavtal', 'framework agreement', 'upphandling',
    'förvärv', 'acquisition', 'acquires', 'acquired', 'merger', 'fusion',
    'strategiskt samarbete', 'strategic partnership', 'samarbete', 'partnership',
    'investering', 'investment', 'expansion', 'kapacitetsökning', 'ny kund',
    'new customer', 'letter of intent', 'avsiktsförklaring', 'memorandum of understanding',
    'delårsrapport', 'årsredovisning', 'interim report', 'annual report',
    'vd', 'ceo', 'cfo', 'nyemission', 'riktad emission', 'share issue',
)
RISK_WORDS = (
    'företrädesemission', 'nyemission', 'bankruptcy', 'konkurs',
    'vinstvarning', 'profit warning', 'nedskrivning', 'impairment',
    'förlust', 'loss', 'återkallelse', 'recall', 'utredning', 'investigation',
    'försening', 'delay', 'avbokning', 'cancellation', 'insolvens', 'insolvency',
)


def load_config(path=CONFIG_PATH):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(config, dict) or not isinstance(config.get('companies'), list):
        raise ValueError('Ogiltig nyhetsbevakningslista')
    for company in config['companies']:
        if not company.get('name') or not company.get('aliases'):
            raise ValueError('Bolag behöver namn och sökord')
        for feed in company.get('feeds', []):
            parsed = urlparse(feed)
            if parsed.scheme != 'https' or not parsed.hostname:
                raise ValueError('Nyhetsflöden måste ha giltiga HTTPS-adresser')
    return config


def parse_date(raw):
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


class _MFNHTMLParser(HTMLParser):
    """Small, conservative parser for MFN's public company news archive page."""
    DATE_RE = re.compile(r'\b(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)\b')

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.context = ''
        self.href = None
        self.anchor_text = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            attrs = dict(attrs)
            self.href = attrs.get('href')
            self.anchor_text = []

    def handle_data(self, data):
        if self.href is not None:
            self.anchor_text.append(data)
        else:
            self.context = (self.context + ' ' + data)[-500:]

    def handle_endtag(self, tag):
        if tag.lower() != 'a' or self.href is None:
            return
        title = ' '.join(' '.join(self.anchor_text).split())
        href = urljoin(self.base_url, self.href)
        match = self.DATE_RE.search(self.context)
        if title and match and '/a/' in href and urlparse(href).hostname:
            self.items.append({
                'title': unescape(title), 'link': href,
                'date': parse_date(match.group(1)), 'description': '',
            })
        self.href = None
        self.anchor_text = []
        self.context = ''


def extract_items(xml_bytes, source_url=None):
    raw = xml_bytes.decode('utf-8', errors='replace') if isinstance(xml_bytes, bytes) else str(xml_bytes)
    if '<html' in raw[:1000].casefold() or 'mfn.se/all/a/' in (source_url or ''):
        parser = _MFNHTMLParser(source_url or 'https://www.mfn.se/')
        parser.feed(raw)
        return parser.items
    root = ET.fromstring(raw.encode('utf-8'))
    entries = []
    for node in root.iter():
        if node.tag.split('}')[-1] not in ('item', 'entry'):
            continue
        fields = {}
        for child in node:
            key = child.tag.split('}')[-1]
            if key == 'link':
                fields['link'] = child.attrib.get('href') or (child.text or '')
            elif key in ('title', 'pubDate', 'published', 'updated', 'description', 'summary'):
                fields[key] = ''.join(child.itertext()).strip()
        entries.append({'title': unescape(fields.get('title', '')),
                        'link': fields.get('link', ''),
                        'date': parse_date(fields.get('pubDate') or fields.get('published') or fields.get('updated')),
                        'description': unescape(fields.get('description') or fields.get('summary') or ''),
                        'metadata': ' '.join(' '.join(node.itertext()).split()) + ' ' +
                                    ' '.join(str(v) for el in node.iter() for v in el.attrib.values())})
    return entries


def has_phrase(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(phrase.casefold()) + r'(?!\w)', text.casefold()))


def classify_news_detailed(item, company, now, max_age_hours=24):
    published = item.get('date')
    if published is None:
        return None, 'datum_saknas'
    age = now - published
    if not timedelta(0) <= age <= timedelta(hours=max_age_hours):
        return None, 'utanför_datumintervall'
    link = item.get('link', '')
    parsed = urlparse(link)
    if parsed.scheme != 'https' or not parsed.hostname:
        return None, 'ogiltig_länk'
    text = item.get('title', '') + ' ' + item.get('description', '')
    issuer_text = text + ' ' + item.get('metadata', '')
    issuer_match = item.get('_feed_company') == company['name'] or any(
        has_phrase(issuer_text, alias) for alias in company['aliases']
    )
    if not issuer_match:
        return None, 'bolag_matchar_inte'
    if any(has_phrase(text, word) for word in RISK_WORDS):
        category = 'RISKNYHET'
    elif any(has_phrase(text, word) for word in KEYWORDS):
        category = 'ORDER/AVTAL – GRANSKA'
    elif item.get('_feed_company') == company['name']:
        category = 'BOLAGSNYHET – GRANSKA'
    else:
        return None, 'ingen_relevant_nyhetskategori'
    key = hashlib.sha256((company['name'] + '\n' + link).encode()).hexdigest()[:24]
    return {'kind': 'NYHET-VAKTA', 'category': category, 'company': company['name'],
            'title': item['title'][:180], 'description': item.get('description', '')[:4000], 'url': link, 'published': published,
            'id': 'NEWS:' + key}, 'match'


def classify_news(item, company, now, max_age_hours=24):
    match, _ = classify_news_detailed(item, company, now, max_age_hours=max_age_hours)
    return match


def scan_detailed(config=None, now=None, fetch=None, max_age_hours=24):
    """Fetch each unique RSS feed once, then match its items to configured issuers."""
    config = config if config is not None else load_config()
    now = now or datetime.now(timezone.utc)

    def default_fetch(url):
        request = Request(url, headers={'User-Agent': 'AktieRadar/6.0 NewsMonitor'})
        with urlopen(request, timeout=15) as response:
            return response.read(2_000_000)

    fetch = fetch or default_fetch
    feed_companies = {}
    for company in config['companies']:
        for url in company.get('feeds', []):
            feed_companies.setdefault(url, []).append(company)

    results = []
    failures = []
    diagnostics = []
    for url, companies in feed_companies.items():
        try:
            items = extract_items(fetch(url), source_url=url)
            raw_count = len(items)
            if len(companies) == 1:
                items = [dict(item, _feed_company=companies[0]['name']) for item in items]
        except Exception as exc:
            names = ', '.join(company['name'] for company in companies)
            failures.append((names, type(exc).__name__))
            diagnostics.append({'feed': url, 'companies': names, 'status': 'FEL', 'raw_items': 0, 'matched': 0, 'error': type(exc).__name__})
            continue
        before_count = len(results)
        rejects = {'datum_saknas': 0, 'utanför_datumintervall': 0, 'ogiltig_länk': 0,
                   'bolag_matchar_inte': 0, 'ingen_relevant_nyhetskategori': 0}
        for item in items:
            for company in companies:
                match, reason = classify_news_detailed(item, company, now, max_age_hours=max_age_hours)
                if match:
                    results.append(match)
                elif reason in rejects:
                    rejects[reason] += 1
        diagnostics.append({'feed': url, 'companies': ', '.join(c['name'] for c in companies),
                            'status': 'OK', 'raw_items': raw_count,
                            'matched': len(results) - before_count, **rejects, 'error': ''})

    unique = {item['id']: item for item in results}
    return list(unique.values()), failures, diagnostics


def scan(config=None, now=None, fetch=None, max_age_hours=24):
    matches, failures, _ = scan_detailed(config=config, now=now, fetch=fetch, max_age_hours=max_age_hours)
    return matches, failures
