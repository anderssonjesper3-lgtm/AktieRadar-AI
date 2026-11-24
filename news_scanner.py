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
    'höjer prognosen', 'raises guidance', 'höjd prognos', 'raised guidance',
    'myndighetsgodkännande', 'regulatory approval', 'order', 'orders', 'beställning', 'beställningar', 'kontrakt', 'contract',
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


class _CompanyNewsHTMLParser(HTMLParser):
    """Extract dated article links from official investor/press-release pages.

    It uses nearby visible publication dates and article-like links only.
    A page that cannot be parsed produces zero items and remains visible in diagnostics.
    """
    DATE_PATTERNS = (
        re.compile(r'\b(20\d{2}[-.]\d{2}[-.]\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\b'),
        re.compile(r'\b(\d{1,2}\s+[A-Za-z]{3,9},?\s+20\d{2}(?:\s+at\s+\d{1,2}:\d{2})?)\b', re.I),
        re.compile(r'\b([A-Za-z]{3,9}\s+\d{1,2},?\s+20\d{2})\b', re.I),
    )
    ARTICLE_HINTS = ('news', 'press', 'release', 'investor', 'announcement', 'article', '/a/')

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts = []
        self.anchors = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for date_attr in ('datetime', 'data-date', 'content'):
            if attrs.get(date_attr):
                self.parts.append(' ' + str(attrs[date_attr]) + ' ')
        if tag.lower() == 'a' and attrs.get('href'):
            self.active = {'href': attrs['href'], 'start': sum(map(len, self.parts)), 'text': []}

    def handle_data(self, data):
        if not data:
            return
        self.parts.append(data)
        if self.active is not None:
            self.active['text'].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.active is not None:
            self.active['end'] = sum(map(len, self.parts))
            self.anchors.append(self.active)
            self.active = None

    @staticmethod
    def _date_near(text):
        candidates = []
        for pattern in _CompanyNewsHTMLParser.DATE_PATTERNS:
            for match in pattern.finditer(text):
                parsed = parse_date(match.group(1))
                if parsed is None:
                    # Handle common English dates without a timezone.
                    for fmt in ('%d %B %Y', '%d %b %Y', '%d %B, %Y', '%d %b, %Y',
                                '%B %d %Y', '%B %d, %Y', '%b %d %Y', '%b %d, %Y',
                                '%d %b, %Y at %H:%M', '%d %B, %Y at %H:%M',
                                '%d %b %Y %H:%M', '%d %B %Y %H:%M'):
                        try:
                            parsed = datetime.strptime(match.group(1), fmt).replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            pass
                if parsed:
                    candidates.append((match.start(), parsed))
        return candidates

    def items(self):
        text = ''.join(self.parts)
        results, seen = [], set()
        for anchor in self.anchors:
            title = ' '.join(' '.join(anchor['text']).split())
            href = urljoin(self.base_url, anchor['href'])
            parsed_url = urlparse(href)
            if (len(title) < 12 or parsed_url.scheme != 'https' or not parsed_url.hostname
                    or parsed_url.hostname != urlparse(self.base_url).hostname
                    or href in seen):
                continue
            path = parsed_url.path.casefold()
            if not any(hint in path for hint in self.ARTICLE_HINTS):
                continue
            # Date text is usually adjacent to the headline card. Use a bounded
            # window around the link; no date means no fabricated timestamp.
            start = max(0, anchor['start'] - 450)
            finish = min(len(text), anchor['end'] + 250)
            nearby = text[start:finish]
            dates = self._date_near(nearby)
            if not dates:
                continue
            # The closest date to the center of the anchor window is the safest match.
            center = max(0, anchor['start'] - start)
            date_pos, published = min(dates, key=lambda pair: abs(pair[0] - center))
            seen.add(href)
            results.append({
                'title': unescape(title), 'link': href, 'date': published,
                'description': nearby[:1500],
            })
        return results


def extract_items(xml_bytes, source_url=None):
    raw = xml_bytes.decode('utf-8', errors='replace') if isinstance(xml_bytes, bytes) else str(xml_bytes)
    if '<html' in raw[:3000].casefold() or '<!doctype html' in raw[:3000].casefold():
        parser = _CompanyNewsHTMLParser(source_url or 'https://example.invalid/')
        parser.feed(raw)
        return parser.items()
    if 'mfn.se/' in (source_url or '') and '<' in raw[:1000]:
        parser = _CompanyNewsHTMLParser(source_url)
        parser.feed(raw)
        return parser.items()
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
            if len(companies) == 1 and companies[0].get('source_type') == 'official_investor_relations':
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
        samples = [
            {'title': (item.get('title') or '')[:140],
             'published': item.get('date').isoformat() if item.get('date') else 'SAKNAS',
             'url': item.get('link', '')[:220]}
            for item in items[:20]
        ]
        diagnostics.append({'feed': url, 'companies': ', '.join(c['name'] for c in companies),
                            'status': 'OK', 'raw_items': raw_count,
                            'matched': len(results) - before_count, **rejects,
                            'sample_headlines': samples, 'error': ''})

    unique = {item['id']: item for item in results}
    return list(unique.values()), failures, diagnostics


def scan(config=None, now=None, fetch=None, max_age_hours=24):
    matches, failures, _ = scan_detailed(config=config, now=now, fetch=fetch, max_age_hours=max_age_hours)
    return matches, failures
