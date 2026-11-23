"""Historical replay must not execute at the candle that generated its signal."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kryptoradar.engine import performance_summary, evaluate_positions
from kryptoradar.backtest import replay

def test_performance_excludes_open():
    j=[{"action":"BUY","symbol":"XBTUSD","stake":1000,"pnl":None},
       {"action":"SELL","symbol":"XBTUSD","stake":1000,"pnl":25}]
    s=performance_summary(j)
    assert s["trades"]==1 and s["win_rate"]==100 and s["pnl"]==25

def test_stop_closes_position():
    j=[{"event_id":"a","symbol":"XBTUSD","action":"BUY","closed":False,
        "price":100,"qty":9.975,"stake":1000,"time":"t","pnl":None}]
    j,status=evaluate_positions(j,"XBTUSD",{"price":98,"status":"VAKTA","timestamp":"t2"})
    assert status=="SÄLJ-KANDIDAT" and j[0]["closed"] and j[1]["reason"]=="STOP-LOSS"

def test_flat_history_no_trades():
    n=50
    d=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=n,freq="min",tz="UTC"),
                    "open":[100.]*n,"high":[100.]*n,"low":[100.]*n,
                    "close":[100.]*n,"volume":[10.]*n})
    result=replay(d)
    assert result["summary"]["trades"]==0
