import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from news_scanner import load_config
from news_ai_pilot import run_news_only

def alert_text(item):
    return ('🔔 NY BOLAGSNYHET | ' + item['company'] + '\n' + item['title'] + '\n'
            + 'Bedömning: ' + item['direction'] + '\n' + item['economic_case']
            + '\nRisk: ' + item['risk'] + '\n' + item['url']
            + '\nRegelbaserad bedömning – inte köpsignal.')

def interval_minutes(now):
    local = now.astimezone(ZoneInfo('Europe/Stockholm'))
    minute = local.hour * 60 + local.minute
    if 420 <= minute < 570 or 990 <= minute < 1080:
        return 5
    if 570 <= minute < 990:
        return 10
    return 15

def scheduled_due(now):
    local = now.astimezone(ZoneInfo('Europe/Stockholm'))
    return local.minute % interval_minutes(now) == 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-check', action='store_true')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--state', default='news_seen.json')
    parser.add_argument('--scheduled-at', help='ISO timestamp of intended schedule slot')
    args = parser.parse_args()
    if args.scheduled_at and not scheduled_due(datetime.fromisoformat(args.scheduled_at)):
        print('Outside selected polling interval')
        return
    result = run_news_only(load_config())
    from news_followup import advance, load_state, save_state
    save_state(advance(load_state(), result['items'], load_config(), datetime.now(timezone.utc)))
    print(json.dumps(result, default=str, ensure_ascii=False))
    if args.send:
        from aktieradar_telegram import telegram_send
        state = Path(args.state)
        seen = set(json.loads(state.read_text())) if state.exists() else set()
        for item in result['items']:
            if item['id'] in seen or not timedelta(0) <= datetime.now(timezone.utc)-item['published'] <= timedelta(hours=12):
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
