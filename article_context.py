import re
from functools import lru_cache
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from bs4 import BeautifulSoup

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

@lru_cache(maxsize=256)
def read_article(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname != 'news.cision.com' or p.username or p.password or p.port not in (None,443):
        return {'status':'unsupported source'}
    try:
        with build_opener(NoRedirect()).open(Request(url,headers={'User-Agent':'AktieRadar NewsMonitor'}),timeout=10) as response:
            raw = response.read(2000000)
        soup = BeautifulSoup(raw,'html.parser')
        for tag in soup.select('script,style,nav,footer,header,aside'):
            tag.decompose()
        body = soup.select_one('[itemprop="articleBody"], .release-body, .release-content, article, main')
        if body is None:
            return {'status':'article not identified'}
        text = ' '.join(body.stripped_strings)[:30000]
        if len(text)<100:
            return {'status':'article too short'}
        return {'status':'ok','text':text}
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
