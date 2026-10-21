"""Issuer identity counts describe supplied exposures, never diversification quality."""
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portfolio_decision as decision
import quant_workbench as workbench
import report_facts


def row(name, issuer=None, amount='10', kind='equity', **extra):
    return dict(id=name, issuer_id=issuer, notional=amount, notional_basis='gross_notional',
                instrument_type=kind, **extra)


def summary(rows):
    return decision.allocation_context({'currency':'USD', 'role':'supplied_observation',
        'denominator':{'amount':'100', 'basis':'supplied account'}, 'rows':rows})['issuer_identity_summary']


class IssuerSummaryTests(unittest.TestCase):
    def test_report_projects_counts_with_count_units_and_unknown_total(self):
        document={'currency':'USD','role':'supplied_observation',
                  'denominator':{'amount':'100','basis':'supplied account'},
                  'rows':[row('known','issuer-a'),row('unknown')]}
        bundle=workbench.freeze({'schema_version':1,
            'contract':{'prompt':'Describe supplied identity coverage','purpose':'local test',
                        'base_currency':'USD','horizon_id':'P1Y','as_of':'2027-05-04T13:00:00Z'},
            'jobs':[{'id':'context','operation':'planning.allocation_context',
                     'inputs':{'document':document}}]})
        facts=report_facts.project(json.dumps(bundle).encode(),'quant')['facts']
        for field, expected in [('distinct_known_issuer_count',1),('total_distinct_issuer_count',None)]:
            fact=next(f for f in facts if f['source']['pointer'].endswith('/issuer_identity_summary/'+field))
            self.assertEqual(fact['value'],expected)
            self.assertEqual(fact['unit'],'count')

    def test_duplicate_classes_cash_and_zero_exposures(self):
        got=summary([row('class-a','issuer-a'),row('class-b','issuer-a'),row('second','issuer-b'),
                     row('cash','cash-label',kind='cash'),row('zero','issuer-zero',amount='0')])
        self.assertEqual(got['distinct_known_issuer_ids'],['issuer-a','issuer-b'])
        self.assertEqual(got['distinct_known_issuer_count'],2)
        self.assertEqual(got['total_distinct_issuer_count'],2)
        self.assertEqual(got['count_status'],'COMPLETE_WITHIN_SUPPLIED_ROWS')
        self.assertFalse(got['correlation_established'])
        self.assertFalse(got['risk_or_diversification_ranking_established'])

    def test_unknown_labels_and_unquantified_rows_are_lower_bounds(self):
        for missing in (row('missing'),row('unquantified','unmeasured',amount=None),
                        row('opaque','sponsor',kind='fund')):
            with self.subTest(missing=missing):
                got=summary([row('known','issuer-a'),missing])
                self.assertEqual(got['distinct_known_issuer_count'],1)
                self.assertIsNone(got['total_distinct_issuer_count'])
                self.assertEqual(got['count_status'],'KNOWN_LOWER_BOUND_ONLY')

    def test_nested_fund_merges_classes_and_does_not_count_wrapper(self):
        fund=row('fund','sponsor',kind='fund',lookthrough={'constituents':[
            {'id':'one','weight':'.3','instrument_type':'equity','issuer_id':'issuer-a'},
            {'id':'two','weight':'.2','instrument_type':'equity','issuer_id':'issuer-a'},
            {'id':'nested','weight':'.5','instrument_type':'fund','lookthrough':{'constituents':[
                {'id':'leaf','weight':'.5','instrument_type':'equity','issuer_id':'issuer-b'},
                {'id':'cash','weight':'.5','instrument_type':'cash','issuer_id':'cash-label'}]}}]})
        got=summary([fund])
        self.assertEqual(got['distinct_known_issuer_ids'],['issuer-a','issuer-b'])
        self.assertEqual(got['total_distinct_issuer_count'],2)
        fund['lookthrough']['constituents'].append({'id':'unknown-weight','weight':None,
            'instrument_type':'equity','issuer_id':'unknown-weight-issuer'})
        got=summary([fund])
        self.assertIsNone(got['total_distinct_issuer_count'])
        self.assertEqual(got['distinct_known_issuer_count'],2)
        self.assertTrue(got['unknown_weight_fund_paths'])

    def test_cash_only_and_zero_unknown_exposure_add_no_issuer(self):
        got=summary([row('cash','cash-label',kind='cash'),row('zero',amount='0')])
        self.assertEqual(got['total_distinct_issuer_count'],0)
        self.assertEqual(got['distinct_known_issuer_ids'],[])


if __name__=='__main__': unittest.main()
