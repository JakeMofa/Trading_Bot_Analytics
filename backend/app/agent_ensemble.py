"""Agent: run ensemble computation continuously for new snapshots."""
import time
from collector import connect
from ensemble import compute_ensemble_for_snapshot


def loop(db_path='data/btc_intelligence.db', interval=15):
    db = connect(db_path)
    try:
        while True:
            # Find latest snapshot id and compute ensemble
            row = db.execute('SELECT id FROM feature_snapshots ORDER BY id DESC LIMIT 1').fetchone()
            if row:
                sid = row[0]
                try:
                    compute_ensemble_for_snapshot(db, sid)
                except Exception:
                    pass
            time.sleep(interval)
    finally:
        db.close()


if __name__ == '__main__':
    loop()
