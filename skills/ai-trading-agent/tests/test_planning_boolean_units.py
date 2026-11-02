"""Boolean metadata must not masquerade as monetary/numeric measurements."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import planning_roles


def document(value, unit, currency='USD'):
    return {'currency': currency, 'role': 'hypothetical_scenario', 'records': [
        {'id': 'flag', 'value': value, 'unit': unit,
         'source_role': 'user_assumption', 'semantic_role': 'scenario'}]}


class BooleanUnitsTests(unittest.TestCase):
    def test_true_and_false_reject_currency_and_numeric_units_without_mutation(self):
        for value in (False, True):
            for unit in ('USD', ' eur ', 'shares', 'percent', 'bps', 'count'):
                with self.subTest(value=value, unit=unit):
                    source = document(value, unit)
                    before = deepcopy(source)
                    with self.assertRaisesRegex(ValueError, 'BOOLEAN_VALUE_UNIT_MISMATCH:flag'):
                        planning_roles.input_roles(source)
                    self.assertEqual(source, before)

    def test_declared_currency_also_rejected_without_guessing_other_custom_units(self):
        with self.assertRaisesRegex(ValueError, 'BOOLEAN_VALUE_UNIT_MISMATCH'):
            planning_roles.input_roles(document(True, 'XYZ', currency='XYZ'))
        output = planning_roles.input_roles(document(True, 'XYZ'))
        self.assertIs(output['records'][0]['value'], True)
        self.assertEqual(output['records'][0]['unit'], 'XYZ')

    def test_boolean_unitless_and_unknown_units_preserved_exactly(self):
        for value in (False, True):
            for unit in ('boolean', 'bool', 'unitless', 'dimensionless', None, 'custom_state'):
                with self.subTest(value=value, unit=unit):
                    source = document(value, unit)
                    output = planning_roles.input_roles(source)
                    self.assertIs(output['records'][0]['value'], value)
                    self.assertEqual(output['records'][0]['unit'], unit)
                    self.assertEqual(output['retained_input'], source)

    def test_numeric_currency_and_missing_values_unchanged(self):
        for value in (0, 1, 17.25, '17.25', None):
            output = planning_roles.input_roles(document(value, 'USD'))
            self.assertEqual(output['records'][0]['value'], value)
            self.assertEqual(type(output['records'][0]['value']), type(value))

    def test_source_roles_and_comparison_records_share_validation(self):
        with self.assertRaisesRegex(ValueError, 'BOOLEAN_VALUE_UNIT_MISMATCH'):
            planning_roles.source_roles({'currency':'USD', 'role':'hypothetical_scenario',
                'source':{'currency':'USD', 'capital':False}, 'source_ref':'source.json#',
                'source_role':'user_assumption'})
        record = document(True, 'USD')['records'][0]
        with self.assertRaisesRegex(ValueError, 'BOOLEAN_VALUE_UNIT_MISMATCH'):
            planning_roles.reference_comparison({'currency':'USD', 'role':'hypothetical_scenario',
                'sleeves':[{'id':'sleeve', 'allocation_record':record}]})


if __name__ == '__main__':
    unittest.main()
