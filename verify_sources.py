"""Read-only discovery and data health checks. Never writes IDs or sends alerts."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from fastmcp import Client
from avanza_mcp import mcp
from multi_engine import companies, analyze_all
from news_scanner import scan_detailed
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
        cfg=companies(); articles, failures, diagnostics=scan_detailed({'companies':cfg});report['news']={'configured_feeds':sum(len(c.get('feeds',[])) for c in cfg),'matching_articles':len(articles),'failures':failures,'sources':diagnostics,'parsed_sources':sum(d['raw_items']>0 for d in diagnostics)}
    health=report.get('market_health',[])
    if health:
        report['market_summary']={
            'configured_stocks':len(health),
            'stocks_with_candles':sum(x['five_min_candles']>0 for x in health),
            'stocks_with_usable_signals':sum(x['signal_kind'] is not None for x in health),
            'stocks_with_errors':sum(bool(x['error']) for x in health),
        }
    news=report.get('news')
    report['verified_live']=bool(health) and all(
        x['five_min_candles']>0 and not x['error'] for x in health
    ) and (news is None or (news['configured_feeds']>0 and
        news['parsed_sources']==news['configured_feeds'] and not news['failures']))
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('Report written:',a.output)
    print('VERIFIED_LIVE:',report['verified_live'])
    print('MARKET_SUMMARY:',report.get('market_summary'))
    print('NEWS_SUMMARY:',{k:v for k,v in report.get('news',{}).items() if k!='sources'})
    for row in report.get('market_health',[]):print(row['ticker'],row['status'],row['error'] or '')
    print('Ingen Telegram-notis skickad.')
if __name__=='__main__':main()
