"""Read-only latency audit for AktieRadar 6.0.

Run during Stockholm trading hours:
    python realtime_probe.py

Uses the same public Avanza chart endpoint as the app. Does not log in,
place orders, send Telegram messages, or modify the paper journal.
This tests observed feed lag, NOT whether an alternative real-time API exists.
"""
import asyncio
import json
from datetime import datetime
from statistics import median

from multi_engine import companies
from test_avanza_forbattrad import SWEDEN, fetch_points


def assess_lag(age_minutes):
    if age_minutes is None or age_minutes < -2:
        return "INVALID"
    if age_minutes <= 5:
        return "NEAR_LIVE_CANDIDATE_UNVERIFIED"
    if age_minutes <= 12:
        return "LAGGING"
    if age_minutes <= 25:
        return "LIKELY_DELAYED_15M"
    return "STALE"


async def audit():
    rows = []
    for company in companies():
        now = datetime.now(SWEDEN)
        row = {"company": company["name"], "ticker": company.get("ticker"),
               "checked_at": now.isoformat(), "source": "Avanza chart via avanza_mcp"}
        try:
            points, _ = await fetch_points(str(company["order_book_id"]))
            if not points:
                row.update(status="NO_POINTS", point_count=0)
            else:
                last = datetime.fromtimestamp(points[-1]["timestamp"] / 1000, tz=SWEDEN)
                age = round((now - last).total_seconds() / 60, 2)
                row.update(status=assess_lag(age), point_count=len(points),
                           last_point=last.isoformat(), age_minutes=age)
        except Exception as exc:
            row.update(status="ERROR", error=str(exc)[:240])
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    ages = [r["age_minutes"] for r in rows if "age_minutes" in r]
    print(json.dumps({"summary": {"observed": len(ages), "total": len(rows),
          "median_lag_minutes": median(ages) if ages else None,
          "near_live_candidates": sum(r["status"] == "NEAR_LIVE_CANDIDATE_UNVERIFIED" for r in rows),
          "note": "Low lag alone does not prove exchange real-time licensing."}},
          ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(audit())
