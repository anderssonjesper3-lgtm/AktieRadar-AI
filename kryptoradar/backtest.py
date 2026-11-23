"""Historical replay of Kraken's available CLOSED one-minute candles.
Signals use only data available at candle close; execution is NEXT candle open.
This is an in-sample exploratory replay, not a validated forward test.
"""
from .engine import analyze, performance_summary

def replay(df, *, stake=1000, fee_pct=0.25, slippage_pct=0.10, stop_pct=1.0):
    journal = []
    signals = []
    position = None
    # At least 35 bars for indicators, plus a following bar to fill.
    for i in range(35, len(df) - 1):
        window = df.iloc[:i+1]
        signal = analyze(window)
        next_bar = df.iloc[i+1]
        execution = float(next_bar["open"])
        stamp = next_bar["timestamp"].isoformat()
        if position is not None:
            move = 100 * (signal["price"] / position["entry"] - 1)
            reason = ("STOP-LOSS" if move <= -stop_pct else
                      "TEKNISK SÄLJSIGNAL" if signal["status"] == "SÄLJ/VARNING" else None)
            if reason:
                exit_price = execution * (1-slippage_pct/100)
                proceeds = position["qty"] * exit_price * (1-fee_pct/100)
                pnl = round(proceeds - stake, 2)
                journal.append({"action":"SELL","symbol":"BACKTEST","time":stamp,
                                "price":exit_price,"pnl":pnl,"stake":stake,
                                "reason":reason,"entry_time":position["time"]})
                position = None
        elif signal["status"] == "KÖP-KANDIDAT":
            entry = execution * (1+slippage_pct/100)
            position = {"entry":entry,"qty":stake*(1-fee_pct/100)/entry,"time":stamp}
            journal.append({"action":"BUY","symbol":"BACKTEST","time":stamp,
                            "price":entry,"pnl":None,"stake":stake})
        if signal["status"] in ("KÖP-KANDIDAT","SÄLJ/VARNING"):
            signals.append({"time":signal["timestamp"],"signal":signal["status"],
                            "close":signal["price"],"volume_ratio":round(signal["volume_ratio"],2)})
    return {"journal":journal,"signals":signals,
            "summary":performance_summary(journal),
            "open_position":position is not None}
