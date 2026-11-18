"""Offline recurring economic intent bound to explicitly selected request bytes.

Full JSON retains private original instructions, routing and context. Store it
privately. Hashes/selected spans prove byte correspondence, not semantic scope,
source completeness, user authorization or native broker capability.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

from execution_handoff import recurring_dollar_intent
from handoff_report import bind, encode, local_path, select, sha, strict_json

ROLES = {'instruction', 'recurring_request', 'companion_context', 'currency_evidence'}
LIMITS = {'sources': 32, 'source_bytes': 1048576, 'total_bytes': 4194304,
          'selections': 256, 'intents': 256}


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('INVALID_FIELDS')


def _sources(items):
    if not isinstance(items, dict) or not items or len(items) > LIMITS['sources']:
        raise ValueError('BOUNDED_SOURCE_INVENTORY_REQUIRED')
    result = {}
    total = 0
    for name, item in items.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError('SOURCE_ID_REQUIRED')
        _keys(item, ('text', 'sha256', 'roles'))
        roles = item['roles']
        if (not isinstance(roles, list) or not roles or
                any(not isinstance(r, str) or r not in ROLES for r in roles) or len(set(roles)) != len(roles)):
            raise ValueError('EXPLICIT_SOURCE_ROLES_REQUIRED')
        if not isinstance(item['text'], str):
            raise ValueError('UTF8_SOURCE_TEXT_REQUIRED')
        raw = item['text'].encode('utf-8')
        total += len(raw)
        if len(raw) > LIMITS['source_bytes'] or total > LIMITS['total_bytes']:
            raise ValueError('SOURCE_SIZE_LIMIT')
        if item['sha256'] != sha(raw):
            raise ValueError('SOURCE_BYTES_HASH_MISMATCH')
        result[name] = raw
    return result


def _json_selection(spec, sources, *, nullable=False, lexemes=False):
    _keys(spec, ('source_id', 'json_pointer'))
    if spec['source_id'] not in sources:
        raise ValueError('SOURCE_NOT_FOUND')
    raw = sources[spec['source_id']]
    try:
        value, provenance = bind(raw, sha(raw), spec['json_pointer'])
    except ValueError as exc:
        # The accepted binder refuses null as a handoff payload. Here it is only
        # a source-field observation; never pass it off as preserved handoff data.
        if not nullable or str(exc) != 'NULL_SELECTION_NOT_PRESERVABLE_BY_HANDOFF':
            raise
        value = None
        provenance = {'artifact_sha256': sha(raw), 'pointer': spec['json_pointer'],
                      'selected_value_sha256': sha(b'null'),
                      'selection_basis': 'CALLER_EXPLICIT_NULL_FIELD_OBSERVATION'}
    if lexemes:
        # bind already checked duplicates/nonfinite values/pointer. Keep decimal
        # source spelling for the economic constructor, alongside exact raw bytes.
        value = select(json.loads(raw.decode('utf-8-sig'), parse_float=str), spec['json_pointer'])
        provenance['decimal_representation'] = 'ORIGINAL_JSON_FRACTIONAL_NUMBER_LEXEMES_AS_STRINGS'
    return value, dict(provenance, source_id=spec['source_id'])


def _currency(spec, sources):
    _keys(spec, ('source_id', 'intent_symbols'), ('json_pointer', 'utf8_span'))
    if ('json_pointer' in spec) == ('utf8_span' in spec):
        raise ValueError('ONE_CURRENCY_SELECTION_REQUIRED')
    if spec['source_id'] not in sources:
        raise ValueError('SOURCE_NOT_FOUND')
    if 'json_pointer' in spec:
        value, provenance = _json_selection({k: spec[k] for k in ('source_id', 'json_pointer')}, sources, nullable=True)
    else:
        raw = sources[spec['source_id']]
        span = spec['utf8_span']
        if (not isinstance(span, list) or len(span) != 2 or
                any(type(i) is not int for i in span) or not 0 <= span[0] < span[1] <= len(raw)):
            raise ValueError('INVALID_UTF8_SPAN')
        start, end = span
        # Both boundaries must be UTF-8 character boundaries and outside words.
        before, value, after = raw[:start].decode('utf-8'), raw[start:end].decode('utf-8'), raw[end:].decode('utf-8')
        if (before and (before[-1].isalnum() or before[-1] == '_')) or (after and (after[0].isalnum() or after[0] == '_')):
            raise ValueError('CURRENCY_TOKEN_BOUNDARY_REQUIRED')
        provenance = {'source_id': spec['source_id'], 'artifact_sha256': sha(raw),
                      'utf8_span': span, 'selected_quote': value,
                      'selection_basis': 'CALLER_EXPLICIT_NOT_INFERRED'}
    if value is not None and (not isinstance(value, str) or not re.fullmatch('[A-Za-z]{3}', value)):
        raise ValueError('EXPLICIT_THREE_LETTER_CURRENCY_CODE_OR_JSON_NULL_REQUIRED')
    return value, provenance


def build(spec):
    """Build an informational artifact; selection validity never gates execution."""
    _keys(spec, ('sources', 'recurring_request'), ('companion_context', 'currency_selections'))
    sources = _sources(spec['sources'])
    request, request_binding = _json_selection(spec['recurring_request'], sources, lexemes=True)
    if 'recurring_request' not in spec['sources'][spec['recurring_request']['source_id']]['roles']:
        raise ValueError('RECURRING_SOURCE_ROLE_REQUIRED')
    context, context_binding = None, None
    if 'companion_context' in spec:
        context, context_binding = _json_selection(spec['companion_context'], sources, nullable=True)
        if 'companion_context' not in spec['sources'][spec['companion_context']['source_id']]['roles']:
            raise ValueError('CONTEXT_SOURCE_ROLE_REQUIRED')
    record = recurring_dollar_intent(request, companion_context=context)
    symbols = [row['symbol'] for row in record['economic_intents']]
    if len(symbols) > LIMITS['intents']:
        raise ValueError('INTENT_COUNT_LIMIT')
    selections = spec.get('currency_selections', [])
    if not isinstance(selections, list) or len(selections) > LIMITS['selections']:
        raise ValueError('BOUNDED_CURRENCY_SELECTIONS_REQUIRED')
    mapped = {symbol: [] for symbol in symbols}
    for item in selections:
        value, provenance = _currency(item, sources)
        scope = item['intent_symbols']
        if (not isinstance(scope, list) or not scope or any(not isinstance(s, str) or s not in mapped for s in scope)
                or len(set(scope)) != len(scope)):
            raise ValueError('EXPLICIT_KNOWN_INTENT_SCOPE_REQUIRED')
        for symbol in scope:
            mapped[symbol].append({'value': value, 'source': deepcopy(provenance), 'declared_scope': list(scope)})
    instructions = [name for name, item in spec['sources'].items() if 'instruction' in item['roles']]
    for intent in record['economic_intents']:
        observations = mapped[intent['symbol']]
        values = {o['value'] for o in observations}
        if not observations:
            status = 'CURRENCY_MAPPING_UNRESOLVED' if instructions else 'REQUEST_CONTEXT_UNBOUND'
        elif len(values) > 1:
            status = 'CONFLICTING_SOURCE_SELECTIONS'
        elif values == {None}:
            status = 'SOURCE_FIELD_NULL'
        else:
            status = 'SOURCE_SELECTED'
            intent['currency'] = observations[0]['value']
        intent['currency_status'] = status
        intent['currency_observations'] = observations
    statuses = {i['currency_status'] for i in record['economic_intents']}
    record['currency_status'] = next(iter(statuses)) if len(statuses) == 1 else 'PER_INTENT_STATUS'
    record['kind'] = 'SOURCE_BOUND_RECURRING_ECONOMIC_INTENT'
    record['original_sources'] = deepcopy(spec['sources'])
    record['request_binding'] = request_binding
    record['context_binding'] = context_binding
    record['request_context_status'] = 'ORIGINAL_INSTRUCTION_BYTES_RETAINED' if instructions else 'REQUEST_CONTEXT_UNBOUND'
    record['instruction_source_ids'] = instructions
    record['limitations'] = [
        'Inventory completeness, source roles and intent scope are caller declarations, not independently verified.',
        'Selected bytes do not prove currency applicability: review negation, historical context and scope in the complete original request.',
        'A null field or omitted mapping does not establish that the user supplied no currency elsewhere.',
        'Three-letter syntax is not an ISO registry validation; no currency is inferred, converted or selected automatically.',
        'Hashes do not authenticate sources or user authorization. No broker capability, execution permission or refusal is established.',
        'Full original sources and context can include private data; this JSON is not a redacted display copy.']
    record['implementation_sha256'] = {name: sha((Path(__file__).resolve().parent/name).read_bytes())
                                         for name in ('recurring_intent_report.py', 'execution_handoff.py', 'handoff_report.py')}
    record['summary'] = summary(record)
    return record


def summary(record):
    lines = ['UNMAPPED recurring economic intent; no broker tool or argument schema is bound.',
             'Request context: ' + record['request_context_status'] + '.']
    for intent in record['economic_intents']:
        unit = intent['currency'] if intent['currency'] is not None else 'currency unresolved'
        lines.append(f"- Buy amount {intent['requested_dollar_amount']} ({unit}) for {intent['symbol']}; {intent['currency_status']}.")
    lines.append('Source selections and intent scope are caller-declared. Review the complete retained request; byte binding does not prove semantic applicability or completeness.')
    lines.append('Null or missing mapping does not establish absent user currency. No submission or schedule was created; this artifact neither grants nor refuses execution.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Source inventory and explicit selections JSON; full output contains private source text')
    args = parser.parse_args(argv)
    path = local_path(args.input)
    if path.stat().st_size > 8 * LIMITS['total_bytes']:
        raise ValueError('INPUT_SIZE_LIMIT')
    record = build(strict_json(path.read_bytes()))
    print(encode(record))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
