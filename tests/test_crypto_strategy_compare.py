import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kryptoradar.strategy_compare import compare

def test_flat_market_no_trades():
    n=200
    d=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=n,freq="min",tz="UTC"),
                    "open":[100.]*n,"high":[100.]*n,"low":[100.]*n,
                    "close":[100.]*n,"volume":[10.]*n})
    results=compare(d)
    assert len(results)==3
    assert all(x["Test: affärer"]==0 and x["Träning: affärer"]==0 for x in results)
