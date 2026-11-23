import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from forward_reconciliation import assess


class ForwardReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.data = {'decisions': self.pair(['hold', 'rebalance']),
                     'orders': self.pair([['rebalance', 'part'], ['rebalance', 'miss']]),
                     'fills': self.pair([['part', 'fill-a'], ['part', 'fill-b']]),
                     'unresolved_exceptions': []}

    @staticmethod
    def pair(rows):
        return {'reference': rows, 'accounted': copy.deepcopy(rows)}

    def test_documented_miss_and_partial_fills_preserve_distinct_order_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / 'registers.json'
            path.write_text(json.dumps(self.data), encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT / 'scripts/forward_reconciliation.py'), str(path)]
            result = json.loads(subprocess.run(command, check=True, capture_output=True).stdout)
        self.assertEqual(result['status'], 'LINKS_RECONCILED')
        self.assertEqual(result['matched_fill_parent_count'], 1)
        self.assertEqual(result['reference_counts'], {'decisions': 2, 'orders': 2, 'fills': 2})

    def test_unfilled_intent_missing_journal_and_orphan_never_disappear_in_fill_denominator(self):
        for group, side, mutation, reason in [
            ('decisions', 'accounted', ['rebalance'], 'decisions.missing'),
            ('orders', 'accounted', [['rebalance', 'part']], 'orders.missing'),
            ('fills', 'accounted', [['part', 'fill-a'], ['miss', 'fill-b']], 'fills.missing'),
            ('fills', 'accounted', [['part', 'fill-a'], ['absent', 'fill-b']], 'fills.accounted.orphan_links'),
            ('orders', 'reference', [['rebalance', 'part'], ['rebalance', 'part']], 'orders.reference.duplicate_ids'),
        ]:
            with self.subTest(reason=reason):
                data = copy.deepcopy(self.data)
                data[group][side] = mutation
                result = assess(data)
                self.assertEqual(result['status'], 'HOLD_FOR_RECONCILIATION')
                self.assertGreater(result['differences'][reason], 0)
        self.data['fills'] = self.pair([[None, 'unidentified']])
        self.assertEqual(assess(self.data)['status'], 'HOLD_FOR_RECONCILIATION')

    def test_held_and_empty_registers_and_unknown_controls(self):
        self.data['orders'] = self.pair([])
        self.data['fills'] = self.pair([])
        result = assess(self.data)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertEqual(result['matched_fill_parent_count'], 0)
        self.data['decisions']['accounted'] = None
        self.data['unresolved_exceptions'] = None
        result = assess(self.data)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertCountEqual(result['unavailable_registers'], ['decisions.accounted', 'unresolved_exceptions'])
        self.data['unresolved_exceptions'] = ['unexplained cash balance']
        self.assertEqual(assess(self.data)['status'], 'HOLD_FOR_RECONCILIATION')

    def test_same_misparenting_on_both_sides_is_still_an_exception(self):
        self.data['orders'] = self.pair([['unknown-decision', 'part'], ['rebalance', 'miss']])
        self.assertEqual(assess(self.data)['differences']['orders.reference.orphan_links'], 1)
        self.data['orders'] = self.pair([['hold', 'part'], ['rebalance', 'part']])
        self.assertEqual(assess(self.data)['differences']['orders.reference.duplicate_ids'], 1)
