"""Read-only Avanza instrument and quote verification.

Never changes configured IDs, places orders, or sends Telegram alerts.
A quote is labelled LIVE only when the provider explicitly reports real-time
status and supplies a recent provider timestamp.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastmcp import Client
from avanza_mcp import mcp

SWEDEN = ZoneInfo("Europe/Stockholm")
MAX_QUOTE_AGE_SECONDS = 180


def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _find_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _find_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_dicts(child)


def _normalize_text(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _candidate_rows(raw):
    rows = []
    for item in _find_dicts(raw):
        if any(k in item for k in ("orderBookId", "order_book_id", "instrumentId", "id")):
            rows.append(item)
    # De-duplicate without assuming provider's response schema.
    seen, result = set(), []
    for row in rows:
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def assess_identity(company, configured_id, candidates):
    wanted = {_normalize_text(company.get("name"))}
    wanted.update(_normalize_text(x) for x in company.get("aliases", []))
    wanted.discard("")
    matched_id = []
    for row in candidates:
        rid = str(row.get("orderBookId", row.get("order_book_id", row.get("instrumentId", row.get("id", "")))))
        if rid == str(configured_id):
            matched_id.append(row)
    if not matched_id:
        return "ID_NOT_FOUND_IN_SEARCH", None
    # Require a returned name/title matching a configured company name/alias.
    for row in matched_id:
        name = row.get("name") or row.get("instrumentName") or row.get("title") or row.get("description")
        normalized = _normalize_text(name)
        if normalized and any(normalized == x or x in normalized or normalized in x for x in wanted):
            return "ID_AND_NAME_MATCH", row
    return "ID_FOUND_NAME_UNCONFIRMED", matched_id[0]


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Handle seconds and milliseconds.
        stamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(stamp, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def assess_quote(raw, now=None):
    now = now or datetime.now(timezone.utc)
    payload = raw if isinstance(raw, dict) else {}
    candidates = list(_find_dicts(payload))
    real_time = next((x.get("isRealTime") for x in candidates if "isRealTime" in x), None)
    stamp_value = next((x.get("timeOfLast") or x.get("timestamp") or x.get("time") for x in candidates
                        if x.get("timeOfLast") or x.get("timestamp") or x.get("time")), None)
    stamp = _parse_timestamp(stamp_value)
    age = (now - stamp).total_seconds() if stamp else None
    if real_time is True and age is not None and 0 <= age <= MAX_QUOTE_AGE_SECONDS:
        status = "LIVE"
    elif real_time is False:
        status = "DELAYED"
    elif age is not None and age > MAX_QUOTE_AGE_SECONDS:
        status = "STALE"
    else:
        status = "UNKNOWN"
    return {"status": status, "provider_isRealTime": real_time,
            "provider_timestamp": stamp.isoformat() if stamp else None,
            "age_seconds": round(age, 1) if age is not None else None}


async def verify_company(client, company):
    row = {"company": company.get("name"), "ticker": company.get("ticker"),
           "configured_id": str(company.get("order_book_id") or ""),
           "identity_status": "UNKNOWN", "quote_status": "UNKNOWN",
           "chart_status": "UNKNOWN", "errors": []}
    if not row["configured_id"].isdigit():
        row["identity_status"] = "CONFIGURED_ID_MISSING_OR_INVALID"
        return row

    try:
        search = await client.call_tool("search_instruments", {
            "query": company.get("name", ""), "instrument_type": "stock"
        })
        raw = _plain(getattr(search, "structured_content", None) or {})
        row["search_response"] = raw
        candidates = _candidate_rows(raw)
        status, matched = assess_identity(company, row["configured_id"], candidates)
        row["identity_status"] = status
        row["matched_instrument"] = matched
        row["candidate_count"] = len(candidates)
    except Exception as exc:
        row["errors"].append("instrument_search: " + type(exc).__name__ + ": " + str(exc))

    try:
        quote = await client.call_tool("get_stock_quote", {"order_book_id": row["configured_id"]})
        quote_raw = _plain(getattr(quote, "structured_content", None) or {})
        row["quote"] = quote_raw
        row.update(assess_quote(quote_raw))
        row["quote_status"] = row["status"]
    except Exception as exc:
        row["quote_status"] = "QUOTE_TOOL_UNAVAILABLE_OR_FAILED"
        row["errors"].append("quote: " + type(exc).__name__ + ": " + str(exc))

    try:
        chart = await client.call_tool("get_stock_chart", {
            "order_book_id": row["configured_id"], "time_period": "today", "offset": 0, "limit": 10
        })
        chart_raw = _plain(getattr(chart, "structured_content", None) or {})
        data = chart_raw.get("data", {}) if isinstance(chart_raw, dict) else {}
        ohlc = data.get("ohlc") if isinstance(data, dict) else None
        resolution = (data.get("metadata", {}).get("resolution", {}).get("chartResolution")
                      if isinstance(data, dict) else None)
        row["chart_status"] = "OK" if isinstance(ohlc, list) and bool(ohlc) and resolution == "minute" else "UNVERIFIED_RESPONSE"
        row["chart_resolution"] = resolution
        row["chart_points_returned"] = len(ohlc) if isinstance(ohlc, list) else 0
        row["latest_chart_point"] = ohlc[-1] if isinstance(ohlc, list) and ohlc else None
    except Exception as exc:
        row["chart_status"] = "CHART_FETCH_FAILED"
        row["errors"].append("chart: " + type(exc).__name__ + ": " + str(exc))
    return row


async def run(config_path="news_watchlist.json"):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "read_only": True, "orders_placed": False, "telegram_sent": False,
              "live_data_verified": False, "companies": []}
    async with Client(mcp) as client:
        for company in config.get("companies", []):
            report["companies"].append(await verify_company(client, company))
    rows = report["companies"]
    report["summary"] = {
        "total": len(rows),
        "identity_confirmed": sum(x["identity_status"] == "ID_AND_NAME_MATCH" for x in rows),
        "quote_live": sum(x["quote_status"] == "LIVE" for x in rows),
        "chart_ok": sum(x["chart_status"] == "OK" for x in rows),
    }
    report["live_data_verified"] = bool(rows) and all(
        x["identity_status"] == "ID_AND_NAME_MATCH" and
        x["quote_status"] == "LIVE" and x["chart_status"] == "OK" for x in rows
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="news_watchlist.json")
    parser.add_argument("--output", default="avanza_verification_report.json")
    args = parser.parse_args()
    report = asyncio.run(run(args.config))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    for item in report["companies"]:
        print(item["ticker"], item["identity_status"], item["quote_status"], item["chart_status"])
    print("LIVE DATA VERIFIED:", report["live_data_verified"])
    print("Read-only: no orders and no Telegram alerts.")


if __name__ == "__main__":
    main()
