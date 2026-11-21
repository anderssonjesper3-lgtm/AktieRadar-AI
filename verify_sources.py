"""Read-only discovery and data health checks. Never writes IDs or sends alerts."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from fastmcp import Client
from avanza_mcp import mcp
from multi_engine import companies, analyze_all
from news_scanner import scan
from test_avanza_forbattrad import SWEDEN

async def discover():
    results=[]
    async with Client(mcp) as client:
        for c in companies():
            item={'company':c['name'],'ticker':c['ticker'],'configured_id':c.get('order_book_id'),'candidates':[]}
            try:
                result=await client.call_tool('search_instruments', {'query':c['name'],'instrument_type':'stock'})
                raw=result.structured_content or {}
                # Preserve provider response; never silently select the first match.
                item['search_response']=raw
                item['verification']='MANUAL_REVIEW_REQUIRED'
            except Exception as exc:
                item['error']=f'{type(exc).__name__}: {exc}'
            results.append(item)
    return results

async def health():
    now=datetime.now(SWEDEN)
    result=[]
    for c,r in zip(companies(),await analyze_all(now=now)):
        candles=r['candles']
        last=candles[-1]['time'] if candles else None
        age=(now-(last.replace(tzinfo=SWEDEN) if last.tzinfo is None else last)).total_seconds()/60-5 if last else None
        result.append({'company':c['name'],'ticker':c['ticker'],'id':c.get('order_book_id'),
                       'status':r['status'],'error':r['error'],'five_min_candles':len(candles),
                       'gaps':r.get('gaps'),'last_candle':last.isoformat() if last else None,
                       'age_after_close_minutes':round(age,1) if age is not None else None,
                       'signal_kind':r['signal']['kind'] if r['signal'] else None})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--discover',action='store_true');p.add_argument('--health',action='store_true');p.add_argument('--news',action='store_true');p.add_argument('--output',default='verification_report.json');a=p.parse_args()
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'verified_live':False,'notes':'IDs and feed URLs must be independently confirmed; data can be delayed.'}
    if a.discover:report['instrument_discovery']=asyncio.run(discover())
    if a.health:report['market_health']=asyncio.run(health())
    if a.news:
        cfg=companies(); articles, failures=scan({'companies':cfg});report['news']={'configured_feeds':sum(len(c.get('feeds',[])) for c in cfg),'matching_articles':len(articles),'failures':failures}
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('Report written:',a.output)
    for row in report.get('market_health',[]):print(row['ticker'],row['status'],row['error'] or '')
    print('Ingen Telegram-notis skickad.')
if __name__=='__main__':main()
