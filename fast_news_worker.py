"""Standalone fast press-feed worker. Dry run unless --send is supplied."""
import argparse
import json
import time
import os
from pathlib import Path
from datetime import datetime, timezone
from news_scanner import load_config, scan_detailed

def run(interval, state_path, send=False, once=False):
    if interval < 30:
        raise ValueError("Minimum interval 30 seconds pending source approval")
    state = Path(state_path)
    seen = set(json.loads(state.read_text())) if state.exists() else set()
    if send:
        if not state.exists():
            raise RuntimeError("Seed state from existing news_seen.json before enabling live alerts")
        from aktieradar_telegram import telegram_send
    def matched(item):
        if item['id'] in seen:
            return
        detected = datetime.fromisoformat(item['detected_at'])
        exact = item.get('publication_precision') == 'exact'
        message = ('🔔 SNABBNOTIS – VAKTA | ' + item['company'] + '\n' +
                   item['title'] + '\n' + item['url'] +
                   '\nPreliminär nyhet – inte köpsignal.')
        started = time.monotonic()
        if send:
            try:
                telegram_send(message)
            except RuntimeError:
                print(json.dumps(dict(event='telegram_failed', id=item['id'])), flush=True)
                return
        confirmed = datetime.now(timezone.utc)
        seen.add(item['id'])
        tmp = state.with_suffix('.tmp')
        tmp.write_text(json.dumps(sorted(seen)))
        os.replace(tmp, state)
        print(json.dumps(dict(event='telegram_confirmed' if send else 'dry_run',
            id=item['id'], detected_at=detected.isoformat(), confirmed=confirmed.isoformat(),
            publication_to_confirmation_seconds=(confirmed-item['published']).total_seconds() if exact else None,
            send_seconds=round(time.monotonic()-started,3)), ensure_ascii=False), flush=True)
    delay = interval
    while True:
        started = time.monotonic()
        try:
            config = load_config()
            companies = [dict(c, feeds=[]) for c in config['companies']
                         if c.get('segment_verified') is True and c.get('segment') in ('Mid Cap','Small Cap','First North')]
            _, failures, diagnostics = scan_detailed(dict(companies=companies, shared_feeds=config.get('shared_feeds', [])), on_match=matched)
            print(json.dumps(dict(event='poll', failures=failures, sources=[dict(feed=d['feed'],status=d['status'],raw_items=d['raw_items']) for d in diagnostics], seconds=round(time.monotonic()-started,3))), flush=True)
            delay = min(300, delay*2) if failures else interval
        except Exception as exc:
            print(json.dumps(dict(event='poll_error', error=type(exc).__name__)), flush=True)
            delay = min(300, delay*2)
        if once:
            return
        time.sleep(max(1, delay-(time.monotonic()-started)))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--interval', type=int, default=30)
    p.add_argument('--state', default='fast_news_dry_seen.json')
    p.add_argument('--send', action='store_true')
    p.add_argument('--once', action='store_true')
    args = p.parse_args()
    if args.send and args.state == 'fast_news_dry_seen.json':
        p.error('Use a separate seeded live state file')
    run(args.interval, args.state, args.send, args.once)
