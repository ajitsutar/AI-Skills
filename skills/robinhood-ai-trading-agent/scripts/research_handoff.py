"""Bind a research mandate, source freshness and final order to executable evidence.

Offline only. Reproducibility does not authenticate sources or validate alpha.
Keep the public scorer unchanged; investment review remains a separate stage.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from price_audit import timestamp
from public_research import digest, make_bundle, number, profile, require
from screen_review import review_screen

ROOT = Path(__file__).resolve().parents[1]


def implementation():
    paths = ['VERSION', 'scripts/public_research.py', 'scripts/research_handoff.py', 'scripts/research_source_overlay.py',
             'scripts/screen_review.py', 'scripts/horizon_review.py',
             'scripts/deterministic_rank.py', 'profiles/public-vqm-discovery-v1.json']
    return {p: hashlib.sha256((ROOT / p).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for p in paths}


def lock(mandate):
    """Do this before selection; no defaults inherited from previous conversations."""
    m = copy.deepcopy(mandate)
    for field in ('prompt', 'universe', 'hold', 'risk_posture', 'early_exit_policy'):
        require(isinstance(m.get(field), str) and m[field].strip(), 'MANDATE_REQUIRED:' + field)
    require(type(m.get('count')) is int and m['count'] > 0, 'COUNT_REQUIRED')
    require(m.get('standing_preferences') in {'ignore', 'explicit_in_this_mandate'}, 'PREFERENCE_SCOPE_REQUIRED')
    require(m.get('earnings_policy') in {'allow_with_disclosure', 'exclude_during_hold'}, 'EARNINGS_POLICY_REQUIRED')
    require(m.get('selection_mode') == 'computed_order', 'DISCRETIONARY_SUBSTITUTION_NOT_ALLOWED')
    require(m.get('allowed_statuses') in [['Eligible'], ['Eligible', 'Speculative']], 'ALLOWED_STATUSES_REQUIRED')
    require(m.get('custom_filters') == [], 'CUSTOM_PROFILE_REQUIRES_SEPARATE_VERSIONED_IMPLEMENTATION')
    a, entry, end = [timestamp(m[k]) for k in ('information_cutoff', 'entry_at', 'exit_at')]
    require(a < entry < end, 'MANDATE_CLOCK_INVALID')
    require(date.fromisoformat(m['price_date']) <= a.date(), 'FUTURE_PRICE_DATE')
    require(number(m.get('capital')) > 0, 'CAPITAL_REQUIRED')
    # Horizon parsing is not a performance claim. No untested tactical score is invented.
    return {'schema_version': 1, 'mandate': m, 'mandate_sha256': digest(m),
            'implementation': implementation(), 'profile_sha256': digest(profile()),
            'route': 'PUBLIC_VQM_RESEARCH_THEN_HORIZON_REVIEW',
            'source_policy': 'OPEN_SOURCES_PRIMARY_PRECEDENCE_WITH_AUDITED_CORRECTIONS_V1',
            'horizon_alpha_validated': False, 'execution_authorized': False}


def verify_contract(contract):
    require(contract == lock(contract['mandate']), 'CONTRACT_OR_IMPLEMENTATION_MISMATCH')


def source(record, source_root=None):
    require(isinstance(record, dict), 'SOURCE_RECORD_REQUIRED')
    require(urlparse(record.get('url', '')).scheme == 'https', 'PRIMARY_HTTPS_URL_REQUIRED')
    require(record.get('kind') in {'issuer', 'regulator'}, 'PRIMARY_SOURCE_KIND_REQUIRED')
    require(isinstance(record.get('content_sha256'), str) and len(record['content_sha256']) == 64
            and all(c in '0123456789abcdef' for c in record['content_sha256']), 'SOURCE_HASH_REQUIRED')
    require(source_root is not None, 'SOURCE_ROOT_REQUIRED')
    name = record.get('file')
    require(isinstance(name, str) and name.strip() and '\\' not in name
            and ':' not in name, 'RELATIVE_SOURCE_FILE_REQUIRED')
    relative = Path(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'SOURCE_PATH_ESCAPE')
    root = Path(source_root).resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), 'SOURCE_PATH_ESCAPE')
    require(path.stat().st_size > 0, 'EMPTY_SOURCE_FILE')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == record['content_sha256'],
            'SOURCE_BYTES_HASH_MISMATCH')


def freshness(audit, vendor_period, cutoff, source_root=None):
    """Check latest release AND amendments; a fresh provider timestamp is insufficient.

    Saved bytes are required for both sources; hashes alone cannot establish freshness.
    Source authenticity and latest-report declarations still require actual review.
    A primary release before the next 10-Q must be included. Unknown is never clear.
    """
    if not audit:
        return {'status': 'UNKNOWN', 'reasons': ['PRIMARY_LATEST_RELEASE_CHECK_MISSING']}
    try:
        source(audit['latest_release'], source_root); source(audit['release_index'], source_root)
        checked = timestamp(audit['checked_at'])
        published = timestamp(audit['latest_release']['published_at'])
        information_at = checked
        if checked > cutoff:
            require(timestamp(audit['information_as_of']) == cutoff and bool(audit.get('point_in_time_evidence')),
                    'LATER_RETRIEVAL_REQUIRES_POINT_IN_TIME_EVIDENCE')
            information_at = cutoff
        require(0 <= (cutoff - information_at).total_seconds() <= 86400, 'SOURCE_CHECK_NOT_CURRENT')
        require(published <= information_at, 'FUTURE_RELEASE')
        latest = date.fromisoformat(audit['latest_release']['period_end'])
        require(latest <= published.date(), 'PERIOD_AFTER_PUBLICATION')
        require(audit.get('amendments_checked') is True, 'AMENDMENT_CHECK_MISSING')
        require(audit.get('unresolved_restatements') is False, 'RESTATEMENT_UNRESOLVED')
        reviewed = date.fromisoformat(audit['reviewed_period_end'])
        require(reviewed == latest, 'LATEST_RELEASE_NOT_REVIEWED')
        vendor = date.fromisoformat(vendor_period)
        delta = abs((vendor - latest).days)
        if delta and (delta > 7 or not audit.get('period_bridge')):
            return {'status': 'STALE_OR_MISMATCHED', 'vendor_period_end': str(vendor),
                    'primary_period_end': str(latest), 'reasons': ['REFRESH_FINANCIALS_AND_RERANK'],
                    'note': 'Do not drop the stale name and call its replacement superior.'}
        return {'status': 'CURRENT', 'vendor_period_end': str(vendor),
                'primary_period_end': str(latest), 'reasons': []}
    except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
        return {'status': 'UNKNOWN', 'reasons': [str(exc)]}


def evaluate(contract, snapshot, ledger, review_document=None, source_root=None):
    verify_contract(contract)
    m = contract['mandate']; cutoff = timestamp(m['information_cutoff'])
    require(snapshot['price_date'] == m['price_date'], 'PRICE_CUTOFF_MISMATCH')
    require(snapshot['mandate']['hold'] == m['hold'], 'HOLD_MISMATCH')
    require(snapshot.get('universe_evidence', {}).get('universe_id') == m['universe'], 'UNIVERSE_MISMATCH')
    require(ledger.get('contract_sha256') == digest(contract), 'LEDGER_CONTRACT_MISMATCH')
    declared = ledger.get('rows', [])
    require(len({r['symbol'] for r in declared}) == len(declared), 'DUPLICATE_FRESHNESS_ROW')
    require({r['symbol'] for r in declared} <= set(snapshot['universe_symbols']), 'FRESHNESS_OUTSIDE_UNIVERSE')
    # Preserve reused input provenance. Never silently rename an old acquisition fresh.
    acquisition = ledger.get('acquisition')
    require(acquisition in {'independent_fresh', 'shared_snapshot', 'incremental_reuse'}, 'ACQUISITION_MODE_REQUIRED')
    if snapshot.get('source_overlay'):
        overlay = snapshot['source_overlay']
        require(timestamp(overlay['information_cutoff']) <= cutoff, 'CORRECTION_AFTER_CUTOFF')
        require(ledger.get('source_overlay_sha256') == overlay['overlay_sha256'], 'CORRECTION_LEDGER_MISMATCH')
        require(ledger.get('corrected_input_sha256') == digest(snapshot), 'CORRECTED_INPUT_BINDING')
    discovery = make_bundle(snapshot, m['count'])
    r = discovery['result']; audits = {a['symbol']: a for a in r['field_audit']}
    records = {a['symbol']: a for a in declared}
    reviewed = {}
    if review_document is not None:
        require(review_document.get('decision_mode') == 'fixed_horizon', 'HORIZON_REVIEW_REQUIRED')
        review = review_screen(review_document)
        h = review['horizon']
        require(timestamp(h['as_of']) == cutoff and timestamp(h['entry_at']) == timestamp(m['entry_at'])
                and timestamp(h['exit_at']) == timestamp(m['exit_at']), 'REVIEW_CLOCK_MISMATCH')
        reviewed = {a['symbol']: a for a in review['candidates']}
    rows, provisional, pending = [], [], []
    for q in r['review_queue']:
        symbol = q['symbol']; record = records.get(symbol)
        if record:
            require(record.get('vendor_row_sha256') == audits[symbol]['source_sha256'], 'FRESHNESS_INPUT_BINDING:' + symbol)
        a = freshness(record, audits[symbol]['period_end'], cutoff, source_root)
        v = reviewed.get(symbol)
        reason = 'REVIEW_REQUIRED'
        if v and v['status'] == 'Reject' and v.get('primary_evidence_complete') and a['status'] == 'CURRENT':
            reason = 'EVIDENCED_REJECTION'
        elif a['status'] != 'CURRENT':
            reason = 'FINANCIAL_FRESHNESS_UNRESOLVED'
        elif v and v['event_status'] == 'blocked':
            reason = 'EVENT_BLOCKED'
        elif v and (v['status'] in m['allowed_statuses'] and not v['unresolved_checks']
                    and v.get('primary_evidence_complete') and v.get('horizon_review', {}).get('evidence_complete')
                    and v['event_status'] == 'clear'):
            events = records[symbol].get('earnings_during_hold')
            require(type(events) is bool, 'EARNINGS_EXPOSURE_UNRESOLVED:' + symbol)
            reason = ('EVENT_BLOCKED' if events and m['earnings_policy'] == 'exclude_during_hold'
                      else 'REVIEW_GATES_COMPLETE')
            if reason == 'REVIEW_GATES_COMPLETE':
                provisional.append(symbol)
        if reason in {'REVIEW_REQUIRED', 'FINANCIAL_FRESHNESS_UNRESOLVED'}:
            pending.append(symbol)
        rows.append({**q, 'freshness': a, 'decision_reason': reason,
                     'classification': v['status'] if v else 'Watch'})
    provisional = provisional[:m['count']]
    frontier = next((q['rank'] for q in rows if provisional and q['symbol'] == provisional[-1]), len(rows))
    blockers = [q['symbol'] for q in rows if q['rank'] <= frontier and q['symbol'] in pending]
    stale = [q['symbol'] for q in rows if q['freshness']['status'] == 'STALE_OR_MISMATCHED']
    # A known stale lower-ranked name may leapfrog the frontier after correction.
    complete = (not blockers and not stale and len(provisional) == m['count']
                and not r['ranking_relevant_acquisition_failures'])
    # Incomplete review is never a license to cherry-pick familiar lower-ranked names.
    return {'schema_version': 1, 'contract_sha256': digest(contract), 'input_sha256': digest(snapshot),
            'ledger_sha256': digest(ledger), 'review_document_sha256': digest(review_document),
            'public_result_sha256': discovery['result_sha256'], 'scorer_sha256': discovery['scorer_sha256'],
            'research_candidates': r['research_candidates'], 'provisional_reviewed_choices': provisional,
            'selected_symbols': provisional if complete else [],
            'selection_status': 'COMPUTED_REVIEWED_COMPARISON' if complete else 'INCOMPLETE_REVIEW',
            'blocking_review_symbols': blockers, 'known_stale_symbols_requiring_rerank': stale, 'decisions': rows,
            'coverage': {k: r[k] for k in ('universe_securities', 'scored_issuers', 'acquisition_failure_securities',
                         'ranking_relevant_acquisition_failures', 'full_universe_scored')},
            'acquisition': acquisition, 'horizon_alpha_validated': False, 'strong_buy_available': False,
            'source_byte_policy': 'SAVED_RELEASE_AND_INDEX_BYTES_REQUIRED',
            'ranking_acquisition_complete': not bool(r['ranking_relevant_acquisition_failures']),
            'source_policy': contract['source_policy'], 'source_overlay': snapshot.get('source_overlay'),
            'execution_authorized': False,
            'limitations': 'Research order is deterministic. Source/normalization judgments are retained inputs, not model-independent facts. Unscored issuers and provider failures remain coverage gaps. No validated one-month return model or automatic source certification.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['lock', 'evaluate'])
    p.add_argument('input', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--snapshot', type=Path); p.add_argument('--ledger', type=Path)
    p.add_argument('--review', type=Path)
    p.add_argument('--source-root', type=Path,
                   help='Directory containing saved release and release-index files; omission leaves freshness UNKNOWN')
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    data = read(a.input)
    if a.operation == 'lock':
        result = lock(data)
    else:
        require(a.snapshot is not None and a.ledger is not None, 'SNAPSHOT_AND_LEDGER_REQUIRED')
        result = evaluate(data, read(a.snapshot), read(a.ledger), read(a.review) if a.review else None, a.source_root)
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in {'decisions', 'blocking_review_symbols', 'implementation'}}, indent=2))


if __name__ == '__main__':
    main()
