import unittest
from datetime import datetime, timezone
from news_ai_pilot import run_news_pilot, score_news, explain_news, candidate_kind, smart_exit, simulated_result

class NewsPilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_interesting_verified_issuer_fetches_quotes(self):
        now = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
        config = {'companies': [
            {'name':'Testbolag', 'aliases':['Testbolag'], 'segment':'Mid Cap',
             'segment_verified':True, 'feeds':['https://example.invalid/rss']},
            {'name':'Other', 'aliases':['Other'], 'segment':'Small Cap',
             'segment_verified':False, 'feeds':['https://example.invalid/other']}
        ]}
        rss = b"""<rss><channel>
        <item><title>Testbolag receives order</title><link>https://example.invalid/1</link><pubDate>Mon, 05 Jan 2026 11:00:00 GMT</pubDate></item>
        <item><title>Testbolag annual meeting</title><link>https://example.invalid/2</link><pubDate>Mon, 05 Jan 2026 11:00:00 GMT</pubDate></item>
        <item><title>Testbolag receives order</title><link>https://example.invalid/3</link><pubDate>Mon, 05 Jan 2026 11:00:00 GMT</pubDate></item>
        </channel></rss>"""
        calls = []
        async def quote(company, now):
            calls.append(company['name'])
            return {'candles':[], 'error':'test fixture: no quotes'}
        result = await run_news_pilot(config, now, fetch=lambda url:rss, quote=quote)
        async def broken_quote(company, now):
            raise TimeoutError('fixture')
        failed = await run_news_pilot(config, now, fetch=lambda url:rss, quote=broken_quote)
        self.assertEqual(len(failed['candidates']), 1)
        self.assertEqual(failed['candidates'][0]['kind'], 'NYHET-VAKTA')
        self.assertEqual(failed['candidates'][0]['quote']['error'], 'TimeoutError')
        self.assertEqual(result['eligible_count'], 1)
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(calls, ['Testbolag'])
        self.assertEqual(result['candidates'][0]['kind'], 'NYHET-VAKTA')

    def test_economic_explanation(self):
        case, risk = explain_news({'title':'Testbolag receives order'}, 70)
        self.assertIn('intäkter', case)
        self.assertIn('ordervärde', risk)

    def test_exit_and_costs(self):
        self.assertEqual(smart_exit(100, 105, 105), 'BEHÅLL')
        self.assertEqual(smart_exit(100, 105, 103), 'SMART EXIT')
        self.assertEqual(smart_exit(100, 100, 98), 'STOPP')
        self.assertEqual(simulated_result(100, 105, 10, 5)['net_sek'], 40)

    def test_delayed_gate(self):
        q = {'candles':[{}], 'signal':{'kind':'KÖP-KANDIDAT'}, 'last_candle_age_minutes':15}
        self.assertEqual(candidate_kind(q), 'KÖP-KANDIDAT (FÖRDRÖJD)')
        q['last_candle_age_minutes'] = 30
        self.assertEqual(candidate_kind(q), 'NYHET-VAKTA')

    def test_risk_overrides_positive(self):
        self.assertEqual(score_news({'title':'Receives order', 'description':'letter of intent'})[0],0)

if __name__ == '__main__':
    unittest.main()
