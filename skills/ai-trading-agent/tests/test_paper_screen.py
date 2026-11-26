"""Synthetic regressions for paper portfolio selection and rebalance screens."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyst_revisions import estimate_revision_signal, recommendation_gate
from analyst_sources import provider_consensus_batch
from paper_screen import calendar_completeness, low_es_screen


CLOCK = '2034-11-10T21:00:00Z'
OBS = {'observed_at': '2034-11-10T20:00:00Z', 'source_ref': 'original/observation'}
SPAN = {'from': '2034-11-12', 'through': '2034-11-25'}


def calendar(vendor, confirmation=None):
    row = {'symbol': 'EXM', 'vendor': {'upstream': 'A', **OBS, **vendor}}
    if confirmation is not None:
        row['confirmation'] = {'upstream': 'issuer', **OBS, **confirmation}
    return calendar_completeness({'as_of': CLOCK, 'window_start': SPAN['from'],
                                  'window_end': SPAN['through'], 'candidates': [row]})


def book(**values):
    return {'period': '0m', 'strongBuy': 0, 'buy': 2, 'hold': 1, 'sell': 0, 'strongSell': 0, **values}


class PaperScreenTests(unittest.TestCase):
    def test_calendar_empty_independent_coverage_and_vintages(self):
        vendor = {'past_dates': [], 'vendor_calendar': {'Earnings Date': '[]'}, 'coverage': SPAN}
        other = {'coverage': SPAN, 'window_reviewed_clear': True}
        self.assertEqual(calendar(vendor)['blocking_symbols'], ['EXM'])
        self.assertEqual(calendar(vendor, other)['status'], 'PASS')
        for changes in ({'upstream': ' a '}, {'observed_at': '2034-11-11T10:00:00Z'},
                        {'window_reviewed_clear': False}, {'coverage': {'from': SPAN['from'], 'through': SPAN['from']}}):
            self.assertEqual(calendar(vendor, {**other, **changes})['status'], 'BLOCKED')
        for dates in ([SPAN['from']], ['2034-11'], ['2034-11-11', '2034-11-26']):
            self.assertEqual(calendar({**vendor, 'next_dates': dates}, other)['status'], 'BLOCKED')

    def test_calendar_covered_names_and_history_without_coverage(self):
        vendor = {'past_dates': ['2034-08-01']}
        self.assertEqual(calendar(vendor)['status'], 'BLOCKED')
        self.assertEqual(calendar({**vendor, 'next_dates': ['2035-01-05']})['status'], 'PASS')
        self.assertEqual(calendar({**vendor, 'coverage': SPAN})['status'], 'PASS')
        early = {**vendor, 'observed_at':'2034-01-01T20:00:00Z', 'next_dates':['2035-01-05']}
        self.assertEqual(calendar(early)['status'], 'BLOCKED')
        self.assertEqual(calendar({'next_dates': ['2035-01-05']})['status'], 'BLOCKED')

    def test_nonvacuous_named_period_and_no_dimension_guess(self):
        sell_only = book(buy='0', hold='0', sell='7', strongSell='4')
        favorable = book(buy='5', strongBuy='3', hold='6')
        self.assertEqual(recommendation_gate([sell_only])['status'], 'FAIL')
        self.assertEqual(recommendation_gate([book(period='-1m'), favorable])['favorable'], 8)
        for rows in ([favorable, favorable], [book(hold=None)], [book(sell=True)], [book(buy='-1')]):
            self.assertEqual(recommendation_gate(rows)['status'], 'UNRESOLVED')
        trend = {'period': '0y', 'currency': 'USD', 'current': '1.1', '30daysAgo': '1', '90daysAgo': '-1.2'}
        row = {'symbol': 'EXM', 'issuer_id': 'EXM-common', 'provider': 'Feed', **OBS,
               'recommendations': [sell_only], 'period': '0y', 'currency': 'USD',
               'eps_basis': 'GAAP', 'fiscal_period_end': '2034-12-31', 'eps_trend': [trend]}
        def run(**changes):
            return estimate_revision_signal({'as_of': CLOCK, 'candidates': [{**row, **changes}]})['candidates'][0]
        result = run()
        self.assertEqual((result['revision_status'], result['recommendation']['status']), ('PASS', 'FAIL'))
        self.assertEqual(result['deltas']['90daysAgo']['delta'], '2.3')
        self.assertIsNone(result['deltas']['90daysAgo']['percent_change'])
        self.assertEqual(run(eps_trend=[{**trend, '30daysAgo': '1.1'}])['revision_status'], 'FAIL')
        for changes in ({'period': '+1y'}, {'eps_trend': [trend,trend]}, {'observed_at':'2034-11-12T00:00:00Z'},
                        {'eps_trend': [{**trend, 'current':'NaN'}]}, {'eps_trend': [{**trend, 'currency':'EUR'}]}):
            self.assertEqual(run(**changes)['revision_status'], 'UNRESOLVED')
        incomplete = run(fiscal_period_end=None)
        self.assertEqual(incomplete['revision_status'], 'UNRESOLVED')
        self.assertTrue(incomplete['both_deltas_positive'])

    def test_low_es_guards_precede_beta_and_rank(self):
        end = date.fromisoformat(CLOCK[:10])
        sessions = sorted((end - timedelta(days=i)).isoformat() for i in range(100)
                          if (end - timedelta(days=i)).weekday() < 5)[-64:]
        bars = [{'date': d, 'close': 99+i/3, 'volume': 10000} for i,d in enumerate(sessions)]
        clear = {**OBS, 'status': 'no_indicator'}
        normal = {**OBS, 'observed_at':CLOCK, 'bars': bars, 'issuer_profile': clear, 'deal_news': clear,
                  'beta': 0.4, 'beta_ref': 'benchmark fit', 'price_basis': 'adjusted USD'}
        pinned = [{**b, 'close': 100+(i%2)*.1} for i,b in enumerate(bars)]
        rows = [dict(normal,symbol='OK'), dict(normal,symbol='PIN',bars=pinned,beta=0),
                dict(normal,symbol='DEAL',deal_news={**clear, 'status': 'tender_offer'}),
                dict(normal,symbol='SHELL',issuer_profile={**clear,'industry':'Shell Companies'}),
                dict(normal,symbol='MISSING',bars=bars[:-1]),
                dict(normal,symbol='CARRY',bars=[*bars[:-1],{**bars[-1], 'carried':True}]),
                dict(normal,symbol='HIGHEST',beta=.8),
                dict(normal,symbol='STALE',observed_at='2034-10-01T00:00:00Z'),
                dict(normal,symbol='UNKNOWN',observed_at=None)]
        request = {'sessions':sessions, 'calendar_ref':'calendar', 'as_of':CLOCK,'max_beta':.8,'candidates':rows}
        out = low_es_screen(request)
        self.assertEqual(out['ranked_symbols'], ['OK'])
        self.assertIn('NARROW_63_SESSION_CLOSE_RANGE',out['candidates'][1]['reasons'])
        for row in out['candidates'][1:]:
            self.assertIsNone(row['loss_expected_shortfall'])
        for row in out['candidates'][-2:]:
            self.assertIn('PRICE_CAPTURE_MISSING_OR_OUTSIDE_SESSION_WINDOW', row['reasons'])
        before_close = sessions[-1]+'T18:10:00Z'
        with self.assertRaisesRegex(ValueError, 'TARGET_SESSION_NOT_CLOSED_AT_DECISION'):
            low_es_screen({**request, 'as_of':before_close})
        early_news = {**clear,'observed_at':before_close}
        early = {**rows[0], 'observed_at':before_close, 'deal_news':early_news, 'issuer_profile':early_news}
        out = low_es_screen({**request, 'as_of':before_close, 'session_close_at':sessions[-1]+'T18:00:00Z',
                             'candidates':[early]})
        self.assertEqual(out['ranked_symbols'], ['OK'])

    def test_provider_grouping_same_record_pin_and_missing_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / 'source.json'
            manifest = root / 'manifest.json'
            provider = {'provider':'A', 'issuer':'EXM', 'source':{'observed_at':OBS['observed_at'],
                        'published_at':'2034-11-09T09:00:00Z', 'url':'https://example.test/report'},
                        'as_of':'2034-11-08', 'recommendations':book()}
            target = {**provider, 'provider':'B', 'mean':15, 'minimum':14, 'maximum':17, 'target_count':7,
                      'currency':'USD', 'price_basis':'per share', 'target_horizon':'12 months'}
            partial = {**target, 'provider': 'C', 'target_count': None, 'target_horizon': None}
            rows = [provider,target,partial,{**target,'issuer':'OTHER','as_of':'2034-11-11'}]
            original.write_text(json.dumps({'provider_consensus':rows}), encoding='utf8')
            source_hash = hashlib.sha256(original.read_bytes()).hexdigest()
            manifest.write_text(json.dumps({'schema_version':1, 'sources':[
                {'id':'s', 'path':original.name,'sha256':source_hash,'format':'json'}]}),encoding='utf8')
            pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
            request = {'issuers':['EXM','OTHER','ABSENT'], 'as_of':CLOCK}
            output = provider_consensus_batch(request,manifest,pin,root)
            reports = output['by_issuer']['EXM']
            self.assertEqual([r['provider'] for r in reports], ['A','B','C'])
            self.assertEqual([r['source_ref']['pointer'] for r in reports],
                             ['/provider_consensus/0','/provider_consensus/1','/provider_consensus/2'])
            self.assertEqual(reports[2]['unknown_target_dimensions'], ['target_horizon', 'constituent_count'])
            self.assertEqual(reports[0]['source']['sha256'], source_hash)
            self.assertEqual(reports[0]['methodology_status'], 'UNKNOWN')
            self.assertEqual(reports[1]['mean'],15)
            self.assertEqual(output['missing_issuers'], ['OTHER','ABSENT'])
            self.assertFalse(output['independent_consensus_computed'])
            self.assertIsNone(output['return_forecast'])
            original.write_text('{}',encoding='utf8')
            with self.assertRaises(ValueError):
                provider_consensus_batch(request,manifest,pin,root)


if __name__ == '__main__':
    unittest.main()
