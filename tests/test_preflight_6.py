"""Offline preflight checks. No real orders, Telegram messages, or live API writes."""
from datetime import datetime, timezone
from unittest.mock import patch

from aktieradar_telegram import format_message, should_notify
from performance import record_signal, update_open_trades, load_journal, summary


def test_ticker_scoped_alerts():
    now = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)
    signal = {"kind": "KÖP-KANDIDAT", "time": now}
    history = [{"id": f"SAAB B:KÖP-KANDIDAT:{now.isoformat()}",
                "kind": "KÖP-KANDIDAT", "time": now.isoformat(), "status": "sent"}]
    assert should_notify(signal, history, "SAAB B")[0] is False
    assert should_notify(signal, history, "OVZON")[0] is True


def test_message_has_correct_stock_and_newlines():
    signal = {"kind": "SÄLJ", "company": "Ovzon", "ticker": "OVZON",
              "time": datetime(2026, 11, 23, 9, 5),
              "close": 42.0, "score": None, "reasons": ["Smart Exit"]}
    msg = format_message(signal)
    assert "Ovzon (OVZON)" in msg
    assert "Saab B" not in msg
    assert "\nTid:" in msg


def test_paper_journal_dedup_and_stop(tmp_path):
    path = tmp_path / "paper.json"
    signal = {"kind": "KÖP-KANDIDAT", "time": datetime(2026, 11, 23, 9, 0),
              "close": 100.0, "score": 80, "reasons": ["test"]}
    assert record_signal("Testbolag", "TEST", signal, path=path)
    assert not record_signal("Testbolag", "TEST", signal, path=path)
    assert len(load_journal(path)["trades"]) == 1
    assert update_open_trades({"TEST": 98.5}, path=path) == 1
    assert update_open_trades({"TEST": 98.0}, path=path) == 0
    journal = load_journal(path)
    assert summary(journal)["closed_trades"] == 1
    assert summary(journal)["realized_pnl_sek"] < 0


def test_shared_journal_read_does_not_write():
    import journal_store
    payload = {"version": 1, "events": [], "trades": []}
    raw = __import__("base64").b64encode(__import__("json").dumps(payload).encode()).decode()
    with patch.object(journal_store, "_config", return_value=("owner/repo", None)):
        with patch.object(journal_store, "_request", return_value={"content": raw, "sha": "abc"}) as request:
            journal, sha = journal_store.read_shared()
    assert journal == payload and sha == "abc"
    assert request.call_args.args[0] == "GET"
