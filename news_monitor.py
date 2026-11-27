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
    # News may arrive outside trading hours; keep the same target cadence.
    return 5

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
    started = datetime.now(timezone.utc)
    config = load_config()
    notify = None
    if args.send:
        from aktieradar_telegram import telegram_send
        state = Path(args.state)
        seen = set(json.loads(state.read_text())) if state.exists() else set()
        def notify(item):
            if item['id'] in seen:
                return
            detected = datetime.fromisoformat(item['detected_at'])
            published = item['published']
            exact = item.get('publication_precision') == 'exact'
            if exact and not timedelta(0) <= detected-published <= timedelta(hours=24):
                return
            local = ZoneInfo('Europe/Stockholm')
            pub = published.astimezone(local).strftime('%Y-%m-%d %H:%M') if exact else published.date().isoformat() + ' (exakt tid ej verifierad)'
            message = ('🔔 SNABBNOTIS – VAKTA | ' + item['company'] + '\n'
                       + item['title'] + '\nPublicerad: ' + pub
                       + '\nUpptäckt: ' + detected.astimezone(local).strftime('%H:%M:%S')
                       + '\n' + item['url'] + '\nPreliminär nyhet – djupanalys återstår, inte köpsignal.')
            sent_at = datetime.now(timezone.utc)
            try:
                telegram_send(message)
            except RuntimeError:
                print(json.dumps({'event':'telegram_failed','id':item['id']}), flush=True)
                return
            confirmed = datetime.now(timezone.utc)
            seen.add(item['id'])
            temp = state.with_suffix('.tmp')
            temp.write_text(json.dumps(sorted(seen)))
            temp.replace(state)
            print(json.dumps({'event':'telegram_confirmed','id':item['id'],
                'published':published.isoformat() if exact else None,
                'publication_precision':item.get('publication_precision','unknown'),
                'scan_started':started.isoformat(),'detected_at':detected.isoformat(),
                'send_started':sent_at.isoformat(),'confirmed':confirmed.isoformat(),
                'detection_to_telegram_seconds':round((confirmed-detected).total_seconds(),3),
                'telegram_api_seconds':round((confirmed-sent_at).total_seconds(),3),
                'publication_to_telegram_seconds':round((confirmed-published).total_seconds(),1) if exact else None}, ensure_ascii=False), flush=True)
    result = run_news_only(config, on_match=notify)
    if notify is not None:
        for item in result['items']:
            if item.get('detected_at'):
                notify(item)
    from news_followup import advance, load_state, save_state
    save_state(advance(load_state(), result['items'], load_config(), datetime.now(timezone.utc)))
    print(json.dumps(result, default=str, ensure_ascii=False))
    if args.live_check:
        shared = set(load_config().get('shared_feeds', []))
        if not any(d['feed'] in shared and d['status'] == 'OK' and d['raw_items'] > 0
                   for d in result['diagnostics']):
            raise SystemExit('No verified live shared-feed entries')

if __name__ == '__main__':
    main()
