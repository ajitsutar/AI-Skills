"""Independent adverse inputs for ledger units and analyst table semantics."""
import unittest
from test_holdings_ledger import base, event, mark, replay, T0, T1
from test_analyst_adapter import request, extract


class IndependentReviewTests(unittest.TestCase):
    def test_conflicting_opening_mark_currency_is_rejected(self):
        d = base(); d['opening']['marks'][0]['currency'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'MARK_CURRENCY_MISMATCH'):
            replay(d)

    def test_ambiguous_double_target_not_inferred_direction(self):
        d = request('Analyst | Firm | Target | Date\nA | B | $100 $90 | 2026-10-30')
        self.assertEqual(extract(d)['records'], [])

    def test_report_date_not_after_source_evidence(self):
        d = request('Analyst | Firm | Target | Date\nA | B | $90 | 2026-11-01')
        d['as_of'] = '2026-11-03T00:00:00Z'
        self.assertEqual(extract(d)['records'], [])

    def test_split_cannot_reuse_pre_action_price_units(self):
        d = base()
        d['events'] = [event('split', security_id='P', factor='2'),
                       dict(event('mark'), **mark('P', 100, T0))]
        # The mark is supplied after the split event but describes an old quote.
        d['events'][1]['at'] = T1
        try:
            result = replay(d)
        except ValueError:
            return
        self.assertIsNone(result['final']['gross_nav'])

    def test_spinoff_old_parent_mark_cannot_reenter_nav(self):
        d = base()
        d['events'] = [event('spinoff', security_id='P', child_security_id='C',
                             child_ratio='.5', child_basis_fraction='.2', tax_amount='0'),
                       dict(event('mark'), **mark('P', 100, T0)),
                       dict(event('mark'), id='child-mark', **mark('C', 20, T1))]
        try:
            result = replay(d)
        except ValueError:
            return
        self.assertIsNone(result['final']['gross_nav'])


if __name__ == '__main__':
    unittest.main()
