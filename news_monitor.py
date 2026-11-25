import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from news_scanner import load_config
from news_ai_pilot import run_news_only

def alert_text(item):
    return ('NYHETSSPÅR | ' + item['company'] + '\n' + item['title'] + '\n'
            + 'Bedömning: ' + item['direction'] + '\n' + item['economic_case']
            + '\nRisk: ' + item['risk'] + '\n' + item['url']
            + '\nRegelbaserad bedömning – inte köpsignal.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-check', action='store_true')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--state', default='news_seen.json')
    args = parser.parse_args()
    result = run_news_only(load_config())
    print(json.dumps(result, default=str, ensure_ascii=False))
    if args.send:
        from aktieradar_telegram import telegram_send
        state = Path(args.state)
        seen = set(json.loads(state.read_text())) if state.exists() else set()
        for item in result['items']:
            if item['direction'] == 'Oklar' or item['id'] in seen:
                continue
            telegram_send(alert_text(item))
            seen.add(item['id'])
            state.write_text(json.dumps(sorted(seen)))
    if args.live_check:
        shared = set(load_config().get('shared_feeds', []))
        if not any(d['feed'] in shared and d['status'] == 'OK' and d['raw_items'] > 0
                   for d in result['diagnostics']):
            raise SystemExit('No verified live shared-feed entries')

if __name__ == '__main__':
    main()
