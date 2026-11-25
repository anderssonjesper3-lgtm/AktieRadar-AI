import unittest
from datetime import datetime, timezone, timedelta
from news_ai_pilot import run_news_pilot, score_news, explain_news, candidate_kind, news_candidate_kind, update_paper_journal, smart_exit, simulated_result

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

    def test_no_pre_news_paper_entry(self):
        published = datetime(2026, 1, 5, 12, 2, tzinfo=timezone.utc)
        q = {'candles':[{'time':published-timedelta(minutes=2), 'close':100}],
             'signal':{'kind':'KÖP-KANDIDAT'}, 'last_candle_age_minutes':15}
        item = {'company':'Test', 'id':'test', 'published':published,
                'kind':'KÖP-KANDIDAT (FÖRDRÖJD)', 'quote':q}
        journal = {}
        self.assertEqual(news_candidate_kind(q, published), 'NYHET-VAKTA')
        self.assertEqual(update_paper_journal(journal, [item], {}), [])
        q['candles'][0]['time'] = published + timedelta(minutes=3)
        self.assertEqual(news_candidate_kind(q, published), item['kind'])
        self.assertEqual(len(update_paper_journal(journal, [item], {})), 1)

    def test_risk_overrides_positive(self):
        self.assertEqual(score_news({'title':'Receives order', 'description':'letter of intent'})[0],0)


class NewsOnlyTests(unittest.TestCase):
    def test_impact_directions(self):
        from news_ai_pilot import assess_impact
        for title, direction in [('Bolaget erhåller order', 'Positiv'),
                                 ('Bolaget sänker prognosen', 'Negativ'),
                                 ('Bolaget genomför nyemission', 'Blandad'),
                                 ('Bolaget tecknar avsiktsförklaring', 'Osäker'),
                                 ('Årsstämma', 'Oklar')]:
            self.assertEqual(assess_impact({'title': title})['direction'], direction)

    def test_no_price_requests(self):
        from news_ai_pilot import run_news_only
        from unittest.mock import patch
        with patch('news_ai_pilot.analyze_company', side_effect=AssertionError('Unexpected price request')):
            result = run_news_only({'companies': []})
        self.assertEqual(result['quote_count'], 0)
        self.assertEqual(result['items'], [])


if __name__ == '__main__':
    unittest.main()
