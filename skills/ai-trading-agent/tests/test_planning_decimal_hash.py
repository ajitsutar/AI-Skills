"""Calculation hashes preserve finite decimal values without changing byte pins."""
import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_alignment import finish
from quant_common import digest


class PlanningDecimalHashTests(unittest.TestCase):
    def test_ordinary_json_hash_is_unchanged(self):
        doc = {'currency': 'EUR', 'role': 'user_assumption', 'values': [1, 1.25, '1.25', True, None]}
        self.assertEqual(finish(doc, 'generic')['input_sha256'], digest(doc))

    def test_nested_decimal_hash_uses_exact_decimal_strings_without_input_mutation(self):
        doc = {'currency': 'EUR', 'role': 'user_assumption',
               'values': [Decimal('0.12345678901234567890123456789'), {'value': Decimal('-2.500')}]}
        original = copy.deepcopy(doc)
        expected = {'currency': 'EUR', 'role': 'user_assumption',
                    'values': ['0.12345678901234567890123456789', {'value': '-2.500'}]}
        result = finish(doc, 'generic', computed=Decimal('0.12345678901234567890123456789'))
        self.assertEqual(result['input_sha256'], digest(expected))
        self.assertEqual(result['computed'], expected['values'][0])
        self.assertEqual(doc, original)
        self.assertNotEqual(result['input_sha256'], digest({**expected, 'values': ['0.12345678901234568', {'value': '-2.500'}]}))

    def test_nonfinite_decimals_rejected_in_input_and_output(self):
        base = {'currency': 'EUR', 'role': 'user_assumption'}
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'FINITE_DECIMAL_REQUIRED'):
                finish({**base, 'extra': [Decimal(value)]}, 'generic')
            with self.subTest(output=value), self.assertRaisesRegex(ValueError, 'FINITE_DECIMAL_REQUIRED'):
                finish(base, 'generic', computed=Decimal(value))

    def test_unrelated_non_json_types_are_not_stringified(self):
        with self.assertRaises(TypeError):
            finish({'currency': 'EUR', 'role': 'user_assumption', 'value': {1, 2}}, 'generic')


if __name__ == '__main__':
    unittest.main()
