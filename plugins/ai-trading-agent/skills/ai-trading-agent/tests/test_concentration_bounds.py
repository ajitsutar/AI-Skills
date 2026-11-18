"""Exposure bounds do not survive arbitrary incomplete denominators."""
from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from concentration_bounds import ratio_evidence
from planning_comparison import source_alternatives


def evidence(n='39500', d='76600', nr='EXACT', dr='EXACT'):
    return ratio_evidence(n, d,
                          numerator_completeness='COMPLETE' if nr == 'EXACT' else 'INCOMPLETE',
                          denominator_completeness='COMPLETE' if dr == 'EXACT' else 'INCOMPLETE',
                          numerator_relation=nr, denominator_relation=dr,
                          assumptions=['Supplied relations are conditional assertions about the same complete account.'])


def source_fixture():
    return {'currency': 'USD', 'role': 'hypothetical_scenario',
            'source': {'employer': {'symbol': 'EMP'}, 'identities': {'EMP': {'issuer_id': 'issuer'}}},
            'alternatives': [{'id': 'held'}]}


def projection_fixture():
    return {'projection': {'position_values': [{'asset_id': 'EMP', 'market_value': '39500'}],
                           'net_equity': None, 'identified_assets': '76600', 'target_date': '2042-05-15',
                           'cash': '37100', 'tax_reserve': '0', 'other_assets_value': None,
                           'total_liabilities': '0'}}


class ConcentrationBoundsTests(unittest.TestCase):
    def test_exact_lower_and_upper_monotonicity(self):
        for nr, dr, expected in [('EXACT', 'EXACT', 'EXACT'),
                                 ('LOWER_BOUND', 'EXACT', 'LOWER_BOUND'),
                                 ('EXACT', 'UPPER_BOUND', 'LOWER_BOUND'),
                                 ('LOWER_BOUND', 'UPPER_BOUND', 'LOWER_BOUND'),
                                 ('UPPER_BOUND', 'EXACT', 'UPPER_BOUND'),
                                 ('EXACT', 'LOWER_BOUND', 'UPPER_BOUND'),
                                 ('UPPER_BOUND', 'LOWER_BOUND', 'UPPER_BOUND')]:
            with self.subTest(numerator=nr, denominator=dr):
                result = evidence(nr=nr, dr=dr)
                self.assertEqual(result['bound_status'], expected)
                self.assertFalse(result['assumptions_externally_verified'])
                self.assertTrue(result['assumptions'])

    def test_both_incomplete_same_direction_supports_neither_ratio_bound(self):
        for nr, dr in [('LOWER_BOUND', 'LOWER_BOUND'), ('UPPER_BOUND', 'UPPER_BOUND'),
                       ('UNKNOWN', 'EXACT'), ('EXACT', 'UNKNOWN'), ('UNKNOWN', 'UNKNOWN')]:
            result = evidence(nr=nr, dr=dr)
            self.assertEqual(result['bound_status'], 'UNKNOWN')
            self.assertEqual(result['value_role'], 'SENSITIVITY_ONLY')
        original = evidence(nr='LOWER_BOUND', dr='LOWER_BOUND')['ratio']
        # Two portfolios satisfying the same pair of lower operand bounds
        # move the full ratio to opposite sides of the observed ratio.
        self.assertLess(Decimal('39500') / Decimal('86600'), original)
        self.assertGreater(Decimal('49500') / Decimal('86600'), original)

    def test_c060_missing_non_employer_assets_is_not_lower_concentration(self):
        doc, receipt = source_fixture(), projection_fixture()
        original = deepcopy(doc)
        with patch('portfolio_projection.source_projection', return_value=receipt):
            result = source_alternatives(doc)['alternatives'][0]
        sensitivity = result['identified_assets_employer_concentration_evidence']
        self.assertEqual(sensitivity['bound_status'], 'UNKNOWN')
        self.assertEqual(sensitivity['value_role'], 'SENSITIVITY_ONLY')
        self.assertEqual(result['employer_exposure_evidence']['bound_status'], 'LOWER_BOUND')
        self.assertEqual(result['employer_concentration_evidence']['bound_status'], 'UNKNOWN')
        self.assertIsNone(result['known_employer_fraction'])
        self.assertEqual(doc, original)
        with localcontext() as ctx:
            ctx.prec = 50
            observed_percent = Decimal(sensitivity['ratio']) * 100
            complete_percent = Decimal('39500') / Decimal('86600') * 100
        self.assertEqual(observed_percent.quantize(Decimal('.0001')), Decimal('51.5666'))
        self.assertEqual(complete_percent.quantize(Decimal('.0001')), Decimal('45.6120'))
        self.assertLess(complete_percent, observed_percent)

    def test_complete_projection_exact_ratio_and_incomplete_overlap_lower_ratio(self):
        doc, receipt = source_fixture(), projection_fixture()
        receipt['projection'].update(net_equity='76600', other_assets_value='0')
        with patch('portfolio_projection.source_projection', return_value=receipt):
            row = source_alternatives(doc)['alternatives'][0]
        self.assertEqual(row['employer_concentration_evidence']['bound_status'], 'EXACT')
        self.assertEqual(row['identified_assets_employer_concentration_evidence']['bound_status'], 'EXACT')
        receipt['projection']['position_values'].append({'asset_id': 'UNKNOWN', 'market_value': '1000'})
        with patch('portfolio_projection.source_projection', return_value=receipt):
            row = source_alternatives(doc)['alternatives'][0]
        self.assertEqual(row['employer_concentration_evidence']['bound_status'], 'LOWER_BOUND')
        self.assertIsNone(row['complete_employer_exposure'])

    def test_identified_assets_with_liabilities_is_not_complete_net_equity(self):
        receipt = projection_fixture()
        receipt['projection'].update(net_equity='71600', other_assets_value='0', total_liabilities='5000')
        with patch('portfolio_projection.source_projection', return_value=receipt):
            row = source_alternatives(source_fixture())['alternatives'][0]
        self.assertEqual(row['employer_concentration_evidence']['bound_status'], 'EXACT')
        self.assertEqual(row['identified_assets_employer_concentration_evidence']['bound_status'], 'UNKNOWN')

    def test_declared_full_fund_coverage_without_full_weights_is_incomplete(self):
        doc, receipt = source_fixture(), projection_fixture()
        doc['source']['funds'] = [{'symbol': 'FUND', 'holdings_coverage': '1',
                                 'holdings': [{'symbol': 'EMP', 'weight': '.5'}]}]
        receipt['projection'].update(net_equity='76600', other_assets_value='0')
        receipt['projection']['position_values'] = [{'asset_id': 'FUND', 'market_value': '1000'}]
        with patch('portfolio_projection.source_projection', return_value=receipt):
            row = source_alternatives(doc)['alternatives'][0]
        self.assertEqual(row['known_employer_exposure'], '500.0')
        self.assertEqual(row['employer_exposure_evidence']['bound_status'], 'LOWER_BOUND')
        self.assertIn('FUND', row['unresolved_employer_overlap'])
        for invalid_weight in ['-.1', '1.1']:
            doc['source']['funds'][0]['holdings'][0]['weight'] = invalid_weight
            with patch('portfolio_projection.source_projection', return_value=receipt):
                with self.assertRaises(ValueError):
                    source_alternatives(doc)

    def test_nonpositive_projection_equity_is_unavailable_not_a_ratio(self):
        for value in ['0', '-5']:
            receipt = projection_fixture()
            receipt['projection']['net_equity'] = value
            with patch('portfolio_projection.source_projection', return_value=receipt):
                row = source_alternatives(source_fixture())['alternatives'][0]
            self.assertIsNone(row['employer_concentration_evidence']['ratio'])
            self.assertEqual(row['employer_concentration_evidence']['denominator_unavailable_reason'], 'NONPOSITIVE')

    def test_nested_fund_never_treated_as_complete_sponsor_issuer_exposure(self):
        for declared_inner_table in [True, False]:
            for kind in ['fund', 'ETF']:
                doc, receipt = source_fixture(), projection_fixture()
                doc['source']['identities']['INNER'] = {'issuer_id': 'fund-manager', 'kind': kind}
                doc['source']['funds'] = [{'symbol': 'OUTER', 'holdings_coverage': '1',
                                         'holdings': [{'symbol': 'INNER', 'weight': '1'}]}]
                if declared_inner_table:
                    doc['source']['funds'].append({'symbol': 'INNER', 'holdings_coverage': '1',
                                                  'holdings': [{'symbol': 'EMP', 'weight': '1'}]})
                receipt['projection'].update(net_equity='1000', identified_assets='1000', other_assets_value='0')
                receipt['projection']['position_values'] = [{'asset_id': 'OUTER', 'market_value': '1000'}]
                with patch('portfolio_projection.source_projection', return_value=receipt):
                    row = source_alternatives(doc)['alternatives'][0]
                self.assertEqual(row['known_employer_exposure'], '0')
                self.assertIsNone(row['complete_employer_exposure'])
                self.assertEqual(row['employer_exposure_evidence']['bound_status'], 'LOWER_BOUND')
                self.assertEqual(row['employer_concentration_evidence']['bound_status'], 'LOWER_BOUND')
                self.assertIn('INNER', row['unresolved_employer_overlap'])

    def test_fund_without_holdings_table_is_not_its_sponsor_equity(self):
        for sponsor in ['issuer', 'other-issuer']:
            doc, receipt = source_fixture(), projection_fixture()
            doc['source']['identities']['OPAQUE'] = {'issuer_id': sponsor, 'kind': 'fund'}
            receipt['projection'].update(net_equity='1000', identified_assets='1000', other_assets_value='0')
            receipt['projection']['position_values'] = [{'asset_id': 'OPAQUE', 'market_value': '1000'}]
            with patch('portfolio_projection.source_projection', return_value=receipt):
                row = source_alternatives(doc)['alternatives'][0]
            self.assertEqual(row['known_employer_exposure'], '0')
            self.assertIsNone(row['complete_employer_exposure'])
            self.assertIn('OPAQUE', row['unresolved_employer_overlap'])

    def test_ratio_metadata_types_are_validated_before_membership(self):
        for field in ['numerator_completeness', 'denominator_completeness', 'numerator_relation', 'denominator_relation']:
            for invalid in [[], {}, ['EXACT'], {'kind': 'COMPLETE'}, None, True, 1]:
                args = {'numerator_completeness': 'COMPLETE', 'denominator_completeness': 'COMPLETE'}
                args[field] = invalid
                with self.subTest(field=field, value=invalid), self.assertRaises(ValueError):
                    ratio_evidence('1', '2', **args)

    def test_missing_operands_explicit_relations_and_validation(self):
        result = evidence(n=None, nr='UNKNOWN')
        self.assertEqual(result['bound_status'], 'UNKNOWN')
        self.assertEqual(result['value_role'], 'UNAVAILABLE')
        for n, d in [('NaN', '1'), ('1', 'Infinity'), (True, '1'), ('-1', '1'), ('1', '0'), ('1', '-1')]:
            with self.subTest(n=n, d=d), self.assertRaises(ValueError):
                evidence(n, d)
        with self.assertRaisesRegex(ValueError, 'BOUND_ASSUMPTIONS_REQUIRED'):
            ratio_evidence('1', '2', numerator_completeness='INCOMPLETE', denominator_completeness='COMPLETE',
                           numerator_relation='LOWER_BOUND')
        with self.assertRaisesRegex(ValueError, 'EXACT_REQUIRES_COMPLETE'):
            ratio_evidence('1', '2', numerator_completeness='INCOMPLETE', denominator_completeness='COMPLETE',
                           numerator_relation='EXACT')
        with self.assertRaisesRegex(ValueError, 'COMPLETE_RELATION'):
            ratio_evidence('1', '2', numerator_completeness='COMPLETE', denominator_completeness='COMPLETE',
                           numerator_relation='LOWER_BOUND')

    def test_net_equity_ratio_can_exceed_one_and_retains_decimal_precision(self):
        self.assertEqual(evidence('150', '100')['ratio'], Decimal('1.5'))
        self.assertEqual(evidence('0', '100')['ratio'], Decimal('0'))
        numerator = '100000000000000000000000000000000001'
        with localcontext() as ctx:
            ctx.prec = 5
            result = evidence(numerator, '1')
        self.assertEqual(result['ratio'], Decimal(numerator))


if __name__ == '__main__':
    unittest.main()
