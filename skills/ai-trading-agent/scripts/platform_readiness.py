"""Offline, advisory completeness assessment of supplied platform evidence.

Never calls a host/broker, authorizes an order, or implements an execution gate.
Hashes bind submitted bytes; they do not authenticate their author or truth.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

VERSION = 'platform-evidence/1'
ASSETS = ('stocks', 'etfs', 'options', 'futures', 'fx', 'bonds', 'crypto')
MODES = ('research', 'paper', 'live')
OPERATIONS = ('account', 'quote', 'positions', 'orders', 'fills', 'submit', 'cancel')
CHECKS = {
    'deployment': ('exact_package', 'exact_runtime', 'regression_suite', 'installation_identity'),
    'data_entitlements': ('intended_use_rights', 'coverage_and_latency', 'timestamp_and_units'),
    'calculation_validation': ('independent_arithmetic', 'missingness_and_boundaries', 'frozen_replay'),
    'instrument_semantics': ('instrument_identity', 'valuation_units', 'economic_events'),
    'host_capability': ('inventory_observed', 'schema_contract_test', 'account_capability_observed'),
    'order_identity': ('durable_intent_id', 'lost_response_reconciliation', 'duplicate_delivery'),
    'order_lifecycle': ('partial_and_terminal_fills', 'reject_and_unknown', 'cancel_replace_race'),
    'restart_recovery': ('restart_after_submit', 'restart_after_fill', 'reconnect_event_replay'),
    'reconciliation': ('orders_and_fills', 'positions_and_cash', 'unexplained_break_handling'),
    'feed_drills': ('stale_and_disconnected', 'late_or_corrected_data', 'halt_and_resume', 'operator_stop_recovery'),
    'environment_separation': ('endpoint_and_account_identity', 'wrong_environment_negative_test', 'secret_redaction'),
    'monitoring': ('heartbeat_and_owner', 'delivery_and_response_drill', 'rollback_and_recovery'),
    'strategy_validation': ('frozen_strategy_and_costs', 'complete_trials', 'untouched_evaluation'),
    'forward_validation': ('precommitted_decisions', 'new_outcomes', 'cost_and_benchmark_reconciliation'),
    'live_operational_validation': ('live_endpoint_identity', 'actual_order_reconciliation', 'observed_recovery'),
}
ASSET_CHECKS = {
    'stocks': ('corporate_actions_and_settlement',),
    'etfs': ('fund_distributions_and_settlement',),
    'options': ('multiplier_and_expiry', 'exercise_assignment_and_settlement', 'option_permissions_and_margin'),
    'futures': ('expiry_roll_and_delivery', 'variation_margin_and_collateral'),
    'fx': ('base_quote_and_pip_convention', 'rollover_and_settlement'),
    'bonds': ('clean_dirty_price_and_daycount', 'coupon_redemption_and_credit'),
    'crypto': ('pair_units_and_venue', 'custody_and_trading_permissions'),
}
RESEARCH = ('deployment', 'data_entitlements', 'calculation_validation', 'instrument_semantics')
PAPER = RESEARCH + ('host_capability', 'order_identity', 'order_lifecycle', 'restart_recovery',
                    'reconciliation', 'feed_drills', 'environment_separation', 'monitoring', 'strategy_validation')
REQUIRED = {'research': RESEARCH, 'paper': PAPER,
            'live': PAPER + ('forward_validation', 'live_operational_validation')}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def obj(value, fields, name):
    require(isinstance(value, dict), 'OBJECT_REQUIRED:' + name)
    require(set(value) == set(fields), 'EXACT_FIELDS_REQUIRED:' + name)


def string(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'NONEMPTY_TEXT_REQUIRED:' + name)
    return value


def clock(value):
    string(value, 'timestamp')
    match = re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?P<offset>Z|[+-]\d{2}:\d{2})', value)
    require(match is not None, 'EXACT_AWARE_TIMESTAMP_REQUIRED')
    offset = match.group('offset')
    # fromisoformat normalizes offsets such as +01:60; these are malformed
    # source timestamps and must never enter evidence eligibility arithmetic.
    if offset != 'Z':
        require(int(offset[1:3]) <= 23 and int(offset[4:6]) <= 59, 'INVALID_TIMESTAMP_OFFSET')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.astimezone(timezone.utc)


def sha(value, nullable=False):
    require((nullable and value is None) or
            (isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{64}', value))), 'SHA256_REQUIRED')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def required_checks(kind, asset_class):
    require(kind in CHECKS and asset_class in ASSETS, 'UNKNOWN_EVIDENCE_KIND_OR_ASSET')
    return CHECKS[kind] + (ASSET_CHECKS[asset_class] if kind == 'instrument_semantics' else ())


def required_categories(mode):
    require(mode in REQUIRED, 'UNKNOWN_MODE')
    return REQUIRED[mode]


def unique_list(value, name, allowed=None, nonempty=False):
    require(isinstance(value, list), 'ARRAY_REQUIRED:' + name)
    require(not nonempty or bool(value), 'NONEMPTY_ARRAY_REQUIRED:' + name)
    require(all(isinstance(x, str) and x.strip() for x in value), 'TEXT_ITEMS_REQUIRED:' + name)
    require(len(set(value)) == len(value), 'DUPLICATE_ITEMS:' + name)
    if allowed is not None:
        require(set(value) <= set(allowed), 'UNKNOWN_ITEM:' + name)


def validate(document):
    obj(document, ('schema_version', 'as_of', 'host', 'requests', 'evidence', 'documentation'), 'document')
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    clock(document['as_of'])
    host = document['host']
    obj(host, ('id', 'package_sha256', 'runtime_sha256'), 'host')
    string(host['id'], 'host.id')
    for field in ('package_sha256', 'runtime_sha256'):
        sha(host[field], nullable=True)
    require(isinstance(document['requests'], list) and document['requests'], 'REQUESTS_REQUIRED')
    keys = set()
    for row in document['requests']:
        obj(row, ('asset_class', 'mode', 'scope_id', 'scope_description'), 'request')
        require(row['asset_class'] in ASSETS and row['mode'] in MODES, 'UNKNOWN_ASSET_OR_MODE')
        string(row['scope_id'], 'scope_id')
        string(row['scope_description'], 'scope_description')
        key = (row['asset_class'], row['mode'], row['scope_id'])
        require(key not in keys, 'DUPLICATE_REQUEST')
        keys.add(key)
    require(isinstance(document['evidence'], list), 'EVIDENCE_ARRAY_REQUIRED')
    ids = set()
    for record in document['evidence']:
        obj(record, ('id', 'receipt', 'receipt_sha256'), 'evidence')
        string(record['id'], 'evidence.id')
        require(record['id'] not in ids, 'DUPLICATE_EVIDENCE_ID')
        ids.add(record['id'])
        sha(record['receipt_sha256'])
        receipt = record['receipt']
        require(isinstance(receipt, dict), 'RECEIPT_OBJECT_REQUIRED')
        kind = receipt.get('kind')
        require(isinstance(kind, str) and kind in CHECKS, 'UNKNOWN_EVIDENCE_KIND')
        common = ('kind', 'host_id', 'asset_class', 'mode', 'scope_id', 'scope_sha256', 'observed_at', 'valid_until',
                  'package_sha256', 'runtime_sha256', 'capability_sha256', 'artifact_ref', 'checks')
        extra = ('capability_status', 'tools') if kind == 'host_capability' else ()
        obj(receipt, common + extra, 'receipt')
        require(digest(receipt) == record['receipt_sha256'], 'RECEIPT_HASH_MISMATCH')
        for field in ('host_id', 'scope_id', 'artifact_ref'):
            string(receipt[field], field)
        require(receipt['asset_class'] in ASSETS and receipt['mode'] in MODES, 'UNKNOWN_RECEIPT_ASSET_OR_MODE')
        require(clock(receipt['observed_at']) < clock(receipt['valid_until']), 'INVALID_EVIDENCE_VALIDITY_INTERVAL')
        for field in ('package_sha256', 'runtime_sha256'):
            sha(receipt[field])
        sha(receipt['scope_sha256'])
        if kind == 'host_capability' or receipt['mode'] == 'research':
            require(receipt['capability_sha256'] is None, 'NO_RECURSIVE_OR_RESEARCH_CAPABILITY_BINDING')
        else:
            sha(receipt['capability_sha256'])
        require(isinstance(receipt['checks'], list), 'CHECKS_ARRAY_REQUIRED')
        check_ids = set()
        for check in receipt['checks']:
            obj(check, ('id', 'outcome', 'evidence_ref'), 'check')
            require(check['id'] in required_checks(kind, receipt['asset_class']), 'UNKNOWN_CHECK')
            require(check['id'] not in check_ids, 'DUPLICATE_CHECK')
            check_ids.add(check['id'])
            require(check['outcome'] in ('pass', 'fail', 'not_run'), 'CHECK_OUTCOME_REQUIRED')
            string(check['evidence_ref'], 'check.evidence_ref')
        if kind == 'host_capability':
            require(receipt['capability_status'] in ('supported', 'unsupported', 'unknown'), 'CAPABILITY_STATUS')
            require(isinstance(receipt['tools'], list), 'TOOLS_ARRAY_REQUIRED')
            names = set()
            for tool in receipt['tools']:
                obj(tool, ('name', 'operations', 'input_schema', 'schema_sha256'), 'tool')
                string(tool['name'], 'tool.name')
                require(tool['name'] not in names, 'DUPLICATE_TOOL_NAME')
                names.add(tool['name'])
                unique_list(tool['operations'], 'tool.operations', OPERATIONS, nonempty=True)
                require(isinstance(tool['input_schema'], dict) and tool['input_schema'], 'TOOL_SCHEMA_OBJECT_REQUIRED')
                sha(tool['schema_sha256'])
                require(digest(tool['input_schema']) == tool['schema_sha256'], 'TOOL_SCHEMA_HASH_MISMATCH')
    require(isinstance(document['documentation'], list), 'DOCUMENTATION_ARRAY_REQUIRED')
    docs = set()
    for row in document['documentation']:
        obj(row, ('id', 'host_id', 'asset_classes', 'modes', 'observed_at', 'source_url', 'summary', 'support'), 'documentation')
        string(row['id'], 'documentation.id')
        require(row['id'] not in docs, 'DUPLICATE_DOCUMENTATION_ID')
        docs.add(row['id'])
        string(row['host_id'], 'documentation.host_id')
        unique_list(row['asset_classes'], 'asset_classes', ASSETS, nonempty=True)
        unique_list(row['modes'], 'modes', MODES, nonempty=True)
        clock(row['observed_at'])
        require(isinstance(row['source_url'], str) and row['source_url'].startswith('https://'), 'HTTPS_SOURCE_REQUIRED')
        string(row['summary'], 'summary')
        require(row['support'] in ('documented', 'not_documented', 'documented_unsupported'), 'DOCUMENTATION_SUPPORT')


def assess(document):
    """Check a frozen evidence catalog, never actual host readiness or order permission."""
    validate(document)
    as_of, host = clock(document['as_of']), document['host']
    results = []
    for request in document['requests']:
        qualified = {}
        excluded = []
        missing = []
        conflicts = []
        current = []
        for record in document['evidence']:
            receipt = record['receipt']
            if any(receipt[k] != request[k] for k in ('asset_class', 'mode', 'scope_id')):
                continue
            reasons = []
            if receipt['host_id'] != host['id']:
                reasons.append('DIFFERENT_HOST')
            if receipt['scope_sha256'] != digest(request):
                reasons.append('DIFFERENT_REQUEST_SCOPE')
            if clock(receipt['observed_at']) > as_of:
                reasons.append('FUTURE_EVIDENCE')
            if clock(receipt['valid_until']) <= as_of:
                reasons.append('EXPIRED_EVIDENCE')
            for field in ('package_sha256', 'runtime_sha256'):
                if host[field] is None or receipt[field] != host[field]:
                    reasons.append('UNBOUND_' + field.upper())
            if reasons:
                excluded.append({'id': record['id'], 'reasons': reasons})
            else:
                current.append(record)
        capabilities = set()
        for record in current:
            r = record['receipt']
            if r['kind'] == 'host_capability' and r['capability_status'] == 'supported':
                checks = {c['id']: c['outcome'] for c in r['checks']}
                operations = {op for tool in r['tools'] for op in tool['operations']}
                if all(checks.get(k) == 'pass' for k in CHECKS['host_capability']) and set(OPERATIONS) <= operations:
                    capabilities.add(record['receipt_sha256'])
        bound_current = []
        for record in current:
            r = record['receipt']
            if request['mode'] != 'research' and r['kind'] != 'host_capability' and r['capability_sha256'] not in capabilities:
                excluded.append({'id': record['id'], 'reasons': ['UNBOUND_HOST_CAPABILITY_RECEIPT']})
            else:
                bound_current.append(record)
        current = bound_current
        capability_states = set()
        for kind in required_categories(request['mode']):
            records = [r for r in current if r['receipt']['kind'] == kind]
            passed = []
            failed = []
            incomplete = []
            for record in records:
                receipt = record['receipt']
                checks = {c['id']: c['outcome'] for c in receipt['checks']}
                if any(value == 'fail' for value in checks.values()):
                    failed.append(record['id'])
                complete = all(checks.get(name) == 'pass' for name in required_checks(kind, request['asset_class']))
                if kind == 'host_capability':
                    # A current, fully documented negative observation is scoped,
                    # not a permanent platform-wide denial. Omissions are unknown.
                    if complete:
                        capability_states.add(receipt['capability_status'])
                    operations = {op for tool in receipt['tools'] for op in tool['operations']}
                    complete = complete and receipt['capability_status'] == 'supported' and set(OPERATIONS) <= operations
                if complete:
                    passed.append(record['id'])
                else:
                    incomplete.append(record['id'])
            if passed and not failed:
                qualified[kind] = sorted(passed)
            else:
                missing.append({'category': kind, 'required_checks': list(required_checks(kind, request['asset_class'])),
                                'failed_receipts': sorted(failed), 'incomplete_receipts': sorted(incomplete)})
            if passed and failed:
                conflicts.append({'category': kind, 'passing_receipts': sorted(passed), 'failed_receipts': sorted(failed)})
        contradiction = 'supported' in capability_states and 'unsupported' in capability_states
        if contradiction:
            conflicts.append({'category': 'host_capability', 'reason': 'CONFLICTING_CURRENT_CAPABILITY_RECEIPTS'})
        common_capabilities = set(capabilities)
        if request['mode'] != 'research' and not missing:
            for kind, record_ids in qualified.items():
                if kind != 'host_capability':
                    common_capabilities &= {r['receipt']['capability_sha256'] for r in current if r['id'] in record_ids}
            if not common_capabilities:
                conflicts.append({'category': 'host_capability', 'reason': 'NO_COMMON_CAPABILITY_RECEIPT_ACROSS_CATEGORIES'})
        if conflicts:
            status = 'CONFLICTING_EVIDENCE'
        elif 'unsupported' in capability_states:
            status = 'UNSUPPORTED_IN_SUPPLIED_HOST_OBSERVATION'
        elif not missing:
            status = 'EVIDENCE_QUALIFIED_CONDITIONAL'
        else:
            status = 'UNVERIFIED'
        documentation = []
        for row in document['documentation']:
            if row['host_id'] == host['id'] and request['asset_class'] in row['asset_classes'] and request['mode'] in row['modes']:
                documentation.append({**copy.deepcopy(row), 'future_relative_to_assessment': clock(row['observed_at']) > as_of,
                                      'qualifies_host': False})
        results.append({**copy.deepcopy(request), 'evidence_status': status,
                        'catalog_evidence_complete': status == 'EVIDENCE_QUALIFIED_CONDITIONAL',
                        'common_capability_receipts': sorted(common_capabilities) if status == 'EVIDENCE_QUALIFIED_CONDITIONAL' else [],
                        'qualified_categories': qualified, 'missing_or_failed_categories': missing,
                        'considered_receipts': [{'id': r['id'], 'kind': r['receipt']['kind'],
                                                 'receipt_sha256': r['receipt_sha256']} for r in current],
                        'conflicts': conflicts, 'excluded_receipts': excluded,
                        'documentation_context': documentation,
                        'readiness_claim': 'NOT_ESTABLISHED_BY_THIS_ASSESSOR'})
    return {'schema_version': 1, 'method': VERSION, 'as_of': document['as_of'],
            'input_sha256': digest(document), 'host': copy.deepcopy(host), 'results': results,
            'catalog_evidence_complete': all(r['catalog_evidence_complete'] for r in results),
            'advisory_only': True, 'enforces_execution': False, 'execution_authorized': False,
            'skill_submitted_order': False, 'external_permissions_changed': False,
            'limitations': [
                'Qualified means the submitted catalog meets this schema, binding, time and check coverage; not verified production capability.',
                'Receipt hashes bind supplied content, not authenticity, actual execution, source rights, signature trust or substantive test quality.',
                'Evidence expiry, scope descriptions and pass/fail outcomes are supplied assertions; no artifact is opened and no broker is contacted.',
                'Tool schemas are retained and hash-bound, not independently discovered or fully semantically validated here.',
                'Research, paper and live evidence is not transferable across modes, asset classes, scopes, hosts or deployment/runtime hashes.',
                'Documentary support never qualifies an observed host. Unknown is not unsupported; negative observations have a specific scope and expiry.',
                'No dataset, strategy alpha, instrument-specific implementation or permitted order is established by a complete checklist.',
                'This output cannot authorize or block native host/broker actions; existing user/platform instructions remain authoritative.']}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY:' + key)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        document = json.loads(args.input.read_text(encoding='utf-8-sig'), object_pairs_hook=strict_object,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError('NONFINITE_JSON:' + value)))
        result = assess(document)
        output = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        if args.output:
            require(args.output.resolve() != args.input.resolve(), 'PRESERVE_INPUT')
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(output)
        else:
            print(output, end='')
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        parser.exit(2, 'platform_readiness: ' + str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
