"""Read-only, unauthenticated Avanza MCP market probe. Never asserts realtime."""
import asyncio
import json
from datetime import datetime, timezone
from test_avanza_forbattrad import fetch_points, build_candles, SWEDEN

async def main():
    report={"checked_at_utc":datetime.now(timezone.utc).isoformat(),"provider":"avanza_mcp_unofficial","realtime_verified":False}
    try:
        points, raw_count=await asyncio.wait_for(fetch_points(order_book_id="5401"),timeout=90)
        candles,gaps=build_candles(points)
        report.update(raw_points=raw_count,unique_points=len(points),completed_five_minute_buckets=len(candles),incomplete_buckets=len(gaps))
        if points:
            latest=datetime.fromtimestamp(points[-1]["timestamp"]/1000,timezone.utc)
            report["latest_source_point_utc"]=latest.isoformat()
            report["latest_point_age_seconds"]=round((datetime.now(timezone.utc)-latest).total_seconds(),1)
            report["latest_point_in_future"]=latest>datetime.now(timezone.utc)
            report["latest_close"]=points[-1].get("close")
        report["status"]="DATA_RETURNED_UNVERIFIED" if points else "EMPTY"
    except Exception as exc:
        report.update(status="ERROR",error_type=type(exc).__name__,error=str(exc)[:400])
    print(json.dumps(report,ensure_ascii=False))
    if report["status"]=="ERROR":
        raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
