"""Persistent paper-trade journal for AktieRadar AI.

Records signal candidates once and simulates exits at configurable target/stop levels.
Never places orders. The JSON file is local to the app host; use persistent storage
or export backups when deploying to an ephemeral hosting platform.
"""
from __future__ import annotations
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CAPITAL_SEK = 5000.0
DEFAULT_TARGET_PCT = 2.0
DEFAULT_STOP_PCT = 1.0
DEFAULT_FEE_RATE = 0.0025
DEFAULT_MIN_FEE_SEK = 1.0
DEFAULT_SLIPPAGE_RATE = 0.001


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "events": [], "trades": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Signaljournalen kan inte läsas; skrivning stoppad för att skydda historiken.") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("events"), list) or not isinstance(data.get("trades"), list):
        raise RuntimeError("Signaljournalens format är ogiltigt; skrivning stoppad.")
    return data


def load_journal(path: str | Path = "signal_journal.json") -> dict[str, Any]:
    return _read(Path(path))


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def record_signal(company: str, ticker: str, signal: dict[str, Any], *,
                  capital_sek: float = DEFAULT_CAPITAL_SEK,
                  fee_rate: float = DEFAULT_FEE_RATE,
                  min_fee_sek: float = DEFAULT_MIN_FEE_SEK,
                  slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
                  path: str | Path = "signal_journal.json") -> bool:
    """Append one signal; BUY candidates open one simulated position, deduped by candle."""
    if signal.get("kind") not in {"KÖP-KANDIDAT", "VAKTA", "MORGON-VAKTA"}:
        return False
    price = float(signal["close"])
    if price <= 0 or capital_sek <= 0:
        raise ValueError("Kurs och positionsstorlek måste vara positiva.")
    stamp = signal["time"].isoformat() if hasattr(signal["time"], "isoformat") else str(signal["time"])
    event_id = f"{ticker}:{signal['kind']}:{stamp}"
    p = Path(path)
    data = _read(p)
    if any(e.get("id") == event_id for e in data["events"]):
        return False
    data["events"].append({"id": event_id, "company": company, "ticker": ticker,
                           "kind": signal["kind"], "time": stamp, "price": price,
                           "score": signal.get("score"), "reasons": signal.get("reasons", []),
                           "recorded_at": _now_iso()})
    if signal["kind"] == "KÖP-KANDIDAT":
        entry = price * (1 + slippage_rate)
        shares = capital_sek / entry
        entry_fee = max(min_fee_sek, capital_sek * fee_rate)
        trade_id = f"{ticker}:{stamp}"
        if not any(t.get("id") == trade_id for t in data["trades"]):
            data["trades"].append({
                "id": trade_id, "company": company, "ticker": ticker,
                "entry_time": stamp, "signal_price": price, "entry_price": entry,
                "capital_sek": capital_sek, "shares": shares, "entry_fee_sek": entry_fee,
                "target_pct": DEFAULT_TARGET_PCT, "stop_pct": DEFAULT_STOP_PCT,
                "status": "OPEN", "exit_time": None, "exit_price": None,
                "exit_reason": None, "exit_fee_sek": None, "pnl_sek": None,
                "pnl_pct": None,
            })
    _write(p, data)
    return True


def update_open_trades(prices: dict[str, float], *, fee_rate: float = DEFAULT_FEE_RATE,
                       min_fee_sek: float = DEFAULT_MIN_FEE_SEK,
                       slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
                       now: datetime | None = None,
                       path: str | Path = "signal_journal.json") -> int:
    """Close paper trades when +target or -stop is touched; never assumes an intrabar fill."""
    p = Path(path)
    data = _read(p)
    now = now or datetime.now(timezone.utc)
    closed = 0
    for trade in data["trades"]:
        if trade.get("status") != "OPEN" or trade["ticker"] not in prices:
            continue
        market = float(prices[trade["ticker"]])
        if market <= 0:
            continue
        entry = float(trade["entry_price"])
        move = (market / entry - 1) * 100
        reason = "TARGET +2%" if move >= float(trade["target_pct"]) else ("STOP -1%" if move <= -float(trade["stop_pct"]) else None)
        if reason is None:
            continue
        exit_price = market * (1 - slippage_rate)
        gross = (exit_price - entry) * float(trade["shares"])
        exit_fee = max(min_fee_sek, exit_price * float(trade["shares"]) * fee_rate)
        pnl = gross - float(trade["entry_fee_sek"]) - exit_fee
        trade.update(status="CLOSED", exit_time=now.isoformat(), exit_price=exit_price,
                     exit_reason=reason, exit_fee_sek=exit_fee, pnl_sek=pnl,
                     pnl_pct=(pnl / float(trade["capital_sek"])) * 100)
        closed += 1
    if closed:
        _write(p, data)
    return closed


def summary(data: dict[str, Any]) -> dict[str, float | int]:
    trades = data.get("trades", [])
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("pnl_sek") is not None]
    wins = [t for t in closed if float(t["pnl_sek"]) > 0]
    pnl = sum(float(t["pnl_sek"]) for t in closed)
    return {"total_trades": len(trades), "open_trades": sum(t.get("status") == "OPEN" for t in trades),
            "closed_trades": len(closed), "wins": len(wins), "losses": len(closed) - len(wins),
            "win_rate_pct": (100 * len(wins) / len(closed)) if closed else 0.0,
            "realized_pnl_sek": pnl,
            "return_pct": (100 * pnl / sum(float(t["capital_sek"]) for t in closed)) if closed else 0.0}


def trades_csv(data: dict[str, Any]) -> str:
    import io
    fields = ["company", "ticker", "entry_time", "signal_price", "entry_price", "capital_sek",
              "shares", "entry_fee_sek", "status", "exit_time", "exit_price", "exit_reason",
              "exit_fee_sek", "pnl_sek", "pnl_pct"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data.get("trades", []))
    return output.getvalue()
