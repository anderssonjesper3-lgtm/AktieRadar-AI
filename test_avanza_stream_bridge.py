"""Offline contract tests for the experimental Avanza quote bridge.

Run: python -m unittest test_avanza_stream_bridge.py
No credentials, network access or live market data required.
"""
import unittest
from datetime import datetime, timezone
from avanza_stream_bridge import normalize_quote

class QuoteContractTests(unittest.TestCase):
    def setUp(self):
        self.received = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)

    def test_valid_quote_is_explicitly_unverified(self):
        q = normalize_quote({"orderbookId": "5401", "lastPrice": 512.5}, self.received)
        self.assertEqual(q["last_price"], 512.5)
        self.assertEqual(q["orderbook_id"], "5401")
        self.assertFalse(q["realtime_verified"])
        self.assertFalse(q["latency_verified"])
        self.assertEqual(q["received_at_utc"], "2026-11-23T09:00:00+00:00")

    def test_source_timestamp_not_invented(self):
        q = normalize_quote({"orderbookId": "5401", "lastPrice": 1}, self.received)
        self.assertIsNone(q["source_timestamp_raw"])

    def test_source_timestamp_retained(self):
        q = normalize_quote({"orderbookId": "5401", "lastPrice": 1, "updated": "09:00"}, self.received)
        self.assertEqual(q["source_timestamp_raw"], "09:00")

    def test_bad_quotes_rejected(self):
        for payload in [None, [], {}, {"orderbookId": "5401"}, {"orderbookId": "5401", "lastPrice": 0}, {"orderbookId": "5401", "lastPrice": True}]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    normalize_quote(payload, self.received)

if __name__ == "__main__":
    unittest.main()
