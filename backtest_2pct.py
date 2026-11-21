"""Offline event-outcome evaluator, NOT a historical signal backtester.
CSV columns: signal_time,entry_time,entry_price,high,low,close,time
Each signal must have subsequent intraday 5-min bars in the CSV. High/low tie is
counted as STOP first (conservative); no claims about executable fills.
"""
import argparse
import csv
from datetime import datetime


def evaluate(bars, signals, target=0.02, stop=0.01):
    results=[]
    for signal in signals:
        t=datetime.fromisoformat(signal['entry_time'])
        price=float(signal['entry_price'])
        day=t.date()
        future=[b for b in bars if datetime.fromisoformat(b['time']).date()==day
                and datetime.fromisoformat(b['time']) > t]
        result='TIMEOUT'
        for b in sorted(future,key=lambda x:x['time']):
            hi,lo=float(b['high']),float(b['low'])
            if lo <= price*(1-stop):
                result='STOP'; break
            if hi >= price*(1+target):
                result='TARGET'; break
        results.append({'entry_time':signal['entry_time'],'outcome':result})
    return results


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--bars',required=True,help='CSV med efterföljande 5-minutersstaplar')
    ap.add_argument('--signals',required=True,help='CSV med historiska signaler och realistiska inträden')
    args=ap.parse_args()
    with open(args.bars,newline='',encoding='utf-8-sig') as f: bars=list(csv.DictReader(f))
    with open(args.signals,newline='',encoding='utf-8-sig') as f: signals=list(csv.DictReader(f))
    if not signals: raise SystemExit('Inga signaler: kan inte beräkna träffsäkerhet')
    outcomes=evaluate(bars,signals)
    n=len(outcomes)
    for key in ('TARGET','STOP','TIMEOUT'):
        k=sum(x['outcome']==key for x in outcomes)
        print(f'{key}: {k}/{n} ({k/n:.1%})')
    print('OBS: Ej nettoresultat; exkluderar courtage, spread, slippage och datakvalitetsfel.')

if __name__=='__main__': main()
