"""Deterministic readback of a selected strategy and separately declared research choices."""
import json
import math
import re


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    need(isinstance(value, str) and value.strip(), 'NONEMPTY_DESIGN_TEXT_REQUIRED')
    return value


def fields(value, names):
    need(isinstance(value, dict) and set(value) == set(names), 'DESIGN_CONTROL_FIELDS_REQUIRED')


def controls(spec, rules):
    fields(spec, ('session_basis', 'initial_state', 'warmup', 'variants', 'sample', 'uncertainty'))
    for name in ('session_basis', 'initial_state', 'warmup'):
        text(spec[name])
    variants = spec['variants']
    need(isinstance(variants, dict), 'VARIANT_POLICY_REQUIRED')
    mode = variants.get('mode')
    need(mode in ('fixed_primary', 'development_selection'), 'VARIANT_POLICY_REQUIRED')
    names = ['mode', 'primary']
    if mode == 'development_selection':
        names.extend(('selection_measure', 'tie_break', 'multiplicity_adjustment', 'lock_before'))
    fields(variants, names)
    for name in names[2:]:
        text(variants[name])
    primary = variants['primary']
    need(isinstance(primary, dict) and set(primary) in ({'record_pointer'}, {'proposal'}), 'VARIANT_PRIMARY_BASIS_REQUIRED')
    text(next(iter(primary.values())))
    sample = spec['sample']
    fields(sample, ('minimum_observations', 'observation_unit', 'minimum_events', 'event_unit', 'rationale'))
    for name, floor in [('minimum_observations', 2), ('minimum_events', 1)]:
        need(type(sample[name]) is int and sample[name] >= floor, 'POSITIVE_SAMPLE_FLOOR_REQUIRED')
    for name in ('observation_unit', 'event_unit', 'rationale'):
        text(sample[name])
    interval = spec['uncertainty']
    fields(interval, ('performance_rule', 'confidence', 'method', 'dependence_treatment'))
    index = interval['performance_rule']
    need(type(index) is int and 0 <= index < len(rules) and rules[index]['purpose'] == 'performance'
         and rules[index]['comparison'] in ('>', '>=', '<', '<='), 'DIRECTIONAL_PERFORMANCE_RULE_REQUIRED')
    level = interval['confidence']
    need(type(level) in (int, float) and math.isfinite(level) and 0 < level < 1, 'CONFIDENCE_FRACTION_REQUIRED')
    text(interval['method'])
    text(interval['dependence_treatment'])
    return spec


def inline(value):
    # Render untrusted source data as a single Markdown code span. JSON preserves
    # types and escapes newlines. A delimiter longer than every embedded run is safe.
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except TypeError:
        # Selected numeric fields are parsed as Decimal. Keep their exact JSON number.
        from handoff_report import encode
        encoded = encode(value)
    ticks = '`' * (1 + max((len(s) for s in re.findall(r'`+', encoded)), default=0))
    return ticks + ' ' + encoded + ' ' + ticks


def render(result):
    lines = ['# Prospective strategy ' + ('paper protocol' if result['design_kind'] == 'forward_paper' else 'research contract'),
             '', '## Supplied strategy', '',
             'Source ' + inline(result['source_path']) + ', record ' + inline(result['source_pointer'])
             + ', SHA-256 ' + inline(result['source_sha256']) + '.', '']
    for name, value in result['supplied_strategy'].items():
        pointer = '/' + name.replace('~', '~0').replace('/', '~1')
        lines.append('- ' + inline(pointer) + ' = ' + inline(value))
    if 'clock_scope' in result:
        scope = result['clock_scope']
        lines.append('')
        for role, field in scope['decision_and_holding'].items():
            lines.append('Strategy ' + role.replace('_', ' ') + ' from ' + inline(scope['selected_record'] + field['record_pointer'])
                         + ' — ' + inline(field['value']) + '.')
        lines.append('The registered evaluation dates below delimit observations. A holding rule can instead depend '
                     'on a signal. Use only the selected record for supplied strategy clock fields.')
    lines.extend(['', '## Design conventions', ''])
    registration = result.get('strategy_registration')
    if registration is not None:
        from strategy_registration import render_registration
        lines.extend(render_registration(registration, inline))
    for name, term in result['design_terms'].items():
        if registration is not None and name in ('benchmark', 'evaluation_window', 'development_validation_split'):
            continue
        basis = 'Supplied from ' + inline(term['record_pointer']) if term['basis'] == 'supplied' else 'Proposed'
        lines.append('- ' + name.replace('_', ' ') + ' (' + basis + ') — ' + inline(term['value']))
    c = result['answer_controls']
    lines.extend(['', '## Proposed registration and clock', '',
                  'Freeze the selected rule, implementation digest, data and adjustment versions, comparator, execution conventions and decision thresholds with an independent timestamp before observing the evaluation segment.',
                  'An elapsed or viewed segment without contemporaneous registration remains exploratory. Retain its original dates and register any future extension separately.',
                  '', 'Calendar and eligibility — ' + inline(c['session_basis']),
                  '', 'Initial position and signal state — ' + inline(c['initial_state']),
                  '', 'Warm-up history and first eligible decision — ' + inline(c['warmup']),
                  '', 'The first actionable session requires eligible historical observations and a verified trading calendar. An elapsed calendar-day count alone cannot establish a signal or execution date.'])
    v = c['variants']
    primary = result['primary_specification']
    basis = 'supplied from ' + inline(primary['record_pointer']) if primary['basis'] == 'supplied' else 'proposed'
    lines.extend(['', '## Proposed variant decision', '', 'Primary specification (' + basis + ') — ' + inline(primary['value'])])
    if v['mode'] == 'fixed_primary':
        lines.append('Report all prespecified alternatives as sensitivities. Only the locked primary controls the decision; promoting a sensitivity requires fresh registration and an untouched sample.')
    else:
        for key in ('selection_measure', 'tie_break', 'multiplicity_adjustment', 'lock_before'):
            lines.append('- ' + key.replace('_', ' ') + ' — ' + inline(v[key]))
        lines.append('Apply selection only on the development sample. Record every candidate, freeze the winner and evaluate it once on the untouched sample.')
    lines.extend(['', '## Proposed decision criteria', ''])
    for n, rule in enumerate(result['proposed_decision_rules'], 1):
        lines.extend([str(n) + '. ' + rule['purpose'].capitalize() + ' — ' + inline(rule['measure'])
                      + ' ' + rule['comparison'] + ' ' + inline(rule['threshold']) + ' ' + inline(rule['units'])
                      + ' over ' + inline(rule['measurement_window']) + '. On failure ' + inline(rule['on_failure'])
                      + '. If unmeasurable ' + inline(rule['if_unmeasurable']) + '.'])
    sample = c['sample']
    lines.extend(['', 'Require at least ' + str(sample['minimum_observations']) + ' ' + inline(sample['observation_unit'])
                  + ' and ' + str(sample['minimum_events']) + ' ' + inline(sample['event_unit']) + '. Rationale — '
                  + inline(sample['rationale']) + '. Insufficient coverage makes the decision inconclusive.'])
    u = c['uncertainty']
    rule = result['proposed_decision_rules'][u['performance_rule']]
    side = 'lower' if rule['comparison'].startswith('>') else 'upper'
    lines.extend(['', 'Use the ' + side + ' confidence bound at level ' + str(u['confidence']) + ' for rule '
                  + str(u['performance_rule'] + 1) + ' with ' + inline(u['method']) + '. Dependence treatment — '
                  + inline(u['dependence_treatment']) + '. The bound must satisfy the same threshold. Insufficient precision or unavailable inputs make the decision inconclusive.'])
    if result['design_kind'] == 'forward_paper':
        lines.extend(['', '## Proposed decision, quote and execution journal', '',
                      'For each variant and expected session preserve a decision ID, including holds, warm-up and missing observations. Record source versions, cutoff, completed-bar time, inputs, rule state, intended next eligible execution, symbol, side and quantity.',
                      'Link decision ID to order ID, quote IDs and execution IDs. Retain the decision-time quote or closed-market status, then the opening/arrival quote with venue, bid, ask, sizes, timestamp and availability. Preserve submission, acknowledgement, rejection, cancellation, expiry, partial fills, remaining quantity and missed orders.',
                      'Measure shortfall against the timestamped arrival reference, including the unfilled portion and fees. Report measured costs and latency separately from modeled assumptions. Reconcile signed fills, fees, cash, open quantities and positions to independent original statements. Preserve and investigate any missing or unmatched event.'])
    if 'forward_reconciliation' in result:
        policy = result['forward_reconciliation']
        lines.extend(['', '## Forward-paper reconciliation before evaluating tolerances', ''])
        for name, population in policy['populations'].items():
            lines.append('- ' + name.capitalize() + ' — ' + population)
        lines.extend(['', policy['exceptions'], ''])
        for outcome in policy['dispositions'].values():
            lines.append('- ' + outcome)
    lines.extend(['', '## Evidence required', '',
                  'This design provides no observed outcome. Preserve original data, source clocks and implementation versions, document deviations and obtain independent reproduction and review. Untouched status, genuine forward observations and live trading authority require separate evidence.'])
    return '\n'.join(lines) + '\n'
