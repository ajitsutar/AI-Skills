"""Fictional research records exercise replay, completion and numeric selection."""
import copy
import importlib.metadata
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cash_benchmark import review_cash_benchmark
from horizon_review import resolve_horizon, review_scenarios
from personal_runtime import doctor
from research_bundle import create_bundle, verify_bundle, compare_bundles, canonical_hash
from screen_review import review_screen


def fixture():
    return json.loads((ROOT/'examples/fictional-ranked-screen.json').read_text(encoding='utf-8'))


def several():
    doc = fixture()
    original = copy.deepcopy(doc)
    names = ['ZETA', 'ALPHA', 'BETA']
    doc['universe']['symbols'] = names
    for key in ('screening', 'candidates', 'ranking_inputs'):
        doc[key] = []
        for symbol in names:
            row = copy.deepcopy(original[key][0])
            row['symbol'] = symbol
            if key == 'candidates':
                row['horizon_review']['event_calendar']['symbol'] = symbol
            doc[key].append(row)
    doc['report'].update(stage='draft', kind='screened_hypotheses', ranked_symbols=[], selection_rationale={})
    doc['ranking_spec']['selection_count'] = 2
    return doc


class ResearchIntegrityTests(unittest.TestCase):
    def test_empty_candidates_cannot_hide_misplaced_schedule(self):
        doc = fixture()
        doc['candidates'] = []
        doc['horizon']['event_policy'].update(coverage_mode='rolling_review', next_review_at='2026-02-01T14:00:00Z')
        with self.assertRaisesRegex(ValueError, 'horizon.review_schedule'):
            review_screen(doc)

    def test_empty_candidates_cannot_hide_invalid_event_contract(self):
        for key, value in [('scope', 'bad'), ('before_sessions', -1), ('after_sessions', True),
                           ('max_age_seconds', 0), ('blocked_kinds', 'earnings'), ('coverage_mode', 'bad')]:
            doc = fixture()
            doc['candidates'] = []
            doc['horizon']['event_policy'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review_screen(doc)

    def test_missing_rolling_schedule_rejected_before_candidates(self):
        doc = fixture()
        doc['candidates'] = []
        doc['horizon']['event_policy']['coverage_mode'] = 'rolling_review'
        with self.assertRaisesRegex(ValueError, 'horizon.review_schedule'):
            review_screen(doc)

    def test_draft_incomplete_and_complete_are_distinct(self):
        doc = fixture()
        self.assertEqual(review_screen(doc)['completion']['status'], 'COMPLETE')
        doc['report']['stage'] = 'draft'
        self.assertEqual(review_screen(doc)['completion']['status'], 'DRAFT')
        doc['candidates'] = []
        doc['report'].update(ranked_symbols=[], selection_rationale={})
        self.assertEqual(review_screen(doc)['completion']['status'], 'INCOMPLETE')

    def test_cli_strict_final_cannot_succeed_for_missing_reviews(self):
        doc = fixture()
        doc.pop('ranking_spec')
        doc['candidates'] = []
        doc['report'].update(stage='draft', ranked_symbols=[], selection_rationale={})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'input.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT/'scripts/screen_review.py'), str(path)]
            draft = subprocess.run(command, capture_output=True, text=True)
            final = subprocess.run(command+['--strict-final'], capture_output=True, text=True)
            self.assertEqual(draft.returncode, 0, draft.stderr)
            self.assertEqual(final.returncode, 2, final.stderr)
            self.assertEqual(json.loads(final.stdout)['completion']['status'], 'INCOMPLETE')

    def test_final_stage_enforces_cli_completion_without_flag(self):
        doc = fixture()
        doc.pop('ranking_spec')
        doc['candidates'] = []
        doc['report'].update(ranked_symbols=[], selection_rationale={})
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/screen_review.py'),str(path)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2,run.stderr)

    def test_bundle_replays_full_inputs_and_named_results(self):
        bundle = create_bundle(fixture())
        result = verify_bundle(bundle)
        self.assertEqual(result['status'], 'REPLAY_MATCH')
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(bundle['result']['ranking']['selected_symbols'], ['FICTION_VALUE'])

    def test_bundle_rejects_changed_inputs(self):
        bundle = create_bundle(fixture())
        bundle['input_document']['candidates'] = []
        with self.assertRaisesRegex(ValueError, 'input hash'):
            verify_bundle(bundle)

    def test_bundle_rejects_fabricated_results_even_with_rehashed_output(self):
        bundle = create_bundle(fixture())
        bundle['result']['candidates'] = []
        bundle['result_sha256'] = canonical_hash(bundle['result'])
        with self.assertRaisesRegex(ValueError, 'do not reproduce'):
            verify_bundle(bundle)

    def test_bundle_rejects_different_code_or_dependencies(self):
        for field in ('skill_version', 'dependencies', 'source_sha256'):
            bundle = create_bundle(fixture())
            bundle['implementation'][field] = 'altered'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'code/version/dependencies'):
                verify_bundle(bundle)

    def test_comparison_explains_changed_numeric_input(self):
        a = fixture()
        b = copy.deepcopy(a)
        b['ranking_inputs'][0]['metrics']['peer_discount'] = '0.4'
        result = compare_bundles(create_bundle(a), create_bundle(b))
        self.assertEqual(result['differing_components'], ['ranking_inputs'])
        self.assertTrue(result['same_picks'])

    def test_complete_watch_report_is_not_a_buy_report(self):
        doc = fixture()
        doc.pop('ranking_spec')
        doc['report']['kind'] = 'screened_hypotheses'
        doc['candidates'][0]['checks']['cash_support']['status'] = 'unresolved'
        result = review_screen(doc)
        self.assertEqual(result['completion']['status'], 'COMPLETE')
        self.assertEqual(result['completion']['eligible_candidates'], 0)
        self.assertEqual(result['candidates'][0]['status'], 'Watch')

    def test_zero_retained_candidates_does_not_force_quota(self):
        doc = fixture()
        doc.pop('ranking_spec')
        doc['screening'][0]['outcome'] = 'excluded'
        doc['candidates'] = []
        doc['report'].update(ranked_symbols=[], selection_rationale={})
        self.assertEqual(review_screen(doc)['completion']['status'], 'COMPLETE')


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        doc = fixture()
        self.resolved = resolve_horizon(doc['horizon'])
        self.scenarios = doc['candidates'][0]['horizon_review']['terminal_scenarios']
        self.cash = self.scenarios['cash_benchmark']

    def test_annual_rate_converted_for_exact_interval(self):
        self.cash.update(basis='annual_simple',rate_or_return=.04,day_count='ACT/365F')
        result=review_cash_benchmark(self.cash,self.resolved)
        from price_audit import timestamp
        years=(timestamp(self.resolved['exit_at'])-timestamp(self.resolved['entry_at'])).total_seconds()/86400/365
        self.assertAlmostEqual(result['holding_period_return'],.04*years)
        self.assertLess(result['holding_period_return'],.011)

    def test_effective_compounding_and_short_intraday_interval(self):
        self.cash.update(basis='annual_effective',rate_or_return=.04,day_count='ACT/365F')
        self.resolved['exit_at']='2026-01-15T20:00:00Z'
        self.cash.update(exit_at=self.resolved['exit_at'],instrument_maturity_at=self.resolved['exit_at'])
        result=review_cash_benchmark(self.cash,self.resolved)
        self.assertAlmostEqual(result['holding_period_return'],1.04**(5/24/365)-1)

    def test_stale_future_or_mismatched_benchmark_is_unverified(self):
        for key,value in [('observed_at','2025-08-01T14:00:00Z'),('observed_at','2026-01-16T14:00:00Z'),
                          ('exit_at','2027-01-15T20:00:00Z'),('entry_at','2026-01-15T16:00:00Z'),
                          ('basis','bill_discount_yield'),('rate_or_return',float('nan'))]:
            cash=copy.deepcopy(self.cash)
            cash[key]=value
            with self.subTest(key=key):
                self.assertIsNone(review_cash_benchmark(cash,self.resolved)['holding_period_return'])

    def test_roll_or_early_sale_assumptions_required(self):
        for maturity in ('2026-02-15T19:45:00Z','2027-04-15T19:45:00Z',None):
            self.cash['instrument_maturity_at']=maturity
            self.assertEqual(review_cash_benchmark(self.cash,self.resolved)['status'],'UNVERIFIED')
            self.cash['horizon_adjustment_evidence']=['Fictional rate/reinvestment or early-sale assumption, not guaranteed']
            self.assertEqual(review_cash_benchmark(self.cash,self.resolved)['status'],'CALCULATED_ASSUMPTION')
            self.cash.pop('horizon_adjustment_evidence')

    def test_missing_benchmark_preserves_arithmetic_but_not_cash_outperformance(self):
        self.scenarios.pop('cash_benchmark')
        result=review_scenarios(self.scenarios,self.resolved)
        self.assertTrue(result['arithmetic_valid'])
        self.assertFalse(result['complete'])
        self.assertIsNone(result['cases'][1]['excess_over_cash'])
        self.assertEqual(result['valuation_evidence_status'],'DECLARED_NOT_VERIFIED')

    def test_conflicting_legacy_percentage_is_rejected(self):
        self.scenarios['cash_benchmark_return']=.0386
        with self.assertRaisesRegex(ValueError,'conflicts'):
            review_scenarios(self.scenarios,self.resolved)


class DeterministicSelectionTests(unittest.TestCase):
    def test_callers_decimal_precision_cannot_change_picks_or_scores(self):
        from decimal import localcontext
        doc=several()
        expected=review_screen(doc)['ranking']['scores']
        with localcontext() as context:
            context.prec=2
            self.assertEqual(review_screen(doc)['ranking']['scores'],expected)

    def test_model_name_and_row_order_cannot_change_picks(self):
        doc=several()
        first=review_screen(doc)['ranking']
        doc['run_spec']['model_context']='Different model; never a scoring input'
        for key in ('candidates','ranking_inputs','screening'):
            doc[key].reverse()
        second=review_screen(doc)['ranking']
        self.assertEqual(first['selected_symbols'],['ALPHA','BETA'])
        self.assertEqual(first['selected_symbols'],second['selected_symbols'])
        self.assertEqual(first['scores'],second['scores'])

    def test_missing_metrics_and_stale_data_do_not_receive_imputed_scores(self):
        doc=several()
        doc['ranking_inputs'][1]['metrics'].pop('peer_discount')
        doc['ranking_inputs'][2]['observed_at']='2026-01-01T14:00:00Z'
        result=review_screen(doc)['ranking']
        self.assertEqual(result['selected_symbols'],['ZETA'])
        self.assertEqual(len(result['excluded']),2)

    def test_no_watch_or_event_blocked_promotion_by_score(self):
        doc=several()
        doc['candidates'][1]['checks']['cash_support']['status']='unresolved'
        doc['candidates'][2]['event_review']['status']='blocked'
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['ZETA'])

    def test_group_cap_and_filter_are_deterministic(self):
        doc=several()
        doc['ranking_spec']['max_per_group']=1
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['ALPHA'])
        doc['ranking_inputs'][1]['metrics']['peer_discount']='-0.1'
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['BETA'])

    def test_profile_changes_are_hashed(self):
        doc=several()
        before=review_screen(doc)['ranking']['profile_sha256']
        doc['ranking_spec']['criteria'][0]['weight']='0.5'
        doc['ranking_spec']['criteria'][1]['weight']='0.5'
        self.assertNotEqual(before,review_screen(doc)['ranking']['profile_sha256'])

    def test_incomplete_snapshot_or_bad_weights_cannot_rank(self):
        for operation in ('row','weight','nan','boolean'):
            doc=several()
            if operation=='row': doc['ranking_inputs'].pop()
            elif operation=='weight': doc['ranking_spec']['criteria'][0]['weight']='0.7'
            elif operation=='nan': doc['ranking_inputs'][0]['metrics']['peer_discount']='NaN'
            else: doc['ranking_inputs'][0]['metrics']['peer_discount']=True
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                review_screen(doc)

    def test_final_prose_ranking_cannot_override_computed_order(self):
        doc=several()
        doc['report'].update(stage='final',ranked_symbols=['BETA','ALPHA'],selection_rationale={'BETA':'fixture','ALPHA':'fixture'})
        with self.assertRaisesRegex(ValueError,'match deterministic'):
            review_screen(doc)

    def test_higher_unreviewed_contender_prevents_complete_final_report(self):
        doc=several()
        doc['candidates']=[r for r in doc['candidates'] if r['symbol']!='ALPHA']
        doc['screening'][1]['outcome']='not_advanced'
        doc['report'].update(stage='final',ranked_symbols=['BETA','ZETA'],selection_rationale={'BETA':'fixture','ZETA':'fixture'})
        result=review_screen(doc)
        self.assertEqual(result['ranking']['blocking_review_queue'],['ALPHA'])
        self.assertIn('HIGHER_RANKED_CONTENDERS_NEED_REVIEW',result['completion']['reasons'])

    def test_speculative_requires_explicit_profile_and_complete_evidence(self):
        doc=several()
        doc['candidates'][1]['checks']['balance_sheet']['status']='material_risk'
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['BETA','ZETA'])
        doc['ranking_spec']['allowed_statuses'].append('Speculative')
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['ALPHA','BETA'])
        doc['candidates'][1]['primary_review']['status']='unresolved'
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['BETA','ZETA'])

    def test_lower_is_better_direction_and_clipping(self):
        doc=several()
        doc['ranking_spec']['criteria'][0]['direction']='lower'
        doc['ranking_spec']['minimum_score']='0'
        doc['ranking_inputs'][0]['metrics']['peer_discount']='1.5'
        doc['ranking_inputs'][1]['metrics']['peer_discount']='0.1'
        self.assertEqual(review_screen(doc)['ranking']['selected_symbols'],['ALPHA','BETA'])


class CapabilityTests(unittest.TestCase):
    def test_missing_arch_is_visible_without_blocking_research(self):
        original=importlib.metadata.version
        def version(name):
            if name=='arch':
                raise importlib.metadata.PackageNotFoundError(name)
            return original(name)
        with tempfile.TemporaryDirectory() as temp, patch('personal_runtime.importlib.metadata.version',side_effect=version):
            result=doctor(temp)
        self.assertEqual(result['checks']['garch_capability'],'SKIPPED_MISSING_DEPENDENCIES')
        self.assertIn('MISSING_DEPENDENCY:arch',result['warnings'])
        self.assertNotIn('MISSING_DEPENDENCY:arch',result['failures'])
        self.assertEqual(result['checks']['skill_version'],(ROOT/'VERSION').read_text().strip())


if __name__=='__main__':
    unittest.main()
