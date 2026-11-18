"""Generic final artifact counterexamples; no private evaluation values."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import final_report as module


class FinalReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='final-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.originals = self.root / 'originals'; self.originals.mkdir()
        self.manifest = self.root / 'manifest.json'; self.request = self.root / 'plan.json'; self.output = self.root / 'output'
        self.sources([('filing', 'json', {'common_cash': 17})])
        self.plan = {'sections': [{'kind': 'source_claim', 'request': {'operation': 'presence', 'terms': ['common']}}]}

    def sources(self, rows):
        entries = []
        for sid, fmt, value in rows:
            raw = json.dumps(value).encode() if fmt == 'json' else value.encode() if isinstance(value, str) else value
            name = sid + '.source'; (self.originals / name).write_bytes(raw)
            entries.append({'id': sid, 'path': name, 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': entries}), encoding='utf-8')
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def compose(self):
        self.request.write_text(json.dumps(self.plan), encoding='utf-8')
        return module.compose(self.request, self.output, self.manifest, self.pin, self.originals)

    def report(self): return (self.output / 'first-response.md').read_text(encoding='utf-8')

    def resign_inventory(self):
        path = self.output / 'receipt.json'; receipt = json.loads(path.read_bytes())
        receipt['artifacts'] = module.source.file_inventory(self.output)
        path.write_bytes(module.source.encode(receipt))

    def accounting(self, weighted=False):
        data = {'income': {'value': 19.5, 'attribution': 'diluted_income_available_to_common' if weighted else 'consolidated_net_income',
                           'period_start': '2031-01-01', 'period_end': '2031-12-31', 'issuer': 'Sample', 'currency': 'EUR', 'unit_scale': 1},
                'shares': {'value': 6.5, 'basis': 'weighted_average_diluted' if weighted else 'as_of_date',
                           'period_end': '2031-12-31', 'issuer': 'Sample', 'unit_scale': 1}}
        if weighted: data['shares']['period_start'] = '2031-01-01'
        self.sources([('filing', 'json', data)])
        req = {'operation': 'accounting', **{group: {key: {'source_id': 'filing', 'pointer': '/' + group + '/' + key}
               for key in data[group]} for group in ('income', 'shares')}}
        self.plan = {'sections': [{'kind': 'source_claim', 'request': req}]}

    def terminal(self):
        from test_terminal_capital_boundary import document
        source = document()
        self.sources([('model', 'json', source), ('other', 'text', 'Unresolved context retained.')])
        self.plan = {'sections': [{'kind': 'terminal_objectives',
            'contract': {'prompt': 'Inspect the supplied declared model.', 'purpose': 'offline research',
                         'base_currency': 'EUR', 'horizon_id': 'P2Y', 'as_of': '2031-01-01T00:00:00Z'},
            'document': {'$source': {'id': 'model', 'pointer': ''}}}]}

    def test_presence_real_execution_final_bytes_and_receipt(self):
        receipt = self.compose()
        self.assertEqual(receipt['status'], 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH')
        self.assertFalse(receipt['whole_report_semantic_pass'])
        self.assertEqual(receipt['response_file'], 'first-response.md')
        self.assertIn('SOURCE_CANDIDATE_PRESENT', self.report())
        self.assertIn('source absence', self.report())
        self.assertEqual(module.verify(self.output)['final_response_sha256'], receipt['final_response_sha256'])

    def test_dated_shares_cannot_be_reported_eps(self):
        self.accounting(); self.compose()
        self.assertIn('DIAGNOSTIC_RATIO_ONLY', self.report())
        self.assertIn('not established reported EPS or P/E', self.report())
        self.assertNotIn('Retained fields classify as diluted_eps', self.report())

    def test_explicit_wrong_eps_label_fails_without_final_receipt(self):
        self.accounting(); self.plan['sections'][0]['label'] = 'diluted_eps'
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_ACCOUNTING_LABEL'): self.compose()
        self.assertTrue((self.output/'failure.json').is_file())
        self.assertTrue((self.output/'sections/000/producer/result.json').is_file())
        self.assertFalse((self.output/'receipt.json').exists())

    def test_actual_decimal_weighted_eps_is_rendered(self):
        self.accounting(weighted=True); self.compose()
        self.assertIn('Retained fields classify as diluted_eps', self.report())
        self.assertIn('3', self.report())
        module.verify(self.output)

    def test_partial_analyst_revision_cannot_be_silently_dropped(self):
        text = ('Firm Quill, analyst Ava, issued 2031-01-02T10:00:00Z: SYN target EUR 61 '
                'per common share; horizon forward_12_months; access FULL_REPORT. No split adjustment.\n')
        revision = 'Quill initiated new coverage January 9: FY2033 adjusted EPS EUR 4.10; target EUR 72.'
        self.sources([('main', 'text', text), ('supplementary', 'text', revision)])
        request = {'as_of': '2031-01-20T12:00:00Z', 'cohort': {'issuer': 'SYN', 'currency': 'EUR',
                   'price_basis': 'common_share_unadjusted', 'target_horizon': 'forward_12_months'},
                   'extraction_profile': {'formats': ['labelled_sentences']}}
        self.plan = {'sections': [{'kind': 'source_report', 'producer': 'analyst_sources', 'request': request}]}
        self.compose(); text = self.report()
        self.assertIn('INCOMPLETE', text); self.assertIn('January 9', text); self.assertIn('72', text)
        self.assertIn('Unresolved extracted records', text)
        self.assertEqual((self.output/'originals/supplementary.source').read_text(), revision)

    def test_terminal_native_workflow_comparator_not_dcf(self):
        self.terminal(); self.compose(); text = self.report()
        self.assertIn('DCF discount closure: unavailable', text)
        self.assertIn('after-cost holding-period return >= 0', text)
        self.assertIn('No general joint necessary or sufficient', text)
        audit = module.verify(self.output)
        self.assertEqual(audit['sections'][0]['workflow_audit']['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
        self.assertTrue((self.output/'sections/000/workflow/sources/other.source').is_file())

    def test_terminal_assumptions_only_do_not_pose_as_source_bound(self):
        self.terminal()
        from test_terminal_capital_boundary import document
        self.plan['sections'][0]['document'] = {'$assumption': document(), 'reason': 'Declared hypothetical model'}
        with self.assertRaisesRegex(ValueError, 'TERMINAL_ORIGINAL_SOURCE_BINDING_REQUIRED'): self.compose()

    def test_all_three_section_kinds_compose_in_order(self):
        self.terminal(); terminal = self.plan['sections'][0]
        self.plan['sections'] = [terminal, {'kind': 'source_claim', 'request': {'operation': 'presence', 'terms': ['context']}},
                                {'kind': 'source_report', 'producer': 'source_claims', 'request': {'operation': 'presence', 'terms': ['model']}}]
        self.compose(); audit = module.verify(self.output)
        self.assertEqual([s['kind'] for s in audit['sections']], ['terminal_objectives', 'source_claim', 'source_report'])

    def test_unaudited_contradictory_prose_remains_partial_with_byte_spans(self):
        self.plan['unverified_prose'] = 'Ω: These numbers prove every company has guaranteed EPS.'
        receipt = self.compose(); self.assertEqual(receipt['status'], 'PARTIAL_UNAUDITED_PROSE')
        raw = (self.output/'first-response.md').read_bytes(); span = receipt['unverified_spans'][0]
        self.assertEqual(raw[span['start_byte']:span['end_byte']], self.plan['unverified_prose'].encode())
        self.assertIn('not verified by the source', self.report()); self.assertFalse(receipt['whole_report_semantic_pass'])

    def test_edited_final_report_rejected_even_after_inventory_resign(self):
        self.compose(); (self.output/'first-response.md').write_text('Fabricated conclusion.')
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'FINAL_RESPONSE_BYTES_MISMATCH'): module.verify(self.output)

    def test_unrelated_published_response_rejected(self):
        self.compose(); path = self.root/'published.md'; path.write_bytes((self.output/'first-response.md').read_bytes())
        module.verify(self.output, path)
        path.write_text('Different saved final response.')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_RESPONSE_DIFFERS'): module.verify(self.output, path)

    def test_authored_cached_result_request_rejected(self):
        self.plan['sections'][0]['result'] = {'status': 'PASS'}
        with self.assertRaisesRegex(ValueError, 'EXACT_PLAN_OR_SECTION'): self.compose()

    def test_changed_producer_output_rejected_after_outer_inventory_resign(self):
        self.compose(); path = self.output/'sections/000/producer/result.json'
        result = json.loads(path.read_bytes()); result['predicate'] = 'SOURCE_ABSENT'; path.write_text(json.dumps(result))
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'RETAINED_ARTIFACT'): module.verify(self.output)

    def test_rehashed_authored_success_cannot_replace_original_producer_replay(self):
        self.compose(); producer=self.output/'sections/000/producer'
        path=producer/'result.json'; result=json.loads(path.read_bytes())
        result['predicate']='SOURCE_ABSENT'; path.write_bytes(module.source.encode(result))
        receipt_path=producer/'receipt.json'; receipt=json.loads(receipt_path.read_bytes())
        receipt['artifacts']=module.source.file_inventory(producer)
        receipt_path.write_bytes(module.source.encode(receipt)); self.resign_inventory()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_REPLAY_MISMATCH'): module.verify(self.output)

    def test_section_deletion_rejected(self):
        self.compose(); shutil.rmtree(self.output/'sections/000'); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'SECTION_SET_CHANGED'): module.verify(self.output)

    def test_relocated_whole_report_replays_with_original_location_removed(self):
        self.accounting(weighted=True); self.compose()
        relocated = self.root/'relocated'; shutil.copytree(self.output, relocated)
        self.output.rename(self.root/'old-run'); self.originals.rename(self.root/'old-sources')
        self.assertEqual(module.verify(relocated)['status'], 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH')

    def test_terminal_relocation_replays_native_output(self):
        self.terminal(); self.compose()
        relocated = self.root/'relocated'; shutil.copytree(self.output, relocated)
        self.output.rename(self.root/'old-run'); self.originals.rename(self.root/'old-sources')
        self.assertEqual(module.verify(relocated)['status'], 'FINAL_REPORT_REPLAY_AND_BYTES_MATCH')

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir(); marker=self.output/'keep'; marker.write_text('original')
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT_REQUIRED'): self.compose()
        self.assertEqual(marker.read_text(), 'original')

    def test_original_manifest_pin_and_nonselected_source_tamper_rejected(self):
        self.sources([('filing','json',{'common_cash':17}),('unselected','text','Other source')])
        (self.originals/'unselected.source').write_text('Changed source')
        with self.assertRaises(ValueError): self.compose()
        self.assertFalse((self.output/'receipt.json').exists())

    def test_real_cli_compose_and_verify(self):
        self.request.write_text(json.dumps(self.plan), encoding='utf8')
        command=[sys.executable,'-B',module.__file__]
        done=subprocess.run(command+['compose',str(self.request),'--manifest',str(self.manifest),
            '--manifest-sha256',self.pin,'--source-root',str(self.originals),'--output',str(self.output)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        checked=subprocess.run(command+['verify',str(self.output),'--final-response',str(self.output/'first-response.md')],capture_output=True,text=True)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)

    def conclusion(self, objective='AFTER_COST_CAPITAL_PRESERVATION'):
        self.terminal()
        self.plan['objective_conclusion_required'] = True
        self.plan['sections'].append({'kind': 'objective_conclusion', 'evidence_section': 0,
                                     'objective_id': objective, 'domain_scope': 'SUPPLIED_ROWS'})

    def test_objective_conclusion_replays_rows_and_labels_uncomputed_judgment(self):
        self.conclusion()
        self.plan['sections'][1]['research_judgment'] = {'stance': 'favorable'}
        receipt = self.compose(); result = receipt['sections'][1]
        self.assertEqual(result['status'], 'EVALUATED_SUPPLIED_ROWS_ONLY')
        self.assertFalse(result['rows'][0]['met'])
        self.assertEqual(result['research_judgment']['status'], 'ANALYST_OPINION_NOT_COMPUTED')
        self.assertIn('net_total_return_fraction >= 0', self.report())
        self.assertIn('not strictly positive return', self.report())
        self.assertFalse(result['general_joint_necessity_established'])
        self.assertTrue(module.verify(self.output)['objective_conclusion_required'])

    def test_dcf_request_does_not_relabel_positive_returns_as_discount_closure(self):
        self.conclusion('DCF_DISCOUNT_CLOSURE')
        from test_terminal_capital_boundary import document
        value = document(); value['scenarios'][0]['exit_ev_to_ebit'] = 12
        self.sources([('model', 'json', value)])
        receipt = self.compose(); conclusion = receipt['sections'][1]
        self.assertEqual(conclusion['status'], 'NOT_EVALUATED')
        self.assertEqual(conclusion['rows'], [])
        self.assertIn('DCF discount closure: NOT_EVALUATED', self.report())
        self.assertIn('No requirements for closing a DCF discount', self.report())
        module.verify(self.output)

    def test_different_passing_joint_assumptions_remain_rows_not_necessity(self):
        self.conclusion()
        from test_terminal_capital_boundary import document
        value = document(); base = value['scenarios'][0]
        value['scenarios'] += [{**base, 'id': 'multiple-only', 'exit_ev_to_ebit': 12},
                               {**base, 'id': 'margin-only', 'terminal_ebit_margin': '.6'}]
        self.sources([('model', 'json', value)])
        receipt = self.compose(); conclusion = receipt['sections'][1]
        self.assertEqual([row['met'] for row in conclusion['rows']], [False, True, True])
        self.assertIn('among these supplied rows', self.report())
        self.assertIn('does not make their joint assumptions necessary', self.report())
        self.assertFalse(conclusion['domain_exhaustive'])

    def test_required_conclusion_missing_or_omitting_another_terminal_rejected(self):
        self.terminal(); self.plan['objective_conclusion_required'] = True
        with self.assertRaisesRegex(ValueError, 'CONCLUSION_REQUIRED_FOR_EACH'):
            module.plan(module.encoded(self.plan))
        self.conclusion(); self.plan['sections'].append(copy.deepcopy(self.plan['sections'][0]))
        with self.assertRaisesRegex(ValueError, 'CONCLUSION_REQUIRED_FOR_EACH'):
            module.plan(module.encoded(self.plan))

    def test_conclusion_rejects_wrong_reference_objective_and_domain(self):
        self.conclusion()
        for field, value, error in [('evidence_section', True, 'EARLIER_TERMINAL'),
                                     ('evidence_section', 1, 'EARLIER_TERMINAL'),
                                     ('evidence_section', -1, 'EARLIER_TERMINAL'),
                                     ('objective_id', 'OUTPERFORM_CASH', 'SUPPORTED_OBJECTIVE'),
                                     ('domain_scope', 'ALL_ECONOMIC_OUTCOMES', 'SUPPORTED_OBJECTIVE')]:
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan); plan['sections'][1][field] = value
                with self.assertRaisesRegex(ValueError, error): module.plan(module.encoded(plan))
        self.plan['sections'][0] = {'kind': 'source_claim', 'request': {'operation': 'presence', 'terms': ['cash']}}
        with self.assertRaisesRegex(ValueError, 'EARLIER_TERMINAL'): module.plan(module.encoded(self.plan))

    def test_no_caller_authored_proof_operator_target_or_and_or_conditions(self):
        self.conclusion()
        for key, value in [('result', {'status': 'SUCCESS'}), ('operator', '>'), ('target', '.12'),
                           ('necessary_conditions', {'AND': ['margin', 'multiple']}),
                           ('sufficient_conditions', {'OR': ['growth', 'debt']})]:
            with self.subTest(key=key):
                plan = copy.deepcopy(self.plan); plan['sections'][1][key] = value
                with self.assertRaisesRegex(ValueError, 'EXACT_PLAN_OR_SECTION'): module.plan(module.encoded(plan))

    def test_unresolved_terminal_is_not_vacuous_conclusion_success(self):
        self.conclusion()
        from test_terminal_capital_boundary import document
        value = document(); del value['currency']; self.sources([('model', 'json', value)])
        receipt = self.compose(); conclusion = receipt['sections'][1]
        self.assertEqual(conclusion['status'], 'UNRESOLVED_EVIDENCE')
        self.assertEqual(conclusion['rows'], [])
        self.assertIn('no passing rows or necessary conditions are established', self.report())

    def test_conclusion_does_not_certify_contradictory_appendix(self):
        self.conclusion('DCF_DISCOUNT_CLOSURE')
        self.plan['unverified_prose'] = 'Unsupported analyst claim: this guarantees discounted value recovery.'
        receipt = self.compose()
        self.assertEqual(receipt['status'], 'PARTIAL_UNAUDITED_PROSE')
        self.assertEqual(receipt['sections'][1]['status'], 'NOT_EVALUATED')
        self.assertIn(self.plan['unverified_prose'], self.report())
        self.assertFalse(receipt['whole_report_semantic_pass'])

    def test_conclusion_request_tamper_and_relocated_exact_replay(self):
        self.conclusion(); self.compose()
        relocated = self.root/'relocated'; shutil.copytree(self.output, relocated)
        self.assertEqual(module.verify(relocated)['sections'][1]['status'], 'EVALUATED_SUPPLIED_ROWS_ONLY')
        path = self.output/'sections/001/conclusion-request.json'; changed = json.loads(path.read_bytes())
        changed['objective_id'] = 'DCF_DISCOUNT_CLOSURE'; path.write_bytes(module.encoded(changed))
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'CONCLUSION_REQUEST_CHANGED'): module.verify(self.output)

    def test_conditional_boundary_and_higher_probe_have_distinct_exact_roles(self):
        from fractions import Fraction
        self.conclusion(); self.plan['sections'][1]['include_boundaries'] = True
        receipt = self.compose(); boundary = receipt['sections'][1]['boundaries'][0]
        minimum = boundary['threshold']; probe = boundary['above_probe']['multiple']
        ratio = lambda value: Fraction(int(value['exact_numerator']), int(value['exact_denominator']))
        self.assertEqual(ratio(probe) - ratio(minimum), 1)
        self.assertEqual(boundary['threshold_relation'], 'AT_TARGET')
        self.assertEqual(boundary['above_probe']['exact_retained_operand_relation'], 'ABOVE_TARGET')
        self.assertIn('Conditional minimum exit EV/EBIT', self.report())
        self.assertIn('probe is not the threshold', self.report())
        self.assertFalse(boundary['strict_positive_return_established_by_equality'])
        self.assertIn('held_assumptions', boundary)
        module.verify(self.output)

    def test_domain_minimum_already_positive_is_not_zero_return_break_even(self):
        self.conclusion(); self.plan['sections'][1]['include_boundaries'] = True
        from test_terminal_capital_boundary import document
        value = document(); value['equity_value_floor_zero'] = True
        value['scenarios'][0]['cumulative_dividends_per_share'] = 100
        self.sources([('model', 'json', value)])
        receipt = self.compose(); boundary = receipt['sections'][1]['boundaries'][0]
        self.assertEqual(boundary['status'], 'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
        self.assertEqual(boundary['threshold_relation'], 'ABOVE_TARGET')
        self.assertIn('not necessarily an equality or zero-return break-even', self.report())

    def test_unattainable_boundary_keeps_probe_separate_and_threshold_unknown(self):
        self.conclusion(); self.plan['sections'][1]['include_boundaries'] = True
        from test_terminal_capital_boundary import document
        value = document(); value['equity_value_floor_zero'] = True
        value['scenarios'][0]['terminal_ebit_margin'] = 0
        self.sources([('model', 'json', value)])
        receipt = self.compose(); boundary = receipt['sections'][1]['boundaries'][0]
        self.assertEqual(boundary['status'], 'UNATTAINABLE_WITH_FIXED_INPUTS')
        self.assertIsNone(boundary['threshold'])
        self.assertEqual(boundary['above_probe']['exact_retained_operand_relation'], 'BELOW_TARGET')
        self.assertIn('No verified threshold is established', self.report())

    def test_boundary_contract_rejects_dcf_relabelling_and_nonboolean_option(self):
        self.conclusion('DCF_DISCOUNT_CLOSURE'); self.plan['sections'][1]['include_boundaries'] = True
        with self.assertRaisesRegex(ValueError, 'BOUNDARIES_REQUIRE_CAPITAL'):
            module.plan(module.encoded(self.plan))
        self.plan['sections'][1]['include_boundaries'] = 'true'
        with self.assertRaisesRegex(ValueError, 'BOUNDARY_OPTION_BOOLEAN'):
            module.plan(module.encoded(self.plan))


    def strict(self):
        self.plan['output_contract'] = module.STRICT

    def analysis(self):
        return json.loads((self.output/'analysis.json').read_bytes())

    def export(self, metadata=None):
        metadata = metadata or {'case_id':'fictional-research', 'runtime_model_metadata':{'model':'unknown','effort':'unknown'}}
        path = self.root/'metadata.json'; path.write_text(json.dumps(metadata), encoding='utf8')
        self.exported = self.root/'published'
        return module.export_response(self.output, path, self.exported)

    def test_canonical_diagnostic_ratio_cannot_become_eps_or_pe(self):
        self.accounting(); self.strict(); self.compose(); receipt = self.export()
        response = json.loads((self.exported/'response.json').read_bytes())
        result = response['rows'][0]['result']
        self.assertEqual(result['classification'], 'DIAGNOSTIC_RATIO_ONLY')
        self.assertEqual(result['raw_operand_ratio'], 3)
        self.assertIsNone(result['eps']); self.assertIsNone(result['pe'])
        self.assertEqual(result['allowed_claims'], [])
        self.assertEqual(response['rows'], self.analysis()['sections'])
        self.assertFalse(receipt['whole_report_semantic_pass'])
        module.verify_response(self.exported)

    def test_canonical_positive_weighted_eps_preserves_type_and_label(self):
        self.accounting(weighted=True); self.strict(); self.compose(); self.export()
        result = json.loads((self.exported/'response.json').read_bytes())['rows'][0]['result']
        self.assertEqual(result['classification'], 'DILUTED_EPS_SOURCE_BOUND')
        self.assertEqual(result['eps'], 3); self.assertIsNone(result['pe'])
        self.assertEqual(result['allowed_claims'], ['diluted_eps'])

    def test_strict_contract_rejects_prose_labels_and_unknown_contract(self):
        self.accounting(); self.strict(); self.plan['unverified_prose'] = 'A caller conclusion.'
        with self.assertRaisesRegex(ValueError, 'STRICT_REPORT_FORBIDS_FREE_PROSE'): module.plan(module.encoded(self.plan))
        del self.plan['unverified_prose']; self.plan['sections'][0]['label'] = 'diagnostic_ratio'
        with self.assertRaisesRegex(ValueError, 'STRICT_REPORT_FORBIDS_CALLER_LABEL'): module.plan(module.encoded(self.plan))
        del self.plan['sections'][0]['label']; self.plan['output_contract'] = 'TRUSTED'
        with self.assertRaisesRegex(ValueError, 'SUPPORTED_OUTPUT_CONTRACT'): module.plan(module.encoded(self.plan))

    def test_response_metadata_cannot_supply_financial_rows_or_overrides(self):
        base = {'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'}}
        for key in ('rows','eps','diluted_eps','price_to_eps','status','limitations','input_hashes','candidate_version','verdict'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'EXACT_PLAN_OR_SECTION'):
                module.response_metadata(module.encoded(dict(base, **{key: {'invented':1}})))
        with self.assertRaisesRegex(ValueError, 'EXACT_PLAN_OR_SECTION'):
            module.response_metadata(module.encoded(dict(base, runtime_model_metadata={'model':'unknown','effort':'unknown','rows':{}})))

    def test_stale_calculation_is_reference_only_not_current_metrics(self):
        self.accounting(); self.strict(); self.compose()
        old = self.root/'old-calculation.json'; old.write_text('{"diluted_eps":9,"pe":14}')
        metadata = {'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'},
            'evidence_paths':[{'path':'old-calculation.json','sha256':hashlib.sha256(old.read_bytes()).hexdigest()}]}
        self.export(metadata); result = json.loads((self.exported/'response.json').read_bytes())
        self.assertIsNone(result['rows'][0]['result']['eps'])
        self.assertEqual(result['metadata_status'], 'PARTICIPANT_DECLARATIONS_AND_EXTERNAL_REFERENCES_NOT_VERIFIED')
        self.assertNotIn('diluted_eps', result)

    def test_rehashed_fabricated_current_response_row_is_rejected(self):
        self.accounting(); self.strict(); self.compose(); self.export()
        path = self.exported/'response.json'; response = json.loads(path.read_bytes())
        response['rows'][0]['result']['eps'] = 9; path.write_bytes(module.encoded(response))
        receipt_path = self.exported/'receipt.json'; receipt = json.loads(receipt_path.read_bytes())
        receipt['response_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt['artifacts'] = module.source.file_inventory(self.exported); receipt_path.write_bytes(module.source.encode(receipt))
        with self.assertRaisesRegex(ValueError, 'CANONICAL_RESPONSE_PROJECTION_MISMATCH'): module.verify_response(self.exported)

    def test_rehashed_canonical_analysis_extra_metric_is_rejected(self):
        self.accounting(); self.strict(); self.compose()
        path = self.output/'analysis.json'; value = self.analysis(); value['sections'][0]['result']['made_up_metric'] = 9
        path.write_bytes(module.encoded(value)); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'CANONICAL_ANALYSIS_MISMATCH'): module.verify(self.output)

    def test_rehashed_canonical_analysis_missing_section_is_rejected(self):
        self.strict(); self.compose(); value = self.analysis(); value['sections'] = []
        (self.output/'analysis.json').write_bytes(module.encoded(value)); self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'CANONICAL_ANALYSIS_MISMATCH'): module.verify(self.output)

    def test_projection_refuses_analysis_changed_after_real_verification(self):
        self.accounting(); self.strict(); self.compose(); real_verify=module.verify
        def changed(*args, **kwargs):
            audit=real_verify(*args, **kwargs); path=self.output/'analysis.json'; value=json.loads(path.read_bytes())
            value['sections'][0]['result']['eps']=999; path.write_bytes(module.encoded(value)); return audit
        meta=module.encoded({'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'}})
        with mock.patch.object(module,'verify',side_effect=changed), self.assertRaisesRegex(ValueError,'ANALYSIS_CHANGED_AFTER_VERIFICATION'):
            module._response_projection(self.output,meta)

    def test_projection_refuses_ingress_changed_after_real_verification(self):
        self.strict(); self.compose(); real_verify=module.verify
        def changed(*args, **kwargs):
            audit=real_verify(*args, **kwargs); path=self.output/'ingress.json'; value=json.loads(path.read_bytes())
            value['sources'][0]['sha256']='0'*64; path.write_bytes(module.encoded(value)); return audit
        meta=module.encoded({'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'}})
        with mock.patch.object(module,'verify',side_effect=changed), self.assertRaisesRegex(ValueError,'INGRESS_CHANGED_AFTER_VERIFICATION'):
            module._response_projection(self.output,meta)

    def test_projection_refuses_receipt_changed_after_real_verification(self):
        self.strict(); self.compose(); real_verify=module.verify
        def changed(*args, **kwargs):
            audit=real_verify(*args, **kwargs); path=self.output/'receipt.json'; value=json.loads(path.read_bytes())
            value['invented']=True; path.write_bytes(module.encoded(value)); return audit
        meta=module.encoded({'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'}})
        with mock.patch.object(module,'verify',side_effect=changed), self.assertRaisesRegex(ValueError,'REPORT_RECEIPT_CHANGED_DURING_PROJECTION'):
            module._response_projection(self.output,meta)

    def test_duplicate_metadata_keys_rejected(self):
        with self.assertRaises(ValueError):
            module.response_metadata(b'{"case_id":"a","case_id":"b","runtime_model_metadata":{"model":"unknown","effort":"unknown"}}')

    def test_generated_response_requires_strict_contract_even_without_prose(self):
        self.compose()
        with self.assertRaisesRegex(ValueError, 'REQUIRED_OUTPUT_CONTRACT_MISMATCH'): self.export()
        self.assertTrue((self.exported/'failure.json').is_file())
        self.assertFalse((self.exported/'receipt.json').exists())

    def test_response_relocates_with_originals_and_rejects_published_edit(self):
        self.strict(); self.compose(); self.export()
        copied = self.root/'relocated-export'; shutil.copytree(self.exported, copied)
        published = self.root/'response-copy.json'; published.write_bytes((copied/'response.json').read_bytes())
        module.verify_response(copied, published)
        published.write_text('{"rows":[]}')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_STRUCTURED_RESPONSE_DIFFERS'): module.verify_response(copied, published)

    def test_derived_version_and_complete_ingress_hashes(self):
        self.sources([('first','json',{'common_cash':17}),('second','text','Unselected context.')]); self.strict()
        self.compose(); self.export(); result=json.loads((self.exported/'response.json').read_bytes())
        self.assertEqual(result['input_hashes'], {r['path']:r['sha256'] for r in json.loads(self.manifest.read_bytes())['sources']})
        self.assertEqual(result['candidate_version'], (module.source.ROOT/'VERSION').read_text().strip())

    def test_two_accounting_results_keep_separate_contexts(self):
        self.accounting(); request = copy.deepcopy(self.plan['sections'][0]); self.plan['sections'].append(request)
        self.strict(); self.compose(); self.export(); rows=json.loads((self.exported/'response.json').read_bytes())['rows']
        self.assertEqual([r['section_index'] for r in rows], [0,1])
        self.assertTrue(all(r['result']['eps'] is None for r in rows))
        self.assertTrue(all(r['result']['bound_fields'] for r in rows))

    def test_canonical_terminal_minimum_probe_and_dcf_unavailability(self):
        self.conclusion(); self.plan['sections'][1]['include_boundaries'] = True
        self.plan['sections'].append({'kind':'objective_conclusion','evidence_section':0,'objective_id':'DCF_DISCOUNT_CLOSURE','domain_scope':'SUPPLIED_ROWS'})
        self.strict(); self.compose(); self.export(); rows=json.loads((self.exported/'response.json').read_bytes())['rows']
        self.assertIn('threshold', rows[1]['result']['boundaries'][0])
        self.assertIn('above_probe', rows[1]['result']['boundaries'][0])
        self.assertEqual(rows[2]['result']['status'], 'NOT_EVALUATED')

    def test_real_response_cli_and_wrong_flag_rejection(self):
        self.strict(); self.compose(); metadata=self.root/'metadata.json'
        metadata.write_text(json.dumps({'case_id':'fictional-research','runtime_model_metadata':{'model':'unknown','effort':'unknown'}}))
        target=self.root/'export'; command=[sys.executable,'-B',module.__file__]
        done=subprocess.run(command+['response',str(self.output),'--metadata',str(metadata),'--output',str(target)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        done=subprocess.run(command+['verify-response',str(target),'--published-response',str(target/'response.json')],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        rejected=subprocess.run(command+['verify-response',str(target),'--rows','invented'],capture_output=True,text=True)
        self.assertNotEqual(rejected.returncode,0)
        workflow=[sys.executable,'-B',str(module.source.ROOT/'scripts/research_workflow.py')]
        target2=self.root/'workflow-export'
        done=subprocess.run(workflow+['final-response',str(self.output),'--response-metadata',str(metadata),
            '--private-output-dir',str(target2)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        checked=subprocess.run(workflow+['final-response-verify',str(target2),'--final-response',str(target2/'response.json')],capture_output=True,text=True)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
        self.assertEqual((target/'response.json').read_bytes(),(target2/'response.json').read_bytes())
        rejected=subprocess.run(workflow+['final-verify',str(self.output),'--response-metadata',str(metadata)],capture_output=True,text=True)
        self.assertNotEqual(rejected.returncode,0)

    def reit_fixture(self):
        from test_reit_sources import fixture
        request, original=fixture(); self.sources([('original','json',original)])
        self.plan={'sections':[{'kind':'source_report','producer':'reit_sources','request':request}]}
        return request, original

    def test_issuer_facts_full_result_and_topic_coverage_survive_export(self):
        from test_issuer_evidence import record
        import issuer_evidence
        self.sources([('primary','json',{'issuers':[record()], 'as_of':'2031-07-01',
            'events':[{'text':'Scheduled operational update.','event_date':'2031-07-10'}]})])
        self.plan={'output_contract':module.STRICT,'sections':[{'kind':'issuer_facts',
            'request':{'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},
                'research_plan':{'cadence':'QUARTERLY','rules':[
                    {'purpose':'REVIEW_THESIS','metric':'cfo_less_capex','operator':'gt',
                     'threshold':{'kind':'ANALYST_ASSUMPTION','value':0}},
                    {'purpose':'INVALIDATE_HYPOTHESIS','metric':'shares_point_change_percent','operator':'gt',
                     'threshold':{'kind':'ANALYST_ASSUMPTION','value':20}}],
                    'as_of_ref':{'source_id':'primary','pointer':'/as_of'},'event_window_days':30,
                    'events':[{'source_ref':{'source_id':'primary','pointer':'/events/0/text'},
                               'date_ref':{'source_id':'primary','pointer':'/events/0/event_date'}}]}}}]}
        self.compose(); self.export(); result=json.loads((self.exported/'response.json').read_bytes())['rows'][0]['result']
        self.assertEqual(set(result['topic_coverage']),set(issuer_evidence.TOPICS))
        self.assertIn('original_facts',result);self.assertIn('funding_comparisons',result)
        self.assertFalse(result['source_coverage']['all_corpus_semantics_reviewed'])
        self.assertEqual(result,json.loads((self.output/'sections/000/producer/result.json').read_bytes()))
        self.assertEqual(result['research_plan']['cadence'],'QUARTERLY')
        self.assertEqual(result['research_plan']['purpose_coverage'],{'REVIEW_THESIS':True,'INVALIDATE_HYPOTHESIS':True})
        self.assertEqual(result['research_plan']['events'][0]['timing_status'],'WITHIN_SELECTED_REVIEW_WINDOW')
        self.assertFalse(result['research_plan']['rules'][1]['objective_truth_established'])
        module.verify_response(self.exported)

    def test_reit_real_execution_final_bytes_and_receipt(self):
        self.reit_fixture(); receipt=self.compose()
        self.assertIn('source-record compatible arithmetic',self.report())
        self.assertEqual(module.verify(self.output)['final_response_sha256'],receipt['final_response_sha256'])
        self.assertFalse(receipt['whole_report_semantic_pass'])

    def test_original_property_fact_survives_omitted_requested_rows(self):
        request, original=self.reit_fixture(); request['document'].pop('property_fractions',None)
        original['portfolio']={'largest_tenant_revenue_fraction':0.37}; self.sources([('original','json',original)])
        self.strict(); self.compose(); self.export(); text=self.report()
        self.assertIn('0.37',text);self.assertIn('revenue',text);self.assertIn('unknown',text.lower())
        module.verify_response(self.exported)

    def test_multiple_reit_sections_preserve_order(self):
        self.reit_fixture(); self.plan['sections'].append(copy.deepcopy(self.plan['sections'][0]))
        self.plan['sections'][1]['request']['bindings']=[]; self.strict(); self.compose(); self.export()
        self.assertEqual([s['kind'] for s in module.verify(self.output)['sections']],['source_report','source_report'])
        self.assertIn('conditional', self.report().lower())
        rows=json.loads((self.exported/'response.json').read_bytes())['rows']
        self.assertNotEqual(rows[0]['result'],rows[1]['result'])
        self.assertIn('UNRESOLVED', json.dumps(rows[1]['result']))


    def missing_terminal_role(self):
        self.terminal()
        path = self.originals/'model.source'
        value = json.loads(path.read_bytes()); value.pop('role')
        self.sources([('model', 'json', value), ('other', 'text', 'Unresolved context retained.')])
        return value

    def prepare(self):
        self.request.write_text(json.dumps(self.plan), encoding='utf8')
        return module.prepare(self.request, self.output, self.manifest, self.pin, self.originals)

    def test_readiness_missing_role_retains_diagnostics_without_first_answer(self):
        self.missing_terminal_role(); self.strict()
        with self.assertRaisesRegex(ValueError, 'STRICT_TERMINAL_PREPARATION_NOT_READY'): self.compose()
        for name in ('first-response.md', 'analysis.json', 'receipt.json', 'preparation.json', 'response.json'):
            self.assertFalse((self.output/name).exists(), name)
        result = json.loads((self.output/'sections/000/workflow/result.json').read_bytes())
        self.assertEqual(result['jobs'][0]['status'], 'REJECTED_INPUT')
        self.assertIn('INPUT_ROLE_REQUIRED', result['jobs'][0]['reason'])
        self.assertEqual(json.loads((self.output/'original-plan.json').read_bytes()), self.plan)
        self.assertTrue((self.output/'failure.json').is_file())

    def test_readiness_explicit_assumption_corrects_new_attempt_not_originals(self):
        value = self.missing_terminal_role(); self.strict()
        with self.assertRaisesRegex(ValueError, 'STRICT_TERMINAL_PREPARATION_NOT_READY'): self.prepare()
        failed = self.output; retained = module.source.file_inventory(failed)
        original = (self.originals/'model.source').read_bytes()
        self.output = self.root/'corrected'
        self.plan['sections'][0]['document'] = {
            key: {'$source': {'id': 'model', 'pointer': '/' + key}} for key in value}
        self.plan['sections'][0]['document']['role'] = {
            '$assumption': 'hypothetical_scenario', 'reason': 'Explicitly declared scenario model, not an observation.'}
        prepared = self.prepare()
        self.assertFalse((self.output/'first-response.md').exists())
        self.assertEqual(prepared['status'], 'PREPARED_FOR_FINALIZATION')
        finalized = module.finalize(self.output, prepared['preparation_sha256'])
        self.assertEqual(finalized['sections'][0]['job_status'], 'COMPUTED')
        self.assertEqual((self.originals/'model.source').read_bytes(), original)
        self.assertEqual(module.source.file_inventory(failed), retained)
        module.verify(self.output)

    def test_readiness_unsupported_role_is_not_normalized(self):
        self.terminal(); value = json.loads((self.originals/'model.source').read_bytes())
        value['role'] = 'trust_this_model'
        self.sources([('model', 'json', value)]); self.strict()
        with self.assertRaisesRegex(ValueError, 'STRICT_TERMINAL_PREPARATION_NOT_READY'): self.compose()
        arguments = json.loads((self.output/'sections/000/workflow/jobs/0000/arguments.json').read_bytes())
        self.assertEqual(arguments['document']['role'], 'trust_this_model')
        self.assertFalse((self.output/'first-response.md').exists())

    def test_readiness_negative_return_and_unknown_dcf_are_valid(self):
        self.terminal(); self.strict(); receipt = self.compose()
        self.assertEqual(receipt['readiness_policy'], module.READINESS)
        result = self.analysis()['sections'][0]['result']['jobs'][0]['result']
        self.assertLess(float(result['scenarios'][0]['net_total_return_fraction']), 0)
        self.assertIn('DCF discount closure: unavailable', self.report())
        self.export(); module.verify_response(self.exported)

    def test_readiness_legacy_rejection_still_renders_and_replays(self):
        self.missing_terminal_role(); self.compose()
        self.assertIn('REJECTED_INPUT', self.report())
        self.assertEqual(module.verify(self.output)['output_contract'], module.LEGACY)
        with self.assertRaisesRegex(ValueError, 'REQUIRED_OUTPUT_CONTRACT_MISMATCH'): self.export()

    def test_preparation_changed_plan_blocks_finalization(self):
        prepared = self.prepare()
        path = self.output/'original-plan.json'; path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_PLAN_CHANGED'):
            module.finalize(self.output, prepared['preparation_sha256'])
        self.assertFalse((self.output/'first-response.md').exists())

    def test_preparation_changed_source_blocks_finalization(self):
        prepared = self.prepare()
        (self.output/'originals/filing.source').write_text('{"common_cash":18}')
        with self.assertRaises(ValueError): module.finalize(self.output, prepared['preparation_sha256'])
        self.assertFalse((self.output/'first-response.md').exists())

    def test_preparation_changed_implementation_blocks_finalization(self):
        prepared = self.prepare(); changed = module.source.implementations() | {'unretained.py': '0'*64}
        with mock.patch.object(module.source, 'implementations', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'FINAL_REPORT_IMPLEMENTATION_CHANGED'):
                module.finalize(self.output, prepared['preparation_sha256'])
        self.assertFalse((self.output/'first-response.md').exists())

    def test_preparation_pin_and_duplicate_finalization_refuse_overwrite(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(ValueError, 'PREPARATION_PIN_CHANGED'):
            module.finalize(self.output, '0'*64)
        module.finalize(self.output, prepared['preparation_sha256']); original = (self.output/'first-response.md').read_bytes()
        with self.assertRaisesRegex(ValueError, 'UNFINALIZED_SUCCESSFUL_PREPARATION_REQUIRED'):
            module.finalize(self.output, prepared['preparation_sha256'])
        self.assertEqual((self.output/'first-response.md').read_bytes(), original)

    def test_rehashed_legacy_rejection_cannot_be_promoted_to_strict_replay_or_export(self):
        self.missing_terminal_role(); self.compose()
        self.strict(); raw = module.encoded(self.plan)
        (self.output/'original-plan.json').write_bytes(raw)
        path = self.output/'context.json'; context = json.loads(path.read_bytes())
        context['plan_sha256'] = module.source.digest(raw); path.write_bytes(module.source.encode(context))
        self.resign_inventory()
        with self.assertRaisesRegex(ValueError, 'STRICT_TERMINAL_PREPARATION_NOT_READY'): module.replay(self.output)
        with self.assertRaisesRegex(ValueError, 'STRICT_TERMINAL_PREPARATION_NOT_READY'): self.export()
        self.assertFalse((self.exported/'response.json').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
