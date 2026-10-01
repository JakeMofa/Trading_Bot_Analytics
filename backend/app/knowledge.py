"""Timestamp-safe, retrospective evidence links for stored 15-minute forecasts."""
import argparse
from datetime import timezone
import json

from cases import match_cases
from collector import connect, timestamp, utcnow
from forecasts import initialize as initialize_forecasts
from news import initialize as initialize_news, search_events


def initialize(db):
    initialize_forecasts(db)
    initialize_news(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS prediction_context_links (
      id INTEGER PRIMARY KEY,
      prediction_id INTEGER NOT NULL REFERENCES predictions(id),
      kind TEXT NOT NULL CHECK(kind IN ('news','case')),
      news_event_id INTEGER REFERENCES news_events(id),
      prior_market_id TEXT REFERENCES markets(id),
      prior_snapshot_id INTEGER REFERENCES feature_snapshots(id),
      outcome_observation_id INTEGER REFERENCES observations(id),
      observed_outcome TEXT CHECK(observed_outcome IN ('UP','DOWN')),
      method TEXT NOT NULL, query_text TEXT, distance TEXT,
      linked_at TEXT NOT NULL,
      CHECK((kind='news' AND news_event_id IS NOT NULL
          AND prior_market_id IS NULL AND prior_snapshot_id IS NULL
          AND outcome_observation_id IS NULL AND observed_outcome IS NULL)
        OR (kind='case' AND news_event_id IS NULL
          AND prior_market_id IS NOT NULL AND prior_snapshot_id IS NOT NULL
          AND outcome_observation_id IS NOT NULL AND observed_outcome IS NOT NULL)));
    CREATE UNIQUE INDEX IF NOT EXISTS prediction_context_one_news
      ON prediction_context_links(prediction_id,news_event_id) WHERE kind='news';
    CREATE UNIQUE INDEX IF NOT EXISTS prediction_context_one_prior_market
      ON prediction_context_links(prediction_id,prior_market_id) WHERE kind='case';
    ''')


def link_eligible_context(db, prediction_id, news_query=None, news_limit=5,
                          case_limit=5, now=None):
    """Record evidence eligible at forecast time, without claiming model use.

    This can run later: linked_at is the time of retrospective association, while
    news first_seen and confirmed-case observation times must precede the forecast.
    """
    initialize(db)
    row = db.execute('''SELECT p.snapshot_id,p.as_of,p.created_at,p.market_id,
        s.as_of,s.market_id,m.end FROM predictions p
      JOIN feature_snapshots s ON s.id=p.snapshot_id
      JOIN markets m ON m.id=p.market_id WHERE p.id=?''',
      (prediction_id,)).fetchone()
    if not row:
        raise ValueError('Prediction not found')
    snapshot_id, as_of, created_at, market_id, snapshot_as_of, snapshot_market, end = row
    if market_id != snapshot_market or timestamp(as_of) != timestamp(snapshot_as_of):
        raise ValueError('Prediction and snapshot disagree')
    if not timestamp(as_of) <= timestamp(created_at) < timestamp(end):
        raise ValueError('Prediction was not saved before market close')
    if not 0 <= news_limit <= 20 or not 0 <= case_limit <= 20:
        raise ValueError('limits must be 0..20')
    if news_query and news_limit:
        news = search_events(db, news_query, as_of, news_limit)
    else:
        news = []
    cases = match_cases(db, snapshot_id, case_limit)['matches'] if case_limit else []
    now = now or utcnow()
    if now.tzinfo is None:
        raise ValueError('now needs timezone')
    if now.astimezone(timezone.utc) < timestamp(created_at):
        raise ValueError('Evidence link cannot predate the prediction')
    linked_at = now.astimezone(timezone.utc).isoformat()
    inserted_news = inserted_cases = 0
    with db:
        for event in news:
            inserted_news += db.execute('''INSERT OR IGNORE INTO prediction_context_links
              (prediction_id,kind,news_event_id,method,query_text,linked_at)
              VALUES(?,'news',?,'fts5_eligible_headline_v1',?,?)''',
              (prediction_id,event['id'],news_query,linked_at)).rowcount
        for case in cases:
            inserted_cases += db.execute('''INSERT OR IGNORE INTO prediction_context_links
              (prediction_id,kind,prior_market_id,prior_snapshot_id,
               outcome_observation_id,observed_outcome,method,distance,linked_at)
              VALUES(?,'case',?,?,?,?,?,?,?)''',
              (prediction_id,case['market_id'],case['snapshot_id'],
               case['outcome_observation_id'],case['outcome'],
               'fixed_scale_L1_exploratory_v1',case['distance'],linked_at)).rowcount
    return {'prediction_id':prediction_id,'as_of':as_of,'linked_at':linked_at,
            'new_news_links':inserted_news,'new_case_links':inserted_cases,
            'semantics':'retrospectively eligible context; not used by forecast model'}


def trace_prediction(db, prediction_id):
    """Traverse prediction -> snapshot and explicitly linked eligible context."""
    row = db.execute('''SELECT p.id,p.market_id,p.snapshot_id,p.as_of,p.created_at,
        p.model_version,p.probability_up,s.version
      FROM predictions p JOIN feature_snapshots s ON s.id=p.snapshot_id
      WHERE p.id=?''',(prediction_id,)).fetchone()
    if not row:
        raise ValueError('Prediction not found')
    news = db.execute('''SELECT l.id,e.id,e.title,e.url,e.published_at,
        e.first_seen,l.query_text,l.linked_at
      FROM prediction_context_links l JOIN news_events e ON e.id=l.news_event_id
      WHERE l.prediction_id=? AND l.kind='news' ORDER BY l.id''',
      (prediction_id,)).fetchall()
    cases = db.execute('''SELECT l.id,l.prior_market_id,m.slug,l.prior_snapshot_id,
        s.as_of,l.outcome_observation_id,l.observed_outcome,l.distance,l.linked_at
      FROM prediction_context_links l JOIN markets m ON m.id=l.prior_market_id
      JOIN feature_snapshots s ON s.id=l.prior_snapshot_id
      WHERE l.prediction_id=? AND l.kind='case' ORDER BY l.id''',
      (prediction_id,)).fetchall()
    return {'prediction_id':row[0],'market_id':row[1],
            'snapshot':{'id':row[2],'version':row[7]},
            'as_of':row[3],'created_at':row[4],
            'model_version':row[5],'probability_up':row[6],
            'news':[dict(zip(('link_id','event_id','title','url','published_at',
                              'first_seen','query','linked_at'),item)) for item in news],
            'prior_cases':[dict(zip(('link_id','market_id','slug','snapshot_id',
                                      'snapshot_as_of','outcome_observation_id',
                                      'observed_outcome','distance','linked_at'),item))
                           for item in cases],
            'link_semantics':'retrospectively eligible context; not used by forecast model'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default='data/btc_intelligence.db')
    parser.add_argument('--prediction-id',type=int)
    parser.add_argument('--link',action='store_true',help='Persist eligible context links')
    parser.add_argument('--news-query',default='bitcoin')
    args=parser.parse_args()
    db=connect(args.db)
    try:
        initialize(db)
        prediction_id=args.prediction_id
        if prediction_id is None:
            row=db.execute('SELECT id FROM predictions ORDER BY id DESC LIMIT 1').fetchone()
            if not row:
                parser.error('No predictions stored')
            prediction_id=row[0]
        if args.link:
            print(json.dumps(link_eligible_context(db,prediction_id,args.news_query),indent=2))
        print(json.dumps(trace_prediction(db,prediction_id),indent=2))
    finally:
        db.close()


if __name__=='__main__': main()
