"""Read-only coverage and health report for a bounded 15-minute collection run."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

from collector import timestamp, utcnow


def audit(db, since, until):
    since, until = timestamp(since), timestamp(until)
    if since >= until:
        raise ValueError('since must precede until')
    begin, end = since.isoformat(), until.isoformat()
    market_rows = db.execute('''SELECT o.market_id,MIN(o.received_at),m.slug,m.start,m.end,
      m.status,m.result,m.last_seen FROM observations o JOIN markets m ON m.id=o.market_id
      WHERE m.duration=900 AND o.kind='metadata' AND o.received_at>=? AND o.received_at<?
        AND julianday(m.end)>julianday(?) AND julianday(m.start)<julianday(?)
      GROUP BY o.market_id ORDER BY MIN(o.received_at)''', (begin,end,begin,end)).fetchall()
    snapshot_rows = db.execute('''SELECT market_id,as_of,quality_json
      FROM feature_snapshots WHERE as_of>=? AND as_of<? ORDER BY as_of''', (begin,end)).fetchall()
    prediction_rows = db.execute('''SELECT market_id,probability_up,abstain_reason
      FROM predictions WHERE created_at>=? AND created_at<?''', (begin,end)).fetchall()
    failures = db.execute('''SELECT source,COUNT(*) FROM runs WHERE success=0
      AND received_at>=? AND received_at<? GROUP BY source ORDER BY source''', (begin,end)).fetchall()
    quality = [json.loads(row[2]) for row in snapshot_rows]
    missing = Counter(name for row in quality for name in row.get('missing_features',[]))
    price_status = Counter(row.get('price',{}).get('status','unknown') for row in quality)
    candle_status = Counter(row.get('candle_status','unknown') for row in quality)
    gaps = [(timestamp(snapshot_rows[i][1])-timestamp(snapshot_rows[i-1][1])).total_seconds()
            for i in range(1,len(snapshot_rows))]
    outcomes = Counter(row[6] if row[6] in ('UP','DOWN')
                       and row[5]=='MARKET_STATUS_RESOLVED' and timestamp(row[7])<=until
                       else 'unconfirmed' for row in market_rows)
    return {
        'window': {'since':begin,'until':end,'hours':(until-since).total_seconds()/3600},
        'markets': {'seen':len(market_rows),'rollovers_observed':max(0,len(market_rows)-1),
                    'confirmed':sum(row[6] in ('UP','DOWN') and row[5]=='MARKET_STATUS_RESOLVED'
                                    and timestamp(row[7])<=until
                                    for row in market_rows),
                    'outcomes':dict(outcomes),
                    'sessions':[{'id':row[0],'slug':row[2],'start':row[3],'end':row[4],
                                 'first_observed_in_window':row[1],
                                 'current_status':row[5], 'current_result':row[6],
                                 'confirmed_by_window_end':bool(row[6] in ('UP','DOWN')
                                    and row[5]=='MARKET_STATUS_RESOLVED'
                                    and timestamp(row[7])<=until)} for row in market_rows]},
        'features': {'snapshots':len(snapshot_rows),
                     'markets_with_snapshots':len({row[0] for row in snapshot_rows}),
                     'complete_snapshots':sum(not row.get('missing_features') for row in quality),
                     'missing_feature_counts':dict(missing),
                     'price_status_counts':dict(price_status),
                     'candle_status_counts':dict(candle_status),
                     'largest_snapshot_gap_seconds':max(gaps) if gaps else None,
                     'gaps_over_90_seconds':sum(gap>90 for gap in gaps)},
        'forecasts': {'total':len(prediction_rows),
                      'markets_with_forecasts':len({row[0] for row in prediction_rows}),
                      'probabilities':sum(row[1] is not None for row in prediction_rows),
                      'abstentions':sum(row[2] is not None for row in prediction_rows),
                      'abstain_reasons':dict(Counter(row[2] for row in prediction_rows if row[2]))},
        'recorded_failures':dict(failures),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/btc_intelligence.db')
    parser.add_argument('--since',required=True,help='UTC ISO timestamp of run start')
    parser.add_argument('--until',help='UTC ISO timestamp; defaults to now')
    args=parser.parse_args()
    path=Path(args.db).resolve()
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        report=audit(db,args.since,args.until or utcnow().isoformat())
        report['integrity']={'quick_check':db.execute('PRAGMA quick_check').fetchone()[0],
                             'foreign_key_violations':len(db.execute('PRAGMA foreign_key_check').fetchall())}
        print(json.dumps(report,indent=2))
    finally:
        db.close()


if __name__=='__main__': main()
