"""Explicit, source-checked partial collection; no network or hidden model cache.

The caller supplies retained source-index observations. Hashes establish byte
integrity, not whether a publisher or the caller's source mapping is truthful.
Missing checks always fall back to normal fresh component acquisition.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from research_memory import digest, file_hash, instant, local_file, verify

STATEMENTS = ('income', 'balance', 'cashflow')
INVALID_INPUT = (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError)


def source_index(check, component, root, earliest, latest):
    """Validate a retained adapter observation, including all retained periods."""
    index = check['source_index']
    checked = instant(index['checked_at'])
    if not earliest <= checked <= latest:
        raise ValueError('SOURCE_CHECK_OUTSIDE_CURRENT_COLLECTION_WINDOW')
    url = urlparse(index['source_url'])
    if url.scheme != 'https' or not url.netloc:
        raise ValueError('SOURCE_INDEX_HTTPS_URL_REQUIRED')
    if check['component_sha256'] != digest(component):
        raise ValueError('COMPONENT_HASH_MISMATCH')
    metadata = check['metadata']
    if not all(isinstance(metadata.get(k), str) and metadata[k].strip()
               for k in ('provider', 'currency', 'units', 'periodicity', 'scope', 'mapping_basis')):
        raise ValueError('STATEMENT_SOURCE_METADATA_REQUIRED')
    if metadata['periodicity'] != 'quarterly':
        raise ValueError('STATEMENT_PERIODICITY_MISMATCH')
    periods = component.get('columns')
    if not periods or len(set(periods)) != len(periods):
        raise ValueError('STATEMENT_PERIODS_MISSING_OR_DUPLICATE')
    if index['periods'] != periods:
        raise ValueError('SOURCE_PERIOD_MAPPING_MISMATCH')
    if index.get('review_scope') != 'latest_period_and_all_retained_revisions':
        raise ValueError('INCOMPLETE_SOURCE_INDEX_REVIEW')
    if index.get('latest_period') != max(periods):
        raise ValueError('NEW_PERIOD_OR_INVALID_LATEST_PERIOD')
    releases = index['releases']
    if (not isinstance(releases, list) or len(releases) != len(periods)
            or {r['period'] for r in releases} != set(periods)):
        raise ValueError('ALL_RETAINED_PERIOD_RELEASES_REQUIRED')
    for release in releases:
        if (not all(isinstance(release.get(k), str) and release[k].strip()
                    for k in ('release_id', 'revision_id'))
                or release.get('amendment_status') not in ('none', 'incorporated')):
            raise ValueError('RELEASE_REVISION_OR_AMENDMENT_UNKNOWN')
    evidence = local_file(root, index['evidence_path'])
    if file_hash(evidence) != index['evidence_sha256']:
        raise ValueError('SOURCE_INDEX_EVIDENCE_HASH_MISMATCH')
    return index


def same_releases(before, after):
    """Compare source identity and revision history, not TTL or market prices."""
    def contract(index):
        return {k: index[k] for k in ('source_url', 'periods', 'latest_period')}, sorted(
            index['releases'], key=lambda r: r['period'])
    return contract(before) == contract(after)


class PartialFetch:
    """One run's immutable parent and current source checks, with explicit fallback."""
    def __init__(self, parent_root, manifest_path, receipt_path, output, started_at,
                 baseline_only=False):
        self.output = Path(output)
        self.baseline_only = baseline_only
        self.started = instant(started_at)
        self.parent_root = Path(parent_root) if parent_root else None
        self.current_root = Path(receipt_path).resolve().parent if receipt_path else None
        self.parent_rows, self.checks = {}, {}
        self.parent_manifest_sha256 = None
        self.parent_snapshot_sha256 = None
        self.status = 'PARTIAL_FETCH_REQUESTED'
        self.errors = []
        self.decisions = []
        self.evidence_lock = threading.Lock()
        self.manifest_paths = set()
        try:
            if not receipt_path:
                raise ValueError('CURRENT_SOURCE_CHECKS_NOT_SUPPLIED')
            receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8-sig'))
            if receipt.get('schema_version') != 1:
                raise ValueError('UNSUPPORTED_FRESHNESS_RECEIPT')
            self.checks = self._rows(receipt['rows'])
            self.receipt_sha256 = file_hash(Path(receipt_path))
        except INVALID_INPUT as exc:
            self.errors.append(type(exc).__name__ + ':' + str(exc))
            self.checks = {}
        if baseline_only:
            self.status = 'FRESH_FETCH_WITH_OPTIONAL_SOURCE_CHECKS'
            return
        try:
            if not all((parent_root, manifest_path, receipt_path)):
                raise ValueError('PARTIAL_FETCH_REQUIRES_EXPLICIT_BUNDLE_AND_CURRENT_CHECKS')
            manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8-sig'))
            verify(self.parent_root, manifest)
            self.manifest_paths = {a['path'] for a in manifest['artifacts']}
            snapshots = [a for a in manifest['artifacts'] if a['kind'] == 'snapshot']
            if len(snapshots) != 1:
                raise ValueError('EXACTLY_ONE_PARENT_SNAPSHOT_REQUIRED')
            artifact = snapshots[0]
            parent = json.loads(local_file(self.parent_root, artifact['path']).read_text(encoding='utf-8-sig'))
            self.parent_rows = self._rows(parent['rows'])
            self.parent_profile = parent['profile_sha256']
            self.parent_started = instant(parent['contract']['decision_at'])
            self.parent_completed = instant(parent['completed_at'])
            parent_sealed_at = instant(manifest['as_of'])
            if not self.parent_started <= self.parent_completed <= parent_sealed_at <= self.started:
                raise ValueError('PARENT_COLLECTION_OR_MANIFEST_CHRONOLOGY_INVALID')
            self.parent_manifest_sha256 = manifest['manifest_sha256']
            self.parent_snapshot_sha256 = artifact['sha256']
        except INVALID_INPUT as exc:
            self.status = 'FRESH_FETCH_FALLBACK'
            self.errors.append(type(exc).__name__ + ':' + str(exc))
            self.parent_rows, self.checks = {}, {}
        if not self.checks:
            self.status = 'FRESH_FETCH_FALLBACK'

    def attach_current_checks(self, row, checked_until):
        """Optionally bind checks to freshly fetched bytes for a future parent."""
        current = self.checks.get(row['symbol'])
        if (not current or current.get('issuer_id') != row.get('issuer_id')
                or current.get('provider_symbol') != row.get('provider_symbol')):
            return
        for component in STATEMENTS:
            if component in row.get('component_source_checks', {}):
                continue
            try:
                check = current['components'][component]
                currency = row.get('info', {}).get('financialCurrency')
                if currency and check['metadata']['currency'] != currency:
                    raise ValueError('CURRENT_PROVIDER_FINANCIAL_CURRENCY_CHANGED')
                source_index(check, row[component], self.current_root,
                             self.started, instant(checked_until))
                row.setdefault('component_source_checks', {})[component] = self.retain_check(
                    check, component, row['symbol'])
            except INVALID_INPUT:
                # An absent or mismatched source observation never taints fresh data.
                continue

    @staticmethod
    def _rows(rows):
        indexed = {r['symbol']: r for r in rows}
        if len(indexed) != len(rows):
            raise ValueError('DUPLICATE_RECEIPT_OR_SNAPSHOT_SYMBOL')
        return indexed

    def choose(self, identity, profile_sha256, checked_until):
        """Return only eligible statement components; current identity wins."""
        selected, reasons = {}, {}
        symbol = identity['symbol']
        prior = self.parent_rows.get(symbol)
        current = self.checks.get(symbol)
        provider_symbol = identity.get('provider_symbol', symbol.replace('.', '-'))
        for component in STATEMENTS:
            try:
                if not prior or not current:
                    raise ValueError('NO_EXPLICIT_PARENT_OR_CURRENT_CHECK')
                if self.parent_profile != profile_sha256:
                    raise ValueError('PARENT_PROFILE_MISMATCH')
                if (prior.get('issuer_id') != identity['issuer_id']
                        or current.get('issuer_id') != identity['issuer_id']
                        or prior.get('provider_symbol') != provider_symbol
                        or current.get('provider_symbol') != provider_symbol):
                    raise ValueError('ISSUER_OR_PROVIDER_MAPPING_CHANGED')
                if any(e.get('component') == component for e in prior.get('errors', [])):
                    raise ValueError('PARENT_COMPONENT_FAILED')
                value = prior[component]
                if not value.get('index') or not value.get('data'):
                    raise ValueError('PARENT_STATEMENT_EMPTY')
                old_check = prior['component_source_checks'][component]
                original_time = instant(prior['component_retrieved_at'][component])
                if original_time > self.parent_completed:
                    raise ValueError('COMPONENT_RETRIEVED_AFTER_PARENT_COMPLETED')
                if original_time < self.parent_started:
                    inherited = prior.get('component_acquisition', {}).get(component, {})
                    if (inherited.get('acquisition') != 'source_checked_reuse'
                            or inherited.get('original_retrieved_at') != prior['component_retrieved_at'][component]
                            or inherited.get('component_sha256') != digest(value)
                            or inherited.get('current_checked_at') != old_check['source_index']['checked_at']
                            or not inherited.get('parent_manifest_sha256')
                            or not inherited.get('parent_snapshot_sha256')):
                        raise ValueError('OLD_COMPONENT_REQUIRES_INHERITED_REUSE_PROVENANCE')
                before = source_index(old_check, value, self.parent_root,
                                      self.parent_started, self.parent_completed)
                if before['evidence_path'] not in self.manifest_paths:
                    raise ValueError('PARENT_SOURCE_INDEX_NOT_SEALED')
                check = current['components'][component]
                after = source_index(check, value, self.current_root,
                                     self.started, instant(checked_until))
                if not same_releases(before, after):
                    raise ValueError('SOURCE_RELEASE_OR_REVISION_CHANGED')
                if old_check['metadata'] != check['metadata']:
                    raise ValueError('STATEMENT_SOURCE_METADATA_CHANGED')
                selected[component] = {
                    'value': copy.deepcopy(value),
                    'retrieved_at': prior['component_retrieved_at'][component],
                    'source_check': self.retain_check(check, component, symbol),
                    'provenance': {'acquisition': 'source_checked_reuse',
                        'parent_manifest_sha256': self.parent_manifest_sha256,
                        'parent_snapshot_sha256': self.parent_snapshot_sha256,
                        'component_sha256': digest(value),
                        'original_retrieved_at': prior['component_retrieved_at'][component],
                        'current_checked_at': after['checked_at'],
                        'freshness_receipt_sha256': self.receipt_sha256}}
                reasons[component] = 'SOURCE_CHECKED_REUSE'
            except INVALID_INPUT as exc:
                reasons[component] = 'FETCH_FRESH:' + str(exc)
        self.decisions.append({'symbol': symbol, 'components': reasons,
                               'info': 'FETCH_FRESH', 'history': 'FETCH_FULL_WITH_ACTIONS'})
        return selected

    def retain_check(self, check, component, symbol):
        """Keep portable current source evidence so this run can become a parent."""
        result = copy.deepcopy(check)
        index = result['source_index']
        evidence = local_file(self.current_root, index['evidence_path'])
        # Content-addressed names avoid unsafe symbols and repeated writes.
        relative = 'incremental-evidence/' + index['evidence_sha256'] + '.source'
        path = self.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.evidence_lock:
            try:
                with path.open('xb') as stream:
                    stream.write(evidence.read_bytes())
            except FileExistsError:
                if file_hash(path) != index['evidence_sha256']:
                    raise ValueError('RETAINED_EVIDENCE_CONFLICT')
        index['evidence_path'] = relative
        return result

    def receipt(self, rows=None):
        decisions = copy.deepcopy(self.decisions)
        observed = {r['symbol']: r for r in (rows or [])}
        reused = 0
        for decision in decisions:
            row = observed.get(decision['symbol'], {})
            for component, reason in decision['components'].items():
                mode = row.get('component_acquisition', {}).get(component, {}).get('acquisition')
                if mode == 'source_checked_reuse':
                    reused += 1
                elif reason == 'SOURCE_CHECKED_REUSE':
                    decision['components'][component] = 'FETCH_FRESH:CURRENT_PROVIDER_METADATA_OR_COLLECTION_CHANGED'
        return {'schema_version': 1, 'status': self.status,
                'mode': ('full_fetch_with_optional_source_checks' if self.baseline_only
                         else 'explicit_optional_partial_fetch'),
                'parent_manifest_sha256': self.parent_manifest_sha256,
                'parent_snapshot_sha256': self.parent_snapshot_sha256,
                'errors': self.errors,
                'rows': sorted(decisions, key=lambda r: r['symbol']),
                'reused_statement_components': reused,
                'fresh_required': ['membership', 'info', 'full_history_and_actions',
                                   'estimates', 'news', 'events'],
                'outside_collector': ['estimates', 'news', 'events'],
                'history_tail_reuse_certified': False,
                'note': 'Source-index observations are caller/adapter evidence, not independent certification. Full histories refresh because adjusted-history reconciliation is not implemented. Rerank the full current universe; shared reuse is not independent acquisition.'}
