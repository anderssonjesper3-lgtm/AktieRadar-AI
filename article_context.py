import re
import json
from urllib.parse import urlparse, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
from bs4 import BeautifulSoup

def allowed(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in ('news.cision.com', 'mfn.se', 'www.mfn.se') and not p.username and not p.password and p.port in (None,443)

class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def extract_article(raw):
    soup = BeautifulSoup(raw, 'html.parser')
    candidates = []
    def walk(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get('articleBody'), str):
                candidates.append(('JSON-LD', BeautifulSoup(obj['articleBody'], 'html.parser').get_text(' ', strip=True)))
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(tag.get_text()))
        except (ValueError, TypeError):
            pass
    for tag in soup.select('script,style,nav,footer,header,aside'):
        tag.decompose()
    for body in soup.select('[itemprop="articleBody"], .release-body, .release-content, .mfn-news-body, .mfn-article-body, .press-release-body, article'):
        candidates.append(('HTML', ' '.join(body.stripped_strings)))
    candidates = [(method, text) for method, text in candidates if len(text) >= 30]
    if not candidates:
        return {'status':'article not identified', 'reason':'No identifiable article body'}
    method, text = max(candidates, key=lambda pair: len(pair[1]))
    return {'status':'ok','text':text[:100000], 'method':method,'truncated':len(text)>100000}

def read_article(url):
    if not allowed(url):
        return {'status':'unsupported source'}
    try:
        with build_opener(SafeRedirect()).open(Request(url,headers={'User-Agent':'AktieRadar NewsMonitor'}),timeout=10) as response:
            raw = response.read(2000001)
            final_url = response.geturl()
            content_type = response.headers.get('Content-Type','')
        if len(raw)>2000000:
            return {'status':'unavailable','reason':'Response exceeds size limit'}
        if 'pdf' in content_type.lower() or raw.startswith(b'%PDF'):
            return {'status':'PDF not supported'}
        result = extract_article(raw)
        if result['status'] != 'ok' and urlparse(final_url).hostname in ('mfn.se','www.mfn.se') and not urlparse(final_url).path.endswith('.iframe'):
            p = urlparse(final_url)
            alternate = p._replace(path=p.path+'.iframe',fragment='').geturl()
            if allowed(alternate):
                with build_opener(SafeRedirect()).open(Request(alternate,headers={'User-Agent':'AktieRadar NewsMonitor'}),timeout=10) as response:
                    raw = response.read(2000001)
                if len(raw)<=2000000:
                    alternate_result = extract_article(raw)
                    if alternate_result['status']=='ok':
                        result = dict(alternate_result, method='MFN iframe / '+alternate_result['method'])
        return result
    except Exception as exc:
        return {'status':'unavailable','error':type(exc).__name__}

def article_facts(title, article):
    if article.get('status')!='ok':
        return {}
    body = article['text']
    sentences = re.split(r'(?<=[.!?])\s+',body)
    terms = r'\b(purchase[d]?|bought|sold|sale|acquired|disposed|köpt|sålt|förvärvat|avyttrat|order|contract|kontrakt|MSEK|million|miljoner|shares|aktier)\b'
    excerpts = [s.strip()[:600] for s in sentences if re.search(terms,s,re.I)][:4]
    return {'excerpts':excerpts,'note':'Utdrag ur originaltexten; transaktionens riktning och belopp måste framgå uttryckligen.'}


def swedish_summary(item, article):
    title = item.get('title','').casefold()
    body = article.get('text','').casefold() if article.get('status') == 'ok' else ''
    if any(x in title for x in ('notification of trade','insider','insyn')):
        buy = bool(re.search(r'\b(purchased|purchase|bought|köpt)\b',body))
        sell = bool(re.search(r'\b(sold|sale|sålt)\b',body))
        direction = 'aktieköp' if buy and not sell else 'aktieförsäljning' if sell and not buy else 'oklar transaktionsriktning'
        return 'Insynsanmälan: texten indikerar '+direction+'. Kontrollera originalet. En insynsaffär påverkar normalt inte bolagets intäkter direkt.'
    for terms, summary in [
        (('profit warning','vinstvarning','lowers guidance'),'Bolaget meddelar en vinstvarning eller sänkt prognos.'),
        (('raises guidance','höjer prognosen'),'Bolaget meddelar en höjd prognos.'),
        (('letter of intent','avsiktsförklaring'),'Nyheten gäller en avsiktsförklaring.'),
        (('share issue','rights issue','nyemission'),'Nyheten gäller en aktieemission.'),
        (('order','contract','kontrakt'),'Nyheten gäller en order eller ett avtal.'),
        (('interim report','delårsrapport'),'Bolaget har publicerat en delårsrapport.'),
        (('acquisition','förvärv'),'Nyheten gäller ett förvärv.')]:
        if any(t in title for t in terms):
            return summary+' '+item.get('economic_case','')
    return 'Bolaget har publicerat ett meddelande. Innehållet kan inte sammanfattas säkert automatiskt; se originalutdragen.'
