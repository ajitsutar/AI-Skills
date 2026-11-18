import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import market_sources as ms
import market_flow

AT = '2026-11-12T22:00:00+00:00'


def document(text='Date,Open,High,Low,Close,Volume,Adjusted\n2026-11-12,10,12,9,11,150.5,10.5\n'):
    return dict(schema_version=1, adapter='daily_bars_csv', as_of=AT, raw_complete=True,
        ticker='DEMO', source=dict(id='permitted-supplied-export', url='https://data.example.test/export',
            retrieved_at=AT, observed_at=AT, raw_sha256='a' * 64), text=text,
        columns=dict(date='Date', open='Open', high='High', low='Low', close='Close',
                     volume='Volume', adjusted_close='Adjusted'),
        bar_context=dict(feed_id='explicit-export', currency='USD', issuer_id='example-issuer',
            share_class='common', price_basis='unadjusted_daily_ohlc',
            volume_basis='provider_reported_share_volume', adjustment_basis='declared_share_basis',
            comparison_group='declared_regular_session', volume_unit='shares', role='current',
            sessions={'2026-11-12': dict(start_at='2026-11-12T14:30:00+00:00',
                                        end_at='2026-11-12T21:00:00+00:00')}))


class DailyBarIntakeTests(unittest.TestCase):
    def test_distinct_facets_preserve_raw_ohlc_adjusted_close_and_fractional_volume(self):
        d = document(); before = copy.deepcopy(d); p = ms.parse(d)
        self.assertEqual(d, before)
        self.assertEqual(len(p['records']), 2)
        self.assertEqual({r['payload']['bar_type'] for r in p['records']}, {'cumulative', 'daily_volume'})
        for row in p['records']:
            self.assertTrue(row['eligible'])
            self.assertEqual(row['payload']['open'], '10')
            self.assertEqual(row['payload']['close'], '11')
            self.assertEqual(row['payload']['adjusted_close'], '10.5')
            self.assertEqual(row['payload']['volume'], '150.5')
        flow = market_flow.analyze(dict(schema_version=1, as_of=AT, records=p['records']))
        self.assertEqual(len(flow['cumulative_bars']), 1)
        self.assertEqual(flow['cumulative_bars'][0]['return_percent'], 10)

    def test_no_implicit_columns_role_calendar_or_ticker(self):
        for field in ('columns', 'bar_context', 'ticker'):
            d = document(); del d[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                ms.parse(d)
        for field in ('role', 'sessions', 'price_basis', 'volume_basis'):
            d = document(); del d['bar_context'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                ms.parse(d)

    def test_future_unfinished_and_unknown_session_remain_ineligible(self):
        d = document(); d['as_of'] = '2026-11-12T20:59:59+00:00'
        self.assertTrue(all(not r['eligible'] for r in ms.parse(d)['records']))
        d = document(); d['bar_context']['sessions'] = {'2026-11-11': d['bar_context']['sessions']['2026-11-12']}
        self.assertTrue(all(not r['eligible'] for r in ms.parse(d)['records']))

    def test_explicit_early_close_used_without_normal_close_substitution(self):
        d = document(); d['as_of'] = d['source']['retrieved_at'] = d['source']['observed_at'] = '2026-11-27T19:00:00+00:00'
        d['text'] = d['text'].replace('2026-11-12', '2026-11-27')
        d['bar_context']['sessions'] = {'2026-11-27': dict(start_at='2026-11-27T14:30:00+00:00',
                                                        end_at='2026-11-27T18:00:00+00:00')}
        p = ms.parse(d)
        self.assertTrue(all(r['eligible'] for r in p['records']))
        self.assertTrue(all(r['payload']['end_at'] == '2026-11-27T18:00:00+00:00' for r in p['records']))

    def test_ohlc_invalid_nonfinite_missing_and_negative_volume_retained(self):
        for fragment in ('10,8,9,11,150.5', '10,12,9,NaN,150.5', '10,12,9,11,-1',
                         '10,12,9,,150.5', '10,12,9,11,Infinity'):
            d = document(); d['text'] = d['text'].replace('10,12,9,11,150.5', fragment)
            with self.subTest(fragment=fragment):
                p = ms.parse(d)
                self.assertEqual(len(p['records']), 2)
                self.assertTrue(all(not r['eligible'] and r.get('parse_error') for r in p['records']))

    def test_duplicate_dates_do_not_choose_first(self):
        d = document(); d['text'] += '2026-11-12,10,12,9,11,150.5,10.5\n'
        p = ms.parse(d)
        self.assertEqual(len(p['records']), 4)
        self.assertTrue(all(not r['eligible'] for r in p['records']))

    def test_partial_or_conflicting_completeness_cannot_enter_analysis(self):
        for variant in (None, False, 1, 'conflict'):
            d = document()
            if variant is None:
                del d['raw_complete']
            elif variant == 'conflict':
                d['source']['raw_complete'] = False
            else:
                d['raw_complete'] = variant
            with self.subTest(variant=variant):
                self.assertTrue(all(not r['eligible'] for r in ms.parse(d)['records']))

    def test_duplicate_headers_aliases_and_extra_row_values_rejected_or_retained(self):
        d = document(); d['text'] = d['text'].replace('High', 'Open')
        with self.assertRaisesRegex(ValueError, 'HEADERS'):
            ms.parse(d)
        d = document(); d['columns']['high'] = 'Open'
        with self.assertRaisesRegex(ValueError, 'COLUMNS'):
            ms.parse(d)
        d = document(); d['text'] = d['text'].replace('10.5\n', '10.5,unexpected\n')
        self.assertTrue(all(not r['eligible'] for r in ms.parse(d)['records']))

    def test_missing_or_unsupported_volume_units_do_not_become_shares(self):
        for unit in (None, 'lots', True):
            d = document(); d['bar_context']['volume_unit'] = unit
            with self.subTest(unit=unit), self.assertRaisesRegex(ValueError, 'SHARE_VOLUME_UNIT'):
                ms.parse(d)

    def test_unterminated_quotes_do_not_become_valid_complete_rows(self):
        d = document(); d['text'] = d['text'].replace(',10.5\n', ',"10.5')
        with self.assertRaisesRegex(ValueError, 'MALFORMED_BAR_CSV'):
            ms.parse(d)

    def test_role_override_is_explicit_and_unknown_volume_basis_stays_unknown(self):
        d = document(); d['bar_context']['role'] = 'baseline'
        d['bar_context']['role_by_session'] = {'2026-11-12': 'current'}
        d['bar_context']['volume_basis'] = 'unknown'
        p = ms.parse(d)
        self.assertTrue(all(r['payload']['role'] == 'current' for r in p['records']))
        flow = market_flow.analyze(dict(schema_version=1, as_of=AT, records=p['records']))
        self.assertIsNone(flow['cumulative_bars'][0]['relative_volume'])


if __name__ == '__main__':
    unittest.main()
