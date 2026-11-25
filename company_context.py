import re
import math
from functools import lru_cache
from datetime import datetime, timezone

@lru_cache(maxsize=512)
def _profile(ticker, day):
    import yfinance as yf
    info = yf.Ticker(ticker).get_info()
    keys = ('totalRevenue','marketCap','operatingMargins','totalCash','totalDebt','industry','financialCurrency','currency','longName')
    return {k: info.get(k) for k in keys}

def company_profile(company, now=None):
    ticker = company.get('ticker','').strip().replace(' ','-')
    if not ticker or not re.fullmatch(r'[A-Za-z0-9.-]+',ticker):
        return {'status':'missing ticker'}
    symbol = ticker + '.ST'
    try:
        data = _profile(symbol, (now or datetime.now(timezone.utc)).date().isoformat())
        return dict(data, status='ok' if data.get('totalRevenue') else 'incomplete',
                    source='https://finance.yahoo.com/quote/'+symbol+'/', symbol=symbol)
    except Exception as exc:
        return {'status':'unavailable', 'error':type(exc).__name__}

def order_comparison(item, profile):
    title = item.get('title','')
    if not re.search(r'order|contract|kontrakt|avtal',title,re.I):
        return None
    matches = re.findall(r'(?:SEK\s*)?(\d+(?:[.,]\d+)?)\s*(MSEK|miljoner kronor|million SEK|miljarder kronor|billion SEK|BSEK)',title,re.I)
    revenue = profile.get('totalRevenue')
    if len(matches)!=1 or profile.get('financialCurrency')!='SEK' or not isinstance(revenue,(int,float)) or not math.isfinite(revenue) or revenue<=0:
        return None
    number, unit = matches[0]
    value = float(number.replace(',','.')) * (1e9 if unit.lower() in ('miljarder kronor','billion sek','bsek') else 1e6)
    return {'mentioned_amount_sek':value,'revenue_ratio_pct':round(100*value/revenue,2),
            'note':'Belopp nämnt i rubriken jämfört med rapporterad omsättning; inte verifierat ordervärde eller årlig intäkt.'}
