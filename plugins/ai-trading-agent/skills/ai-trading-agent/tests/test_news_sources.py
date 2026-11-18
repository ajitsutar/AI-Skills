import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_sources as ns


NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
SOURCE = {'id': 'issuer_news', 'url': 'https://issuer.example/news/rss',
          'adapter': 'rss', 'source_kind': 'issuer', 'scope_issuers': ['DEMO']}
RSS = b'''<rss version="2.0"><channel><item><title>Demo raises guidance</title>
<description>&lt;p&gt;Revenue outlook &amp;amp; profitability.&lt;/p&gt;</description>
<link>https://issuer.example/release/1</link>
<pubDate>Mon, 12 Oct 2026 14:00:00 GMT</pubDate></item></channel></rss>'''


class NewsParsingTests(unittest.TestCase):
    def test_timestamp_formats_are_utc_and_timezone_is_mandatory(self):
        self.assertEqual(ns.iso('2026-10-12T08:00:00-07:00'), ns.iso(NOW))
        self.assertEqual(ns.iso('Mon, 12 Oct 2026 08:00:00 -0700'), ns.iso(NOW))
        self.assertEqual(ns.iso('20261012T150000Z'), ns.iso(NOW))
        for value in ('2026-10-12', '2026-10-12T15:00:00', '', None, 'invalid'):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                ns.stamp(value)

    def test_rss_and_atom_keep_publication_separate_from_revision(self):
        rss = ns.parse_feed(RSS, SOURCE)
        self.assertEqual(len(rss), 1)
        self.assertEqual(rss[0]['summary'], 'Revenue outlook & profitability.')
        self.assertEqual(rss[0]['evidence_kind'], 'FEED_EXCERPT')
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>Demo update</title><published>2026-10-12T12:00:00Z</published>
        <updated>2026-10-12T14:30:00Z</updated>
        <link rel="self" href="/ignored"/><link rel="alternate" href="/release/2"/>
        <summary type="html">&lt;p&gt;Business update&lt;/p&gt;</summary>
        </entry></feed>'''
        row = ns.parse_feed(atom, SOURCE)[0]
        self.assertEqual(row['url'], 'https://issuer.example/release/2')
        self.assertEqual(row['published_at'], '2026-10-12T12:00:00Z')
        self.assertEqual(row['updated_at'], '2026-10-12T14:30:00Z')

    def test_xxe_html_and_malformed_xml_are_not_valid_empty_news(self):
        for raw in (b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///private">]><rss>&x;</rss>',
                    b'<html><body>Access denied</body></html>', b'<rss>'):
            with self.subTest(raw=raw), self.assertRaises(Exception):
                ns.parse_feed(raw, SOURCE)
        self.assertEqual(ns.parse_feed(b'<rss><channel/></rss>', SOURCE), [])

    def test_utf16_and_utf32_doctype_cannot_bypass_entity_rejection(self):
        xml = '<!DOCTYPE rss [<!ENTITY x "expanded">]><rss><channel><item><title>&x;</title></item></channel></rss>'
        for encoding in ('utf-16', 'utf-16-le', 'utf-16-be', 'utf-32'):
            with self.subTest(encoding=encoding), self.assertRaises(ValueError):
                ns.parse_feed(xml.encode(encoding), SOURCE)
        self.assertEqual(ns.parse_feed(b'\xef\xbb\xbf<rss><channel/></rss>', SOURCE), [])

    def test_sec_includes_interquarter_forms_and_validates_issuer(self):
        forms = ['8-K', '6-K/A', '10-Q', '4']
        raw = json.dumps({'cik': '123', 'name': 'Demo Inc', 'filings': {'recent': {
            'form': forms, 'accessionNumber': ['0000000123-26-000001'] * 4,
            'primaryDocument': ['update.htm'] * 4, 'items': ['2.02,7.01'] * 4,
            'acceptanceDateTime': ['2026-10-12T14:00:00Z'] * 4}}}).encode()
        source = dict(SOURCE, adapter='sec_submissions', source_kind='sec', cik=123)
        rows = ns.parse_sec(raw, source)
        self.assertEqual([r['form'] for r in rows], ['8-K', '6-K/A', '10-Q'])
        self.assertTrue(all(r['evidence_kind'] == 'FILING_METADATA_ONLY' for r in rows))
        self.assertEqual(rows[0]['items'], '2.02,7.01')
        self.assertIn('/123/000000012326000001/update.htm', rows[0]['url'])
        with self.assertRaisesRegex(ValueError, 'CIK mismatch'):
            ns.parse_sec(raw, dict(source, cik=124))

    def test_gdelt_observation_time_is_not_fabricated_publication_time(self):
        rows = ns.parse_gdelt(json.dumps({'articles': [{'title': 'Demo update',
            'url': 'https://publisher.example/news', 'seendate': '20261012T143000Z'}]}), SOURCE)
        self.assertIsNone(rows[0]['published_at'])
        record = ns.normalize(rows[0], SOURCE, NOW, {})
        self.assertIn('PUBLICATION_TIME_UNKNOWN', record['flags'])
        self.assertEqual(record['provider_seen_at'], '2026-10-12T14:30:00Z')
        self.assertEqual(record['available_at'], ns.iso(NOW))
        self.assertEqual(ns.parse_gdelt('{"articles": []}', SOURCE), [])
        with self.assertRaisesRegex(ValueError, 'articles missing'):
            ns.parse_gdelt('{"error": "limit"}', SOURCE)

    def test_missing_future_and_invalid_article_times_are_flagged(self):
        base = ns.parse_feed(RSS, SOURCE)[0]
        missing = ns.normalize(dict(base, published_at=None, url='javascript:alert(1)'), SOURCE, NOW, {})
        self.assertIn('PUBLICATION_TIME_UNKNOWN', missing['flags'])
        self.assertIn('ARTICLE_URL_INVALID', missing['flags'])
        future = ns.normalize(dict(base, published_at='2026-10-12T16:00:00Z'), SOURCE, NOW, {})
        self.assertIn('PUBLISHED_AT_IN_FUTURE', future['flags'])
        self.assertEqual(future['available_at'], '2026-10-12T16:00:00Z')

    def test_first_seen_survives_retrieval_and_changed_content_is_new_revision(self):
        row = ns.parse_feed(RSS, SOURCE)[0]
        first = ns.normalize(row, SOURCE, NOW, {})
        seen = {first['event_id']: first['first_seen_at']}
        again = ns.normalize(row, SOURCE, NOW + timedelta(hours=1), seen)
        self.assertEqual(again['event_id'], first['event_id'])
        self.assertEqual(again['available_at'], first['available_at'])
        self.assertFalse(again['new_revision'])
        revised = ns.normalize(dict(row, summary='Corrected revenue outlook'), SOURCE,
                               NOW + timedelta(hours=1), seen)
        self.assertNotEqual(revised['event_id'], first['event_id'])
        self.assertEqual(revised['first_seen_at'], '2026-10-12T16:00:00Z')
        self.assertTrue(revised['new_revision'])

    def test_nasdaq_events_keep_symbols_status_and_actual_eastern_event_time(self):
        raw = b'''<rss xmlns:n="urn:nasdaq"><channel>
        <item><title>Trading halt</title><pubDate>Mon, 12 Oct 2026 00:00:00 -0400</pubDate>
        <n:IssueSymbol>DEMO</n:IssueSymbol><n:HaltDate>10/12/2026</n:HaltDate>
        <n:HaltTime>10:45:00</n:HaltTime><n:ReasonCode>T1</n:ReasonCode></item>
        <item><title>Trading halt</title><pubDate>Mon, 12 Oct 2026 00:00:00 -0400</pubDate>
        <n:IssueSymbol>TEST</n:IssueSymbol><n:HaltDate>10/12/2026</n:HaltDate>
        <n:HaltTime>10:45:00</n:HaltTime><n:ReasonCode>T7</n:ReasonCode>
        <n:ResumptionQuoteTime>11:15:00</n:ResumptionQuoteTime>
        <n:ResumptionTradeTime></n:ResumptionTradeTime></item>
        </channel></rss>'''
        source = dict(SOURCE, source_kind='exchange', scope_issuers=[])
        rows = ns.parse_feed(raw, source)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['published_at'] is None for r in rows))
        self.assertEqual(rows[0]['event_at'], '2026-10-12T14:45:00Z')
        self.assertIn('00:00:00', rows[0]['feed_dateline'])
        self.assertNotEqual(rows[0]['source_item_id'], rows[1]['source_item_id'])
        self.assertEqual(rows[1]['exchange_fields']['ResumptionTradeTime'], '')
        first, second = [ns.normalize(r, source, NOW, {}) for r in rows]
        self.assertNotEqual(first['event_id'], second['event_id'])
        revised = copy.deepcopy(rows[1])
        revised['exchange_fields']['ResumptionTradeTime'] = '11:20:00'
        later = ns.normalize(revised, source, NOW + timedelta(hours=1),
                             {second['event_id']: second['first_seen_at']})
        self.assertNotEqual(later['event_id'], second['event_id'])
        self.assertEqual(later['available_at'], '2026-10-12T16:00:00Z')

    def test_eastern_event_dst_ambiguity_is_not_silently_resolved(self):
        self.assertEqual(ns.eastern_event('10/12/2026', '09:30:00'), '2026-10-12T13:30:00Z')
        self.assertEqual(ns.eastern_event('12/14/2026', '09:30:00'), '2026-12-14T14:30:00Z')
        self.assertIsNone(ns.eastern_event('11/01/2026', '01:30:00'))
        self.assertIsNone(ns.eastern_event('03/08/2026', '02:30:00'))
        self.assertIsNone(ns.eastern_event('not a date', '09:30:00'))

    def test_endpoint_requires_public_https_and_rejects_private_dns_answers(self):
        global_address = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch.object(ns.socket, 'getaddrinfo', return_value=global_address):
            ns.validate_url('https://publisher.example/feed?q=guidance')
            # Assemble fictional credential syntax without triggering export scanning.
            for url in ('http://publisher.example/feed', 'https://user:password' + '@publisher.example/',
                        'https://publisher.example:8443/', 'https://publisher.example/?api_key' + '=private',
                        'file:///tmp/news.xml'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    ns.validate_url(url)
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            with patch.object(ns.socket, 'getaddrinfo', return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))]):
                with self.subTest(address=address), self.assertRaisesRegex(ValueError, 'Private/local'):
                    ns.validate_url('https://publisher.example/feed')

    def test_fetch_has_no_login_profile_redirect_following_or_unbounded_response(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.headers = {'ETag': 'v1'}
        response.iter_content.return_value = [b'<rss/>']
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = response
        with patch.object(ns, 'validate_url'), patch('requests.Session', return_value=session):
            code, headers, body = ns.fetch(SOURCE, {'etag': 'v0', 'last_modified': 'Mon, 12 Oct 2026 12:00:00 GMT'},
                                           'Fictional research contact' + '@example.invalid')
            self.assertFalse(session.trust_env)
            options = session.get.call_args.kwargs
            self.assertFalse(options['allow_redirects'])
            self.assertEqual(options['headers']['If-None-Match'], 'v0')
            self.assertIn('If-Modified-Since', options['headers'])
            self.assertEqual((code, body), (200, b'<rss/>'))
            response.iter_content.return_value = [b'12345']
            with patch.object(ns, 'MAX_BYTES', 4), self.assertRaisesRegex(ValueError, 'size limit'):
                ns.fetch(SOURCE, {}, 'Fictional research contact' + '@example.invalid')


class NewsPollingTests(unittest.TestCase):
    def test_unknown_source_kind_cannot_silently_skip_specialized_handling(self):
        self.config['sources'][0]['source_kind'] = 'EXCHANGE_PRIMARY'
        with self.assertRaisesRegex(ValueError, 'source_kind'):
            self.poll()
        self.assertFalse(self.calls)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'
        self.config = {'user_agent': 'Fictional research contact' + '@example.invalid', 'sources': [copy.deepcopy(SOURCE)]}
        self.now = NOW
        self.calls = []
        self.response = (200, {'ETag': 'v1'}, RSS)
        self.run_count = 0

    def transport(self, source, previous, user_agent):
        self.calls.append((copy.deepcopy(source), copy.deepcopy(previous)))
        return self.response

    def poll(self):
        self.run_count += 1
        return ns.poll(self.config, self.state, self.root / ('run' + str(self.run_count)),
                       transport=self.transport, clock=lambda: self.now, sleeper=lambda _: None)

    def test_conditional_polling_preserves_cached_history_and_waits_until_due(self):
        first = self.poll()
        self.assertEqual(first['sources'][0]['status'], 'PARSED')
        self.assertEqual(first['sources'][0]['new_revision_count'], 1)
        self.assertEqual((self.root / 'run1' / 'issuer_news.response').read_bytes(), RSS)
        self.now += timedelta(seconds=60)
        not_due = self.poll()
        self.assertEqual(not_due['sources'][0]['status'], 'NOT_DUE')
        self.assertEqual(not_due['records'][0]['retrieved_at'], first['records'][0]['retrieved_at'])
        self.assertEqual(not_due['records'][0]['source_refresh_status'], 'NOT_DUE')
        self.assertFalse(not_due['records'][0]['new_revision'])
        self.assertEqual(len(self.calls), 1)
        self.now += timedelta(seconds=240)
        self.response = (304, {}, b'')
        unchanged = self.poll()
        self.assertEqual(unchanged['sources'][0]['status'], 'UNCHANGED')
        self.assertEqual(self.calls[-1][1]['etag'], 'v1')
        self.assertEqual(len(unchanged['records']), 1)
        self.assertEqual(unchanged['records'][0]['event_id'], first['records'][0]['event_id'])
        self.assertEqual(unchanged['records'][0]['available_at'], first['records'][0]['available_at'])
        self.assertFalse(unchanged['records'][0]['new_revision'])
        self.now += timedelta(seconds=300)
        self.response = (200, {}, RSS)
        replay = self.poll()
        self.assertEqual(replay['sources'][0]['new_revision_count'], 0)
        self.assertEqual(replay['records'][0]['first_seen_at'], first['records'][0]['first_seen_at'])
        state = json.loads(self.state.read_text())
        self.assertNotIn('etag', state['sources']['issuer_news'])

    def test_429_retry_after_is_respected_and_success_clears_failures(self):
        self.response = (429, {'Retry-After': '1200'}, b'too many requests')
        failed = self.poll()['sources'][0]
        self.assertEqual(failed['status'], 'RATE_LIMITED')
        self.assertEqual(ns.stamp(failed['next_poll_at']), NOW + timedelta(seconds=1200))
        self.now += timedelta(seconds=600)
        pending = self.poll()['sources'][0]
        self.assertEqual(pending['previous_status'], 'RATE_LIMITED')
        self.assertIsNone(pending['last_success_at'])
        self.now += timedelta(seconds=600)
        self.response = (200, {}, b'<rss><channel/></rss>')
        self.assertEqual(self.poll()['sources'][0]['status'], 'EMPTY_VALID')
        self.assertEqual(json.loads(self.state.read_text())['sources']['issuer_news']['failures'], 0)

    def test_parse_failure_retains_last_success_without_claiming_empty_news(self):
        first = self.poll()['sources'][0]
        self.now += timedelta(seconds=300)
        self.response = (200, {'ETag': 'broken'}, b'<html>sign in</html>')
        failed = self.poll()
        self.assertEqual(failed['sources'][0]['status'], 'FAILED')
        self.assertEqual(failed['sources'][0]['last_success_at'], first['last_success_at'])
        self.assertEqual(len(failed['records']), 1)
        self.assertEqual(failed['records'][0]['retrieved_at'], ns.iso(NOW))
        self.assertEqual(failed['records'][0]['source_refresh_status'], 'FAILED')
        self.assertFalse(failed['records'][0]['new_revision'])
        cached = json.loads(self.state.read_text())['sources']['issuer_news']
        self.assertEqual(cached['etag'], 'v1')
        self.assertEqual(cached['failures'], 1)

    def test_304_without_prior_success_is_failure(self):
        self.response = (304, {}, b'')
        receipt = self.poll()['sources'][0]
        self.assertEqual(receipt['status'], 'FAILED')
        self.assertIsNone(receipt['last_success_at'])

    def test_changed_endpoint_does_not_reuse_old_success_or_validators(self):
        self.poll()
        self.config['sources'][0]['url'] = 'https://different.example/rss'
        self.response = (304, {}, b'')
        report = self.poll()
        self.assertEqual(self.calls[-1][1], {})
        self.assertEqual(report['sources'][0]['status'], 'FAILED')

    def test_lock_is_not_stolen_and_owned_lock_is_cleaned_on_error(self):
        lock = self.state.with_name(self.state.name + '.lock')
        lock.write_text('another process')
        with self.assertRaises(FileExistsError):
            self.poll()
        self.assertEqual(lock.read_text(), 'another process')
        lock.unlink()
        self.state.write_text('{invalid json')
        with self.assertRaises(json.JSONDecodeError):
            self.poll()
        self.assertFalse(lock.exists())
        self.assertEqual(self.calls, [])

    def test_access_denial_and_redirect_are_visible_and_never_followed(self):
        for code, status in ((403, 'ACCESS_DENIED'), (302, 'REDIRECT_REQUIRES_CONFIG'), (500, 'HTTP_ERROR')):
            with self.subTest(code=code):
                self.response = (code, {'Location': 'https://private.example/login'}, b'')
                receipt = self.poll()['sources'][0]
                self.assertEqual(receipt['status'], status)
                self.assertIsNone(receipt['last_success_at'])
                self.now = ns.stamp(receipt['next_poll_at'])

    def test_safe_ids_sec_contact_and_adapter_validation_precede_poll(self):
        for source in (dict(SOURCE, id='../unsafe'), dict(SOURCE, adapter='unknown')):
            self.config['sources'] = [source]
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.poll()
        self.config['sources'] = [SOURCE, SOURCE]
        with self.assertRaises(ValueError):
            self.poll()
        self.config['sources'] = [dict(SOURCE, adapter='sec_submissions')]
        self.config['user_agent'] = 'No real contact included'
        with self.assertRaisesRegex(ValueError, 'contact'):
            self.poll()
        self.assertEqual(self.calls, [])

    def test_disabled_source_does_not_use_network_or_claim_access(self):
        self.config['sources'] = [dict(SOURCE, adapter='sec_submissions', enabled=False)]
        result = self.poll()
        self.assertEqual(result['sources'][0]['status'], 'DISABLED')
        self.assertIsNone(result['sources'][0]['last_success_at'])
        self.assertEqual(result['records'], [])
        self.assertEqual(self.calls, [])

    def test_provider_cadence_floors_and_http_date_retry(self):
        self.assertEqual(ns.interval(dict(SOURCE, poll_seconds=1)), 300)
        self.assertEqual(ns.interval(dict(SOURCE, url='https://www.nasdaqtrader.com/rss.aspx', poll_seconds=1)), 60)
        self.assertEqual(ns.interval(dict(SOURCE, adapter='sec_submissions', poll_seconds=1)), 60)
        self.assertEqual(ns.interval(dict(SOURCE, adapter='gdelt', poll_seconds=1)), 900)
        self.assertEqual(ns.delay_seconds('Mon, 12 Oct 2026 15:10:00 GMT', NOW), 600)
        self.assertEqual(ns.delay_seconds('nonsense', NOW), 0)


if __name__ == '__main__':
    unittest.main()
