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

from test_avanza_forbattrad import calculate_ema, calculate_rsi, calculate_macd

DEFAULT_CAPITAL_SEK = 5000.0
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
                "stop_pct": DEFAULT_STOP_PCT, "exit_signal_status": "BEHÅLL", "exit_signal_reasons": [],
                "status": "OPEN", "exit_time": None, "exit_price": None,
                "exit_reason": None, "exit_fee_sek": None, "pnl_sek": None,
                "pnl_pct": None,
            })
    _write(p, data)
    return True


def evaluate_smart_exit(candles: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """Conservative 5-minute Smart Exit assessment from completed candles.

    States: BEHÅLL/TREND STARK, VAKTA VINSTEN, SÄLJ-KANDIDAT.
    A sell candidate needs at least three independent bearish confirmations.
    This is a transparent rule-based paper-trading signal, not a forecast.
    """
    if len(candles) < 35:
        return "DATA SAKNAS", ["Behöver minst 35 färdiga femminutersljus för EMA/MACD/RSI"]

    closes = [float(x["close"]) for x in candles]
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    rsi = calculate_rsi(closes, 14)
    _, _, hist = calculate_macd(closes)
    i = len(candles) - 1
    if any(series[i] is None for series in (ema9, ema21, rsi, hist)):
        return "DATA SAKNAS", ["Tekniska indikatorer är ännu inte kompletta"]

    last = candles[i]
    previous = candles[i - 1]
    bearish = []
    if closes[i] < ema21[i]:
        bearish.append("Kurs under EMA 21")
    if ema9[i] < ema21[i]:
        bearish.append("EMA 9 under EMA 21")
    if hist[i] < 0 and hist[i] < hist[i - 1]:
        bearish.append("MACD negativ och försvagas")
    if rsi[i] < 45:
        bearish.append("RSI under 45")
    avg_volume = sum(float(x.get("volume", 0) or 0) for x in candles[max(0, i-5):i]) / max(1, len(candles[max(0, i-5):i]))
    if (last["close"] < last["open"] and avg_volume > 0
            and float(last.get("volume", 0) or 0) >= avg_volume * 1.25):
        bearish.append("Röd stapel med förhöjd volym/säljtryck")

    if len(bearish) >= 3:
        return "SÄLJ-KANDIDAT", bearish
    if (ema9[i] > ema21[i] and closes[i] > ema21[i]
            and rsi[i] >= 50 and hist[i] >= 0):
        return "BEHÅLL / TREND STARK", ["Kurs över EMA 21", "EMA 9 över EMA 21",
                                        "RSI stödjer trenden", "MACD positiv"]
    if len(bearish) >= 1:
        return "VAKTA VINSTEN", bearish
    return "BEHÅLL", ["Ingen bekräftad teknisk säljsignal"]


def update_open_trades(prices: dict[str, float], *,
                       candles_by_ticker: dict[str, list[dict[str, Any]]] | None = None,
                       fee_rate: float = DEFAULT_FEE_RATE,
                       min_fee_sek: float = DEFAULT_MIN_FEE_SEK,
                       slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
                       now: datetime | None = None,
                       path: str | Path = "signal_journal.json") -> int:
    """Update open paper positions; exit only on -1% stop or confirmed Smart Exit."""
    p = Path(path)
    data = _read(p)
    now = now or datetime.now(timezone.utc)
    candles_by_ticker = candles_by_ticker or {}
    closed = 0
    changed = False
    for trade in data["trades"]:
        if trade.get("status") != "OPEN" or trade["ticker"] not in prices:
            continue
        market = float(prices[trade["ticker"]])
        if market <= 0:
            continue

        entry = float(trade["entry_price"])
        move = (market / entry - 1) * 100
        # Hard protective stop remains active; +2% is deliberately NOT an exit.
        if move <= -float(trade.get("stop_pct", DEFAULT_STOP_PCT)):
            reason = "STOP -1%"
            exit_reasons = ["Skyddande stop-loss utlöst"]
            exit_now = True
        else:
            exit_status, exit_reasons = evaluate_smart_exit(candles_by_ticker.get(trade["ticker"], []))
            trade["exit_signal_status"] = exit_status
            trade["exit_signal_reasons"] = exit_reasons
            trade["last_exit_check"] = now.isoformat()
            changed = True
            exit_now = exit_status == "SÄLJ-KANDIDAT"
            reason = "SÄLJ-SIGNAL (Smart Exit)" if exit_now else None

        if not exit_now:
            continue
        exit_price = market * (1 - slippage_rate)
        gross = (exit_price - entry) * float(trade["shares"])
        exit_fee = max(min_fee_sek, exit_price * float(trade["shares"]) * fee_rate)
        pnl = gross - float(trade["entry_fee_sek"]) - exit_fee
        trade.update(status="CLOSED", exit_time=now.isoformat(), exit_price=exit_price,
                     exit_reason=reason, exit_signal_reasons=exit_reasons,
                     exit_fee_sek=exit_fee, pnl_sek=pnl,
                     pnl_pct=(pnl / float(trade["capital_sek"])) * 100)
        closed += 1
        changed = True
    if changed:
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
              "shares", "entry_fee_sek", "status", "exit_signal_status", "exit_signal_reasons", "exit_time", "exit_price", "exit_reason",
              "exit_fee_sek", "pnl_sek", "pnl_pct"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data.get("trades", []))
    return output.getvalue()
