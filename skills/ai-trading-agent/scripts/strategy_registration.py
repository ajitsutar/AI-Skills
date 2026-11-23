"""Typed prospective comparator, calendar partition and uncertainty registration."""
from datetime import date
from decimal import Decimal
import math
import re

from strategy_design_answer import fields, need


STRICT = 'typed_comparator_calendar_and_single_paired_mean_estimator'
LEGACY = 'legacy_open_prose_comparator_calendar_and_estimator_not_validated'


def registration_schema():
    from strategy_economics import economics_schema
    return {
        'scoped_hac_sample': {'minimum_observations': 'study eligibility floor in paired observations',
                              'observation_unit': 'registered paired return interval',
                              'omit_in_scoped_hac': 'rationale; derived from the selected lag and study floor'},
        'executable_design': {'research_economics': economics_schema(), 'forward_economics': economics_schema(True),
                              'omit_design_terms': ['execution_convention'], 'omit_answer_controls': ['initial_state','warmup'],
                              'omit_sample_fields': ['minimum_events','event_unit'],
                              'cash_input': 'Supply a usable explicit cash convention, including a proposed zero rate if justified.'},
        'strategy_registration': {
            'benchmark': {'kind': 'cash', 'currency': {'proposal': 'EUR'}, 'cash_return': {'convention': 'unavailable'}},
            'evaluation': {'start': {'record_pointer': '/start_date'}, 'end': {'record_pointer': '/end_date'}},
            'development_fraction': 0.7,
            'uncertainty': {'performance_rule': 0, 'confidence': 0.95,
                            'estimator': {'name': 'newey_west_normal', 'lag_observations': 3}}},
        'omit_design_terms': ['benchmark', 'evaluation_window', 'development_validation_split'],
        'omit_answer_controls': ['uncertainty'],
        'forward_paper_omit': ['strategy_registration.development_fraction'],
        'linked_primary_rule': {'measure': 'mean_paired_net_active_return', 'units': 'return_fraction',
                                'measurement_window': 'registered_evaluation'},
        'estimator_alternative': {'name': 'circular_moving_block_percentile', 'block_observations': 6,
                                  'replicates': 20000, 'seed': 41},
        'cash_alternative': {'convention': 'annual_effective', 'annual_fraction': {'proposal': 0.0},
                             'day_count': 'actual_365_fixed'}}


def origin(spec, record, lookup):
    need(isinstance(spec, dict) and set(spec) in ({'record_pointer'}, {'proposal'}), 'POINT_SOURCE_OR_PROPOSAL_REQUIRED')
    if 'proposal' in spec:
        return {'basis': 'proposed', 'value': spec['proposal']}
    path = spec['record_pointer']
    need(isinstance(path, str) and path.startswith('/'), 'SELECTED_RECORD_FIELD_REQUIRED')
    return {'basis': 'supplied', 'record_pointer': path, 'value': lookup(record, path)}


def interval_date(spec, record, lookup):
    result = origin(spec, record, lookup)
    value = result['value']
    need(isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value), 'ISO_CALENDAR_DATE_REQUIRED')
    date.fromisoformat(value)
    return result


def benchmark(spec, record, lookup):
    need(isinstance(spec, dict), 'TYPED_BENCHMARK_REQUIRED')
    kind = spec.get('kind')
    need(kind in ('cash', 'buy_and_hold', 'reference_series'), 'BENCHMARK_KIND_REQUIRED')
    names = {'kind', 'currency', 'cash_return'}
    if kind != 'cash':
        names.add('identifier')
    fields(spec, names)
    currency = origin(spec['currency'], record, lookup)
    need(isinstance(currency['value'], str) and re.fullmatch('[A-Z]{3}', currency['value']), 'QUOTE_CURRENCY_CODE_REQUIRED')
    out = {'kind': kind, 'currency': currency}
    if kind != 'cash':
        identifier = origin(spec['identifier'], record, lookup)
        need(isinstance(identifier['value'], str) and identifier['value'].strip(), 'BENCHMARK_IDENTIFIER_REQUIRED')
        out['identifier'] = identifier
    cash = spec['cash_return']
    need(isinstance(cash, dict), 'CASH_CONVENTION_REQUIRED')
    convention = cash.get('convention')
    if convention == 'unavailable':
        fields(cash, {'convention'})
        out['cash_return'] = {'convention': convention, 'on_required_missing_input': 'inconclusive'}
    else:
        fields(cash, {'convention', 'annual_fraction', 'day_count'})
        need(convention in ('annual_effective', 'simple_annual') and cash['day_count'] in ('actual_365_fixed', 'actual_360'), 'CASH_ACCRUAL_CONVENTION_REQUIRED')
        rate = origin(cash['annual_fraction'], record, lookup)
        value = rate['value']
        need((type(value) is int or type(value) is float and math.isfinite(value) or
              isinstance(value, Decimal) and value.is_finite()) and
             (convention != 'annual_effective' or value > -1), 'VALID_ANNUAL_RETURN_FRACTION_REQUIRED')
        out['cash_return'] = {'convention': convention, 'day_count': cash['day_count'], 'annual_fraction': rate}
    return out


def uncertainty(spec, sample):
    fields(spec, {'performance_rule', 'confidence', 'estimator'})
    est = spec['estimator']
    need(isinstance(est, dict), 'ONE_ESTIMATOR_REQUIRED')
    name = est.get('name')
    n = sample['minimum_observations']
    need(type(n) is int and n >= 2, 'POSITIVE_SAMPLE_FLOOR_REQUIRED')
    if name == 'circular_moving_block_percentile':
        fields(est, {'name', 'block_observations', 'replicates', 'seed'})
        block, reps, seed = (est[k] for k in ('block_observations', 'replicates', 'seed'))
        need(type(block) is int and 1 <= block < n and type(reps) is int and reps >= 2 and
             type(seed) is int and seed >= 0, 'FIXED_BOOTSTRAP_PARAMETERS_REQUIRED')
        level = spec['confidence']
        need(type(level) in (float, int) and 0 < level < 1 and reps * (1-level) >= 1-1e-12,
             'BOOTSTRAP_TAIL_REQUIRES_SUFFICIENT_REPLICATES')
        method = 'One-sided nearest-rank empirical percentile bound on the arithmetic mean paired net active return.'
        treatment = (f'Use circular moving blocks of {block} paired observations. Select block starts uniformly with replacement, '
                     f'wrap and truncate to the observed length. Use {reps} replicates, with Python random.Random({seed}).randrange(N) for each block start.')
    elif name == 'newey_west_normal':
        fields(est, {'name', 'lag_observations'})
        lag = est['lag_observations']
        need(type(lag) is int and 0 <= lag < n, 'FIXED_HAC_LAG_REQUIRED')
        method = 'One-sided normal bound on the arithmetic mean paired net active return.'
        treatment = (f'Use Newey-West long-run variance with Bartlett weights and {lag} observation lags, '
                     'autocovariances divided by sample size, with no small-sample correction.')
    else:
        raise ValueError('ONE_SUPPORTED_FIXED_ESTIMATOR_REQUIRED')
    return {'performance_rule': spec['performance_rule'], 'confidence': spec['confidence'],
            'method': method, 'dependence_treatment': treatment}


def apply_registration(document, draft, lookup):
    spec = document['strategy_registration']
    research = document['design_kind'] == 'research_contract'
    economic = 'economics' in spec
    fields(spec, {'benchmark', 'evaluation', 'uncertainty'} | ({'development_fraction'} if research else set()) |
           ({'economics'} if economic else set()))
    owned = {'benchmark', 'evaluation_window'} | ({'development_validation_split'} if research else set())
    need(not owned.intersection(document['design_terms']) and 'uncertainty' not in document['answer_controls'],
         'DUPLICATE_FREE_TEXT_REGISTRATION')
    record = draft['supplied_strategy']
    comparator = benchmark(spec['benchmark'], record, lookup)
    window = spec['evaluation']
    fields(window, {'start', 'end'})
    extent = {k: interval_date(window[k], record, lookup) for k in ('start', 'end')}
    need(extent['start']['value'] <= extent['end']['value'], 'EVALUATION_DATES_OUT_OF_ORDER')
    terms = draft['design_terms']
    terms['benchmark'] = {'basis': 'proposed', 'value': comparator}
    terms['evaluation_window'] = {'basis': 'proposed', 'value': dict(extent, endpoints='inclusive eligible dates')}
    if research:
        fraction = spec['development_fraction']
        need(type(fraction) in (int, float) and 0 < fraction < 1, 'CHRONOLOGICAL_DEVELOPMENT_FRACTION_REQUIRED')
        terms['development_validation_split'] = {'basis':'proposed', 'value': {
            'ends_strictly_before': extent['start']['value'], 'ordered_by':'eligible observation time',
            'development':'first floor(N * fraction) eligible observations', 'development_fraction':fraction,
            'validation':'all remaining observations before evaluation', 'boundary':'purge crossing labels and holding intervals',
            'insufficient_history':'inconclusive'}}
    authored = document['answer_controls']
    if economic:
        from strategy_economics import EVENT, EXECUTION, INITIAL, resolve_economics, warmup
        need('execution_convention' not in document['design_terms'] and
             not {'initial_state', 'warmup'}.intersection(authored) and
             not {'minimum_events','event_unit'}.intersection(authored['sample']), 'DUPLICATE_ECONOMIC_CONTROL')
        economics = resolve_economics(spec['economics'], record, lookup, comparator, not research, authored['variants']['primary'])
        owned.add('execution_convention')
        terms['execution_convention'] = {'basis':'proposed', 'value':EXECUTION}
        authored = dict(authored, initial_state=INITIAL, warmup=warmup(economics),
                        sample=dict(authored['sample'], minimum_events=economics['sample']['minimum_completed_round_trips'],
                                    event_unit=EVENT))
    draft['missing_design_fields'] = [k for k in draft['missing_design_fields'] if k not in owned]
    if not draft['missing_design_fields']:
        draft['design_status'] = 'DRAFT_FOR_REVIEW'
    interval = uncertainty(spec['uncertainty'], authored['sample'])
    estimator = spec['uncertainty']['estimator']
    if 'clock_fields' in document and estimator['name'] == 'newey_west_normal':
        sample = authored['sample']
        need('rationale' not in sample, 'SCOPED_HAC_RATIONALE_IS_GENERATED_OMIT_SAMPLE_RATIONALE')
        lag = estimator['lag_observations']
        minimum = sample['minimum_observations']
        coverage = {'registered_observation_floor': minimum, 'lag_observations': lag,
                    'minimum_for_all_lag_products': lag + 1,
                    'pairs_at_longest_lag_at_registered_floor': minimum - lag}
        draft['hac_coverage'] = coverage
        reason = (f'The study proposes {minimum} paired observations for its decision. With {lag} lags '
                  f'the longest-lag autocovariance uses {minimum - lag} pairs at this floor. '
                  f'At least {lag + 1} observations are needed to form all specified lag products. '
                  'Availability of those products alone establishes neither a usable confidence bound '
                  'nor adequate precision. The study floor is an eligibility choice.')
        authored = dict(authored, sample=dict(sample, rationale=reason))
    index = interval['performance_rule']
    rules = draft['proposed_decision_rules']
    need(type(index) is int and 0 <= index < len(rules), 'DIRECTIONAL_PERFORMANCE_RULE_REQUIRED')
    primary = rules[index]
    need(primary['purpose'] == 'performance' and primary['measure'] == 'mean_paired_net_active_return' and
         primary['units'] == 'return_fraction' and primary['measurement_window'] == 'registered_evaluation',
         'BOUND_PERFORMANCE_RULE_REQUIRES_REGISTERED_MEASURE_UNIT_WINDOW')
    draft['strategy_registration'] = {'scope': STRICT, 'benchmark': comparator, 'evaluation': extent,
                                      'uncertainty': spec['uncertainty']}
    if research:
        draft['strategy_registration']['development_fraction'] = spec['development_fraction']
    if economic:
        draft['strategy_registration']['economics'] = economics
    return dict(authored, uncertainty=interval)


def render_registration(registration, inline):
    def display(term):
        value = inline(term['value'])
        if term['basis'] == 'supplied':
            return value + ' (supplied from selected record ' + inline(term['record_pointer']) + ')'
        return value + ' (proposed)'
    bench = registration['benchmark']
    description = bench['kind'].replace('_', ' ')
    if 'identifier' in bench:
        description += ' ' + display(bench['identifier'])
    lines = ['- Proposed comparator — ' + description + ', quote currency ' + display(bench['currency']) + '.']
    cash = bench['cash_return']
    if cash['convention'] == 'unavailable':
        lines.append('- Cash return input unavailable. A comparison requiring this input is inconclusive.')
    else:
        denominator = '365' if cash['day_count'] == 'actual_365_fixed' else '360'
        formula = '(1 + r)^(days/' + denominator + ') − 1' if cash['convention'] == 'annual_effective' else 'r × days/' + denominator
        lines.append('- Cash carry — annual return fraction r = ' + display(cash['annual_fraction'])
                     + '. Proposed day-count formula for elapsed calendar days: ' + formula + '.')
    window = registration['evaluation']
    lines.append('- Proposed evaluation — eligible observations from ' + display(window['start'])
                 + ' through ' + display(window['end']) + ', inclusive.')
    if 'development_fraction' in registration:
        lines.append('- Proposed chronological split — use only eligible observations strictly before evaluation. '
                     + 'The first floor(N × ' + str(registration['development_fraction']) + ') form development and the '
                     + 'remaining earlier observations form validation. Purge labels and holding intervals crossing boundaries. '
                     + 'Insufficient historical coverage is inconclusive.')
    if 'economics' in registration:
        from strategy_economics import render_economics
        lines.extend(render_economics(registration['economics'], bench, display))
    return lines
