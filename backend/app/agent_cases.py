"""Agent: runs case-debug sweeps and writes debug docs into docs/."""
import json
from collector import connect
from cases import match_cases


def run_debug(db_path='data/btc_intelligence.db', limit=5, recent=100):
    db = connect(db_path)
    try:
        # Find recent snapshots to debug
        rows = db.execute('SELECT id FROM feature_snapshots ORDER BY id DESC LIMIT ?', (recent,)).fetchall()
        results = []
        for (sid,) in rows:
            try:
                res = match_cases(db, sid, limit)
                results.append(res)
            except Exception as e:
                results.append({'snapshot_id': sid, 'error': str(e)})
        # Write a debug file locally
        with open('docs/CASE_SIGNAL_DEBUG.json', 'w') as f:
            json.dump(results, f, indent=2)
        return results
    finally:
        db.close()


if __name__ == '__main__':
    run_debug()
