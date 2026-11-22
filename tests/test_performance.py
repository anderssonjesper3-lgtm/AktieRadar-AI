from datetime import datetime, timezone
import json
import pytest
from performance import record_signal, update_open_trades, load_journal, summary, trades_csv


def sig(kind="KÖP-KANDIDAT", price=100.0):
    return {"kind": kind, "time": datetime(2026, 11, 23, 9, 5, tzinfo=timezone.utc),
            "close": price, "score": 80, "reasons": ["test"]}


def test_buy_is_deduplicated_and_opens_one_paper_trade(tmp_path):
    path = tmp_path / "journal.json"
    assert record_signal("Saab B", "SAAB B", sig(), path=path)
    assert not record_signal("Saab B", "SAAB B", sig(), path=path)
    data = load_journal(path)
    assert len(data["events"]) == 1
    assert len(data["trades"]) == 1
    assert data["trades"][0]["status"] == "OPEN"


def test_watch_signal_is_logged_but_does_not_open_trade(tmp_path):
    path = tmp_path / "journal.json"
    assert record_signal("Saab B", "SAAB B", sig("VAKTA"), path=path)
    assert len(load_journal(path)["trades"]) == 0


def test_target_closes_trade_and_accounts_for_costs(tmp_path):
    path = tmp_path / "journal.json"
    record_signal("Saab B", "SAAB B", sig(), path=path)
    closed = update_open_trades({"SAAB B": 103.0}, path=path,
                                now=datetime(2026, 11, 23, 10, tzinfo=timezone.utc))
    data = load_journal(path)
    assert closed == 1
    assert data["trades"][0]["exit_reason"] == "TARGET +2%"
    assert data["trades"][0]["pnl_sek"] > 0
    assert summary(data)["closed_trades"] == 1
    assert "pnl_sek" in trades_csv(data)


def test_stop_closes_trade(tmp_path):
    path = tmp_path / "journal.json"
    record_signal("Saab B", "SAAB B", sig(), path=path)
    assert update_open_trades({"SAAB B": 98.0}, path=path) == 1
    assert load_journal(path)["trades"][0]["exit_reason"] == "STOP -1%"


def test_corrupt_journal_fails_closed(tmp_path):
    path = tmp_path / "journal.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError):
        record_signal("Saab B", "SAAB B", sig(), path=path)
