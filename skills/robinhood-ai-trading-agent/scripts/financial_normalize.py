"""Deterministic offline financial normalization, evidence diagnostics and replay.

Inputs are data, never executable expressions. Reviewed transcriptions are
retained declarations, not proof of authenticity. This helper places no orders.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

from deterministic_rank import digest, number
from filing_extract import observations, numeric
from price_audit import timestamp

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / 'profiles/financial-normalization-v1.json'
ADAPTER_FIELDS = {
    'corporate': ('ebit_ttm', 'net_income_ttm', 'cfo_ttm', 'capex_ttm', 'assets', 'assets_prior',
                  'cash', 'debt', 'preferred_equity', 'noncontrolling_interest'),
    'equity_reit': ('ffo_common_ttm', 'net_income_ttm', 'cfo_ttm', 'capex_ttm', 'assets', 'assets_prior', 'cash', 'debt'),
    'bank': ('common_income_ttm', 'tangible_common_equity', 'tangible_common_equity_prior',
             'cet1', 'risk_weighted_assets', 'nonperforming_loans', 'gross_loans'),
    'insurer': ('common_income_ttm', 'common_equity', 'common_equity_prior', 'assets', 'debt'),
    'other_financial': ('common_income_ttm', 'common_equity', 'common_equity_prior', 'assets', 'debt'),
}
DIRECT = {'ebit_ttm': 'ebit', 'net_income_ttm': 'parent_income', 'cfo_ttm': 'cfo',
          'common_income_ttm': 'common_income', 'ffo_common_ttm': 'ffo_common'}


def policy():
    return json.loads(POLICY_PATH.read_text(encoding='utf-8'))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def publication_bounds(publication):
    precision = publication.get('precision')
    if precision == 'timestamp':
        moment = timestamp(publication['at'])
        return moment, moment
    require(precision == 'date', 'PUBLICATION_PRECISION_REQUIRED')
    day = date.fromisoformat(publication['date'])
    zone = ZoneInfo(publication['timezone'])
    lower = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    upper = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc) - timedelta(microseconds=1)
    return lower, upper


def review_source(source, cutoff):
    errors, bounds = [], None
    try:
        require(source.get('document_origin') in {'regulatory_filing', 'issuer_release'}, 'PRIMARY_ORIGIN_REQUIRED')
        require(source.get('delivery') in {'regulator', 'issuer', 'mirror'}, 'DELIVERY_CLASS_REQUIRED')
        require(nonempty(source.get('distribution_host')) and nonempty(source.get('uri')), 'SOURCE_LOCATION_REQUIRED')
        require(bool(re.fullmatch('[0-9a-f]{64}', source.get('content_sha256', ''))), 'SOURCE_HASH_REQUIRED')
        review = source.get('verification', {})
        require(review.get('status') == 'verified' and nonempty(review.get('method'))
                and isinstance(review.get('evidence'), list) and review['evidence']
                and all(nonempty(x) for x in review['evidence']), 'SOURCE_UNVERIFIED')
        if source['delivery'] == 'mirror':
            require(review.get('primary_content_matched') is True, 'MIRROR_PRIMARY_MATCH_REQUIRED')
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    try:
        bounds = publication_bounds(source['publication'])
        retrieved = timestamp(source['retrieved_at'])
        require(retrieved >= bounds[0], 'RETRIEVAL_PREDATES_PUBLICATION')
        # Captured content was public by retrieval; preserve the day interval.
        bounds = (bounds[0], min(bounds[1], retrieved))
        require(bounds[1] <= cutoff, 'PUBLICATION_AFTER_OR_STRADDLES_CUTOFF')
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    return {'ready': not errors, 'issues': errors,
            'publication_bounds': [x.isoformat() for x in bounds] if bounds else None}


def quantum(decimals):
    if decimals == 'INF':
        return Decimal(0)
    require(isinstance(decimals, (int, str)) and abs(int(decimals)) <= 30, 'FACT_ACCURACY_REQUIRED')
    return Decimal(10) ** -int(decimals) / 2


def resolve_duplicates(records):
    """Never choose a favorable value or discard a conflict by source ordering."""
    require(bool(records), 'MISSING_OBSERVATION')
    values = [(number(r['value']), quantum(r.get('decimals')), r) for r in records]
    low = max(v - q for v, q, _ in values)
    high = min(v + q for v, q, _ in values)
    require(low <= high, 'CONFLICTING_OBSERVATIONS')
    value, error, chosen = min(values, key=lambda x: (x[1], x[2]['source_id'], x[2]['record_id']))
    require(low <= value <= high, 'CONFLICTING_ROUNDING_CENTERS')
    return dict(value=value, error=error, records=sorted({r['record_id'] for r in records}),
                sources=sorted({r['source_id'] for r in records}),
                expression={'operation': 'reported', 'selected_record': chosen['record_id']})


def combine(parts, weights, operation):
    return dict(value=sum(p['value'] * w for p, w in zip(parts, weights)),
                error=sum(p['error'] * abs(w) for p, w in zip(parts, weights)),
                records=sorted({x for p in parts for x in p['records']}),
                sources=sorted({x for p in parts for x in p['sources']}),
                expression={'operation': operation, 'weights': weights,
                            'parts': [p['expression'] for p in parts]})


def same_value(paths):
    require(bool(paths), 'NO_COMPLETE_TTM_PATH')
    low = max(p['value'] - p['error'] for p in paths)
    high = min(p['value'] + p['error'] for p in paths)
    require(low <= high, 'CONFLICTING_TTM_PATHS')
    best = min(paths, key=lambda p: (p['error'], digest(p['expression'])))
    require(low <= best['value'] <= high, 'CONFLICTING_TTM_ROUNDING_CENTERS')
    return {**best, 'records': sorted({x for p in paths for x in p['records']}),
            'sources': sorted({x for p in paths for x in p['sources']}),
            'expression': {'operation': 'reconciled_paths', 'selected': best['expression'],
                           'paths': sorted([p['expression'] for p in paths], key=digest)}}


def ttm(observations_by_period, start, end):
    periods = {k: v for k, v in observations_by_period.items() if k[0] is not None}
    def part(key):
        return resolve_duplicates(periods[key])
    paths = []
    target = (start.isoformat(), end.isoformat())
    if target in periods:
        paths.append(part(target))
    for fs, fe in periods:
        fy_start, fy_end = date.fromisoformat(fs), date.fromisoformat(fe)
        if not (350 <= (fy_end - fy_start).days + 1 <= 380 and start <= fy_end < end):
            continue
        prior_key = (fs, (start - timedelta(days=1)).isoformat())
        current_key = ((fy_end + timedelta(days=1)).isoformat(), end.isoformat())
        if prior_key in periods and current_key in periods:
            # FY minus its initial YTD plus following YTD exactly covers target.
            require(fy_start < start, 'INVALID_TTM_LEGS')
            paths.append(combine([part((fs, fe)), part(current_key), part(prior_key)], [1, 1, -1], 'FY_PLUS_YTD_MINUS_PRIOR_YTD'))
    def quarters(cursor, chosen):
        if len(chosen) == 4:
            if cursor == end + timedelta(days=1):
                paths.append(combine(chosen, [1] * 4, 'FOUR_CONTIGUOUS_QUARTERS'))
            return
        for a, b in sorted(periods):
            first, last = date.fromisoformat(a), date.fromisoformat(b)
            if first == cursor and 70 <= (last - first).days + 1 <= 105 and last <= end:
                quarters(last + timedelta(days=1), chosen + [part((a, b))])
    quarters(start, [])
    return same_value(paths)


def normalize(document):
    with localcontext() as ctx:
        ctx.prec = policy()['arithmetic_precision']
        return _normalize(document)


def _normalize(document):
    p = policy()
    require(document.get('schema_version') == 1, 'NORMALIZATION_SCHEMA')
    require(document.get('policy_sha256') == digest(p), 'NORMALIZATION_POLICY_HASH')
    cutoff = timestamp(document['information_cutoff'])
    sources, source_reviews, records, extraction_issues = {}, {}, [], []
    for s in document['sources']:
        sid = s['source_id']
        require(nonempty(sid) and sid not in sources, 'DUPLICATE_SOURCE_ID')
        sources[sid] = s
        source_reviews[sid] = review_source(s, cutoff)
    seen_documents = set()
    for d in document.get('documents', []):
        sid = d['source_id']
        require(sid in sources and sid not in seen_documents, 'UNKNOWN_OR_DUPLICATE_DOCUMENT')
        seen_documents.add(sid)
        require(digest(d['extract']) == d.get('extract_sha256'), 'EXTRACT_HASH_MISMATCH:' + sid)
        require(sources[sid].get('extract_sha256') == d['extract_sha256'], 'SOURCE_EXTRACT_BINDING:' + sid)
        rows, issues = observations(d['extract'], sid)
        records.extend(rows)
        extraction_issues.extend(issues)
    allowed = set(p['tags']) | set(p['reviewed_concepts'])
    for supplied in document.get('transcriptions', []):
        row = copy.deepcopy(supplied)
        sid, concept = row['source_id'], row['concept']
        require(sid in sources and concept.startswith('reviewed:') and concept[9:] in allowed, 'TRANSCRIPTION_CONCEPT_OR_SOURCE')
        require(nonempty(row.get('locator')) and nonempty(row.get('quote')), 'TRANSCRIPTION_EVIDENCE')
        require(row.get('review', {}).get('status') == 'reviewed'
                and row['review'].get('policy_sha256') == digest(p)
                and nonempty(row['review'].get('basis_evidence')), 'TRANSCRIPTION_BASIS_REVIEW')
        require(row.get('unit') == 'USD' and nonempty(row.get('entity_id')), 'TRANSCRIPTION_UNIT_OR_ENTITY')
        if concept[9:] in p['required_bases']:
            require(nonempty(row.get('basis')), 'TRANSCRIPTION_BASIS_CODE_REQUIRED')
            if row['basis'] != p['required_bases'][concept[9:]]:
                extraction_issues.append(dict(record_id=row.get('record_id'), concept=concept, reason='ACCOUNTING_BASIS_NOT_SELECTED:' + row['basis']))
                continue
        if 'display_text' in row:
            require('value' not in row, 'TRANSCRIPTION_VALUE_OVERRIDE')
            row['value'], _ = numeric({k: str(row[k]) for k in ('format', 'scale', 'sign', 'decimals') if k in row}, row['display_text'])
        number(row['value'])
        quantum(row.get('decimals'))
        row['acquisition'] = 'reviewed_transcription'
        records.append(row)
    seen_records = set()
    for row in records:
        require(nonempty(row.get('record_id')) and row['record_id'] not in seen_records, 'DUPLICATE_RECORD_ID')
        seen_records.add(row['record_id'])
        date.fromisoformat(row['period_end'])
        if row.get('period_start'):
            require(date.fromisoformat(row['period_start']) <= date.fromisoformat(row['period_end']), 'REVERSED_FACT_PERIOD')
    records_by_id = {r['record_id']: r for r in records}
    records_by_entity = {}
    for row in records:
        bounds = source_reviews[row['source_id']]['publication_bounds']
        if bounds and timestamp(bounds[1]) > cutoff:
            extraction_issues.append({'record_id': row['record_id'], 'concept': row['concept'], 'reason': 'NOT_KNOWN_BY_CUTOFF'})
            continue
        records_by_entity.setdefault(row['entity_id'], []).append(row)
    outputs, seen_issuers, seen_entities = [], set(), set()
    for issuer in sorted(document['issuers'], key=lambda i: i['issuer_id']):
        iid = issuer['issuer_id']
        require(nonempty(iid) and iid not in seen_issuers, 'DUPLICATE_ISSUER')
        seen_issuers.add(iid)
        a = issuer['adapter']
        require(a in ADAPTER_FIELDS, 'UNKNOWN_ADAPTER')
        start, end = date.fromisoformat(issuer['ttm_start']), date.fromisoformat(issuer['financial_period_end'])
        require(350 <= (end-start).days+1 <= 380 and end <= cutoff.date(), 'INVALID_FINANCIAL_WINDOW')
        entity = issuer['entity_id']
        require(nonempty(entity) and entity not in seen_entities, 'DUPLICATE_PRIMARY_ENTITY')
        seen_entities.add(entity)
        aliases = issuer.get('predecessors', [])
        identity_issues = []
        accepted = {entity: None}
        for alias in aliases:
            try:
                effective = date.fromisoformat(alias['effective_date'])
                require(alias.get('successor_entity_id') == entity and alias.get('reporting_basis_unchanged') is True, 'IDENTITY_MAPPING_BASIS')
                require(effective <= cutoff.date() and nonempty(alias.get('evidence')), 'IDENTITY_MAPPING_DATE_OR_EVIDENCE')
                sids = alias.get('source_ids', [])
                require(sids and all(x in source_reviews for x in sids), 'IDENTITY_SOURCE_MISSING')
                require(alias['entity_id'] not in accepted, 'DUPLICATE_IDENTITY_ALIAS')
                accepted[alias['entity_id']] = effective
                if not all(source_reviews[x]['ready'] for x in sids):
                    identity_issues.append('IDENTITY_SOURCE_UNVERIFIED')
            except (ValueError, KeyError, TypeError) as exc:
                identity_issues.append(str(exc))
        eligible_records = []
        for row in (r for entity_id in accepted for r in records_by_entity.get(entity_id, [])):
            until = accepted[row['entity_id']]
            if until and date.fromisoformat(row['period_end']) >= until:
                continue
            eligible_records.append(row)
        semantic = {}
        for concept in allowed:
            tags = set(p['tags'].get(concept, [])) | {'reviewed:' + concept}
            groups = {}
            for row in eligible_records:
                if row['concept'] in tags:
                    groups.setdefault((row.get('period_start'), row['period_end']), []).append(row)
            semantic[concept] = groups
        def component(concept, flow=False, prior=False):
            try:
                day = start - timedelta(days=1) if prior else end
                def resolve(groups):
                    return ttm(groups, start, end) if flow else resolve_duplicates(groups.get((None, day.isoformat()), []))
                verified = {key: [r for r in values if source_reviews[r['source_id']]['ready']]
                            for key, values in semantic[concept].items()}
                verified = {key: values for key, values in verified.items() if values}
                try:
                    return resolve(verified)
                except ValueError as exc:
                    if 'CONFLICT' in str(exc):
                        raise
                    return resolve(semantic[concept])
            except ValueError as exc:
                raise ValueError(concept + ':' + str(exc)) from exc
        def unsigned_components(concepts, flow=False):
            parts, errors = [], []
            for key in concepts:
                try:
                    parts.append(component(key, flow=flow))
                except ValueError as exc:
                    errors.append(str(exc))
            require(not errors, ';'.join(errors))
            require(all(x['value'] >= 0 for x in parts), 'NEGATIVE_UNSIGNED_COMPONENT')
            return parts
        fields, gaps = {}, []
        for name in ADAPTER_FIELDS[a]:
            try:
                if name == 'debt':
                    value = combine(unsigned_components(('debt_current', 'debt_noncurrent', 'finance_leases_current', 'finance_leases_noncurrent')), [1]*4, 'DEBT_COMPONENTS_ONCE')
                elif name == 'capex_ttm':
                    concepts = ('reit_property_purchases', 'reit_development_improvements', 'other_productive_capex') if a == 'equity_reit' else ('ppe_capex', 'other_productive_capex')
                    value = combine(unsigned_components(concepts, flow=True), [1]*len(concepts), 'GROSS_PRODUCTIVE_CAPEX')
                elif name in DIRECT:
                    value = component(DIRECT[name], flow=True)
                else:
                    value = component(name.removesuffix('_prior'), prior=name.endswith('_prior'))
                signed = name in {'ebit_ttm', 'net_income_ttm', 'cfo_ttm', 'common_income_ttm', 'ffo_common_ttm', 'common_equity', 'common_equity_prior', 'tangible_common_equity', 'tangible_common_equity_prior'}
                require(signed or value['value'] >= 0, 'NEGATIVE_UNSIGNED_COMPONENT')
                bad_sources = [sid for sid in value['sources'] if not source_reviews[sid]['ready']]
                period_issues = []
                for rid in value['records']:
                    record = records_by_id[rid]
                    bounds = source_reviews[record['source_id']]['publication_bounds']
                    if bounds and timestamp(bounds[1]).date() < date.fromisoformat(record['period_end']):
                        period_issues.append('SOURCE_PREDATES_FACT:' + rid)
                ready = not bad_sources and not identity_issues and not period_issues
                fields[name] = {
                    'value': str(value['value']), 'unit': 'USD', 'period_end': end.isoformat(),
                    'rounding_error_bound': str(value['error']),
                    'status': 'READY' if ready else 'DRAFT_UNVERIFIED',
                    'source_ids': value['sources'], 'record_ids': value['records'],
                    'derivation': value['expression'],
                    **({'period_start': start.isoformat()} if name.endswith('_ttm') else {}),
                    **({'balance_date': (start-timedelta(days=1)).isoformat()} if name.endswith('_prior') else {}),
                }
                if not ready:
                    gaps.append({'field': name, 'reason': 'UNVERIFIED_EVIDENCE', 'source_ids': bad_sources, 'details': identity_issues + period_issues})
            except (ValueError, KeyError, TypeError) as exc:
                gaps.append({'field': name, 'reason': str(exc)})
        latest = issuer.get('latest_public_period_review', {})
        latest_ready = (latest.get('status') == 'reviewed' and latest.get('information_as_of') == document['information_cutoff']
                        and latest.get('period_end') == end.isoformat() and nonempty(latest.get('evidence'))
                        and bool(latest.get('source_ids'))
                        and all(sid in source_reviews and source_reviews[sid]['ready'] for sid in latest.get('source_ids', [])))
        if not latest_ready:
            gaps.append({'field': 'latest_public_period_review', 'reason': 'LATEST_PERIOD_UNREVIEWED'})
        outputs.append(dict(issuer_id=iid, adapter=a, ttm_start=start.isoformat(), financial_period_end=end.isoformat(),
                            fields=fields, gaps=gaps, latest_public_period_checked=latest_ready,
                            status='READY' if not gaps else 'INCOMPLETE'))
    implementation_sha = digest({name: (ROOT / 'scripts' / name).read_text(encoding='utf-8')
                                 for name in ('financial_normalize.py', 'filing_extract.py', 'deterministic_rank.py', 'price_audit.py')})
    return dict(schema_version=1, policy_sha256=digest(p), input_sha256=digest(document), implementation_sha256=implementation_sha,
                information_cutoff=document['information_cutoff'], issuers=outputs,
                source_reviews=source_reviews, extraction_issues=sorted(extraction_issues, key=lambda x: x['record_id']),
                status='READY' if outputs and all(x['status']=='READY' for x in outputs) else 'INCOMPLETE',
                records=sorted(records, key=lambda r: r['record_id']), execution_authorized=False,
                limitations='Deterministic normalization of supplied evidence. Hashes are not signatures; source and transcription reviews still require actual supporting evidence. No investment or full-universe coverage claim.')


def materialize(snapshot):
    """Schema 2 derives financial facts; callers cannot supply competing numbers."""
    require(snapshot.get('schema_version') == 2, 'NORMALIZED_SNAPSHOT_SCHEMA')
    document = snapshot['financial_normalization']
    require(document['information_cutoff'] == snapshot['information_cutoff'], 'NORMALIZATION_CUTOFF_MISMATCH')
    result = normalize(document)
    data = copy.deepcopy(snapshot)
    by_issuer = {r['issuer_id']: r for r in result['issuers']}
    require(set(by_issuer) == {r['issuer_id'] for r in data['rows']}, 'NORMALIZATION_UNIVERSE_MISMATCH')
    raw_sources = {s['source_id']: s for s in document['sources']}
    emitted = {}
    for row in data['rows']:
        normal = by_issuer[row['issuer_id']]
        require(not (set(row.get('facts', {})) - {'market_cap', 'close_price', 'adv20'}), 'FINANCIAL_FACT_OVERRIDE:' + row['symbol'])
        require(not any(k in row for k in ('financial_period_end', 'ttm_start', 'accounting_basis', 'latest_public_period_checked', 'source_conflicts', 'ffo_basis')), 'FINANCIAL_METADATA_OVERRIDE:' + row['symbol'])
        from vqm_research import adapter
        require(adapter(row) == normal['adapter'], 'NORMALIZATION_ADAPTER_MISMATCH')
        row.update(financial_period_end=normal['financial_period_end'], ttm_start=normal['ttm_start'],
                   accounting_basis='reported_gaap_ttm', latest_public_period_checked=normal['latest_public_period_checked'],
                   currency='USD', source_conflicts=[g['field'] for g in normal['gaps'] if 'CONFLICT' in g['reason']])
        if normal['adapter'] == 'equity_reit':
            row['ffo_basis'] = 'nareit_unadjusted_common'
        for name, fact in normal['fields'].items():
            if fact['status'] != 'READY':
                continue
            sid = 'normalization:' + digest({'issuer': normal['issuer_id'], 'field': name, 'fact': fact, 'policy': result['policy_sha256']})
            components = [raw_sources[x] for x in fact['source_ids']]
            upper = max(timestamp(result['source_reviews'][x]['publication_bounds'][1]) for x in fact['source_ids'])
            emitted[sid] = dict(source_id=sid, kind='financial', origin='issuer_release' if any(s['document_origin']=='issuer_release' for s in components) else 'regulatory_filing',
                                uri='urn:' + sid, content_sha256=digest(fact),
                                published_at=upper.isoformat(), publication_precision='conservative_upper_bound',
                                retrieved_at=max(timestamp(s['retrieved_at']) for s in components).isoformat(), upstream_source_ids=fact['source_ids'])
            row.setdefault('facts', {})[name] = {**fact, 'source_id': sid}
    require(all(s.get('kind') != 'financial' and not s.get('source_id','').startswith('normalization:') for s in data['sources']), 'NORMALIZED_SOURCE_OVERRIDE')
    data['sources'].extend(emitted[k] for k in sorted(emitted))
    return data, result


def diagnose(snapshot):
    """Report normalization and independent market gaps without counterfactuals."""
    data, result = materialize(snapshot)
    diagnostics = []
    for issuer in result['issuers']:
        diagnostics.extend(dict(issuer_id=issuer['issuer_id'], **g) for g in issuer['gaps'])
    from vqm_research import session_grid
    grid = session_grid(snapshot['decision_at'])
    dates = [x['date'] for x in grid]
    for row in data['rows']:
        for name in ('market_cap', 'close_price', 'adv20'):
            try:
                f = row['facts'][name]
                require(f.get('unit') == 'USD' and number(f['value']) > 0, 'MARKET_UNIT_OR_VALUE')
                require(timestamp(f['observed_at']) == timestamp(snapshot['information_cutoff']), 'MARKET_OBSERVATION_CUTOFF')
            except (ValueError, KeyError, TypeError) as exc:
                diagnostics.append(dict(symbol=row['symbol'], field=name, reason=str(exc)))
        h = row.get('total_return_history', {})
        for ok, reason in ((row.get('market_cap_scope') == 'all_common_share_classes', 'MARKET_CAP_SCOPE'),
                           (h.get('dates') == dates, 'PRICE_SESSION_GRID'),
                           (h.get('corporate_actions_reviewed') is True and h.get('unresolved_actions') == [] and nonempty(h.get('audit_evidence')), 'PRICE_ACTION_AUDIT'),
                           (row.get('membership_as_of') == snapshot['information_cutoff'][:10], 'MEMBERSHIP_DATE')):
            if not ok:
                diagnostics.append(dict(symbol=row['symbol'], field=reason.lower(), reason=reason))
    return dict(status='GAPS_FOUND' if diagnostics else 'CHECKED_COMPONENTS_READY', issues=diagnostics,
                normalization=result, execution_authorized=False,
                limitations='Read-only preflight, not final eligibility. Run the scorer and evidence review for complete validation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['normalize', 'diagnose', 'verify'])
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.command == 'normalize':
        result = {'input': data, 'result': normalize(data)}
    elif args.command == 'diagnose':
        result = diagnose(data)
    else:
        require(data['result'] == normalize(data['input']), 'NORMALIZATION_REPLAY_MISMATCH')
        result = {'status': 'REPLAY_MATCH', 'input_sha256': digest(data['input']), 'execution_authorized': False}
    if args.output:
        require(not args.output.resolve().is_relative_to(ROOT), 'Save outputs outside installed skill')
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
