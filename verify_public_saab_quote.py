"""Verify actual public Saab B chart prices and timestamp metadata; never mark live."""
import json
import urllib.request
from datetime import datetime, timezone

URL="https://query1.finance.yahoo.com/v8/finance/chart/SAAB-B.ST?interval=1m&range=1d"
req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
with urllib.request.urlopen(req,timeout=15) as response:
    payload=json.load(response)
result=(payload.get("chart",{}).get("result") or [])[0]
meta=result.get("meta") or {}
timestamps=result.get("timestamp") or []
quotes=(result.get("indicators",{}).get("quote") or [{}])[0]
valid=[]
for i,ts in enumerate(timestamps):
    try:
        close=quotes["close"][i]
        if isinstance(close,(int,float)) and close>0:
            valid.append((ts,close))
    except (KeyError,IndexError,TypeError):
        pass
now=datetime.now(timezone.utc)
report={"provider":"yahoo_chart_public_unofficial","symbol":meta.get("symbol"),
        "exchange_name":meta.get("exchangeName"),"currency":meta.get("currency"),
        "instrument_type":meta.get("instrumentType"),
        "exchange_timezone":meta.get("exchangeTimezoneName"),
        "gmtoffset":meta.get("gmtoffset"),
        "regular_market_time":meta.get("regularMarketTime"),
        "quote_count":len(valid),"realtime_verified":False,
        "exchange_last_trade_verified":False,
        "timestamp_is_exchange_trade_time_verified":False,
        "usage_rights_verified":False,
        "checked_at_utc":now.isoformat()}
if valid:
    ts,close=valid[-1]
    report.update(last_chart_close=round(close,4),last_chart_timestamp_utc=datetime.fromtimestamp(ts,timezone.utc).isoformat(),chart_timestamp_age_seconds=round(now.timestamp()-ts,1))
print(json.dumps(report,ensure_ascii=False))
