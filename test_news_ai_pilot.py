import unittest
from datetime import datetime, timezone
from news_ai_pilot import run_news_pilot, score_news

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
        self.assertEqual(result['eligible_count'], 1)
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(calls, ['Testbolag'])
        self.assertEqual(result['candidates'][0]['kind'], 'NYHET-VAKTA')

    def test_risk_overrides_positive(self):
        self.assertEqual(score_news({'title':'Receives order', 'description':'letter of intent'})[0],0)

if __name__ == '__main__':
    unittest.main()
