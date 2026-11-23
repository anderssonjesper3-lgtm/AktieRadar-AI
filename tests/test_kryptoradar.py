"""Unit tests for news-free KryptoRadar signals and paper journal."""
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kryptoradar"))
from engine import analyze, paper_trade

def test_flat_candles_do_not_buy():
    df = pd.DataFrame({"close":[100.0]*50,"high":[100.0]*50,"volume":[10.0]*50})
    df["timestamp"] = pd.date_range("2026-01-01",periods=50,freq="min",tz="UTC")
    assert analyze(df)["status"] != "KÖP-KANDIDAT"

def test_paper_trade_deduplicates_and_closes():
    j = []
    buy = {"status":"KÖP-KANDIDAT","price":100.0,"timestamp":"2026-01-01T10:00:00Z"}
    sell = {"status":"SÄLJ/VARNING","price":110.0,"timestamp":"2026-01-01T10:01:00Z"}
    paper_trade(j,"XBTUSD",buy)
    paper_trade(j,"XBTUSD",buy)
    assert len(j) == 1
    paper_trade(j,"XBTUSD",sell)
    assert len(j) == 2
    assert j[0]["closed"] is True
    assert j[1]["pnl"] > 0
