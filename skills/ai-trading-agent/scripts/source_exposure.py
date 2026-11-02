"""Complete retained-source mapping for advisory allocation_context; no selection."""
from copy import deepcopy
from decimal import Decimal
import hashlib

from quant_common import digest, require
from report_facts import pointer, strict_json
from portfolio_decision import allocation_context

ROLES = {'supplied_observation', 'hypothetical_scenario', 'user_assumption'}
FIELDS = ('issuer_id', 'sector', 'industry', 'kind', 'share_class', 'instrument_type',
          'business_description', 'dollar_volume')


def _escape(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def _known_label(value, field):
    """Match allocation_context labels: literal unknown is not an identity."""
    require(isinstance(value, str) and bool(value.strip()) and value == value.strip(),
            'EXACT_NONEMPTY_IDENTIFIER_REQUIRED:' + field)
    return value.casefold() != 'unknown'


def source_allocation_context(document):
    """Merge all declared source collections before exposing selected gross rows.

    Sources retain whole UTF-8 JSON text/hash, role, provenance, adapter and root
    binding. Supported adapters are portfolio_context_v1, business_statements_v1,
    and explicit_collections_v1. The latter requires collection bindings.
    Caller rows/denominator are explicit scenarios, never derived preferences.
    """
    require(isinstance(document, dict), 'DOCUMENT_OBJECT_REQUIRED')
    require(document.get('schema_version') == 1 and type(document['schema_version']) is int,
            'SOURCE_EXPOSURE_SCHEMA_VERSION_REQUIRED')
    require(document.get('role') in ROLES, 'INPUT_ROLE_REQUIRED')
    require(isinstance(document.get('currency'), str), 'CURRENCY_REQUIRED')
    require(isinstance(document.get('rows'), list), 'EXPLICIT_GROSS_NOTIONAL_ROWS_REQUIRED')
    require(isinstance(document.get('denominator'), dict), 'EXPLICIT_DENOMINATOR_REQUIRED')
    sources = document.get('sources')
    require(isinstance(sources, list) and sources, 'WHOLE_SOURCES_REQUIRED')
    identities, funds, retained, consumed, conflicts, gaps = {}, {}, [], [], [], []
    seen_source_ids = set()

    def merge(symbol, values, binding):
        require(isinstance(symbol, str) and symbol.strip() == symbol and symbol,
                'EXACT_SYMBOL_REQUIRED')
        require(isinstance(values, dict), 'IDENTITY_OBJECT_REQUIRED')
        item = identities.setdefault(symbol, {'symbol': symbol, 'values': {}, 'bindings': {}})
        for field in FIELDS:
            if field not in values or values[field] is None:
                continue
            fact = deepcopy(values[field])
            evidence = {**binding, 'pointer': binding['pointer'] + '/' + _escape(field)}
            choices = item['bindings'].setdefault(field, [])
            choices.append({'value': fact, **evidence})
            # Conflicts never resolve by last-source-wins or by silent preference.
            established = [c['value'] for c in choices if field not in ('issuer_id', 'sector', 'industry')
                           or _known_label(c['value'], field)]
            if len({digest(value) for value in established}) > 1:
                item['values'][field] = None
                conflicts.append({'symbol': symbol, 'field': field, 'observations': deepcopy(choices)})
            else:
                item['values'][field] = deepcopy(established[0]) if established else None

    for source in sources:
        require(isinstance(source, dict) and isinstance(source.get('text'), str), 'WHOLE_SOURCE_TEXT_REQUIRED')
        sid = source.get('id')
        require(isinstance(sid, str) and sid and sid not in seen_source_ids, 'UNIQUE_SOURCE_IDS_REQUIRED')
        seen_source_ids.add(sid)
        require(source.get('role') in ROLES and source.get('provenance') is not None,
                'SOURCE_ROLE_AND_PROVENANCE_REQUIRED')
        raw = source['text'].encode('utf-8')
        require(hashlib.sha256(raw).hexdigest() == source.get('sha256'), 'SOURCE_BYTES_HASH_MISMATCH')
        parsed = strict_json(raw)
        bindings = source.get('bindings')
        require(isinstance(bindings, dict) and 'root' in bindings, 'EXPLICIT_ROOT_BINDING_REQUIRED')
        root_path = bindings['root']
        root = pointer(parsed, root_path)
        require(isinstance(root, dict), 'SOURCE_ROOT_OBJECT_REQUIRED')
        retained.append({'id': sid, 'text': source['text'], 'bytes_sha256': source['sha256'],
                         'canonical_sha256': digest(parsed), 'role': source['role'],
                         'provenance': deepcopy(source['provenance']), 'adapter': source.get('adapter'),
                         'bindings': deepcopy(bindings), 'retained_document': parsed})

        def evidence(path):
            return {'source_id': sid, 'source_bytes_sha256': source['sha256'],
                    'source_role': source['role'], 'source_provenance': deepcopy(source['provenance']),
                    'pointer': path}

        def consume(path, collection):
            consumed.append({**evidence(path), 'collection': collection})
            return pointer(parsed, path)

        adapter = source.get('adapter')
        if adapter in {'portfolio_context_v1', 'business_statements_v1'}:
            require(set(bindings) == {'root'}, 'NATIVE_ADAPTER_ROOT_BINDING_ONLY')
        if adapter == 'portfolio_context_v1':
            identity_paths = [root_path + '/' + name for name in ('identities', 'other_identity') if name in root]
            fund_paths = [root_path + '/funds'] if 'funds' in root else []
            classification_paths, market_paths = [], []
            if not identity_paths and not fund_paths:
                gaps.append({'code': 'MAPPING_REQUIRED', 'source_id': sid,
                             'reason': 'No recognized portfolio collections at bound root'})
            if root.get('currency') != document['currency']:
                gaps.append({'code': 'SOURCE_CURRENCY_MISMATCH', 'source_id': sid})
        elif adapter == 'business_statements_v1':
            identity_paths, fund_paths, market_paths = [], [], []
            classification_paths = [root_path + '/issuers'] if 'issuers' in root else []
            if not classification_paths:
                gaps.append({'code': 'MAPPING_REQUIRED', 'source_id': sid,
                             'reason': 'Issuer collection absent at bound root'})
        elif adapter == 'explicit_collections_v1':
            gaps.append({'code': 'COLLECTION_INVENTORY_NOT_ESTABLISHED', 'source_id': sid,
                         'reason': 'Caller-selected collection pointers do not establish a complete source collection inventory.'})
            require(set(bindings) <= {'root', 'identity_maps', 'funds', 'classification_rows', 'market_rows'},
                    'UNSUPPORTED_COLLECTION_BINDING')
            identity_paths = bindings.get('identity_maps', [])
            fund_paths = bindings.get('funds', [])
            classification_paths = bindings.get('classification_rows', [])
            market_paths = bindings.get('market_rows', [])
            require(all(isinstance(paths, list) for paths in
                        (identity_paths, fund_paths, classification_paths, market_paths)), 'BINDING_ARRAYS_REQUIRED')
            if not any((identity_paths, fund_paths, classification_paths, market_paths)):
                gaps.append({'code': 'MAPPING_REQUIRED', 'source_id': sid})
        else:
            gaps.append({'code': 'MAPPING_REQUIRED', 'source_id': sid, 'adapter': adapter})
            continue
        for path in identity_paths:
            mapping = consume(path, 'identity_map')
            require(isinstance(mapping, dict), 'IDENTITY_MAP_OBJECT_REQUIRED')
            for symbol, values in mapping.items():
                merge(symbol, values, evidence(path + '/' + _escape(symbol)))
        for path in classification_paths + market_paths:
            records = consume(path, 'classification_rows' if path in classification_paths else 'market_rows')
            require(isinstance(records, list), 'SOURCE_ROW_ARRAY_REQUIRED')
            for index, row in enumerate(records):
                require(isinstance(row, dict), 'SOURCE_ROW_OBJECT_REQUIRED')
                row_path = path + '/' + str(index)
                merge(row.get('symbol'), row, evidence(row_path))
                # Monetary snapshot metadata stay intact; USD alone does not
                # establish per-day units, issuer identity or industry labels.
                if adapter == 'business_statements_v1' and 'adv20' in row.get('raw_snapshot_facts', {}):
                    observation = deepcopy(row['raw_snapshot_facts']['adv20'])
                    market_binding = evidence(row_path + '/raw_snapshot_facts/adv20')
                    monetary = {'amount': observation.get('value'),
                                'currency': row.get('currency') if observation.get('unit') == row.get('currency') else None,
                                'unit': None, 'period': {k: observation[k] for k in
                                    ('period_start', 'period_end', 'observed_at') if k in observation},
                                'raw_observation': observation, 'provenance': market_binding}
                    merge(row['symbol'], {'dollar_volume': monetary}, evidence(row_path))
                    # Correct the synthesized-field binding to its actual source.
                    identities[row['symbol']]['bindings']['dollar_volume'][-1].update(market_binding)
        for path in fund_paths:
            records = consume(path, 'funds')
            require(isinstance(records, list), 'FUNDS_ARRAY_REQUIRED')
            for index, fund in enumerate(records):
                require(isinstance(fund, dict), 'FUND_OBJECT_REQUIRED')
                symbol, fund_path = fund.get('symbol'), path + '/' + str(index)
                require(isinstance(symbol, str) and symbol, 'FUND_SYMBOL_REQUIRED')
                entry = {'record': deepcopy(fund), 'binding': evidence(fund_path)}
                if symbol in funds and digest(funds[symbol]['record']) != digest(fund):
                    conflicts.append({'symbol': symbol, 'field': 'fund', 'observations': [funds[symbol], entry]})
                    funds[symbol]['conflicted'] = True
                else:
                    funds.setdefault(symbol, entry)
                # Constituent rows may carry additional source identities; merge
                # every such row before any fund or selected exposure is built.
                holdings = fund.get('holdings')
                require(holdings is None or isinstance(holdings, list), 'FUND_HOLDINGS_ARRAY_REQUIRED')
                for holding_index, holding in enumerate(holdings or []):
                    require(isinstance(holding, dict), 'HOLDING_OBJECT_REQUIRED')
                    merge(holding.get('symbol'), holding,
                          evidence(fund_path + '/holdings/' + str(holding_index)))
                merge(symbol, {'instrument_type': 'fund'}, evidence(fund_path))
                identities[symbol]['bindings']['instrument_type'][-1].update(
                    {**evidence(fund_path), 'mapping': 'declared fund collection membership'})
                if 'average_daily_dollar_volume' in fund:
                    volume = {'amount': fund['average_daily_dollar_volume'], 'currency': root.get('currency'),
                              'unit': 'currency_per_day', 'period': root.get('as_of'),
                              'provenance': evidence(fund_path + '/average_daily_dollar_volume')}
                    merge(symbol, {'dollar_volume': volume}, evidence(fund_path))
                    identities[symbol]['bindings']['dollar_volume'][-1].update(volume['provenance'])

    # Exact supplied issuer IDs are the only cross-symbol join. Class-specific
    # metadata (share class, kind, market volume) never propagate across aliases.
    issuer_groups = {}
    for item in identities.values():
        issuer = item['values'].get('issuer_id')
        if issuer is not None and _known_label(issuer, 'issuer_id'):
            issuer_groups.setdefault(issuer, []).append(item)
    for issuer, items in issuer_groups.items():
        for field in ('sector', 'industry'):
            observations = [binding for item in items for binding in item['bindings'].get(field, [])
                            if _known_label(binding['value'], field)]
            choices = {digest(o['value']): o['value'] for o in observations}
            if len(choices) > 1:
                conflicts.append({'issuer_id': issuer, 'field': field, 'observations': deepcopy(observations)})
                for item in items:
                    item['values'][field] = None
            elif choices:
                for item in items:
                    item['values'][field] = deepcopy(next(iter(choices.values())))
                    existing = item['bindings'].setdefault(field, [])
                    seen = {digest(binding) for binding in existing}
                    for binding in observations:
                        key = digest(binding)
                        if key not in seen:
                            existing.append(deepcopy(binding))
                            seen.add(key)

    def enrich(symbol, stack=()):
        item = identities.get(symbol)
        values = deepcopy(item['values']) if item else {}
        if item is None:
            gaps.append({'code': 'IDENTITY_MAPPING_MISSING', 'symbol': symbol})
        kind = values.get('instrument_type')
        supplied_kind = {'common_stock': 'equity', 'ETF': 'fund', 'cash': 'cash'}.get(values.get('kind'))
        type_conflict = item is not None and any(len({digest(o['value']) for o in
            item['bindings'].get(field, [])}) > 1 for field in ('kind', 'instrument_type'))
        if kind not in {None, 'unknown'} and supplied_kind is not None and kind != supplied_kind:
            gaps.append({'code': 'CONFLICTING_INSTRUMENT_CLASSIFICATIONS', 'symbol': symbol,
                         'kind': values.get('kind'), 'instrument_type': kind})
            type_conflict = True
        if type_conflict:
            gaps.append({'code': 'INSTRUMENT_CLASSIFICATION_UNRESOLVED', 'symbol': symbol})
            return {**values, 'instrument_type': 'unknown',
                    'classification_provenance': deepcopy(item['bindings']) if item else {}}
        if kind in {None, 'unknown'} and supplied_kind is not None:
            kind = supplied_kind
        # A supplied issuer/sector is usable even when stock/fund type is not
        # established; 'other' does not assert an equity instrument classification.
        if kind in {None, 'unknown'}:
            kind = 'other' if any(values.get(f) is not None for f in ('issuer_id', 'sector', 'industry')) else 'unknown'
            gaps.append({'code': 'INSTRUMENT_TYPE_NOT_SUPPLIED', 'symbol': symbol})
        result = {**values, 'instrument_type': kind,
                  'classification_provenance': deepcopy(item['bindings']) if item else {}}
        fund = funds.get(symbol)
        if fund is not None:
            if fund.get('conflicted') or symbol in stack:
                gaps.append({'code': 'FUND_MAPPING_CONFLICT_OR_CYCLE', 'symbol': symbol})
                return result
            record, binding = fund['record'], fund['binding']
            holdings = record.get('holdings')
            require(holdings is None or isinstance(holdings, list), 'FUND_HOLDINGS_ARRAY_REQUIRED')
            if holdings is not None:
                constituents = []
                for index, holding in enumerate(holdings):
                    require(isinstance(holding, dict), 'HOLDING_OBJECT_REQUIRED')
                    child_symbol = holding.get('symbol')
                    child = enrich(child_symbol, stack + (symbol,))
                    constituents.append({**child, 'id': str(index) + ':' + str(child_symbol),
                                         'symbol': child_symbol, 'weight': holding.get('weight'),
                                         'provenance': {**binding, 'pointer': binding['pointer'] + '/holdings/' + str(index)}})
                coverage = record.get('holdings_coverage')
                known = [Decimal(str(h['weight'])) for h in holdings if h.get('weight') is not None]
                if coverage is not None and (len(known) != len(holdings) or sum(known, Decimal(0)) != Decimal(str(coverage))):
                    gaps.append({'code': 'DECLARED_COVERAGE_WEIGHT_MISMATCH', 'symbol': symbol,
                                 'declared_coverage': coverage, 'binding': deepcopy(binding)})
                result['lookthrough'] = {'constituents': constituents, 'declared_coverage': coverage,
                                         'period': record.get('holdings_as_of'), 'provenance': deepcopy(binding)}
        return result

    # Build complete context for unselected fund alternatives too: these are
    # retained source facts, never additional account notional or selections.
    fund_context = [{'symbol': symbol, 'source_record': deepcopy(entry['record']),
                     'source_binding': deepcopy(entry['binding']), 'mapped_context': enrich(symbol)}
                    for symbol, entry in funds.items()]
    rows = []
    for row in document['rows']:
        require(isinstance(row, dict) and isinstance(row.get('symbol'), str), 'EXPLICIT_ROW_SYMBOL_REQUIRED')
        require(not set(row) & set(FIELDS + ('lookthrough',)), 'ROW_CLASSIFICATION_OVERRIDE_NOT_SUPPORTED')
        rows.append({**deepcopy(row), **enrich(row['symbol'])})
    normalized = {'currency': document['currency'], 'role': document['role'],
                  'denominator': deepcopy(document['denominator']), 'rows': rows}
    result = allocation_context(normalized)
    missing = [{'symbol': symbol, 'fields': [field for field in ('issuer_id', 'sector', 'industry')
                                            if item['values'].get(field) is None]}
               for symbol, item in identities.items() if item['values'].get('kind') != 'cash'
               and item['values'].get('instrument_type') != 'cash']
    missing = [item for item in missing if item['fields']]
    mapping_status = 'MAPPING_REQUIRED' if any(g['code'] == 'MAPPING_REQUIRED' for g in gaps) else (
        'INPUTS_UNRESOLVED' if conflicts or gaps else 'SOURCE_BYTES_BOUND')
    return {'method': 'source-allocation-context-1', 'status': 'PARTIAL_CONTEXT' if
            mapping_status != 'SOURCE_BYTES_BOUND' or result['status'] == 'PARTIAL_CONTEXT' else 'COMPUTED_CONTEXT',
            'currency': document['currency'], 'input_role': document['role'], 'input_sha256': digest(document),
            'retained_input': deepcopy(document), 'sources': retained,
            'identity_context': list(identities.values()), 'fund_context': fund_context,
            'normalized_allocation_input': normalized, 'allocation_result': result,
            'mapping_status': mapping_status, 'mapping_gaps': gaps, 'mapping_conflicts': conflicts,
            'missing_classification_fields': missing,
            'complete_context_receipt': {'status': mapping_status, 'all_declared_collections_consumed':
                None if any(s['adapter'] == 'explicit_collections_v1' for s in retained) else
                not any(g['code'] == 'MAPPING_REQUIRED' for g in gaps), 'consumed_collections': consumed,
                'caller_subset_completeness_established': False,
                'retained_source_count': len(retained), 'identity_symbol_count': len(identities),
                'fund_count': len(funds), 'selected_row_ids': [r.get('id') for r in rows],
                'completeness_scope': 'Native schema: all recognized collections. Explicit bindings: caller subset only, full inventory unestablished. Source authenticity and externally absent metadata are not verified.'},
            'advisory_only': True, 'source_authenticity_verified': False,
            'limitation': 'Explicit gross notionals and denominator only. No selection, diversification conclusion, inferred industry/issuer, liquidity cutoff, ranking or execution gate. Retained observations do not establish absent units or freshness.'}
