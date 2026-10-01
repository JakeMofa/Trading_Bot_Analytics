from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from collector import connect
from news import available_events, collect_once, initialize, parse_feed, search_events

RSS = b'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>CoinDesk</title>
<item><guid>item-1</guid><title>Bitcoin adoption update</title>
<link>https://www.coindesk.com/news/bitcoin-adoption</link>
<pubDate>Wed, 30 Sep 2026 12:00:00 +0000</pubDate>
<category>Bitcoin</category><description>Do not store article bodies</description></item>
<item><guid>item-2</guid><title>Market update</title>
<link>https://www.coindesk.com/news/market-update</link>
<pubDate>bad date</pubDate></item>
<item><guid>evil</guid><title>Bad link</title>
<link>https://example.com/untrusted</link></item>
</channel></rss>'''


class NewsTests(unittest.TestCase):
    def setUp(self): self.db=connect(':memory:')
    def tearDown(self): self.db.close()

    def test_parse_and_deduplicate_with_first_seen(self):
        items, invalid = parse_feed(RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(invalid, 1)
        self.assertEqual(items[0]['asset_tag'], 'BTC')
        first = collect_once(self.db, lambda:RSS,
                             lambda:datetime(2026,9,30,13,tzinfo=timezone.utc))
        second = collect_once(self.db, lambda:RSS,
                              lambda:datetime(2026,9,30,14,tzinfo=timezone.utc))
        self.assertEqual(first['new'], 2)
        self.assertEqual(second['new'], 0)
        self.assertEqual(first['missing_publication_time'], 1)
        self.assertEqual(len(available_events(self.db,'2026-09-30T12:30:00Z')), 0)
        events = available_events(self.db,'2026-09-30T13:30:00Z')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['asset_tag'], 'BTC')
        self.assertNotIn('Do not store article bodies',events[0].values())
        self.assertEqual(self.db.execute('SELECT first_seen,last_seen FROM news_events WHERE source_guid=?',('item-1',)).fetchone(),
                         ('2026-09-30T13:00:00+00:00','2026-09-30T14:00:00+00:00'))

    def test_invalid_feed_and_future_publication(self):
        with self.assertRaises(ValueError): parse_feed(b'<html/>')
        future = RSS.replace(b'Wed, 30 Sep 2026 12:00:00 +0000',
                             b'Thu, 01 Oct 2026 12:00:00 +0000')
        collect_once(self.db,lambda:future,
                     lambda:datetime(2026,9,30,13,tzinfo=timezone.utc))
        self.assertEqual(available_events(self.db,'2026-09-30T14:00:00Z'),[])

    def test_fts_search_respects_first_seen_and_publisher_time(self):
        collect_once(self.db,lambda:RSS,
                     lambda:datetime(2026,9,30,13,tzinfo=timezone.utc))
        self.assertEqual(search_events(self.db,'bitcoin','2026-09-30T12:30:00Z'),[])
        matches=search_events(self.db,'bitcoin','2026-09-30T13:30:00Z',asset_tag='BTC')
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['title'],'Bitcoin adoption update')
        self.assertEqual(search_events(self.db,'bitcoin','2026-09-30T13:30:00Z',asset_tag='general'),[])
        self.assertEqual(search_events(self.db,'OR bitcoin','2026-09-30T13:30:00Z'),[])
        with self.assertRaises(ValueError): search_events(self.db,'*','2026-09-30T13:30:00Z')

    def test_fts_migration_indexes_existing_rows_and_tracks_deletion(self):
        self.db.execute('''CREATE TABLE news_events (
          id INTEGER PRIMARY KEY,source TEXT NOT NULL,source_guid TEXT NOT NULL,
          url TEXT NOT NULL,title TEXT NOT NULL,published_at TEXT,
          first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,
          categories_json TEXT NOT NULL,asset_tag TEXT NOT NULL,
          UNIQUE(source,source_guid))''')
        self.db.execute('''INSERT INTO news_events
          (source,source_guid,url,title,published_at,first_seen,last_seen,
           categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
          ('coindesk_rss','old','https://www.coindesk.com/old','Bitcoin ETF',
           '2026-09-30T12:00:00+00:00','2026-09-30T13:00:00+00:00',
           '2026-09-30T13:00:00+00:00','[]','BTC'))
        initialize(self.db)
        self.assertEqual(len(search_events(self.db,'bitcoin','2026-09-30T14:00:00Z')),1)
        initialize(self.db)
        self.db.execute('DELETE FROM news_events WHERE source_guid=?',('old',))
        self.assertEqual(search_events(self.db,'bitcoin','2026-09-30T14:00:00Z'),[])


if __name__=='__main__': unittest.main()
