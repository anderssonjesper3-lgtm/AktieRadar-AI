"""Compare three pre-defined crypto strategies without changing live paper trades.

Chronological 60/40 split. No parameter tuning on holdout data.
Signals from CLOSED candles; hypothetical fills at next candle open.
"""
import pandas as pd
from .engine import performance_summary

NAMES = {"momentum":"Snabb momentum","trend":"Trendföljning","pullback":"Rekylköp"}

def indicators(df):
    d=df.copy()
    d["ema9"]=d["close"].ewm(span=9,adjust=False).mean()
    d["ema21"]=d["close"].ewm(span=21,adjust=False).mean()
    d["ema50"]=d["close"].ewm(span=50,adjust=False).mean()
    delta=d["close"].diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    d["rsi"]=(100-100/(1+up/down.replace(0,float("nan")))).fillna(50)
    d["volume_ratio"]=d["volume"]/d["volume"].shift(1).rolling(20).mean()
    d["prior_high"]=d["high"].shift(1).rolling(10).max()
    d["prior_low"]=d["low"].shift(1).rolling(5).min()
    d["prior_close"]=d["close"].shift(1)
    return d

def entry(row,kind):
    rising=row["close"]>row["prior_close"]
    if kind=="momentum":
        return (row["ema9"]>row["ema21"] and rising and
                row["close"]>row["prior_high"] and row["volume_ratio"]>=1.15
                and 50<=row["rsi"]<=72)
    if kind=="trend":
        return (row["ema9"]>row["ema21"]>row["ema50"] and
                row["close"]>row["ema9"] and rising and
                row["volume_ratio"]>=0.8 and 48<=row["rsi"]<=68)
    if kind=="pullback":
        return (row["ema21"]>row["ema50"] and
                row["prior_close"]<=row["ema9"] and row["close"]>row["ema9"]
                and rising and 42<=row["rsi"]<=65 and row["volume_ratio"]>=0.8)
    raise ValueError("Unknown strategy")

def run_segment(d, kind, start, end, stake=1000, fee_pct=0.25, slippage_pct=0.10,
                stop_pct=1.0, target_pct=2.0, max_bars=30):
    journal=[]; pos=None; entry_count=0
    # No entries beyond end-1, to ensure next-bar execution remains inside segment.
    for i in range(max(55,start),end-1):
        row=d.iloc[i]; nxt=d.iloc[i+1]
        price=float(nxt["open"]); stamp=nxt["timestamp"].isoformat()
        if pos:
            age=i-pos["signal_index"]
            # Stop/target decisions use known candle close, then next-bar open.
            movement=100*(float(row["close"])/pos["entry"]-1)
            exit_reason=("STOP" if movement<=-stop_pct else
                         "MÅL" if movement>=target_pct else
                         "TID" if age>=max_bars else
                         "TRENDVÄNDNING" if row["ema9"]<row["ema21"] else None)
            if exit_reason:
                exit_price=price*(1-slippage_pct/100)
                pnl=pos["qty"]*exit_price*(1-fee_pct/100)-stake
                journal.append({"action":"SELL","symbol":kind,"time":stamp,"pnl":round(pnl,2),
                                "stake":stake,"reason":exit_reason})
                pos=None
        elif entry(row,kind):
            entry_price=price*(1+slippage_pct/100)
            pos={"entry":entry_price,"qty":stake*(1-fee_pct/100)/entry_price,
                 "signal_index":i}
            entry_count+=1
    summary=performance_summary(journal)
    summary["entries"]=entry_count
    summary["open_position"]=pos is not None
    return summary

def compare(df, **kwargs):
    d=indicators(df)
    if len(d)<150:
        raise ValueError("Minst 150 stängda ljus krävs")
    cut=max(90,int(len(d)*0.6))
    results=[]
    for kind,name in NAMES.items():
        train=run_segment(d,kind,55,cut,**kwargs)
        hold=run_segment(d,kind,cut,len(d),**kwargs)
        results.append({"Strategi":name,"Träning: affärer":train["trades"],
                        "Träning: träff %":round(train["win_rate"],1),
                        "Träning: USD":round(train["pnl"],2),
                        "Test: affärer":hold["trades"],
                        "Test: träff %":round(hold["win_rate"],1),
                        "Test: USD":round(hold["pnl"],2),
                        "Test: öppna":hold["open_position"]})
    return results
