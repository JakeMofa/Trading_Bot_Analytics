"""Read-only CoinDesk RSS headline ingestion with honest availability times."""
import argparse
from datetime import timezone
from email.utils import parsedate_to_datetime
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from collector import connect, record, timestamp, utcnow

SOURCE = 'coindesk_rss'
FEED_URL = 'https://www.coindesk.com/arc/outboundfeeds/rss/'
MAX_FEED_BYTES = 2_000_000
BTC_PATTERN = re.compile(r'\b(?:bitcoin|btc|xbt)\b', re.IGNORECASE)


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS news_events (
      id INTEGER PRIMARY KEY,
      source TEXT NOT NULL, source_guid TEXT NOT NULL,
      url TEXT NOT NULL, title TEXT NOT NULL,
      published_at TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
      categories_json TEXT NOT NULL, asset_tag TEXT NOT NULL,
      UNIQUE(source, source_guid));
    CREATE INDEX IF NOT EXISTS news_events_available
      ON news_events(first_seen, published_at);
    CREATE VIRTUAL TABLE IF NOT EXISTS news_events_fts USING fts5(
      title, categories_json, content='news_events', content_rowid='id');
    CREATE TRIGGER IF NOT EXISTS news_events_fts_insert AFTER INSERT ON news_events BEGIN
      INSERT INTO news_events_fts(rowid,title,categories_json)
      VALUES(new.id,new.title,new.categories_json);
    END;
    CREATE TRIGGER IF NOT EXISTS news_events_fts_update
      AFTER UPDATE OF title,categories_json ON news_events BEGIN
      INSERT INTO news_events_fts(news_events_fts,rowid,title,categories_json)
      VALUES('delete',old.id,old.title,old.categories_json);
      INSERT INTO news_events_fts(rowid,title,categories_json)
      VALUES(new.id,new.title,new.categories_json);
    END;
    CREATE TRIGGER IF NOT EXISTS news_events_fts_delete AFTER DELETE ON news_events BEGIN
      INSERT INTO news_events_fts(news_events_fts,rowid,title,categories_json)
      VALUES('delete',old.id,old.title,old.categories_json);
    END;
    CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY);
    ''')
    if not db.execute("SELECT 1 FROM schema_migrations WHERE name='news_events_fts_v1'").fetchone():
        with db:
            db.execute("INSERT INTO news_events_fts(news_events_fts) VALUES('rebuild')")
            db.execute("INSERT INTO schema_migrations(name) VALUES('news_events_fts_v1')")


def fetch_feed():
    request = Request(FEED_URL, headers={
        'User-Agent': 'BTC-Intelligence-ReadOnly/0.1',
        'Accept': 'application/rss+xml,application/xml'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                body = response.read(MAX_FEED_BYTES + 1)
                if len(body) > MAX_FEED_BYTES:
                    raise ValueError('RSS feed exceeds size limit')
                return body
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _published(text):
    if not text:
        return None
    try:
        value = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def parse_feed(body):
    if len(body) > MAX_FEED_BYTES:
        raise ValueError('RSS feed exceeds size limit')
    root = ET.fromstring(body)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Unexpected RSS document')
    items = []
    invalid = 0
    for item in root.findall('./channel/item')[:100]:
        title = (item.findtext('title') or '').strip()
        url = (item.findtext('link') or '').strip()
        guid = (item.findtext('guid') or url).strip()
        host = urlparse(url).hostname or ''
        if not title or not guid or urlparse(url).scheme != 'https' or not (host == 'coindesk.com' or host.endswith('.coindesk.com')):
            invalid += 1
            continue
        categories = [(category.text or '').strip() for category in item.findall('category')]
        published = _published(item.findtext('pubDate'))
        items.append({'source_guid': guid[:2000], 'url': url[:2000],
                      'title': title[:1000], 'published_at': published,
                      'categories': categories,
                      'asset_tag': 'BTC' if BTC_PATTERN.search(title + ' ' + ' '.join(categories)) else 'general'})
    return items, invalid


def collect_once(db, fetch=fetch_feed, now=utcnow):
    initialize(db)
    body = fetch()
    items, invalid = parse_feed(body)
    if not items:
        raise ValueError('RSS feed contains no valid items')
    retrieved = now().astimezone(timezone.utc).isoformat()
    new = 0
    with db:
        for item in items:
            new += db.execute('''INSERT OR IGNORE INTO news_events
              (source,source_guid,url,title,published_at,first_seen,last_seen,
               categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
              (SOURCE,item['source_guid'],item['url'],item['title'],item['published_at'],
               retrieved,retrieved,json.dumps(item['categories']),item['asset_tag'])).rowcount
            db.execute('''UPDATE news_events SET last_seen=?
              WHERE source=? AND source_guid=?''', (retrieved,SOURCE,item['source_guid']))
    return {'source': SOURCE, 'retrieved_at': retrieved,
            'items': len(items), 'new': new, 'duplicates': len(items)-new,
            'invalid_items': invalid,
            'missing_publication_time': sum(item['published_at'] is None for item in items),
            'btc_tagged': sum(item['asset_tag']=='BTC' for item in items)}


def available_events(db, as_of, limit=20):
    """Headlines observed and published by as_of; suitable for future retrieval."""
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    cutoff = timestamp(as_of).isoformat()
    rows = db.execute('''SELECT id,source,url,title,published_at,first_seen,asset_tag
      FROM news_events WHERE published_at IS NOT NULL
        AND julianday(published_at)<=julianday(?)
        AND julianday(first_seen)<=julianday(?)
      ORDER BY julianday(published_at) DESC,id DESC LIMIT ?''',
      (cutoff,cutoff,limit)).fetchall()
    return [dict(zip(('id','source','url','title','published_at','first_seen','asset_tag'),row))
            for row in rows]


def search_events(db, query, as_of, limit=20, asset_tag=None):
    """Search headline/category text that was published and locally seen by as_of."""
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1..100')
    if asset_tag not in (None, 'BTC', 'general'):
        raise ValueError('asset_tag must be BTC or general')
    tokens = re.findall(r'[a-z0-9]{2,}', query.lower())[:8]
    if not tokens:
        raise ValueError('query must contain a word of at least two characters')
    # Quote plain tokens so callers cannot pass FTS operators or malformed syntax.
    expression = ' '.join('"' + token + '"' for token in tokens)
    cutoff = timestamp(as_of).isoformat()
    rows = db.execute('''SELECT e.id,e.source,e.url,e.title,e.published_at,
        e.first_seen,e.asset_tag,bm25(news_events_fts)
      FROM news_events_fts JOIN news_events e ON e.id=news_events_fts.rowid
      WHERE news_events_fts MATCH ? AND e.published_at IS NOT NULL
        AND julianday(e.published_at)<=julianday(?)
        AND julianday(e.first_seen)<=julianday(?)
        AND (? IS NULL OR e.asset_tag=?)
      ORDER BY bm25(news_events_fts),julianday(e.published_at) DESC,e.id DESC
      LIMIT ?''', (expression,cutoff,cutoff,asset_tag,asset_tag,limit)).fetchall()
    fields = ('id','source','url','title','published_at','first_seen','asset_tag','search_rank')
    return [dict(zip(fields,row)) for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='data/btc_intelligence.db')
    parser.add_argument('--seconds', type=int, default=0,
                        help='Optional bounded polling duration; zero fetches once')
    parser.add_argument('--interval', type=int, default=600,
                        help='Seconds between requests during a bounded run; minimum 300')
    args = parser.parse_args()
    if not 0 <= args.seconds <= 86400 or args.interval < 300:
        parser.error('seconds must be 0..86400 and interval at least 300')
    db = connect(args.db)
    try:
        deadline = time.monotonic() + args.seconds
        while True:
            try:
                result = collect_once(db)
                record(db,SOURCE,True,json.dumps(result))
                print(json.dumps(result),flush=True)
            except Exception as exc:
                record(db,SOURCE,False,f'{type(exc).__name__}: {exc}')
                if args.seconds == 0:
                    raise
                print(json.dumps({'source': SOURCE, 'error': f'{type(exc).__name__}: {exc}'}),flush=True)
            if args.seconds == 0 or time.monotonic() >= deadline:
                break
            time.sleep(min(args.interval, max(0,deadline-time.monotonic())))
            if time.monotonic() >= deadline:
                break
    finally:
        db.close()


if __name__ == '__main__':
    main()
