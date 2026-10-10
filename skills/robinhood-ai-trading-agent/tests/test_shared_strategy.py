"""Fictional economic inputs: controls and parity, not investment performance."""
import copy
import json
import sys
import unittest
from unittest.mock import patch
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_portfolio import construct
from deterministic_rank import digest
from research_bundle import create_bundle, verify_bundle, compare_bundles
from screen_review import review_screen
from horizon_review import review_primary, resolve_horizon
from price_audit import timestamp
from research_preflight import check as preflight
from vqm_research import calculate, profile, raw_metrics, session_grid, prepare_document


def snapshot():
    grid = session_grid('2026-10-09T15:00:00Z')
    cutoff = grid[-1]['close']
    sources = [dict(source_id=kind, kind=kind, uri='https://example.org/fictional/' + kind,
                    content_sha256=digest('fictional-' + kind),
                    published_at='2026-08-01T12:00:00Z' if kind == 'financial' else cutoff,
                    retrieved_at='2026-10-09T15:02:00Z', provider='fictional', origin='regulatory_filing')
               for kind in ('financial', 'market', 'identity')]
    doc = dict(schema_version=1, profile_sha256=digest(profile()), snapshot_id='FICTIONAL-VQM-1',
               universe_id='FICTIONAL-8', benchmark_id='FICTIONAL-TOTAL-RETURN',
               taxonomy_version='GICS-fixture', market_provider='fictional', universe_provider='fictional',
               decision_at='2026-10-09T15:00:00Z', information_cutoff=cutoff,
               contract_defined_at='2026-10-09T14:00:00Z', retrieval_started_at='2026-10-09T15:01:00Z',
               calendar_reviewed_through=grid[-1]['date'], calendar_evidence='Fictional session review for tests',
               sources=sources, universe_symbols=[], rows=[], fictional=True)
    for i in range(8):
        name = 'DEMO' + str(i)
        values = dict(assets=200, assets_prior=180, ebit_ttm=10 + i, cfo_ttm=12 + i,
                      capex_ttm=4, net_income_ttm=8 + i, debt=30 - i, cash=10,
                      preferred_equity=0, noncontrolling_interest=0)
        facts = {k: dict(value=v, unit='USD', source_id='financial', period_end='2026-06-30',
                        **({'period_start': '2025-07-01'} if k.endswith('_ttm') else {}),
                        **({'balance_date': '2025-06-30'} if k.endswith('_prior') else {})) for k, v in values.items()}
        facts.update({k: dict(value=v, unit='USD', source_id='market', period_end=grid[-1]['date'], observed_at=cutoff)
                      for k, v in dict(market_cap=100, close_price=25, adv20=50).items()})
        row = dict(symbol=name, issuer_id=name, sector_code='20', industry_code='201010',
                   identity_source_id='identity', membership_as_of=grid[-1]['date'], identity_conflicts=[],
                   data_status='complete', financial_period_end='2026-06-30', ttm_start='2025-07-01',
                   currency='USD', accounting_basis='reported_gaap_ttm', latest_public_period_checked=True,
                   source_conflicts=[], market_cap_scope='all_common_share_classes', facts=facts,
                   total_return_history=dict(source_id='market', dates=[s['date'] for s in grid],
                     values=[100 + (i + 1) * j / 100 for j in range(253)],
                     corporate_actions_reviewed=True, unresolved_actions=[], audit_evidence='Fictional audited TRI'))
        doc['rows'].append(row)
        doc['universe_symbols'].append(name)
    return doc


def screen():
    doc = json.loads((ROOT / 'examples/fictional-ranked-screen.json').read_text(encoding='utf-8'))
    doc['fictional'] = True
    snap = snapshot()
    doc.pop('horizon')
    doc.pop('ranking_spec')
    doc.pop('ranking_inputs')
    doc['decision_mode'] = 'long_term'
    doc['research_as_of'] = snap['information_cutoff']
    doc['shared_strategy'] = dict(profile_id='vqm-fundamental', profile_version='1.0.0', selection_count=2)
    doc['vqm_snapshot'] = snap
    doc['universe'].update(name='Fictional VQM universe', symbols=snap['universe_symbols'], as_of=snap['information_cutoff'])
    doc['screening'] = [dict(symbol=s, outcome='not_advanced', reason='Awaiting primary review in computed order',
                             evidence=['Fictional snapshot']) for s in snap['universe_symbols']]
    doc['candidates'] = []
    doc['report'] = dict(kind='screened_hypotheses', stage='draft', ranked_symbols=[], selection_rationale={})
    doc['run_spec'].update(methodology_version='vqm-fundamental-1.0.0',
                           mandate='Fictional fundamental research; no recommendation or empirical validation',
                           input_snapshot=['embedded fictional vqm_snapshot'])
    return doc


def portfolio():
    return dict(profile_sha256='fictional-profile', horizon_id='1y-fixed', benchmark_id='fictional-benchmark',
        management_mode='fixed_hold', as_of='2026-10-09T20:00:00Z',
        calibration=dict(profile_sha256='fictional-profile', horizon_id='1y-fixed',
            benchmark_id='fictional-benchmark', management_mode='fixed_hold',
            units='holding_period_excess_total_return_decimal', frozen_at='2020-01-01T00:00:00Z',
            test_start='2021-01-01T00:00:00Z', test_end='2025-01-01T00:00:00Z',
            evidence=['FICTIONAL calibration: schema example only, never live evidence']),
        assets=[dict(symbol='A', issuer='A', sector='S', themes=['T'], eligible=True, alpha=0.04,
                     benchmark_weight=0.5, previous_weight=0.5, one_way_cost=0.001, max_weight=0.7),
                dict(symbol='B', issuer='B', sector='S', themes=['T'], eligible=True, alpha=0,
                     benchmark_weight=0.5, previous_weight=0.5, one_way_cost=0.001, max_weight=0.7)],
        covariance_symbols=['A', 'B'], covariance_horizon_id='1y-fixed', covariance=[[0.04, 0], [0, 0.04]],
        constraints=dict(risk_aversion=2, issuer_cap=0.7, sector_active_cap=0.1, theme_cap=1, turnover_cap=0.2),
        fictional=True)


def fixed_screen():
    doc = screen()
    source = json.loads((ROOT / 'examples/fictional-ranked-screen.json').read_text(encoding='utf-8'))
    horizon = source['horizon']
    horizon.update(as_of=doc['research_as_of'], entry_at='2026-10-09T15:00:00Z',
                   latest_entry_at='2026-10-09T19:00:00Z', anchor_date='2026-10-09',
                   strategy_route='long_term', duration={'unit': 'calendar_years', 'value': 1})
    horizon['event_policy']['coverage_mode'] = 'rolling_review'
    horizon['review_schedule'] = dict(next_review_at='2027-01-08T15:00:00Z', cadence='quarterly and material news', evidence=['Fictional review schedule'])
    doc.update(decision_mode='fixed_horizon', horizon=horizon)
    exit_at = resolve_horizon(horizon)['exit_at']
    for symbol in ('DEMO7', 'DEMO6'):
        candidate = copy.deepcopy(source['candidates'][0])
        candidate['symbol'] = symbol
        candidate['primary_review'].update(latest_public_period_end='2026-06-30', reviewed_period_end='2026-06-30',
            latest_published_at='2026-08-01T12:00:00Z', checked_at='2026-10-09T15:03:00Z',
            information_as_of=doc['research_as_of'], point_in_time_evidence=['Fictional archived filings index'])
        event = candidate['horizon_review']['event_calendar']
        event.update(symbol=symbol, checked_at='2026-10-09T15:03:00Z', information_as_of=doc['research_as_of'],
            point_in_time_evidence=['Fictional archived event calendar'], coverage_start='2026-10-01T00:00:00Z',
            coverage_end='2027-01-20T23:00:00Z', events=[])
        case = candidate['horizon_review']['terminal_scenarios']
        case.update(exit_at=exit_at, entry_price=25, scenario_basis='issuer_specific_valuation',
                    distributions_review={'status': 'reviewed', 'assumption': 'Fictional issuer has no distributions', 'evidence': ['Fictional distribution policy']})
        for c, price in zip(case['cases'], (18, 28, 35)):
            c['terminal_price'] = price
        case['cash_benchmark'].update(observed_at=doc['research_as_of'], entry_at=horizon['entry_at'],
                                     exit_at=exit_at, instrument_maturity_at=exit_at)
        doc['candidates'].append(candidate)
        next(r for r in doc['screening'] if r['symbol'] == symbol)['outcome'] = 'retained'
    doc['report'].update(stage='final', kind='eligible_comparison', ranked_symbols=['DEMO7', 'DEMO6'],
                         selection_rationale={s: 'Fictional complete evidence; computed VQM order, no investment claim' for s in ('DEMO7', 'DEMO6')})
    return doc


class SharedStrategyTests(unittest.TestCase):
    def test_formula_rank_and_fixed_family_weights(self):
        s = snapshot()
        r = calculate(s)
        self.assertEqual(r['status'], 'COMPUTED')
        self.assertEqual(r['discovery_order'], ['DEMO' + str(i) for i in reversed(range(8))])
        top = r['scores'][0]
        # Highest Value and Momentum midrank = .875; cash-conversion ties at 0.
        self.assertEqual(Decimal(top['value']), Decimal('.875'))
        self.assertEqual(Decimal(top['momentum']), Decimal('.875'))
        self.assertAlmostEqual(float(top['quality']), (0.875 + 0 + 0.875) / 3)
        self.assertAlmostEqual(float(top['score']), (0.875 + (1.75 / 3) + 0.875) / 3)

    def test_input_order_does_not_change_picks(self):
        s = snapshot()
        before = calculate(s)
        s['rows'].reverse()
        s['universe_symbols'].reverse()
        self.assertEqual(before['scores'], calculate(s)['scores'])

    def test_decimal_context_does_not_change_scores(self):
        s = snapshot()
        expected = calculate(s)
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(calculate(s), expected)

    def test_ties_use_exact_symbol(self):
        s = snapshot()
        for row in s['rows']:
            row['facts'] = copy.deepcopy(s['rows'][0]['facts'])
            row['total_return_history'] = copy.deepcopy(s['rows'][0]['total_return_history'])
        self.assertEqual(calculate(s)['discovery_order'], sorted(s['universe_symbols']))

    def test_negative_earnings_remain_signed(self):
        s = snapshot()
        s['rows'][0]['facts']['ebit_ttm']['value'] = -5
        r = calculate(s)
        self.assertEqual(r['status'], 'COMPUTED')
        row = next(r for r in r['scores'] if r['symbol'] == 'DEMO0')
        self.assertLess(Decimal(row['value_raw'][0]), 0)

    def test_wrong_profile_rejected(self):
        s = snapshot()
        s['profile_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'PROFILE_HASH'):
            calculate(s)

    def test_future_financial_not_used(self):
        s = snapshot()
        s['sources'][0]['published_at'] = '2026-10-09T14:00:00Z'
        r = calculate(s)
        self.assertFalse(r['scores'])
        self.assertTrue(all('FUTURE_SOURCE' in x['reason'] for x in r['missing']))

    def test_source_cannot_predate_reported_period(self):
        s = snapshot()
        s['sources'][0]['published_at'] = '2025-08-01T12:00:00Z'
        r = calculate(s)
        self.assertFalse(r['scores'])
        self.assertTrue(all('SOURCE_PREDATES_FINANCIAL_PERIOD' in x['reason'] for x in r['missing']))

    def test_prior_balance_may_come_from_its_original_filing(self):
        s = snapshot()
        prior = copy.deepcopy(s['sources'][0])
        prior.update(source_id='prior-financial', published_at='2025-08-01T12:00:00Z')
        s['sources'].append(prior)
        for row in s['rows']:
            row['facts']['assets_prior']['source_id'] = prior['source_id']
        self.assertEqual(calculate(s)['status'], 'COMPUTED')

    def test_preflight_checks_transitive_files_and_separates_optional_tools(self):
        original = Path.is_file
        def missing_rank(path):
            return False if path.name == 'deterministic_rank.py' else original(path)
        with patch.object(Path, 'is_file', missing_rank):
            r = preflight()
            self.assertEqual(r['shared_default'], 'UNAVAILABLE')
            self.assertIn('scripts/deterministic_rank.py', r['missing_files'])
        def missing_garch(path):
            return False if path.name == 'garch_volatility.py' else original(path)
        with patch.object(Path, 'is_file', missing_garch):
            r = preflight()
            self.assertEqual(r['shared_default'], 'AVAILABLE')
            self.assertEqual(r['volatility'], 'SKIPPED_MISSING_COMPONENTS')

    def test_primary_review_cannot_certify_stale_factors(self):
        s = screen()
        s['candidates'] = [dict(symbol='DEMO7', primary_review=dict(latest_public_period_end='2026-09-30', reviewed_period_end='2026-09-30'))]
        with self.assertRaisesRegex(ValueError, 'PRIMARY_FACTOR_PERIOD_MISMATCH'):
            review_screen(s)

    def test_common_stress_cannot_certify_issuer_valuation(self):
        s = screen()
        s['candidates'] = [dict(symbol='DEMO7', horizon_review={'terminal_scenarios': {'scenario_basis': 'uniform_stress'}})]
        with self.assertRaisesRegex(ValueError, 'COMMON_STRESS'):
            prepare_document(s)

    def test_dividends_cash_age_and_price_require_consistent_basis(self):
        base = dict(scenario_basis='issuer_specific_valuation', entry_price=25,
                    distributions_review={'status': 'reviewed', 'evidence': ['fictional no-distribution policy'], 'assumption': 'zero ordinary dividends'},
                    cash_benchmark={'max_age_seconds': 604800})
        for key, value, reason in [('distributions_review', {}, 'DISTRIBUTIONS_REVIEW'),
                                   ('entry_price', 24, 'SCENARIO_PRICE'),
                                   ('cash_benchmark', {'max_age_seconds': 31536000}, 'CASH_BENCHMARK')]:
            s = screen()
            case = copy.deepcopy(base)
            case[key] = value
            s['candidates'] = [dict(symbol='DEMO7', horizon_review={'terminal_scenarios': case})]
            with self.assertRaisesRegex(ValueError, reason):
                prepare_document(s)

    def test_current_session_price_rejected(self):
        s = snapshot()
        s['information_cutoff'] = '2026-10-09T20:00:00Z'
        with self.assertRaisesRegex(ValueError, 'CUTOFF_NOT_LAST'):
            calculate(s)

    def test_missing_value_not_reweighted(self):
        s = snapshot()
        s['rows'][0]['facts'].pop('capex_ttm')
        r = calculate(s)
        self.assertEqual(r['status'], 'INCOMPLETE')
        self.assertNotIn('DEMO0', r['discovery_order'])
        self.assertTrue(any('capex_ttm' in x['reason'] for x in r['missing']))

    def test_provider_and_membership_not_silently_changed(self):
        s = snapshot()
        s['sources'][1]['provider'] = 'alternate'
        with self.assertRaisesRegex(ValueError, 'PROVIDER_CHANGED'):
            calculate(s)
        s = snapshot()
        s['rows'][0]['membership_as_of'] = '2026-10-07'
        self.assertTrue(any('MEMBERSHIP_DATE' in x['reason'] for x in calculate(s)['missing']))

    def test_duplicate_issuer_picks_liquid_class(self):
        s = snapshot()
        extra = copy.deepcopy(s['rows'][0])
        extra['symbol'] = 'DEMO0.B'
        extra['facts']['adv20']['value'] = 60
        s['universe_symbols'].append(extra['symbol'])
        s['rows'].append(extra)
        r = calculate(s)
        self.assertIn('DEMO0.B', r['discovery_order'])
        self.assertNotIn('DEMO0', r['discovery_order'])
        self.assertEqual(r['excluded'][0]['representative'], 'DEMO0.B')

    def test_incomplete_class_blocks_issuer(self):
        s = snapshot()
        extra = copy.deepcopy(s['rows'][0])
        extra['symbol'] = 'DEMO0.B'
        extra['facts'].pop('adv20')
        s['universe_symbols'].append(extra['symbol'])
        s['rows'].append(extra)
        r = calculate(s)
        self.assertNotIn('DEMO0', r['discovery_order'])
        self.assertTrue(any(x['symbol'] == 'DEMO0' and 'ISSUER_SELECTION' in x['reason'] for x in r['missing']))

    def test_momentum_skips_last_21_sessions(self):
        s = snapshot()
        expected = calculate(s)['scores']
        s['rows'][0]['total_return_history']['values'][-21:] = [10000] * 21
        self.assertEqual(calculate(s)['scores'], expected)

    def test_missing_session_and_unreviewed_action_are_gaps(self):
        for key, value in [('corporate_actions_reviewed', False), ('dates', [])]:
            s = snapshot()
            s['rows'][0]['total_return_history'][key] = value
            self.assertNotIn('DEMO0', calculate(s)['discovery_order'])

    def test_peer_fallback_is_published(self):
        s = snapshot()
        s['rows'][0]['industry_code'] = '202010'
        r = calculate(s)
        self.assertTrue(all(x['peer_level'] == 'sector' for x in r['scores']))

    def test_ttm_and_balance_dates_are_checked(self):
        for field, key, value in [('cfo_ttm', 'period_start', '2026-01-01'),
                                   ('assets_prior', 'balance_date', '2026-03-31')]:
            s = snapshot()
            s['rows'][0]['facts'][field][key] = value
            self.assertNotIn('DEMO0', calculate(s)['discovery_order'])

    def test_adapter_formulas(self):
        from price_audit import timestamp
        for industry, name in [('401010', 'bank'), ('403010', 'insurer'), ('402010', 'other_financial'), ('601010', 'equity_reit')]:
            s = snapshot()
            row = s['rows'][0]
            row.update(industry_code=industry, sector_code=industry[:2], ffo_basis='nareit_unadjusted_common')
            for k, value in dict(common_income_ttm=6, tangible_common_equity=40,
                                  tangible_common_equity_prior=20, cet1=12, risk_weighted_assets=100,
                                  nonperforming_loans=2, gross_loans=80, common_equity=40,
                                  common_equity_prior=20, ffo_common_ttm=15).items():
                row['facts'][k] = dict(value=value, source_id='financial', unit='USD', period_end='2026-06-30',
                                      period_start='2025-07-01', balance_date='2025-06-30')
            a, v, q = raw_metrics(row, {x['source_id']: x for x in s['sources']}, timestamp(s['information_cutoff']))
            self.assertEqual(a, name)
            if name == 'bank':
                self.assertEqual(v, [Decimal('.06'), Decimal('.4')])
                self.assertEqual(q, [Decimal('.2'), Decimal('.12'), Decimal('-.025')])
            elif name == 'equity_reit':
                self.assertEqual(v, [Decimal('.15'), Decimal('.08')])
            else:
                self.assertEqual(q, [Decimal('.2'), Decimal('.2'), Decimal('-.75')])

    def test_integration_blocks_unreviewed_contenders(self):
        r = review_screen(screen())
        self.assertEqual(r['completion']['status'], 'INCOMPLETE')
        self.assertEqual(r['ranking']['selected_symbols'], [])
        self.assertEqual(r['ranking']['blocking_review_queue'], ['DEMO' + str(i) for i in reversed(range(8))])

    def test_score_override_and_strong_buy_blocked(self):
        s = screen()
        s['ranking_spec'] = {'criteria': 'model-chosen'}
        with self.assertRaisesRegex(ValueError, 'SHARED_STRATEGY_OVERRIDE'):
            review_screen(s)
        s = screen()
        s['report']['recommendation_label'] = 'Strong Buy'
        with self.assertRaisesRegex(ValueError, 'STRONG_BUY_UNAVAILABLE'):
            review_screen(s)

    def test_intraday_profile_mismatch_rejected(self):
        s = screen()
        s['decision_mode'] = 'fixed_horizon'
        s['horizon'] = {'strategy_route': 'intraday'}
        with self.assertRaisesRegex(ValueError, 'NOT_A_SWING_OR_INTRADAY'):
            prepare_document(s)

    def test_snapshot_replays_and_changed_input_identified(self):
        s = screen()
        bundle = create_bundle(s)
        self.assertEqual(verify_bundle(bundle)['status'], 'REPLAY_MATCH')
        s['vqm_snapshot']['rows'][0]['facts']['ebit_ttm']['value'] = 100
        other = create_bundle(s)
        self.assertIn('vqm_snapshot', compare_bundles(bundle, other)['differing_components'])

    def test_full_one_year_contract_replays_with_fictional_eligible_decisions(self):
        doc = fixed_screen()
        result = review_screen(doc)
        self.assertEqual(result['completion']['status'], 'COMPLETE')
        self.assertEqual(result['ranking']['selected_symbols'], ['DEMO7', 'DEMO6'])
        self.assertEqual(result['horizon']['exit_session'], '2027-10-08')
        self.assertEqual(verify_bundle(create_bundle(doc))['status'], 'REPLAY_MATCH')
        self.assertFalse(result['shared_strategy']['strong_buy_available'])

    def test_overlap_does_not_pass_empty_or_partial_lists(self):
        partial = create_bundle(screen())
        self.assertEqual(compare_bundles(partial, partial)['overlap']['status'], 'INSUFFICIENT_FULL_LISTS')
        full = create_bundle(fixed_screen())
        result = compare_bundles(full, full)['overlap']
        self.assertEqual(result['fraction_of_requested_count'], 1)
        self.assertEqual(result['status'], 'MEETS_OVERLAP_THRESHOLD')

    def test_archived_event_after_cutoff_rejected(self):
        doc = fixed_screen()
        doc['candidates'][0]['horizon_review']['event_calendar']['events'] = [
            dict(kind='earnings', published_at='2026-10-09T14:00:00Z')]
        with self.assertRaisesRegex(ValueError, 'POINT_IN_TIME_EVIDENCE_INVALID'):
            review_screen(doc)

    def test_cutoff_weekend_and_early_close(self):
        self.assertEqual(session_grid('2026-10-10T15:00:00Z')[-1]['date'], '2026-10-09')
        self.assertEqual(session_grid('2026-11-27T18:01:00Z')[-1]['close'], '2026-11-27T18:00:00+00:00')

    def test_primary_retrieval_after_cutoff_needs_historical_evidence(self):
        primary = dict(status='reviewed', reason='Fictional latest-as-of lookup', evidence=['filing'],
                       latest_published_at='2026-08-01T12:00:00Z', checked_at='2026-10-09T16:00:00Z',
                       latest_public_period_end='2026-06-30', reviewed_period_end='2026-06-30')
        asof = timestamp('2026-10-08T20:00:00Z')
        self.assertIn('PRIMARY_PUBLICATION_OR_CHECK_TIME_INVALID', review_primary(primary, asof))
        primary.update(information_as_of=asof.isoformat(), point_in_time_evidence=['archived filing index'])
        self.assertEqual(review_primary(primary, asof), [])
        primary['latest_published_at'] = '2026-10-09T14:00:00Z'
        self.assertIn('PRIMARY_PUBLICATION_OR_CHECK_TIME_INVALID', review_primary(primary, asof))

    def test_rolling_latest_entry_cannot_follow_its_exit(self):
        doc = json.loads((ROOT / 'examples/fictional-horizon-screen.json').read_text(encoding='utf-8'))
        h = doc['horizon']
        h.update(as_of='2026-01-15T14:00:00Z', entry_at='2026-01-15T15:00:00Z',
                 latest_entry_at='2026-01-15T20:59:00Z', anchor_date='2026-01-15',
                 deadline_mode='rolling_from_entry', strategy_route='intraday',
                 duration={'value': 1, 'unit': 'same_session'}, exit_buffer_minutes=15)
        with self.assertRaisesRegex(ValueError, 'Latest entry must precede'):
            resolve_horizon(h)


class AllocationTests(unittest.TestCase):
    def test_uncalibrated_scores_produce_no_weights(self):
        self.assertEqual(construct({})['status'], 'CALIBRATION_REQUIRED')

    def test_alpha_units_and_horizon_mismatch(self):
        for key, val in [('units', 'dimensionless'), ('horizon_id', '1d')]:
            d = portfolio()
            d['calibration'][key] = val
            with self.assertRaises(ValueError):
                construct(d)

    def test_optimum_respects_caps_and_costs(self):
        r = construct(portfolio())
        self.assertEqual(r['status'], 'RESEARCH_PROPOSAL')
        self.assertAlmostEqual(r['weights']['A'], 0.7, places=6)
        self.assertLessEqual(r['one_way_turnover'], 0.2000001)
        self.assertFalse(r['execution_authorized'])
        self.assertFalse(r['strong_buy_available'])

    def test_same_issuer_limit_aggregated(self):
        d = portfolio()
        d['assets'][1]['issuer'] = 'A'
        self.assertEqual(construct(d)['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')

    def test_no_silent_relaxation_of_infeasible_constraints(self):
        d = portfolio()
        d['constraints']['theme_cap'] = 0.5
        self.assertIsNone(construct(d)['weights'])

    def test_indefinite_covariance_rejected(self):
        d = portfolio()
        d['covariance'] = [[0.04, 0.08], [0.08, 0.04]]
        with self.assertRaisesRegex(ValueError, 'NOT_PSD'):
            construct(d)

    def test_missing_theme_mapping_rejected(self):
        d = portfolio()
        del d['assets'][0]['themes']
        with self.assertRaisesRegex(ValueError, 'THEME_MAPPING'):
            construct(d)


if __name__ == '__main__':
    unittest.main()
