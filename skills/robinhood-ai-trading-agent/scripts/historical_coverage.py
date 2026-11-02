"""Audit explicit historical security coverage without constructing return series.

Input identities and evidence reviews are caller declarations. The audit checks
contracts, date coverage and conflicts; it does not authenticate those reviews.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path

RELATIONS = {'same_security', 'same_security_rename', 'merger_exchange',
             'spin_off', 'share_class_change', 'ticker_reuse', 'unknown'}


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('INVALID_ISO_DATE')
    return value


def interval(value):
    start, end = day(value['start_inclusive']), day(value['end_exclusive'])
    if start >= end:
        raise ValueError('INVALID_INTERVAL')
    return start, end


def witnesses(value):
    return (isinstance(value, list) and bool(value) and
            all(isinstance(x, dict) and isinstance(x.get('ref'), str) and x['ref'].strip()
                and isinstance(x.get('sha256'), str) and len(x['sha256']) == 64
                and all(c in '0123456789abcdef' for c in x['sha256']) for x in value))


def positive(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def join_filing_metadata(facts, filings):
    """Join only exact issuer/accession pairs; never substitute a filing date.

    Acceptance is retained as acceptance, not certified public availability.
    Source witnesses and identifiers remain caller declarations.
    """
    indexed = defaultdict(list)
    for filing in filings:
        if not filing.get('issuer_id') or not filing.get('accession'):
            raise ValueError('FILING_IDENTITY_REQUIRED')
        indexed[(filing['issuer_id'], filing['accession'])].append(filing)
    rows = []
    for i, fact in enumerate(facts):
        if not fact.get('issuer_id') or not fact.get('accession'):
            raise ValueError('FACT_FILING_IDENTITY_REQUIRED')
        matches = indexed[(fact['issuer_id'], fact['accession'])]
        stamps, rejected, date_conflicts = set(), [], []
        for j, match in enumerate(matches):
            if fact.get('filed') and match.get('filing_date') and fact['filed'] != match['filing_date']:
                date_conflicts.append(j)
            if not witnesses([match.get('source', {})]) or not match.get('acceptance_at'):
                rejected.append(j)
                continue
            try:
                stamp = datetime.fromisoformat(match['acceptance_at'].replace('Z', '+00:00'))
                if stamp.utcoffset() is None:
                    raise ValueError('TIMEZONE_REQUIRED')
                stamps.add(stamp.astimezone(timezone.utc).isoformat())
            except (ValueError, TypeError, AttributeError):
                rejected.append(j)
        status = ('NO_EXACT_ACCESSION_MATCH' if not matches else
                  'CONFLICTING_METADATA' if len(stamps) > 1 or date_conflicts else
                  'EXACT_ACCESSION_ACCEPTANCE_RETAINED' if len(stamps) == 1 else
                  'ACCEPTANCE_UNKNOWN')
        rows.append({'fact_index': i, 'issuer_id': fact['issuer_id'], 'accession': fact['accession'],
                     'status': status, 'matched_metadata': matches,
                     'acceptance_at': next(iter(stamps)) if status == 'EXACT_ACCESSION_ACCEPTANCE_RETAINED' else None,
                     'rejected_time_or_source_rows': rejected, 'filing_date_conflict_rows': date_conflicts,
                     'public_availability_verified': False})
    return {'rows': rows, 'fact_count': len(facts),
            'exact_acceptance_count': sum(x['acceptance_at'] is not None for x in rows),
            'source_authenticity_verified': False,
            'limits': ['Exact issuer and accession only; dates and similar accession numbers never substitute.',
                       'Acceptance time does not itself certify public or vendor availability.']}


def audit(contract):
    if contract.get('schema_version') != 1:
        raise ValueError('UNSUPPORTED_SCHEMA')
    grid = [day(d) for d in contract['sessions']]
    if not grid or grid != sorted(set(grid)):
        raise ValueError('SORTED_UNIQUE_NONEMPTY_SESSION_GRID_REQUIRED')
    calendar = set(grid)
    calendar_reviewed = (contract.get('calendar_reviewed') is True and
                         witnesses(contract.get('calendar_evidence')))
    securities = contract['securities']
    identities = [s['id'] for s in securities]
    if any(not isinstance(x, str) or not x for x in identities) or len(set(identities)) != len(identities):
        raise ValueError('UNIQUE_SECURITY_IDS_REQUIRED')
    series, parsed = {}, {}
    for source in contract['series']:
        sid = source['id']
        if not isinstance(sid, str) or not sid or sid in series:
            raise ValueError('UNIQUE_SERIES_IDS_REQUIRED')
        series[sid] = source
        dates, usable, duplicate = set(), set(), set()
        invalid, off_calendar, non_observed = set(), set(), set()
        for observation in source.get('observations', []):
            d = day(observation['date'])
            if d in dates:
                duplicate.add(d)
            dates.add(d)
            # Adapters must preserve provider flags; absence is a caller declaration,
            # never proof that the source contains an actual market observation.
            if observation.get('observation_role', 'observed') != 'observed':
                non_observed.add(d)
            if d not in calendar:
                off_calendar.add(d)
            if positive(observation.get('adjusted_close')):
                usable.add(d)
            else:
                invalid.add(d)
        excluded = {day(d) for d in source.get('quality_excluded_dates', [])}
        # Conflicting/duplicate observations cannot silently win by row order.
        usable -= duplicate | invalid | excluded | non_observed
        parsed[sid] = {'observed': dates & calendar, 'usable': usable & calendar,
                       'duplicate': duplicate, 'invalid': invalid,
                       'excluded': excluded, 'off_calendar': off_calendar,
                       'non_observed': non_observed}
    mappings = defaultdict(list)
    for mapping in contract.get('mappings', []):
        if mapping['security_id'] not in identities or mapping['series_id'] not in series:
            raise ValueError('UNKNOWN_MAPPING_ENDPOINT')
        if mapping.get('relationship') not in RELATIONS:
            raise ValueError('UNKNOWN_RELATIONSHIP')
        interval(mapping)
        if not isinstance(mapping.get('reviewed', False), bool):
            raise ValueError('REVIEWED_MUST_BE_BOOLEAN')
        mappings[mapping['security_id']].append(mapping)
    results = []
    for security in securities:
        expected = None
        member = security.get('membership_intervals')
        listing = security.get('listing_intervals')
        if member is not None:
            bounds = [interval(x) for x in member]
            expected = {d for d in calendar if any(a <= d < b for a, b in bounds)}
            if listing is not None:
                listed = [interval(x) for x in listing]
                expected &= {d for d in calendar if any(a <= d < b for a, b in listed)}
        observed, qualified = set(), set()
        segments, rejected = [], []
        for mapping in mappings[security['id']]:
            source = series[mapping['series_id']]
            data = parsed[source['id']]
            a, b = interval(mapping)
            scope = {d for d in calendar if a <= d < b}
            observed |= data['observed'] & scope
            reasons = []
            if mapping['relationship'] not in {'same_security', 'same_security_rename'}:
                reasons.append('CORPORATE_EVENT_REQUIRES_SEPARATE_ACCOUNTING')
            if mapping.get('reviewed') is not True or not witnesses(mapping.get('evidence')):
                reasons.append('IDENTITY_REVIEW_OR_SOURCE_WITNESS_MISSING')
            for field in ('issuer_id', 'share_class_id'):
                if not security.get(field) or security.get(field) != source.get(field):
                    reasons.append(field.upper() + '_MISMATCH_OR_UNKNOWN')
            if security.get('kind') == 'equity' and source.get('kind') != 'equity':
                reasons.append('NON_EQUITY_SOURCE_FOR_EQUITY')
            if security.get('kind') not in {'equity', 'benchmark'}:
                reasons.append('UNKNOWN_REQUESTED_ASSET_KIND')
            if not witnesses([source.get('source', {})]):
                reasons.append('SERIES_SOURCE_WITNESS_MISSING')
            if reasons:
                rejected.append({'series_id': source['id'], 'reasons': reasons,
                                 'start_inclusive': a, 'end_exclusive': b})
                continue
            valid = data['usable'] & scope
            qualified |= valid
            segments.append({'series_id': source['id'], 'start_inclusive': a,
                             'end_exclusive': b, 'qualified_dates': sorted(valid),
                             'source': source['source'], 'identity_evidence': mapping['evidence'],
                             'adjustment_basis': source.get('adjustment_basis'),
                             'vintage': source.get('vintage')})
        verified_bounds = (calendar_reviewed and security.get('membership_reviewed') is True and
                           witnesses(security.get('membership_evidence')) and
                           listing is not None and security.get('listing_reviewed') is True and
                           witnesses(security.get('listing_evidence')))
        missing = sorted(expected - qualified) if expected is not None else None
        complete_sources = [s['series_id'] for s in segments if expected and expected <= set(s['qualified_dates'])]
        if expected is None:
            status = 'EXPECTED_SESSIONS_UNKNOWN'
        elif not expected:
            status = 'NO_EXPECTED_SESSIONS'
        elif missing:
            status = 'GAPS_REMAIN'
        elif not verified_bounds:
            status = 'CONDITIONAL_DATE_COVERAGE'
        else:
            status = 'DECLARED_REVIEWED_DATE_COVERAGE'
        results.append({'security_id': security['id'], 'status': status,
                        'expected_session_count': len(expected) if expected is not None else None,
                        'observed_dates_on_any_declared_mapping': sorted(observed),
                        'identity_qualified_session_count': len(qualified & expected) if expected is not None else len(qualified),
                        'missing_sessions': missing, 'single_source_complete_ids': sorted(set(complete_sources)),
                        'multiple_sources_needed_for_date_union': bool(expected and not missing and not complete_sources),
                        'expected_bounds_reviewed': verified_bounds,
                        'qualified_source_segments': segments, 'rejected_mappings': rejected,
                        'return_series_constructed': False,
                        'terminal_proceeds_reviewed': security.get('terminal_proceeds_reviewed') is True,
                        'terminal_proceeds_evidence_present': witnesses(security.get('terminal_proceeds_evidence'))})
    return {'schema_version': 1, 'security_count': len(securities), 'series_count': len(series),
            'calendar_reviewed': calendar_reviewed,
            'calendar_evidence': contract.get('calendar_evidence', []),
            'missing_identity_qualified_sessions': sum(len(x['missing_sessions'] or []) for x in results),
            'securities_with_unknown_expected_sessions': sum(x['missing_sessions'] is None for x in results),
            'rows': results,
            'source_quality': {sid: {k: sorted(v) for k, v in data.items() if k not in {'observed','usable'}}
                               for sid, data in parsed.items()},
            'point_in_time_complete_certified': False, 'source_authenticity_verified': False,
            'return_series_constructed': False,
            'limits': ['Identity reviews and witness references are caller declarations, not authenticated source facts.',
                       'A union of dates from different providers or adjustment vintages is not an approved stitched return series.',
                       'Unknown listing or membership bounds remain conditional; an empty expected set does not count as complete.',
                       'Terminal proceeds, financial publication timing and market executability need separate evidence.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--mode', choices=('prices', 'filings'), default='prices')
    p.add_argument('--max-input-bytes', type=int, default=64*1024*1024)
    args = p.parse_args()
    if not 0 < args.max_input_bytes <= 512*1024*1024:
        p.error('max-input-bytes must be positive and at most 512 MiB')
    source = Path(args.input)
    opener = gzip.open if source.suffix == '.gz' else open
    with opener(source, 'rb') as f:
        raw = f.read(args.max_input_bytes+1)
    if len(raw) > args.max_input_bytes:
        raise ValueError('INPUT_SIZE_BOUND')
    contract = json.loads(raw)
    result = (audit(contract) if args.mode == 'prices' else
              join_filing_metadata(contract['facts'], contract['filings']))
    result['input_sha256'] = hashlib.sha256(raw).hexdigest()
    payload = (json.dumps(result, indent=2)+'\n').encode()
    output = Path(args.output)
    with output.open('xb') as f:
        f.write(gzip.compress(payload, mtime=0) if output.suffix == '.gz' else payload)
    print(json.dumps({k: v for k, v in result.items() if k not in {'rows','source_quality','limits'}}))


if __name__ == '__main__':
    main()
