import unittest
from market_data_adapter import normalize_eodhd_minute, CandleAggregator

class MarketDataTests(unittest.TestCase):
    def test_duplicate_minute_replaces_volume(self):
        a = CandleAggregator()
        start = 1800000000000 // 300000 * 300000
        for i in range(5):
            a.update(normalize_eodhd_minute({"s":"TEST.ST","i":"1m","t":start+i*60000,"o":10,"h":11,"l":9,"c":10+i/10,"v":10}))
        a.update(normalize_eodhd_minute({"s":"TEST.ST","i":"1m","t":start,"o":10,"h":11,"l":9,"c":10,"v":20}))
        bars=a.closed_five_minute("TEST.ST",start+300000)
        self.assertEqual(len(bars),1)
        self.assertEqual(bars[0]["volume"],60)
        self.assertFalse(bars[0]["realtime_verified"])
        self.assertEqual(a.closed_five_minute("TEST.ST",start+299999),[])

    def test_missing_minute_blocks_candle(self):
        a=CandleAggregator()
        start=1800000000000 // 300000 * 300000
        for i in range(4):
            a.update(normalize_eodhd_minute({"s":"TEST.ST","i":"1m","t":start+i*60000,"o":10,"h":10,"l":10,"c":10,"v":1}))
        self.assertEqual(a.closed_five_minute("TEST.ST",start+300000),[])

    def test_invalid_data_rejected(self):
        with self.assertRaises(ValueError):
            normalize_eodhd_minute({"s":"TEST.ST","i":"1m","t":1,"o":10,"h":9,"l":10,"c":10,"v":1})

if __name__=="__main__":
    unittest.main()
