"""Optional Avanza SSE bridge for AktieRadar.

Requires the third-party avanza-ts CLI installed separately and an authenticated
session on the machine running this process. Never commit session files.
This bridge does not place orders and does not claim exchange real-time rights.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

def normalize_quote(event, received_at=None):
    """Validate raw quote; unknown exchange timestamp means latency is unverified."""
    if not isinstance(event, dict):
        raise ValueError("Quote must be a JSON object")
    orderbook = event.get("orderbookId")
    price = event.get("lastPrice")
    if not orderbook or isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        raise ValueError("Missing orderbookId or valid positive lastPrice")
    received_at = received_at or datetime.now(timezone.utc)
    source_time = event.get("lastPriceUpdated") or event.get("updated") or event.get("timestamp") or event.get("time") or event.get("lastUpdated")
    return {
        "provider": "avanza_unofficial_sse",
        "orderbook_id": str(orderbook),
        "last_price": float(price),
        "source_timestamp_raw": source_time,
        "received_at_utc": received_at.isoformat(),
        "latency_verified": False,
        "realtime_verified": False,
        "raw": event,
    }

def stream_quotes(orderbook_ids, output):
    """Run authenticated CLI and persist valid NDJSON; no secrets in arguments."""
    cmd = ["avanza", "push", "quotes", "--orderbook-ids", ",".join(orderbook_ids)]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1) as process:
        for line in process.stdout:
            try:
                event = json.loads(line)
                quote = normalize_quote(event)
            except (ValueError, json.JSONDecodeError) as exc:
                print(f"Skipped invalid quote: {exc}", file=sys.stderr)
                continue
            output.write(json.dumps(quote, ensure_ascii=False) + "\n")
            output.flush()
        if process.wait() != 0:
            raise RuntimeError(f"Avanza CLI exited with status {process.returncode}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--orderbook-ids", required=True, help="Comma-separated verified Avanza IDs")
    parser.add_argument("--output", default="avanza_quotes.ndjson")
    args = parser.parse_args()
    ids = [x.strip() for x in args.orderbook_ids.split(",") if x.strip()]
    if not ids or not all(x.isdecimal() for x in ids):
        parser.error("Provide numeric, verified Avanza orderbook IDs")
    path = Path(args.output)
    with path.open("a", encoding="utf-8") as output:
        stream_quotes(ids, output)

if __name__ == "__main__":
    main()
