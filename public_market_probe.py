"""Public endpoint connectivity diagnostics. No login, trading or real-time claims."""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

ENDPOINTS={
    "avanza_public_instrument":"https://www.avanza.se/_api/market-guide/stock/5401",
    "yahoo_chart":"https://query1.finance.yahoo.com/v8/finance/chart/SAAB-B.ST?interval=1m&range=1d",
}
def main():
    for name,url in ENDPOINTS.items():
        result={"source":name,"checked_at_utc":datetime.now(timezone.utc).isoformat(),"realtime_verified":False}
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"AktieRadar-data-diagnostic/0.1","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=12) as response:
                data=response.read(1024*1024)
                result.update(http_status=response.status,bytes_received=len(data),json_parseable=False)
                try:
                    body=json.loads(data)
                    result["json_parseable"]=True
                    if name=="yahoo_chart":
                        chart=body.get("chart",{})
                        results=chart.get("result") or []
                        if results:
                            stamps=results[0].get("timestamp") or []
                            result["point_count"]=len(stamps)
                            if stamps:
                                last=datetime.fromtimestamp(max(stamps),timezone.utc)
                                result["latest_timestamp_utc"]=last.isoformat()
                                result["latest_timestamp_age_seconds"]=round((datetime.now(timezone.utc)-last).total_seconds())
                except (ValueError,TypeError):
                    pass
        except Exception as exc:
            result.update(error_type=type(exc).__name__,error=str(exc)[:200])
        print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
