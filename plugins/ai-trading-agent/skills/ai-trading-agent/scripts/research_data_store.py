"""Portable, explicitly owned research storage. No hidden caches or broker actions.

Native bytes and decoded-provider representations have different source_role
values. A complete capture is not normalized data, fresh research, or PIT proof.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import time
import uuid
import zipfile

CHUNK = 1024 * 1024
MARKER = 'RESEARCH-STORE.json'
REQUIRED = ('provider', 'security_id', 'provider_symbol', 'start', 'end',
            'adjustment', 'schema_version', 'parser_version', 'fields',
            'source_role', 'vintage')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return dt


def safe_path(root, relative):
    """Bounded lexical ancestor walk; reject symlink/junction/reparse ancestors."""
    root = Path(root).absolute()
    rel = PurePosixPath(str(relative).replace('\\', '/'))
    if rel.is_absolute() or not rel.parts or any(p in ('..', '.', '') or ':' in p for p in rel.parts):
        raise ValueError('UNSAFE_RELATIVE_PATH')
    target = root.joinpath(*rel.parts)
    current = target
    for _ in range(len(target.parts) + 1):
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('REDIRECTED_STORAGE_PATH')
        if current.parent == current:
            break
        current = current.parent
    else:
        raise ValueError('ANCESTOR_BOUND_EXCEEDED')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('PATH_OUTSIDE_STORE')
    return target


def atomic_json(path, value, replace=False):
    path = Path(path)
    temporary = path.with_name('.write-' + uuid.uuid4().hex[:16] + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and path.exists():
            raise FileExistsError(str(path))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_request(request):
    if not isinstance(request, dict) or any(k not in request for k in REQUIRED):
        raise ValueError('INCOMPLETE_SOURCE_CONTRACT')
    if any(not isinstance(request[k], str) or not request[k].strip() for k in REQUIRED if k != 'fields'):
        raise ValueError('EMPTY_SOURCE_CONTRACT_FIELD')
    if (not isinstance(request['fields'], list) or not request['fields']
            or any(not isinstance(s, str) or not s for s in request['fields'])
            or len(set(request['fields'])) != len(request['fields'])):
        raise ValueError('INVALID_FIELD_CONTRACT')
    # Non-date endpoints must be explicitly named, not silently interpreted.
    if request['start'] != 'not_applicable' and request['end'] != 'not_applicable':
        start, end = datetime.fromisoformat(request['start']), datetime.fromisoformat(request['end'])
        if start > end:
            raise ValueError('REVERSED_DATE_RANGE')
    for key in ('observed_at', 'decision_at', 'published_at', 'available_at'):
        if request.get(key) is not None:
            stamp(request[key])
    return digest(request)


class Store:
    def __init__(self, root, owner, *, create=False, min_free_bytes=256 * CHUNK,
                 max_capture_bytes=512 * CHUNK, max_active_captures=4):
        if not owner or not isinstance(owner, str):
            raise ValueError('EXPLICIT_OWNER_REQUIRED')
        self.root = Path(root).absolute()
        safe_path(self.root.parent, self.root.name)
        self.owner = owner
        self.min_free_bytes = int(min_free_bytes)
        self.max_capture_bytes = int(max_capture_bytes)
        self.max_active_captures = int(max_active_captures)
        if self.min_free_bytes < 0 or self.max_capture_bytes <= 0 or not 1 <= self.max_active_captures <= 32:
            raise ValueError('INVALID_STORAGE_BOUNDS')
        if create:
            # Never adopt an unrelated populated directory or choose another drive.
            self.root.mkdir(parents=True, exist_ok=False)
            atomic_json(self.root / MARKER, {'schema_version': 1, 'owner': owner,
                        'store_id': uuid.uuid4().hex, 'created_at': utc()})
            for name in ('objects', 'records', 'attempts', 'locks', 'archives'):
                (self.root / name).mkdir()
        marker = self.path(MARKER)
        self.identity = json.loads(marker.read_text(encoding='utf-8'))
        if self.identity.get('owner') != owner or self.identity.get('schema_version') != 1:
            raise ValueError('STORE_OWNERSHIP_MISMATCH')

    def path(self, relative):
        return safe_path(self.root, relative)

    def space(self):
        if shutil.disk_usage(self.root).free < self.min_free_bytes + 2 * CHUNK * self.max_active_captures:
            raise OSError('STORAGE_RESERVE_REACHED')

    @contextmanager
    def lock(self, key):
        path = self.path('locks/' + key + '.lock')
        guard = self.path('locks/dispatch.lock')
        deadline = time.monotonic() + 5
        while True:
            try:
                guard.mkdir(); break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('STORE_DISPATCH_BUSY')
                time.sleep(.01)
        try:
            active = [p.name for p in self.path('locks').iterdir() if p != guard]
            if (key == 'maintenance' and active) or 'maintenance.lock' in active:
                raise ValueError('CAPTURE_OR_MAINTENANCE_ACTIVE')
            if key != 'maintenance' and len(active) >= self.max_active_captures:
                raise ValueError('ACTIVE_CAPTURE_LIMIT')
            path.mkdir()  # Atomic same-request exclusion; independent captures allowed.
        finally:
            guard.rmdir()
        try:
            yield
        finally:
            path.rmdir()

    def read_record(self, key):
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('INVALID_RECORD_KEY')
        value = json.loads(self.path('records/' + key + '.json').read_text(encoding='utf-8'))
        if value.get('request_id') != key or validate_request(value['request']) != key:
            raise ValueError('RECORD_CONTRACT_MISMATCH')
        if value.get('status') != 'CAPTURED' or value.get('store_id') != self.identity['store_id']:
            raise ValueError('UNOWNED_OR_INCOMPLETE_RECORD')
        rawhash = value.get('raw_sha256', '')
        if (len(rawhash) != 64 or any(c not in '0123456789abcdef' for c in rawhash)
                or value.get('object_path') != 'objects/' + rawhash + '.gz'
                or not isinstance(value.get('raw_bytes'), int) or value['raw_bytes'] <= 0):
            raise ValueError('INVALID_OWNED_OBJECT_PATH_OR_SIZE')
        return value

    def records(self):
        return [self.read_record(p.stem) for p in sorted(self.path('records').glob('*.json'))]

    def verify_record(self, record, previous=None):
        obj = self.path(record['object_path'])
        if obj.stat().st_size != record['compressed_bytes'] or file_sha(obj) != record['compressed_sha256']:
            raise ValueError('COMPRESSED_OBJECT_MISMATCH')
        seal = digest(record)
        if (previous and previous.get('record_sha256') == seal
                and previous.get('compressed_sha256') == record['compressed_sha256']
                and previous.get('fully_verified') is True):
            return {**previous, 'verification_mode': 'COMPRESSED_BYTES_REHASHED_PRIOR_RAW_SEAL_REUSED'}
        h, size, chunks = hashlib.sha256(), 0, []
        with gzip.open(obj, 'rb') as stream:
            for value in iter(lambda: stream.read(CHUNK), b''):
                h.update(value); size += len(value); chunks.append(hashlib.sha256(value).hexdigest())
                if size > record['raw_bytes']:
                    raise ValueError('RAW_SIZE_EXCEEDED')
        if (size != record['raw_bytes'] or h.hexdigest() != record['raw_sha256']
                or chunks != record['raw_chunk_sha256']):
            raise ValueError('RAW_OBJECT_MISMATCH')
        return {'request_id': record['request_id'], 'record_sha256': seal,
                'compressed_sha256': record['compressed_sha256'], 'fully_verified': True,
                'raw_bytes': size, 'verification_mode': 'FULL_GZIP_CRC_RAW_SHA_CHUNKS'}

    def verify(self, previous=None):
        # Prior seals are explicit caller-supplied local evidence, not provider freshness.
        old = {r['request_id']: r for r in (previous or {}).get('records', [])}
        if previous and previous.get('store_id') != self.identity['store_id']:
            raise ValueError('PRIOR_SEAL_STORE_MISMATCH')
        rows = [self.verify_record(r, old.get(r['request_id'])) for r in self.records()]
        return {'schema_version': 1, 'store_id': self.identity['store_id'],
                'verified_at': utc(), 'records': rows, 'provider_freshness_verified': False}

    def capture(self, request, producer, *, resume=False, retrieved_at=None, revision=None):
        """Producer yields bytes. Only complete responses become immutable records.

        An incomplete transport body remains an attempt, never a valid response.
        Resume of a completed raw response skips producer even if later parsing failed.
        This is frozen-contract resume, not new-date cache reuse.
        """
        key = validate_request(request)
        with self.lock(key):
            target = self.path('records/' + key + '.json')
            if target.exists():
                if not resume:
                    raise FileExistsError('EXISTING_CAPTURE_REQUIRES_EXPLICIT_RESUME')
                record = self.read_record(key)
                self.verify_record(record)
                return record
            self.space()  # Check before calling any network producer.
            at = retrieved_at or utc(); stamp(at)
            attempt = self.path('attempts/' + uuid.uuid4().hex)
            temporary = attempt.with_suffix('.gz')
            h, size, chunks, pending = hashlib.sha256(), 0, [], bytearray()
            try:
                with temporary.open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
                    for value in producer():
                        if not isinstance(value, bytes):
                            raise TypeError('PRODUCER_MUST_YIELD_BYTES')
                        for i in range(0, len(value), CHUNK):
                            chunk = value[i:i + CHUNK]
                            self.space()
                            size += len(chunk)
                            if size > self.max_capture_bytes:
                                raise OSError('CAPTURE_BYTE_LIMIT_REACHED')
                            stream.write(chunk); h.update(chunk); pending.extend(chunk)
                            while len(pending) >= CHUNK:
                                chunks.append(hashlib.sha256(pending[:CHUNK]).hexdigest())
                                del pending[:CHUNK]
                    if pending:
                        chunks.append(hashlib.sha256(pending).hexdigest())
                self.space()
                if not size:
                    raise ValueError('EMPTY_CAPTURE')
                rawhash = h.hexdigest()
                objrel = 'objects/' + rawhash + '.gz'
                obj = self.path(objrel)
                if obj.exists():
                    # Equal raw hash is not permission to merge identity/vintage records.
                    with gzip.open(obj, 'rb') as stream:
                        existing = hashlib.sha256()
                        for part in iter(lambda: stream.read(CHUNK), b''):
                            existing.update(part)
                    if existing.hexdigest() != rawhash:
                        raise ValueError('CONTENT_ADDRESS_COLLISION_OR_CORRUPTION')
                    temporary.unlink()
                else:
                    os.replace(temporary, obj)
                record = {'schema_version': 1, 'status': 'CAPTURED', 'request_id': key,
                    'store_id': self.identity['store_id'], 'request': request,
                    'retrieved_at': at, 'revision': revision, 'object_path': objrel,
                    'raw_sha256': rawhash, 'raw_bytes': size, 'raw_chunk_sha256': chunks,
                    'compressed_sha256': file_sha(obj), 'compressed_bytes': obj.stat().st_size,
                    'normalization_status': 'NOT_ASSERTED', 'historical_information_certified': False}
                self.verify_record(record)
                atomic_json(target, record)
                atomic_json(attempt.with_suffix('.json'), {'status': 'CAPTURED', 'request_id': key,
                    'raw_sha256': rawhash, 'completed_at': utc()})
                return record
            except BaseException as exc:
                atomic_json(attempt.with_suffix('.json'), {'status': 'INCOMPLETE_OR_UNCOMMITTED',
                    'request_id': key, 'request': request, 'received_bytes': size,
                    'error_type': type(exc).__name__, 'ended_at': utc(),
                    'partial_path': temporary.name if temporary.exists() else None})
                raise

    def read_bytes(self, record):
        self.verify_record(record)
        if record['raw_bytes'] > self.max_capture_bytes:
            raise ValueError('MATERIALIZATION_BYTE_LIMIT')
        with gzip.open(self.path(record['object_path']), 'rb') as stream:
            return stream.read(record['raw_bytes'] + 1)

    def reuse_decision(self, key, request, *, partial_fetch=False, check=None):
        """Exact whole-representation reuse only. No inferred freshness or tail splice."""
        record = self.read_record(key)
        reasons = []
        if not partial_fetch:
            reasons.append('EXPLICIT_PARTIAL_FETCH_REQUIRED')
        validate_request(request)
        old_contract = {k: v for k, v in record['request'].items() if k not in ('vintage', 'observed_at', 'decision_at')}
        new_contract = {k: v for k, v in request.items() if k not in ('vintage', 'observed_at', 'decision_at')}
        if old_contract != new_contract:
            reasons.append('SOURCE_IDENTITY_SCHEMA_RANGE_OR_FIELDS_CHANGED')
        check = check or {}
        try:
            evidence = self.path(check['evidence_path'])
            if file_sha(evidence) != check['evidence_sha256']:
                reasons.append('SOURCE_CHECK_BYTES_MISMATCH')
            checked = stamp(check['checked_at'])
            if checked < stamp(record['retrieved_at']) or checked > datetime.now(timezone.utc):
                reasons.append('INVALID_CHECK_TIME')
            decision_at = request.get('decision_at') or request.get('observed_at')
            if not decision_at or checked < stamp(decision_at):
                reasons.append('CHECK_PREDATES_NEW_DECISION_OR_DECISION_UNKNOWN')
            if check.get('scope') != 'entire_retained_representation':
                reasons.append('INCOMPLETE_REVISION_SCOPE')
            if not record.get('revision') or check.get('revision') != record['revision']:
                reasons.append('REVISION_CHANGED_OR_UNKNOWN_FETCH_FULL_AFFECTED_HISTORY')
            if check.get('request_id') != key or check.get('new_request_sha256') != digest(request):
                reasons.append('SOURCE_CHECK_NOT_BOUND_TO_BOTH_REQUESTS')
        except (KeyError, ValueError, OSError, TypeError):
            reasons.append('MISSING_OR_INVALID_CURRENT_SOURCE_CHECK')
        try:
            self.verify_record(record)
        except (ValueError, OSError, EOFError):
            reasons.append('CORRUPT_PARENT_CAPTURE')
        return {'decision': 'REUSE' if not reasons else 'FETCH_FRESH', 'reasons': reasons,
            'parent_request_id': key, 'new_request_sha256': digest(request),
            'original_retrieved_at': record['retrieved_at'], 'current_checked_at': check.get('checked_at'),
            'source_check_authenticity_verified': False,
            'limit': 'Caller must establish the revision index covers the provider representation. Hash checks do not authenticate its meaning.'}

    def archive(self, relative, keys=None):
        """Lossless portable archive of selected owned captures, no broad directory walk."""
        with self.lock('maintenance'):
            return self._archive(relative, keys)

    def _archive(self, relative, keys=None):
        path = self.path(relative)
        if path.parent != self.path('archives') or path.suffix != '.zip' or path.exists():
            raise ValueError('NEW_ARCHIVE_UNDER_OWNED_ARCHIVES_REQUIRED')
        records = self.records() if keys is None else [self.read_record(k) for k in keys]
        if not records:
            raise ValueError('EMPTY_ARCHIVE_SELECTION')
        members = {MARKER}
        for record in records:
            self.verify_record(record)
            members.update((record['object_path'], 'records/' + record['request_id'] + '.json'))
        manifest = {'schema_version': 1, 'store_id': self.identity['store_id'], 'records': [r['request_id'] for r in records],
                    'files': {name: {'sha256': file_sha(self.path(name)), 'bytes': self.path(name).stat().st_size}
                              for name in sorted(members)}}
        self.space()
        with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.writestr('ARCHIVE-MANIFEST.json', json.dumps(manifest, sort_keys=True).encode())
            for name in sorted(members):
                with self.path(name).open('rb') as source, archive.open(name, 'w', force_zip64=True) as dest:
                    for chunk in iter(lambda: source.read(CHUNK), b''):
                        self.space(); dest.write(chunk)
        receipt = verify_archive(path)
        atomic_json(path.with_suffix('.verified.json'), receipt)
        return receipt

    def prune_to(self, retain_keys, archive_relative, *, delete=False):
        """Keep only requested captures after verifying a portable retained subset.

        Unrelated files, skill sources, attempts, archive witnesses and root marker
        are never recursive deletion targets. Dry-run is the default.
        """
        with self.lock('maintenance'):
            return self._prune_to(retain_keys, archive_relative, delete=delete)

    def _prune_to(self, retain_keys, archive_relative, *, delete=False):
        retain = set(retain_keys)
        if not retain:
            raise ValueError('EMPTY_RETAIN_SCOPE')
        archive = self.path(archive_relative)
        proof = verify_archive(archive)
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read('ARCHIVE-MANIFEST.json'))
        if manifest['store_id'] != self.identity['store_id'] or not retain <= set(manifest['records']):
            raise ValueError('RETAINED_SCOPE_NOT_ARCHIVED')
        records = self.records()
        selected = [r for r in records if r['request_id'] in retain]
        if {r['request_id'] for r in selected} != retain:
            raise ValueError('UNKNOWN_RETAIN_KEY')
        # Entire retained records must match sealed archive before any deletion.
        for r in selected:
            for name in (r['object_path'], 'records/' + r['request_id'] + '.json'):
                if file_sha(self.path(name)) != manifest['files'][name]['sha256']:
                    raise ValueError('RETAINED_SOURCE_CHANGED')
        kept_objects = {r['object_path'] for r in selected}
        removed = [r for r in records if r['request_id'] not in retain]
        targets = {'records/' + r['request_id'] + '.json' for r in removed}
        targets.update(r['object_path'] for r in removed if r['object_path'] not in kept_objects)
        validated = [(name, self.path(name), file_sha(self.path(name))) for name in sorted(targets)]
        if delete:
            for name, path, hashed in validated:
                if self.path(name) != path or file_sha(path) != hashed:
                    raise ValueError('DELETE_SOURCE_CHANGED')
                path.unlink()
        receipt = {'status': 'SCOPED_PRUNE_COMPLETE' if delete else 'SCOPED_PRUNE_PREVIEW',
            'store_id': self.identity['store_id'], 'retained_request_ids': sorted(retain),
            'removed_request_ids': [r['request_id'] for r in removed] if delete else [],
            'targets': [{'path': n, 'sha256': h} for n, p, h in validated],
            'archive_sha256': proof['archive_sha256'], 'recursive_deletion': False}
        atomic_json(self.path('attempts/prune-' + uuid.uuid4().hex + '.json'), receipt)
        return receipt


def verify_archive(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('DUPLICATE_ARCHIVE_MEMBERS')
        if archive.getinfo('ARCHIVE-MANIFEST.json').file_size > 32 * CHUNK:
            raise ValueError('ARCHIVE_MANIFEST_BYTE_LIMIT')
        manifest = json.loads(archive.read('ARCHIVE-MANIFEST.json'))
        if set(names) != set(manifest['files']) | {'ARCHIVE-MANIFEST.json'}:
            raise ValueError('ARCHIVE_MEMBER_SET_MISMATCH')
        for name, facts in manifest['files'].items():
            rel = PurePosixPath(name)
            if rel.is_absolute() or any(p in ('..', '.') or ':' in p for p in rel.parts) or '\\' in name:
                raise ValueError('UNSAFE_ARCHIVE_MEMBER')
            h, size = hashlib.sha256(), 0
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(CHUNK), b''):
                    size += len(chunk); h.update(chunk)
            if size != facts['bytes'] or h.hexdigest() != facts['sha256']:
                raise ValueError('ARCHIVE_MEMBER_HASH_MISMATCH')
    return {'status': 'EVERY_ARCHIVE_MEMBER_READ_AND_VERIFIED', 'archive_sha256': file_sha(path),
            'archive_bytes': path.stat().st_size, 'store_id': manifest['store_id'],
            'members_verified': len(manifest['files']), 'record_ids': manifest['records']}


def restore_archive(archive_path, destination, owner, *, min_free_bytes=256 * CHUNK,
                    max_restore_bytes=8 * 1024 * CHUNK):
    """Restore a verified portable store into a NEW explicit root, never overwrite."""
    proof = verify_archive(archive_path)
    destination = Path(destination).absolute()
    safe_path(destination.parent, destination.name)
    if destination.exists():
        raise FileExistsError('RESTORE_DESTINATION_MUST_BE_NEW')
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('ARCHIVE-MANIFEST.json'))
        if sum(row['bytes'] for row in manifest['files'].values()) > max_restore_bytes:
            raise ValueError('RESTORE_BYTE_LIMIT')
        marker = json.loads(archive.read(MARKER))
        if marker['owner'] != owner:
            raise ValueError('RESTORE_OWNER_MISMATCH')
        destination.mkdir(parents=True)
        for name in manifest['files']:
            target = safe_path(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open('xb') as output:
                for chunk in iter(lambda: source.read(CHUNK), b''):
                    if shutil.disk_usage(destination).free < min_free_bytes + 2 * CHUNK:
                        raise OSError('RESTORE_STORAGE_RESERVE_REACHED')
                    output.write(chunk)
        for name in ('objects', 'records', 'attempts', 'locks', 'archives'):
            (destination / name).mkdir(exist_ok=True)
    Store(destination, owner).verify()
    return proof


def coverage(requested, observations, required_sessions=None, decision_at=None):
    """Report declared usable sessions and availability, not source authenticity."""
    if len(set(requested)) != len(requested):
        raise ValueError('DUPLICATE_REQUESTED_SECURITY_ID')
    rows = []
    for security in requested:
        selected = [o for o in observations if o.get('security_id') == security]
        usable = set().union(*(set(o.get('usable_sessions', [])) for o in selected)) if selected else set()
        missing = sorted(set(required_sessions or []) - usable)
        eligible, unknown = [], []
        for o in selected:
            # Fiscal period-end is never substituted for publication availability.
            if decision_at:
                clocks = [stamp(o[k]) for k in ('available_at', 'published_at') if o.get(k)]
                if not clocks:
                    unknown.append(o.get('artifact_id'))
                elif max(clocks) <= stamp(decision_at):
                    eligible.append(o.get('artifact_id'))
        rows.append({'security_id': security, 'artifact_count': len(selected),
            'provider_queries': sorted({o['provider_symbol'] for o in selected if o.get('provider_symbol')}),
            'usable_session_count': len(usable), 'missing_sessions': missing,
            'historical_identity_unresolved': any(not o.get('historical_identity_verified') for o in selected) or not selected,
            'available_at_decision_artifact_ids': eligible, 'availability_unknown_artifact_ids': unknown,
            'session_coverage_assessed': bool(required_sessions),
            'status': ('NOT_ASSESSED' if not required_sessions else
                       'DECLARED_SESSION_COVERAGE' if selected and not missing else 'GAP')})
    return {'requested_security_count': len(requested), 'source_artifact_count': len(observations),
        'rows': rows, 'point_in_time_certified': False, 'source_authenticity_verified': False}


def scope_keys(records, security_ids, *, former_member_ids=(), benchmark_ids=()):
    """Caller supplies dated membership; preserve every capture for included keys."""
    requested = set(security_ids) | set(former_member_ids) | set(benchmark_ids)
    if not requested:
        raise ValueError('EXPLICIT_NONEMPTY_SCOPE_REQUIRED')
    selected = [r for r in records if r['request']['security_id'] in requested]
    found = {r['request']['security_id'] for r in selected}
    return {'request_ids': [r['request_id'] for r in selected],
        'requested_security_ids': sorted(requested), 'missing_security_ids': sorted(requested - found),
        'historical_membership_verified': False, 'selection_basis': 'caller_supplied_explicit_identity_sets'}


def write_parquet_batches(path, batches, schema, *, max_batch_bytes=64 * CHUNK,
                          min_free_bytes=256 * CHUNK):
    """Optional Arrow writer: bounded caller batches, ZSTD, no silent CSV fallback."""
    import pyarrow.parquet as pq
    path = Path(path).absolute()
    safe_path(path.parent, path.name)
    if max_batch_bytes <= 0 or min_free_bytes < 0:
        raise ValueError('INVALID_PARQUET_STORAGE_BOUNDS')
    def space():
        if shutil.disk_usage(path.parent).free < min_free_bytes + max_batch_bytes:
            raise OSError('PARQUET_STORAGE_RESERVE_REACHED')
    space()
    if path.exists():
        raise FileExistsError(str(path))
    temporary = path.with_name(path.name + '.partial-' + uuid.uuid4().hex)
    try:
        with pq.ParquetWriter(temporary, schema, compression='zstd') as writer:
            for batch in batches:
                space()
                if not batch.schema.equals(schema, check_metadata=True):
                    raise ValueError('PARQUET_SCHEMA_CHANGED')
                if batch.nbytes > max_batch_bytes:
                    raise ValueError('PARQUET_BATCH_BYTE_LIMIT')
                writer.write_batch(batch)
        space()
        safe_path(path.parent, path.name)
        if path.exists():
            raise FileExistsError(str(path))
        os.replace(temporary, path)
    except BaseException:
        # Partial is retained as incomplete evidence, never installed as success.
        raise
    return {'path': path.name, 'sha256': file_sha(path), 'compression': 'zstd'}


def read_parquet_batches(path, batch_size=65536, max_batch_bytes=64 * CHUNK):
    """Optional Arrow reader with explicit bounded row batches."""
    import pyarrow.parquet as pq
    if not isinstance(batch_size, int) or batch_size <= 0 or max_batch_bytes <= 0:
        raise ValueError('POSITIVE_BATCH_SIZE_REQUIRED')
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
        if batch.nbytes > max_batch_bytes:
            raise ValueError('PARQUET_BATCH_BYTE_LIMIT')
        yield batch


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--owner', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    c = sub.add_parser('capture-file'); c.add_argument('--request', type=Path, required=True)
    c.add_argument('--input', type=Path, required=True); c.add_argument('--resume', action='store_true')
    v = sub.add_parser('verify'); v.add_argument('--previous', type=Path)
    a = sub.add_parser('archive'); a.add_argument('--name', required=True); a.add_argument('--keys', type=Path)
    r = sub.add_parser('prune'); r.add_argument('--retain-keys', type=Path, required=True)
    r.add_argument('--archive', required=True); r.add_argument('--delete', action='store_true')
    args = p.parse_args(); store = Store(args.root, args.owner, create=args.command == 'init')
    if args.command == 'init': result = store.identity
    elif args.command == 'capture-file':
        def chunks():
            with args.input.open('rb') as stream:
                yield from iter(lambda: stream.read(CHUNK), b'')
        result = store.capture(json.loads(args.request.read_text()), chunks, resume=args.resume)
    elif args.command == 'verify': result = store.verify(json.loads(args.previous.read_text()) if args.previous else None)
    elif args.command == 'archive': result = store.archive('archives/' + args.name, json.loads(args.keys.read_text()) if args.keys else None)
    else: result = store.prune_to(json.loads(args.retain_keys.read_text()), args.archive, delete=args.delete)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
