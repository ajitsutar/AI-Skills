import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import market_sources as ms
from sec_identity import identity_map

AT = '2026-11-12T22:00:00+00:00'
SOURCE = dict(id='sec-identity-test', url='https://www.sec.gov/files/company_tickers_exchange.json',
              retrieved_at=AT, observed_at=AT, published_at=None,
              availability_basis='first_observed_snapshot', raw_sha256='a' * 64)


def document(rows=None):
    return dict(schema_version=1, adapter='sec_company_tickers', as_of=AT,
                raw_complete=True, source=copy.deepcopy(SOURCE),
                data=dict(fields=['cik', 'name', 'ticker', 'exchange'],
                          data=rows if rows is not None else [[1, 'Example One', 'ONE', 'NYSE']]))


def mapped(parsed, **kwargs):
    return identity_map(dict(schema_version=1, as_of=AT, records=parsed['records'],
                             allowed_exchanges=['NYSE', 'Nasdaq', 'TXSE'], **kwargs))


class SecIdentityTests(unittest.TestCase):
    def test_round_trip_preserves_original_rows_source_and_current_scope(self):
        d = document(); before = copy.deepcopy(d)
        p = ms.parse(d); m = mapped(p)
        self.assertEqual(d, before)
        self.assertEqual(p['records'][0]['payload']['raw_fields'], d['data']['data'][0])
        self.assertEqual(m['cik_symbol_mapping']['1']['ticker'], 'ONE')
        self.assertEqual(m['cik_symbol_mapping']['1']['source'], SOURCE)
        self.assertEqual(m['cik_symbol_mapping']['1']['available_at'], AT)
        self.assertFalse(m['historical_membership_verified'])
        self.assertFalse(m['complete_us_listed_universe_verified'])

    def test_plain_table_retained_without_inventing_exchange_or_listed_status(self):
        d = document(); d['data'] = {'0': dict(cik_str=1, ticker='ONE', title='Example One')}
        d['source']['url'] = 'https://www.sec.gov/files/company_tickers.json'
        p = ms.parse(d)
        self.assertTrue(p['records'][0]['eligible'])
        self.assertIsNone(p['records'][0]['payload']['exchange'])
        self.assertEqual(mapped(p)['resolved_ciks'], 0)

    def test_multiclass_never_selects_first_or_filters_into_unique_class(self):
        p = ms.parse(document([[1, 'Example', 'ONE', 'NYSE'], [1, 'Example', 'ONE.A', 'OTC']]))
        m = mapped(p)
        self.assertEqual(m['resolved_ciks'], 0)
        self.assertIn('MULTIPLE_OR_MISSING_SHARE_CLASS_SYMBOLS', m['unresolved_ciks'][0]['reasons'])

    def test_duplicates_and_shared_tickers_do_not_resolve(self):
        for rows in ([[1, 'One', 'ONE', 'NYSE']] * 2,
                     [[1, 'One', 'ONE', 'NYSE'], [2, 'Two', 'ONE', 'NYSE']]):
            with self.subTest(rows=rows):
                self.assertEqual(mapped(ms.parse(document(rows)))['resolved_ciks'], 0)

    def test_unknown_and_otc_exchanges_withheld_explicit_new_exchange_preserved(self):
        p = ms.parse(document([[1, 'One', 'ONE', None], [2, 'Two', 'TWO', 'OTC'],
                               [3, 'Three', 'THREE', 'TXSE']]))
        self.assertEqual(list(mapped(p)['cik_symbol_mapping']), ['3'])

    def test_partial_unknown_and_conflicting_transport_cannot_map(self):
        for variant in ('missing', False, True, 1):
            d = document()
            if variant == 'missing':
                del d['raw_complete']
            elif variant is True:
                d['source']['raw_complete'] = False
            else:
                d['raw_complete'] = variant
            with self.subTest(variant=variant):
                p = ms.parse(d)
                self.assertTrue(p['issues'])
                self.assertEqual(mapped(p)['resolved_ciks'], 0)

    def test_malformed_cik_type_and_rows_are_preserved_and_ineligible(self):
        for row in ([True, 'One', 'ONE', 'NYSE'], [1.0, 'One', 'ONE', 'NYSE'],
                    [1, 'One', '', 'NYSE'], [1, 'One']):
            with self.subTest(row=row):
                p = ms.parse(document([row]))
                self.assertEqual(len(p['records']), 1)
                self.assertFalse(p['records'][0]['eligible'])
                self.assertEqual(p['records'][0]['payload']['raw_fields'], row)

    def test_future_snapshots_and_mixed_vintages_do_not_map(self):
        p = ms.parse(document())
        d = dict(schema_version=1, as_of='2026-11-12T21:59:59+00:00', records=p['records'],
                 allowed_exchanges=['NYSE'])
        self.assertEqual(identity_map(d)['resolved_ciks'], 0)
        second = copy.deepcopy(p['records'][0]); second['id'] += '-other'
        second['source']['raw_sha256'] = 'b' * 64
        d.update(as_of=AT, records=p['records'] + [second])
        with self.assertRaisesRegex(ValueError, 'ONE_IDENTITY_SNAPSHOT'):
            identity_map(d)

    def test_missing_hash_and_nonidentity_records_are_rejected(self):
        p = ms.parse(document())
        del p['records'][0]['source']['raw_sha256']
        with self.assertRaisesRegex(ValueError, 'RAW_HASH'):
            mapped(p)
        p = ms.parse(document()); p['records'][0]['payload']['source_format'] = 'other'
        with self.assertRaisesRegex(ValueError, 'IDENTITY_RECORDS_ONLY'):
            mapped(p)

    def test_explicit_unique_exchange_scope_required(self):
        p = ms.parse(document())
        for values in (None, [], ['NYSE', 'NYSE'], [True]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                identity_map(dict(schema_version=1, as_of=AT, records=p['records'], allowed_exchanges=values))

    def test_data_text_disagreement_and_schema_errors_reject(self):
        d = document(); d['text'] = json.dumps(document([[2, 'Other', 'TWO', 'NYSE']])['data'])
        with self.assertRaisesRegex(ValueError, 'DATA_TEXT_CONFLICT'):
            ms.parse(d)
        for data in ({'fields': ['cik', 'cik'], 'data': []}, {'not-a-number': {}}, {}):
            d = document(); d['data'] = data
            with self.subTest(data=data), self.assertRaises(ValueError):
                ms.parse(d)

    def test_duplicate_raw_json_keys_reject_in_both_decoding_paths(self):
        raw = '{"fields":["cik","name","ticker","exchange"],"data":[[1,"One","ONE","NYSE"]],"data":[[1,"One","ONE.A","NYSE"]]}'
        for supplied_data in (None, json.loads(raw)):
            d = document(); d['text'] = raw
            if supplied_data is None:
                del d['data']
            else:
                d['data'] = supplied_data
            with self.subTest(supplied_data=supplied_data), self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
                ms.parse(d)
        d = document(); del d['data']
        d['text'] = '{"0":{"cik_str":1,"ticker":"ONE","ticker":"ONE.A","title":"One"}}'
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            ms.parse(d)

    def test_identity_mapping_moves_index_availability_forward(self):
        mapping = mapped(ms.parse(document()))['cik_symbol_mapping']
        d = dict(schema_version=1, adapter='sec_daily_index', as_of=AT, raw_complete=True,
            available_at='2026-11-12T21:00:00+00:00',
            source=dict(id='index', url='https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/master.20261112.idx',
                        retrieved_at='2026-11-12T21:00:00+00:00'), cik_symbol_mapping=mapping,
            text='Description: Daily Index of EDGAR Dissemination Feed\nLast Data Received: Nov 12, 2026\n'
                 'CIK|Company Name|Form Type|Date Filed|File Name\n----------\n'
                 '1|Example One|8-K|20261112|edgar/data/1/0000000001-26-000001.txt\n')
        p = ms.parse(d)
        self.assertEqual(p['records'][0]['available_at'], AT)
        self.assertTrue(p['records'][0]['eligible'])

    def test_exact_https_identity_families_and_narrow_ftp_provenance(self):
        for path in ('company_tickers.json', 'company_tickers_exchange.json'):
            self.assertEqual(ms.allowed_public_url('https://www.sec.gov/files/' + path), 'www.sec.gov')
        self.assertTrue(ms._url('ftp://ftp2.interactivebrokers.com/usa.txt'))
        for url in ('ftp://other.example/usa.txt', 'ftp://secret@ftp2.interactivebrokers.com/usa.txt',
                    'ftp://ftp2.interactivebrokers.com/other.txt'):
            self.assertFalse(ms._url(url))
        with self.assertRaisesRegex(ValueError, 'HTTPS only'):
            ms.allowed_public_url('ftp://ftp2.interactivebrokers.com/usa.txt')


if __name__ == '__main__':
    unittest.main()
