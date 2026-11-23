"""Public Kraken OHLC data and conservative, closed-candle paper signals."""
import time
import requests
import pandas as pd

PAIRS = {"Bitcoin": "XBTUSD", "Ethereum": "ETHUSD", "Solana": "SOLUSD"}
URL = "https://api.kraken.com/0/public/OHLC"

def fetch_candles(pair, interval=1):
    response = requests.get(URL, params={"pair": pair, "interval": interval}, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError("; ".join(payload["error"]))
    key = next(k for k in payload["result"] if k != "last")
    rows = payload["result"][key]
    if len(rows) < 35:
        raise ValueError("För få ljus för tillförlitlig analys")
    # Kraken's last OHLC row is the current, unfinished candle.
    rows = rows[:-1]
    df = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","vwap","volume","count"])
    for col in ["open","high","low","close","volume","count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.dropna().sort_values("timestamp").drop_duplicates("timestamp")
    if df.empty:
        raise ValueError("Inga giltiga stängda ljus")
    # No signals if latest CLOSED candle is too old.
    age = time.time() - df.iloc[-1]["timestamp"].timestamp()
    if age > interval * 60 + 180 or age < -60:
        raise ValueError("Kursljusen är för gamla för en aktuell signal")
    return df

def analyze(df):
    d = df.copy()
    d["ema9"] = d["close"].ewm(span=9, adjust=False).mean()
    d["ema21"] = d["close"].ewm(span=21, adjust=False).mean()
    delta = d["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    d["rsi"] = (100 - 100 / (1 + rs)).fillna(50)
    d["vol_baseline"] = d["volume"].shift(1).rolling(20).mean()
    last, prev = d.iloc[-1], d.iloc[-2]
    bullish = last["ema9"] > last["ema21"] and last["close"] > last["ema9"]
    vol_ratio = float(last["volume"] / last["vol_baseline"]) if last["vol_baseline"] > 0 else 0
    breakout = last["close"] > d["high"].iloc[-11:-1].max()
    rising = last["close"] > prev["close"]
    buy = bullish and rising and breakout and vol_ratio >= 1.5 and 52 <= last["rsi"] <= 75
    sell = last["ema9"] < last["ema21"] or last["close"] < last["ema21"] or last["rsi"] < 42
    status = "KÖP-KANDIDAT" if buy else "SÄLJ/VARNING" if sell else "VAKTA" if bullish else "AVVAKTA"
    return {"status":status,"price":float(last["close"]),"rsi":float(last["rsi"]),
            "volume_ratio":vol_ratio,"timestamp":last["timestamp"].isoformat(),
            "ema9":float(last["ema9"]),"ema21":float(last["ema21"]),
            "breakout":bool(breakout),"frame":d}

def paper_trade(journal, symbol, signal, fee_pct=0.25, slippage_pct=0.10, stake=1000):
    """One simulated position per symbol. Never submit exchange orders."""
    event_id = symbol + ":" + signal["timestamp"] + ":" + signal["status"]
    if any(x["event_id"] == event_id for x in journal):
        return journal

    open_trade = next((x for x in reversed(journal) if x["symbol"] == symbol and x["action"] == "BUY" and not x.get("closed")), None)
    if signal["status"] == "KÖP-KANDIDAT" and open_trade is None:
        entry = signal["price"] * (1 + slippage_pct/100)
        qty = stake * (1-fee_pct/100) / entry
        journal.append({"event_id":event_id,"symbol":symbol,"action":"BUY","time":signal["timestamp"],
                        "price":entry,"qty":qty,"stake":stake,"closed":False,"pnl":None})
    elif signal["status"] == "SÄLJ/VARNING" and open_trade:
        exit_price = signal["price"] * (1-slippage_pct/100)
        proceeds = open_trade["qty"] * exit_price * (1-fee_pct/100)
        pnl = proceeds - open_trade["stake"]
        open_trade["closed"] = True
        journal.append({"event_id":event_id,"symbol":symbol,"action":"SELL","time":signal["timestamp"],
                        "price":exit_price,"qty":open_trade["qty"],"stake":open_trade["stake"],
                        "closed":True,"pnl":round(pnl,2)})
    return journal

def evaluate_positions(journal, symbol, signal, fee_pct=0.25, slippage_pct=0.10, stop_pct=1.0):
    """Apply stop or confirmed sell to a paper position; never place orders."""
    position = next((x for x in reversed(journal)
                     if x["symbol"] == symbol and x["action"] == "BUY" and not x.get("closed")), None)
    if position is None:
        return journal, "INGEN POSITION"
    move_pct = 100 * (signal["price"] / position["price"] - 1)
    exit_reason = "STOP-LOSS" if move_pct <= -stop_pct else (
        "TEKNISK SÄLJSIGNAL" if signal["status"] == "SÄLJ/VARNING" else None)
    if exit_reason is None:
        return journal, "BEHÅLL" if move_pct >= 0 else "VAKTA POSITION"
    event_id = symbol + ":" + signal["timestamp"] + ":EXIT"
    if any(x["event_id"] == event_id for x in journal):
        return journal, "REDAN REGISTRERAD"
    exit_price = signal["price"] * (1 - slippage_pct/100)
    proceeds = position["qty"] * exit_price * (1-fee_pct/100)
    pnl = round(proceeds - position["stake"], 2)
    position["closed"] = True
    journal.append({"event_id":event_id,"symbol":symbol,"action":"SELL",
                    "time":signal["timestamp"],"price":exit_price,
                    "qty":position["qty"],"stake":position["stake"],
                    "closed":True,"pnl":pnl,"reason":exit_reason,
                    "entry_time":position["time"]})
    return journal, "SÄLJ-KANDIDAT"


def performance_summary(journal, symbol=None):
    """Realized outcomes only; open positions excluded from profit and win rate."""
    trades = [x for x in journal if x.get("action") == "SELL" and x.get("pnl") is not None
              and (symbol is None or x.get("symbol") == symbol)]
    wins = sum(float(x["pnl"]) > 0 for x in trades)
    pnl = sum(float(x["pnl"]) for x in trades)
    invested = sum(float(x["stake"]) for x in trades)
    return {"trades":len(trades),"wins":wins,"losses":len(trades)-wins,
            "win_rate":100*wins/len(trades) if trades else 0.0,
            "pnl":pnl,"return_pct":100*pnl/invested if invested else 0.0}
