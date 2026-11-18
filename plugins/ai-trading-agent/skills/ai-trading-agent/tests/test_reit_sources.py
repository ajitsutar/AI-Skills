"""Original-record associations, not matching caller metadata, gate comparisons."""
import copy
import hashlib
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import financial_alignment as financial
import reit_sources as subject
import quant_workbench as workbench
from test_reit_provenance import document as old_document, bound


def fixture():
    doc = old_document()
    doc.pop('recurring_capex_mapping')
    for group in ('ffo_bridge', 'affo_bridge', 'cfo', 'gross_capex', 'distributions'):
        doc[group]['basis']['amount_unit'] = 'EUR'
    records, bindings = [], []
    for operand in subject.operands(doc):
        index = len(records)
        records.append({'measure_role': operand['role'], 'value': operand['amount'],
            'entity_id': 'SYNTHETIC-REIT', 'currency': 'EUR', 'unit_scale': 1,
            'period_start': '2028-01-01', 'period_end': '2028-12-31', 'holder_basis': 'common equity'})
        bindings.append({'target_pointer': operand['target_pointer'], 'schema': 'typed_measure_v1',
                         'source_id': 'original', 'record_pointer': '/records/' + str(index), 'sign': 1})
    return {'document': doc, 'bindings': bindings}, {'records': records}


class ReitSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_bound(self, request=None, original=None):
        default_request, default_original = fixture()
        request = default_request if request is None else request
        original = default_original if original is None else original
        raw = json.dumps(original).encode()
        (self.root / 'original.json').write_bytes(raw)
        manifest = {'schema_version': 1, 'sources': [{'id': 'original', 'path': 'original.json',
            'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()}]}
        manifest_raw = json.dumps(manifest).encode()
        path = self.root / 'manifest.json'; path.write_bytes(manifest_raw)
        return subject.analyze(request, path, hashlib.sha256(manifest_raw).hexdigest())

    def test_default_direct_and_workbench_keep_values_conditional(self):
        doc = old_document()
        direct = financial.reit_reconciliation(doc)
        from test_reit_reconciliation import example
        request = example()
        request['jobs'][0]['inputs']['document'] = doc
        public = workbench.run(request)['results'][0]['result']
        for result in (direct, public):
            self.assertEqual(result['declared_calculation_status'], 'COMPUTED')
            self.assertEqual(result['status'], 'PARTIAL')
            metric = result['metric_ledger']['cash_after_gross_capex_and_distributions']
            self.assertIsNone(metric['value'])
            self.assertEqual(metric['conditional_same_basis_value'], '-10')
            self.assertFalse(metric['source_bound_comparability'])
            self.assertIsNone(result['metric_ledger']['ffo']['value'])
            self.assertEqual(result['metric_ledger']['ffo']['conditional_same_basis_value'], '60')
            self.assertEqual(result['metric_ledger']['ffo']['declared_arithmetic_value'], '60')
            self.assertEqual(result['capex_overlap']['status'], 'UNRESOLVED_MAPPING')
            self.assertEqual(result['declared_capex_mapping_arithmetic']['status'], 'DECLARED_MAPPING_RECONCILED')

    def test_source_role_certificate_cannot_promote_direct_output(self):
        _, arguments, provenance = bound()
        result = financial.reit_reconciliation(arguments['document'], provenance)
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertEqual(result['metric_ledger']['affo']['conditional_same_basis_value'], '31')

    def test_all_supported_records_allow_primary_arithmetic_and_fixed_report(self):
        result = self.run_bound()
        metric = result['metric_ledger']['affo']
        self.assertEqual(metric['value'], '31')
        self.assertIsNone(metric['conditional_same_basis_value'])
        self.assertTrue(metric['source_bound_comparability'])
        self.assertEqual(result['source_binding']['mode'], 'PINNED_ORIGINAL_OPERAND_RECORDS')
        self.assertIn('source-record compatible arithmetic', result['report']['text'])
        self.assertEqual(result['report']['sha256'], hashlib.sha256(result['report']['text'].encode()).hexdigest())
        self.assertFalse(result['report']['whole_report_semantic_pass'])
        self.assertEqual(result, self.run_bound())

    def test_missing_holder_does_not_erase_known_period_and_unit(self):
        req, original = fixture()
        index = next(i for i, row in enumerate(original['records']) if row['measure_role'] == 'cfo')
        original['records'][index].pop('holder_basis')
        result = self.run_bound(req, original)
        metric = result['metric_ledger']['cfo_after_gross_capex']
        self.assertIsNone(metric['value']); self.assertEqual(metric['conditional_same_basis_value'], '15')
        self.assertEqual(metric['original_record_compatibility']['unknown_dimensions'], ['holder_basis'])
        self.assertEqual(metric['original_record_compatibility']['resolved_dimensions']['currency'], 'EUR')
        self.assertIn('conditional same-basis arithmetic only', result['report']['text'])

    def test_no_bindings_does_not_convert_source_presence_to_absence(self):
        req, original = fixture(); req['bindings'] = []
        original['common_distribution_label'] = 'explicitly attributable to common holders'
        result = self.run_bound(req, original)
        self.assertIsNone(result['metric_ledger']['distribution_payout_to_ffo']['value'])
        self.assertIn('Unknown mapping does not prove a source label is absent', result['report']['text'])

    def test_different_measure_record_rejected_even_equal_number(self):
        req, original = fixture()
        original['records'][0]['measure_role'] = 'cfo'
        with self.assertRaisesRegex(ValueError, 'MEASURE_ROLE_MISMATCH'):
            self.run_bound(req, original)

    def test_numeric_sibling_and_freeform_selectors_rejected(self):
        req, original = fixture(); original['records'][0]['other_value'] = 999
        req['document']['ffo_bridge']['components'][0]['amount'] = 999
        with self.assertRaisesRegex(ValueError, 'VALUE_MISMATCH'):
            self.run_bound(req, original)
        req['bindings'][0]['value_pointer'] = '/other_value'
        with self.assertRaisesRegex(ValueError, 'BINDING_FIELDS'):
            self.run_bound(req, original)

    def test_cross_entity_scale_period_and_holder_conflicts_block(self):
        for field, value in [('entity_id', 'OTHER'), ('unit_scale', 1000), ('period_end', '2028-11-30'),
                             ('holder_basis', 'consolidated')]:
            req, original = fixture(); original['records'][0][field] = value
            with self.subTest(field=field):
                result = self.run_bound(req, original)
                metric = result['metric_ledger']['affo']
                self.assertEqual(metric['original_record_compatibility']['status'], 'INCOMPATIBLE')
                self.assertIsNone(metric['value']); self.assertIsNone(metric['conditional_same_basis_value'])

    def test_original_holder_conflicts_with_matching_fabricated_declarations(self):
        req, original = fixture()
        for record in original['records']:
            record['holder_basis'] = 'all holders'
        result = self.run_bound(req, original)
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertTrue(result['metric_ledger']['affo']['original_record_compatibility']['source_declaration_conflicts'])

    def test_group_basis_cannot_hide_component_difference(self):
        req, original = fixture()
        index = next(i for i, row in enumerate(original['records']) if row['measure_role'] == 'gross_capex_component')
        original['records'][index]['period_start'] = '2028-02-01'
        result = self.run_bound(req, original)
        self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['value'])
        self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['conditional_same_basis_value'])
        self.assertIsNone(result['metric_ledger']['gross_capex']['value'])
        self.assertIsNone(result['metric_ledger']['gross_capex']['conditional_same_basis_value'])
        self.assertEqual(result['metric_ledger']['gross_capex']['declared_arithmetic_value'], '30')

    def test_no_top_level_inheritance(self):
        req, original = fixture(); original['holder_basis'] = 'common equity'
        for row in original['records']:
            row.pop('holder_basis')
        result = self.run_bound(req, original)
        self.assertEqual(result['metric_ledger']['affo']['original_record_compatibility']['unknown_dimensions'], ['holder_basis'])

    def test_fake_source_and_trusted_flags_rejected(self):
        req, original = fixture(); req['bindings'][0]['source_id'] = 'new-adapter'
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_ORIGINAL_MANIFEST'):
            self.run_bound(req, original)
        req, original = fixture(); req['trusted'] = True
        with self.assertRaisesRegex(ValueError, 'REQUEST_FIELDS'):
            self.run_bound(req, original)

    def test_fixed_transcription_adapter_preserves_unknown_holder(self):
        req, original = fixture()
        index = next(i for i, row in enumerate(original['records']) if row['measure_role'] == 'cfo')
        row = original['records'][index]
        row.update(concept='reviewed:cfo', unit='EUR', decimals='INF')
        row.pop('holder_basis'); row.pop('currency'); row.pop('unit_scale')
        req['bindings'][index]['schema'] = 'financial_transcription_v1'
        result = self.run_bound(req, original)
        self.assertEqual(result['metric_ledger']['cfo_after_gross_capex']['original_record_compatibility']['unknown_dimensions'], ['holder_basis'])

    def test_zero_missing_and_signed_recipe_are_distinct(self):
        req, original = fixture()
        first = req['bindings'][0]; first['sign'] = -1
        req['document']['ffo_bridge']['components'][0]['amount'] *= -1
        result = self.run_bound(req, original)
        self.assertEqual(result['source_binding']['operands'][0]['declared_recipe_sign'], -1)
        req, original = fixture(); original['records'][0]['value'] = None
        with self.assertRaisesRegex(ValueError, 'VALUE_NULL_OR_MISSING'):
            self.run_bound(req, original)
        original['records'][0]['value'] = 0; req['document']['ffo_bridge']['components'][0]['amount'] = 0
        self.assertEqual(self.run_bound(req, original)['metric_ledger']['ffo']['value'], '18')

    def test_binding_cannot_change_nonnegative_measure_sign(self):
        req, original = fixture()
        binding = next(row for row in req['bindings'] if row['target_pointer'] == '/cfo/amount')
        binding['sign'] = -1; req['document']['cfo']['amount'] *= -1
        with self.assertRaisesRegex(ValueError, 'UNSIGNED_OPERAND_TRANSFORM'):
            self.run_bound(req, original)

    def test_matching_original_scales_cannot_hide_wrong_declared_denomination(self):
        req, original = fixture()
        for row in original['records']:
            row['unit_scale'] = 1000
        metric = self.run_bound(req, original)['metric_ledger']['affo']
        self.assertIsNone(metric['value']); self.assertIsNone(metric['conditional_same_basis_value'])
        self.assertTrue(metric['original_record_compatibility']['source_declaration_conflicts'])

    def test_equivalent_scale_spellings_compare_numerically(self):
        req, original = fixture(); original['records'][0]['unit_scale'] = '1.0'
        self.assertEqual(self.run_bound(req, original)['metric_ledger']['affo']['value'], '31')

    def test_absent_adjustment_list_does_not_certify_complete_operands(self):
        req, original = fixture()
        req['document']['affo_bridge'].pop('adjustments')
        req['bindings'] = [row for row in req['bindings'] if '/adjustments/' not in row['target_pointer']]
        metric = self.run_bound(req, original)['metric_ledger']['affo']
        self.assertIsNone(metric['value']); self.assertIsNone(metric['conditional_same_basis_value'])
        self.assertFalse(metric['source_bound_comparability'])
        self.assertIn('other_affo_adjustments', metric['original_record_compatibility']['missing_arithmetic_inputs'])

    def test_original_record_cannot_be_counted_twice_in_one_additive_group(self):
        req, original = fixture()
        req['document']['ffo_bridge']['components'][1]['amount'] = original['records'][0]['value']
        req['bindings'][1]['record_pointer'] = req['bindings'][0]['record_pointer']
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ORIGINAL_WITHIN_GROUP'):
            self.run_bound(req, original)

    def test_original_alias_cannot_double_count_a_record(self):
        req, original = fixture()
        req['document']['ffo_bridge']['components'][1]['amount'] = original['records'][0]['value']
        req['bindings'][1].update(source_id='alias', record_pointer='/records/0')
        raw = json.dumps(original).encode()
        for name in ('one.json', 'two.json'):
            (self.root / name).write_bytes(raw)
        manifest = {'schema_version': 1, 'sources': [{'id': sid, 'path': name, 'format': 'json',
            'sha256': hashlib.sha256(raw).hexdigest()} for sid, name in [('original', 'one.json'), ('alias', 'two.json')]]}
        data = json.dumps(manifest).encode(); path = self.root / 'manifest.json'; path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_ORIGINAL_WITHIN_GROUP'):
            subject.analyze(req, path, hashlib.sha256(data).hexdigest())

    def test_relocated_retained_originals_replay_byte_identically(self):
        req, original = fixture()
        first = self.run_bound(req, original)
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / 'copy'
            shutil.copytree(self.root, copied)
            manifest = copied / 'manifest.json'
            second = subject.analyze(req, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), copied)
        self.assertEqual(subject.encode(first), subject.encode(second))
        self.assertNotIn(str(self.root), subject.encode(first).decode())

    def property_fixture(self, field='largest_tenant_revenue_fraction', value='.37'):
        req, original = fixture()
        req['document']['property_fractions'] = [{'id': 'concentration', 'value': value,
                                                'denominator': None, 'time_anchor': None}]
        original['portfolio'] = {field: value}
        req['bindings'].append({'target_pointer': '/property_fractions/0/value', 'schema': 'property_disclosure_v1',
            'source_id': 'original', 'record_pointer': '/portfolio', 'field': field, 'sign': 1})
        return req, original

    def test_bound_field_retains_broad_revenue_without_inventing_precise_scope_or_time(self):
        req, original = self.property_fixture()
        original['portfolio'].update(symbol='UNASSOCIATED', period_end='2031-12-31')
        result = self.run_bound(req, original)
        row = result['property_fractions'][0]
        self.assertEqual(row['denominator'], 'revenue')
        self.assertEqual(row['binding_status'], 'BOUND')
        self.assertEqual(row['source_bound_fraction'], '0.37')
        self.assertEqual(row['unresolved_fields'], ['denominator_scope', 'time_anchor'])
        self.assertIsNone(row['original_field']['entity_association'])
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertIn('Original denominator: revenue', result['report']['text'])
        self.assertIn('precise denominator scope: None; time anchor: None', result['report']['text'])

    def test_known_original_property_fact_remains_visible_without_any_binding(self):
        req, original = self.property_fixture(); req['bindings'] = []
        result = self.run_bound(req, original)
        self.assertEqual(result['property_fractions'][0]['binding_status'], 'UNBOUND')
        self.assertIsNone(result['property_fractions'][0]['denominator'])
        fact = result['source_binding']['property_source_facts'][0]
        self.assertEqual(fact['denominator'], 'revenue')
        self.assertIn('original/portfolio/largest_tenant_revenue_fraction: fraction 0.37; broad denominator revenue', result['report']['text'])
        req['document']['property_fractions'] = []
        self.assertEqual(self.run_bound(req, original)['source_binding']['property_source_facts'], [fact])

    def test_generic_expiry_does_not_inherit_revenue_or_a_calendar_year(self):
        req, original = self.property_fixture('net_lease_expirations_next_year_fraction', '.18')
        req['document']['property_fractions'][0].update(denominator='revenue', time_anchor='2031')
        result = self.run_bound(req, original); row = result['property_fractions'][0]
        self.assertIsNone(row['denominator']); self.assertIsNone(row['time_anchor'])
        self.assertEqual(row['relative_time_label'], 'next_year')
        self.assertEqual(row['declared_metadata']['denominator'], 'revenue')
        self.assertIn('denominator', row['unresolved_fields'])
        self.assertIn('time_anchor', row['unresolved_fields'])

    def test_source_and_caller_metadata_conflicts_remain_visible(self):
        req, original = self.property_fixture()
        req['document']['property_fractions'][0]['denominator'] = 'area'
        row = self.run_bound(req, original)['property_fractions'][0]
        self.assertEqual(row['binding_status'], 'CONFLICT')
        self.assertEqual(row['denominator'], 'revenue')
        self.assertEqual(row['declaration_conflicts'], ['denominator'])
        original['portfolio']['largest_tenant_revenue_fraction'] = {'value': '.37', 'denominator': 'area'}
        result = self.run_bound(req, original); row = result['property_fractions'][0]
        self.assertEqual(row['source_metadata_conflicts'], ['denominator'])
        self.assertIsNone(row['denominator'])
        self.assertIn('Original metadata conflict; field-name denominator revenue; explicit denominator area', result['report']['text'])

    def test_exact_property_record_metadata_only_and_original_value_checked(self):
        req, original = self.property_fixture()
        original['portfolio']['largest_tenant_revenue_fraction'] = {'value': '.37', 'denominator': 'revenue',
            'denominator_scope': 'portfolio gross rent', 'time_anchor': '2031-06-30'}
        row = self.run_bound(req, original)['property_fractions'][0]
        self.assertEqual(row['unresolved_fields'], [])
        self.assertEqual(row['time_anchor'], '2031-06-30')
        req['document']['property_fractions'][0]['value'] = '.38'
        with self.assertRaisesRegex(ValueError, 'PROPERTY_ORIGINAL_VALUE_MISMATCH'):
            self.run_bound(req, original)

    def test_property_invalid_values_unknown_fields_and_signs_rejected(self):
        for value in (True, 'NaN', '1.2', '-.1'):
            req, original = self.property_fixture(); original['portfolio']['largest_tenant_revenue_fraction'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_bound(req, original)
        req, original = self.property_fixture(); req['bindings'][-1]['field'] = 'some_other_fraction'
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_PROPERTY_FIELD'):
            self.run_bound(req, original)
        req, original = self.property_fixture(); req['bindings'][-1]['sign'] = -1
        with self.assertRaisesRegex(ValueError, 'PROPERTY_UNSIGNED_BINDING'):
            self.run_bound(req, original)

    def test_scan_keeps_ambiguous_multiple_records_and_invalid_fields_separate(self):
        req, original = self.property_fixture(); req['bindings'] = []
        original['other'] = {'largest_tenant_revenue_fraction': '.37'}
        original['invalid'] = {'property_occupancy': 'not a fraction'}
        original['prose'] = 'largest_tenant_revenue_fraction: 0.9'
        result = self.run_bound(req, original); facts = result['source_binding']['property_source_facts']
        self.assertEqual(len(facts), 3)
        self.assertEqual([r['source_pointer'] for r in facts[:2]],
                         ['/portfolio/largest_tenant_revenue_fraction', '/other/largest_tenant_revenue_fraction'])
        self.assertEqual(facts[2]['association_status'], 'INVALID_SUPPORTED_FIELD')
        self.assertIn('invalid supported field', result['report']['text'])
        self.assertIsNone(result['property_fractions'][0]['source_bound_fraction'])

    def test_property_observation_report_replays_after_relocation(self):
        req, original = self.property_fixture()
        result = self.run_bound(req, original)
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / 'copy'; shutil.copytree(self.root, copied)
            manifest = copied / 'manifest.json'
            replay = subject.analyze(req, manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), copied)
        self.assertEqual(subject.encode(result), subject.encode(replay))
        self.assertEqual(result['report']['sha256'], hashlib.sha256(result['report']['text'].encode()).hexdigest())


if __name__ == '__main__':
    unittest.main()
