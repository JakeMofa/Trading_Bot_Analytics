"""Agent: news collector and freshness categorizer.

This agent updates news rows with delay_seconds and freshness_category if missing.
It also provides a simple fast-poll loop to collect basic RSS-based sources when
configured. For now it focuses on labeling existing news entries.
"""
import time
from datetime import datetime
from collector import connect

FRESH_THRESHOLDS = [(60, 'very_fresh'), (300, 'fresh'), (3600, 'usable'), (86400, 'stale')]


def categorize_delay(seconds):
    for sec, label in FRESH_THRESHOLDS:
        if seconds <= sec:
            return label
    return 'old'


def ensure_columns(db):
    cols = [r[1] for r in db.execute('PRAGMA table_info(news)').fetchall()]
    with db:
        if 'delay_seconds' not in cols:
            db.execute('ALTER TABLE news ADD COLUMN delay_seconds REAL')
        if 'freshness_category' not in cols:
            db.execute('ALTER TABLE news ADD COLUMN freshness_category TEXT')


def update_freshness(db):
    rows = db.execute('SELECT id,publication_time,first_seen_time FROM news').fetchall()
    for id_, pub, seen in rows:
        try:
            if pub and seen:
                pub_dt = datetime.fromisoformat(pub)
                seen_dt = datetime.fromisoformat(seen)
                delay = (seen_dt - pub_dt).total_seconds()
                cat = categorize_delay(delay)
                with db:
                    db.execute('UPDATE news SET delay_seconds=?, freshness_category=? WHERE id=?', (delay, cat, id_))
        except Exception:
            continue


def main_loop(db_path='data/btc_intelligence.db'):
    db = connect(db_path)
    try:
        ensure_columns(db)
        while True:
            update_freshness(db)
            time.sleep(30)
    finally:
        db.close()


if __name__ == '__main__':
    main_loop()
