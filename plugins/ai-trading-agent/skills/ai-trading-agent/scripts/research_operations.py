"""Explicit local operations for a supervised PAPER production research workflow.

No scheduler, credentials, source substitution, order submission or live policy is
created. Retained artifacts and local clocks do not authenticate outside events.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
import uuid

import institutional_research as research
import market_sources

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 256 * 1024 * 1024
PARSE_OPTIONS = frozenset(('delimiter', 'value_unit', 'columns', 'venue_scope',
                           'security_context', 'ticker', 'cik', 'report_date',
                           'form', 'id_prefix', 'zip_member', 'form_filter', 'cik_symbol_mapping', 'raw_complete', 'bar_context'))


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8') + b'\n'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _id(value):
    _require(type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', value)
             and value not in ('.', '..'), 'SAFE_IDENTIFIER_REQUIRED')
    return value


def _stamp(value):
    _require(type(value) is str, 'AWARE_TIMESTAMP_REQUIRED')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'AWARE_TIMESTAMP_REQUIRED')
    return parsed.astimezone(timezone.utc)


def _read(path):
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), 'REGULAR_FILE_REQUIRED')
    _require(path.stat().st_size <= MAX_JSON_BYTES, 'INPUT_SIZE_CAP')
    raw = path.read_bytes()
    _require(len(raw) <= MAX_JSON_BYTES, 'INPUT_SIZE_CAP')
    return raw


def _load(path):
    return json.loads(_read(path).decode('utf-8-sig'))


def _publish(path, value):
    research._publish(path, _bytes(value))


def _directory(root, name):
    _id(name)
    path = root / name
    if not path.exists():
        path.mkdir()
    _require(path.is_dir() and not path.is_symlink()
             and path.resolve() == root / name, 'OWNED_DIRECTORY_REQUIRED')
    return path


def _root(value):
    path = Path(value)
    _require(path.is_dir() and not path.is_symlink(), 'EXPLICIT_EXISTING_PRIVATE_ROOT_REQUIRED')
    path = path.resolve()
    def plain(native):
        text = str(native)
        if text.startswith('\\\\?\\UNC\\'):
            return '\\\\' + text[8:]
        return text[4:] if text.startswith('\\\\?\\') else text
    logical = os.path.normcase(os.path.abspath(plain(path)))
    package = os.path.normcase(os.path.abspath(plain(ROOT)))
    try:
        inside = os.path.commonpath((logical, package)) == package
    except ValueError:
        inside = False  # Different explicitly selected volumes.
    _require(not inside, 'PRIVATE_ROOT_OUTSIDE_PACKAGE_REQUIRED')
    if os.name == 'nt':
        # Native hard-link publication otherwise encounters the classic Windows
        # path limit for deeply nested journal/lock archive paths. This changes
        # path spelling only, never system settings, ACLs or the selected root.
        text = plain(path)
        path = Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)
    return path


def _software():
    # Bind transitive implementation modules as well as the released manifest.
    # This is source-byte identity, not attestation of loaded libraries or hosts.
    paths = [ROOT / 'PACKAGE-MANIFEST.json', *sorted((ROOT / 'scripts').rglob('*.py'))]
    _require(all(p.resolve().is_relative_to(ROOT.resolve()) and not p.is_symlink() for p in paths),
             'REGULAR_IMPLEMENTATION_FILES_REQUIRED')
    return {p.relative_to(ROOT).as_posix(): _sha(_read(p)) for p in paths}


def _config(value):
    _require(type(value) is dict and type(value.get('schema_version')) is int
             and value['schema_version'] == 1, 'CONFIG_SCHEMA_REQUIRED')
    _require(set(value) <= {'schema_version', 'workflow', 'sources', 'freshness',
                            'hypothetical_portfolio', 'source_configuration_status',
                            'intended_data_uses', 'deployment'}, 'UNKNOWN_CONFIG_FIELD')
    workflow = value.get('workflow')
    _require(type(workflow) is dict and workflow.get('id'), 'WORKFLOW_REQUIRED')
    _id(workflow['id'])
    configured = research.plan({'schema_version': 1, 'as_of': _now(), 'records': [], 'workflow': workflow})
    _require(not configured['missing_configuration'], 'COMPLETE_ADOPTED_WORKFLOW_CONFIGURATION_REQUIRED')
    _require(type(value.get('sources')) is list and len(value['sources']) <= 32, 'BOUNDED_EXPLICIT_SOURCES_REQUIRED')
    seen = set()
    for source in value['sources']:
        _require(type(source) is dict and set(source) <= {
            'id', 'url', 'adapter', 'user_agent', 'rights', 'parse_options',
            'max_bytes', 'timeout', 'retries'}, 'UNKNOWN_SOURCE_FIELD')
        _id(source.get('id'))
        _require(source['id'] not in seen, 'DUPLICATE_SOURCE_ID')
        seen.add(source['id'])
        _require(source.get('adapter') in market_sources.ADAPTERS, 'SUPPORTED_ADAPTER_REQUIRED')
        public_borrow = source['adapter'] == 'ibkr_shortstock'
        if public_borrow:
            from borrow_intake import allowed_public_url
            allowed_public_url(source.get('url'))
        else:
            market_sources.allowed_public_url(source.get('url'))
        ua = source.get('user_agent')
        if not public_borrow or ua is not None:
            _require(type(ua) is str and 0 < len(ua) <= 300 and '\r' not in ua and '\n' not in ua
                     and ('@' in ua or 'https://' in ua), 'EXPLICIT_RESEARCH_CONTACT_USER_AGENT_REQUIRED')
        _require(type(source.get('rights')) is str and source['rights'].strip(), 'RIGHTS_DECLARATION_REQUIRED')
        options = source.get('parse_options', {})
        _require(type(options) is dict and set(options) <= PARSE_OPTIONS, 'UNKNOWN_PARSE_OPTION')
        size = source.get('max_bytes', 8 * 1024 * 1024)
        retries = source.get('retries', 0)
        timeout = source.get('timeout', 15)
        _require(type(size) is int and 1 <= size <= market_sources.MAX_BYTES, 'INVALID_BYTE_BOUND')
        _require(type(retries) is int and 0 <= retries <= 2, 'INVALID_RETRY_BOUND')
        _require(not public_borrow or retries == 0, 'PUBLIC_FTP_REQUIRES_ZERO_AUTOMATIC_RETRIES')
        _require(type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= 30, 'INVALID_TIMEOUT_BOUND')
    freshness = value.get('freshness')
    age = freshness.get('max_capture_age_seconds') if type(freshness) is dict else None
    _require(type(freshness) is dict and set(freshness) == {'max_capture_age_seconds'}
             and type(age) in (int, float) and math.isfinite(age) and age >= 0, 'EXPLICIT_CAPTURE_FRESHNESS_REQUIRED')
    return deepcopy(value)


def _registration(root, enforce_software=True):
    config = _config(_load(root / 'workflow-config.json'))
    registration = _load(root / 'registration.json')
    _require(registration['config_sha256'] == _sha(_bytes(config)), 'REGISTERED_CONFIG_HASH_MISMATCH')
    if enforce_software:
        _require(registration['software_sha256'] == _software(), 'SOFTWARE_BINDING_CHANGED_REGISTER_NEW_ROOT')
    return config, registration


def _failure(root, operation, run_id, error):
    folder = _directory(root, 'failures')
    value = {'operation': operation, 'run_id': run_id, 'recorded_at': _now(),
             'error_type': type(error).__name__, 'error': str(error), 'execution_authorized': False}
    _publish(folder / (uuid.uuid4().hex + '.json'), value)


def _locked(root, operation, run_id, function):
    with research._lock(root):
        try:
            return function()
        except BaseException as error:
            try:
                _failure(root, operation, run_id, error)
            except BaseException:
                pass  # Preserve the original failure; caller stdout/stderr remains evidence.
            raise


def register(root_value, config):
    root = _root(root_value)
    def action():
        value = _config(config)
        if (root / 'registration.json').exists():
            previous, registration = _registration(root)
            _require(_bytes(previous) == _bytes(value), 'IMMUTABLE_CONFIG_CONFLICT_REGISTER_NEW_ROOT')
            return registration
        _publish(root / 'workflow-config.json', value)
        registration = {'schema_version': 1, 'status': 'REGISTERED_SUPERVISED_RESEARCH_WORKFLOW',
                        'workflow_id': value['workflow']['id'],
                        'config_sha256': _sha(_bytes(value)), 'registered_at': _now(),
                        'software_sha256': _software(), 'execution_authorized': False,
                        'scope': 'LOCAL_WINDOWS_SUPERVISED_PAPER_RESEARCH'}
        _publish(root / 'registration.json', registration)
        return registration
    return _locked(root, 'register', None, action)


def _run(root, run_id, registration, create=False):
    _id(run_id)
    runs = _directory(root, 'runs') if create else root / 'runs'
    path = _directory(runs, run_id) if create else runs / run_id
    _require(path.is_dir() and not path.is_symlink()
             and path.resolve() == root / 'runs' / run_id, 'REGISTERED_RUN_REQUIRED')
    identity = path / 'run.json'
    if not identity.exists() and create:
        _publish(identity, {'schema_version': 1, 'id': run_id, 'config_sha256': registration['config_sha256'],
                            'created_at': _now(), 'execution_authorized': False})
    value = _load(identity)
    _require(value['id'] == run_id and value['config_sha256'] == registration['config_sha256'], 'RUN_IDENTITY_CONFLICT')
    return path, value


def _replace_checkpoint(path, value):
    raw = _bytes(value)
    if path.exists() and _read(path) == raw:
        return
    expected = _read(path) if path.exists() else None
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
        if expected is None:
            os.link(temp, path)
        else:
            _require(_read(path) == expected, 'CONCURRENT_CHECKPOINT_RETAINED')
            os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _pace_public_request(root, source):
    if urlsplit(source['url']).hostname not in ('www.sec.gov', 'data.sec.gov'):
        return
    path = root / 'sec-request-start.json'
    now = _stamp(_now())
    if path.exists():
        previous = _stamp(_load(path)['started_at'])
        elapsed = (now - previous).total_seconds()
        _require(elapsed >= 0, 'SEC_LOCAL_CLOCK_BEFORE_LAST_REQUEST')
        if elapsed < 1:
            time.sleep(1 - elapsed)  # At most one second; caller owns the root lock.
            now = _stamp(_now())
            _require((now - previous).total_seconds() >= 1, 'SEC_REQUEST_PACING_CLOCK_NOT_ADVANCED')
    _replace_checkpoint(path, {'started_at': now.isoformat(), 'minimum_spacing_seconds': 1,
                               'scope': 'THIS_PRIVATE_ROOT_ONLY_OTHER_CLIENTS_REQUIRE_COORDINATION'})


def _attempts(run, source_id):
    folder = run / 'captures' / source_id
    if not folder.exists():
        return []
    _require(folder.is_dir() and not folder.is_symlink()
             and folder.resolve() == run / 'captures' / source_id, 'OWNED_CAPTURE_DIRECTORY_REQUIRED')
    values = sorted(folder.iterdir(), key=lambda p: p.name)
    _require(all(p.is_dir() and not p.is_symlink() and re.fullmatch(r'attempt-\d{4}', p.name) for p in values), 'UNEXPECTED_CAPTURE_PATH')
    return values


def _attempt_info(path, source, write_parse=False):
    planned = _load(path / 'planned.json')
    _require(planned['source_id'] == source['id'] and planned['url'] == source['url'], 'CAPTURE_IDENTITY_MISMATCH')
    info = {'attempt': path.name, 'source_id': source['id'], 'started_at': planned['started_at'],
            'status': 'INCOMPLETE_CAPTURE_REQUIRES_EXPLICIT_RETRY', 'records': [],
            'error': 'No complete acquisition manifest; do not assume whether the public transfer finished.'}
    manifest_path = path / 'download/manifest.json'
    if not manifest_path.exists():
        if (path / 'call-error.json').exists():
            info.update(status='ACQUISITION_FAILED', error=_load(path / 'call-error.json')['error'])
        return info
    _require(manifest_path.resolve() == path / 'download/manifest.json', 'OWNED_DOWNLOAD_DIRECTORY_REQUIRED')
    manifest = _load(manifest_path)
    _require(manifest.get('request_url') == source['url'] and manifest.get('source_id') == source['id'], 'ACQUISITION_MANIFEST_IDENTITY_MISMATCH')
    info.update(manifest_sha256=_sha(_read(manifest_path)), finished_at=manifest.get('finished_at', planned['started_at']))
    if manifest.get('status') != 'ACQUIRED':
        info.update(status='ACQUISITION_FAILED', error=manifest.get('attempts', [{}])[-1].get('error', 'ACQUISITION_NOT_COMPLETE'))
        return info
    last = manifest.get('attempts', [{}])[-1]
    name = manifest.get('raw_file')
    _require(type(name) is str and re.fullmatch(r'attempt-\d{2}\.raw', name), 'SAFE_RAW_FILENAME_REQUIRED')
    raw_path = path / 'download' / name
    raw = _read(raw_path)
    if source['adapter'] == 'ibkr_shortstock':
        from borrow_intake import allowed_public_url
        allowed_public_url(source['url'])
        declared_size = last.get('declared_size_bytes')
        unsupported_size = last.get('size_unavailable_response')
        size_valid = ('declared_size_bytes' in last and
            (type(declared_size) is int and declared_size == len(raw) or
             declared_size is None and type(unsupported_size) is str and
             re.match(r'^(?:500|502|504)(?:\s|$)', unsupported_size) is not None))
        transport_valid = (manifest.get('transport') == last.get('transport') == 'FTP'
            and type(manifest.get('attempts')) is list and len(manifest['attempts']) == 1
            and manifest.get('method') == 'RETR' and type(manifest.get('retries_limit')) is int
            and manifest['retries_limit'] == 0
            and manifest.get('personal_account_access') is False
            and manifest.get('raw_complete') is True
            and manifest.get('source', {}).get('raw_complete') is True
            and manifest.get('source', {}).get('transport') == 'FTP' and 'error' not in last
            and type(last.get('ftp_response_code')) is int and last['ftp_response_code'] == 226
            and type(last.get('retr_commands')) is int and last['retr_commands'] == 1
            and last.get('ftp_control_socket_closed') is True
            and size_valid)
    else:
        transport_valid = last.get('http_status') == 200 and manifest.get('transport', 'HTTPS') == 'HTTPS'
    _require(transport_valid and last.get('raw_complete') is True
             and last.get('final_url') == source['url'] and last.get('raw_file') == name
             and last.get('retained_bytes') == len(raw)
             and manifest.get('raw_sha256') == last.get('raw_sha256') == _sha(raw), 'COMPLETE_RAW_ACQUISITION_BINDING_REQUIRED')
    declared = manifest.get('source', {})
    at = manifest.get('available_at')
    _stamp(at)
    _require(declared.get('id') == source['id'] and declared.get('url') == source['url']
             and declared.get('retrieved_at') == declared.get('observed_at') == at
             and declared.get('availability_basis') == 'first_observed_snapshot', 'ACQUISITION_CLOCK_BINDING_REQUIRED')
    options = deepcopy(source.get('parse_options', {}))
    member = options.pop('zip_member', None)
    text, raw_sha, content_sha = market_sources.raw_text(raw_path, member)
    metadata = deepcopy(declared)
    metadata.update(raw_sha256=raw_sha, decoded_content_sha256=content_sha, raw_complete=True)
    document = dict(options, schema_version=1, adapter=source['adapter'], as_of=at,
                    available_at=at, source=metadata, text=text, raw_complete=True)
    try:
        parsed = market_sources.parse(document)
    except Exception as error:
        if write_parse:
            stable = {'error_type': type(error).__name__, 'error': str(error),
                      'raw_sha256': raw_sha, 'source_id': source['id']}
            folder = _directory(path, 'parse-errors')
            error_path = folder / ('error-' + _sha(_bytes(stable)) + '.json')
            if not error_path.exists():
                _publish(error_path, dict(stable, recorded_at=_now()))
        info.update(status='PARSE_FAILED', error=str(error), available_at=at, raw_sha256=raw_sha)
        return info
    parsed_path = path / 'parsed.json'
    if not parsed_path.exists() and not write_parse:
        info.update(status='PARSE_NOT_COMPLETED', error='Run collect again to complete retained-file parsing; no new GET is needed.',
                    available_at=at, raw_sha256=raw_sha)
        return info
    if write_parse:
        _publish(parsed_path, parsed)
    _require(_read(parsed_path) == _bytes(parsed), 'RETAINED_PARSED_BYTES_MISMATCH')
    eligible = sum(r.get('eligible') is True for r in parsed['records'])
    mapped = sum(r.get('eligible') is True and type(r.get('ticker')) is str and bool(r['ticker'].strip())
                 for r in parsed['records'])
    qualifications = []
    if eligible == 0:
        qualifications.append('NO_ELIGIBLE_RECORDS')
    if mapped == 0:
        qualifications.append('NO_MAPPED_TARGET_IDENTITIES')
    gaps = parsed.get('issues', []) or any(r.get('parse_error') for r in parsed['records']) or qualifications
    info.update(status='PARSED_WITH_GAPS' if gaps else 'PARSED', error=None,
                available_at=at, raw_sha256=raw_sha, parsed_sha256=_sha(_read(parsed_path)),
                records=parsed['records'], parse_issues=parsed.get('issues', []),
                eligible_records=eligible, ineligible_records=len(parsed['records']) - eligible,
                mapped_eligible_records=mapped, qualifications=qualifications)
    return info


def _parse_failure_history(path, source, expected_raw=None):
    candidates = [path / 'parse-error.json'] if (path / 'parse-error.json').exists() else []
    folder = path / 'parse-errors'
    if folder.exists():
        _require(folder.is_dir() and not folder.is_symlink() and folder.resolve() == path / 'parse-errors',
                 'OWNED_PARSE_ERROR_DIRECTORY_REQUIRED')
        files = sorted(folder.iterdir())
        _require(all(re.fullmatch(r'error-[0-9a-f]{64}\.json', p.name) for p in files),
                 'SAFE_PARSE_ERROR_FILENAME_REQUIRED')
        candidates.extend(files)
    history = []
    for error_path in candidates:
        value = _load(error_path)
        _require(value.get('source_id') == source['id'], 'PARSE_FAILURE_SOURCE_MISMATCH')
        if expected_raw is not None:
            _require(value.get('raw_sha256') == expected_raw, 'PARSE_FAILURE_RAW_MISMATCH')
        if error_path.name != 'parse-error.json':
            stable = {k: value[k] for k in ('error_type', 'error', 'raw_sha256', 'source_id')}
            _require(error_path.name == 'error-' + _sha(_bytes(stable)) + '.json', 'PARSE_FAILURE_CONTENT_MISMATCH')
        if value.get('recorded_at') is not None:
            _stamp(value['recorded_at'])
        history.append(dict(value, status='RETAINED_PARSE_FAILURE',
            recorded_at=value.get('recorded_at'), evidence_file=error_path.relative_to(path).as_posix(),
            timestamp_basis='recorded_failure' if value.get('recorded_at') else 'legacy_failure_clock_unknown'))
    return history


def _source_info(run, source, write_parse=False):
    attempts = _attempts(run, source['id'])
    history = []
    for path in attempts:
        try:
            value = _attempt_info(path, source, write_parse=write_parse)
            value['retained_parse_failures'] = _parse_failure_history(path, source, value.get('raw_sha256'))
        except Exception as error:
            value = {'attempt': path.name, 'source_id': source['id'], 'status': 'INTEGRITY_ERROR',
                     'records': [], 'error': str(error), 'started_at': _load(path / 'planned.json').get('started_at')}
        history.append(value)
    latest = history[-1] if history else {'source_id': source['id'], 'status': 'NOT_COLLECTED', 'records': [], 'error': 'No capture attempted.'}
    result = deepcopy(latest)
    result['attempt_history'] = [{k: v for k, v in item.items() if k != 'records'} for item in history]
    return result


def _source_failures(sources):
    result = []
    for source in sources:
        for attempt in source['attempt_history']:
            retained = attempt.get('retained_parse_failures', [])
            if attempt['status'] != 'PARSED' and not (attempt['status'] == 'PARSE_FAILED' and retained):
                result.append(dict(source_id=source['source_id'], **{k: v for k, v in attempt.items() if k != 'source_id'}))
            for failure in retained:
                result.append(dict(failure, source_id=source['source_id'], attempt=attempt['attempt']))
    return result


def _collection(run, identity, config, write_parse=False):
    sources = [_source_info(run, source, write_parse) for source in config['sources']]
    complete = all(s['status'] == 'PARSED' for s in sources)
    status = 'NO_CONFIGURED_SOURCES' if not sources else ('COLLECTED' if complete else 'COLLECTED_WITH_GAPS')
    failures = _source_failures(sources)
    return {'schema_version': 1, 'run_id': identity['id'], 'config_sha256': identity['config_sha256'],
            'status': status, 'sources': [{k: v for k, v in s.items() if k != 'records'} for s in sources],
            'failures': failures, 'coverage_gaps': ['No sources are configured; this is not evidence of zero market activity.'] if not sources else
            [s['source_id'] + ':' + s['status'] for s in sources if s['status'] != 'PARSED'],
            'execution_authorized': False}, sources


def collect(root_value, run_id, retry_failed=False):
    root = _root(root_value)
    def action():
        config, registration = _registration(root)
        run, identity = _run(root, run_id, registration, True)
        for source in config['sources']:
            info = _source_info(run, source, True)
            if info['status'] in ('PARSED', 'PARSED_WITH_GAPS'):
                continue
            if info['status'] != 'NOT_COLLECTED' and not retry_failed:
                continue
            folder = _directory(_directory(run, 'captures'), source['id'])
            attempt = _directory(folder, 'attempt-' + str(len(_attempts(run, source['id'])) + 1).zfill(4))
            _publish(attempt / 'planned.json', {'source_id': source['id'], 'url': source['url'],
                                             'started_at': _now(), 'explicit_retry_failed': bool(retry_failed)})
            try:
                _pace_public_request(root, source)
                if source['adapter'] == 'ibkr_shortstock':
                    from borrow_intake import acquire
                    acquire(source['url'], attempt / 'download', source['id'], source['rights'],
                            source.get('max_bytes', 8 * 1024 * 1024), source.get('timeout', 15),
                            source.get('retries', 0))
                else:
                    market_sources.acquire(source['url'], attempt / 'download', source['id'], source['user_agent'],
                                           source['rights'], source.get('max_bytes', 8 * 1024 * 1024),
                                           source.get('timeout', 15), source.get('retries', 0))
            except Exception as error:
                _publish(attempt / 'call-error.json', {'error_type': type(error).__name__, 'error': str(error)})
        value, _ = _collection(run, identity, config, True)
        _replace_checkpoint(run / 'collection.json', value)
        return value
    return _locked(root, 'collect', run_id, action)


def _body(record):
    return {k: deepcopy(v) for k, v in record.items() if k not in ('eligible', 'exclusion_reasons')}


def _selection(document):
    event = document.get('event')
    ticker = event.get('ticker') if type(event) is dict else None
    _require(type(ticker) is str and ticker.strip(), 'DECLARED_EVENT_TICKER_REQUIRED')
    selection = deepcopy(document.get('selection', {'tickers': [ticker], 'record_ids': []}))
    _require(type(selection) is dict and set(selection) <= {'tickers', 'record_ids'}, 'INVALID_EXPLICIT_SELECTION')
    selection.setdefault('record_ids', [])
    _require(type(selection.get('tickers')) is list and selection['tickers']
             and all(type(t) is str and t.strip() for t in selection['tickers'])
             and ticker in selection['tickers'] and len(set(selection['tickers'])) == len(selection['tickers']), 'EXPLICIT_TARGET_SELECTION_REQUIRED')
    _require(type(selection['record_ids']) is list and all(type(i) is str and i for i in selection['record_ids']), 'EXPLICIT_RECORD_SELECTION_REQUIRED')
    return selection


def _outcome(document, sources):
    value = document.get('run_outcome')
    if value is None:
        return None
    _require(type(value) is dict and value.get('disposition') in ('SOURCE_GAP', 'ABSTAIN', 'NO_EVENT'), 'EXPLICIT_RUN_DISPOSITION_REQUIRED')
    _require(type(value.get('reason')) is str and value['reason'].strip(), 'RUN_DISPOSITION_REASON_REQUIRED')
    coverage = value.get('coverage')
    _require(type(coverage) is dict and type(coverage.get('scope')) is str and coverage['scope'].strip(), 'EXPLICIT_DISPOSITION_COVERAGE_REQUIRED')
    _require(_stamp(coverage.get('checked_at')) <= _stamp(document['as_of']), 'DISPOSITION_COVERAGE_AFTER_CUTOFF')
    if value['disposition'] == 'NO_EVENT':
        observed = coverage.get('observed_source_ids')
        eligible_sources = {s['source_id'] for s in sources if s['status'] == 'PARSED'
                            and _stamp(s['available_at']) <= _stamp(document['as_of'])}
        _require(value.get('observed_no_event') is True and coverage.get('status') == 'COMPLETE_DECLARED_SCOPE'
                 and type(observed) is list and observed and all(s in eligible_sources for s in observed),
                 'NO_EVENT_REQUIRES_EXPLICIT_COMPLETE_SOURCE_OBSERVATION')
    return deepcopy(value)


def _selected(records, selection):
    selected = {r.get('id') for r in records if r.get('ticker') in selection['tickers']
                or r.get('id') in selection['record_ids']}
    changed = True
    while changed:
        before = set(selected)
        for row in records:
            payload = row.get('payload', {})
            parent = row.get('supersedes')
            if row.get('id') in selected:
                if parent is not None:
                    selected.add(parent)
                if type(payload) is dict:
                    benchmark = payload.get('benchmark_record_id')
                    if benchmark is not None:
                        selected.add(benchmark)
            if parent is not None and parent in selected:
                selected.add(row.get('id'))
        # Retain all competing benchmark feed identities. Dropping one before
        # the flow resolver runs could turn an ambiguous comparator into a value.
        def benchmark_key(row):
            payload = row.get('payload')
            if row.get('kind') != 'bar' or not isinstance(payload, dict) or payload.get('bar_type') != 'cumulative':
                return None
            return _bytes([row.get('ticker'), *[payload.get(k) for k in
                ('feed_id', 'start_at', 'end_at', 'session_id', 'comparison_group')]])
        keys = {benchmark_key(row) for row in records if row.get('id') in selected
                and isinstance(row.get('payload'), dict) and row['payload'].get('role') == 'benchmark'}
        keys.discard(None)
        selected.update(row.get('id') for row in records if benchmark_key(row) in keys)
        selected.discard(None)
        changed = selected != before
    return [_body(row) for row in records if row.get('id') in selected]


def _assemble(run, identity, config, document):
    _require(type(document) is dict and type(document.get('schema_version')) is int
             and document['schema_version'] == 1, 'COMMON_ENVELOPE_SCHEMA_REQUIRED')
    _stamp(document.get('as_of'))
    _require(type(document.get('records')) is list and all(type(r) is dict for r in document['records']), 'EXPLICIT_RECORD_LIST_REQUIRED')
    _require(all(type(r.get('id')) is str and r['id'] for r in document['records']), 'EXPLICIT_RECORD_IDENTITIES_REQUIRED')
    _require('workflow' not in document or _bytes(document['workflow']) == _bytes(config['workflow']), 'REGISTERED_WORKFLOW_CONFLICT')
    collection, sources = _collection(run, identity, config, False)
    _require((run / 'collection.json').exists() and _bytes(_load(run / 'collection.json')) == _bytes(collection), 'COLLECTION_CHECKPOINT_MISMATCH_RUN_COLLECT')
    records = [_body(r) for source in sources if source['status'] in ('PARSED', 'PARSED_WITH_GAPS') for r in source['records']]
    by_id = {}
    for row in records:
        by_id.setdefault(row.get('id'), []).append(row)
    configured = {s['id'] for s in config['sources']}
    supplied = []
    for original in document['records']:
        row = _body(original)
        source_id = row.get('source', {}).get('id') if type(row.get('source')) is dict else None
        matches = by_id.get(row.get('id'), [])
        if matches or source_id in configured:
            _require(len(matches) == 1 and _bytes(matches[0]) == _bytes(row), 'CONFIGURED_SOURCE_ROW_NOT_BOUND_TO_RETAINED_PARSE')
        else:
            records.append(row)
            supplied.append(row.get('id'))
    outcome = _outcome(document, sources)
    selection = ({'tickers': [], 'record_ids': [r['id'] for r in document['records']]}
                 if outcome else _selection(document))
    _require(set(selection['record_ids']) <= {r.get('id') for r in records}, 'SELECTED_RECORD_ID_NOT_RETAINED')
    assembled = deepcopy(document)
    assembled.update(workflow=deepcopy(config['workflow']), records=_selected(records, selection), selection=selection)
    if 'portfolio' not in assembled and config.get('hypothetical_portfolio') is not None:
        assembled['portfolio'] = deepcopy(config['hypothetical_portfolio'])
    return assembled, collection, supplied


def _calculate(assembled):
    plan = research.plan(assembled)
    if assembled.get('run_outcome'):
        response = {'schema_version': 1, 'kind': 'RESEARCH_RUN_DISPOSITION',
                    'status': 'RECORDED_' + assembled['run_outcome']['disposition'],
                    'as_of': assembled['as_of'], 'workflow_id': assembled['workflow']['id'],
                    'run_outcome': deepcopy(assembled['run_outcome']), 'execution_authorized': False,
                    'limitation': 'Explicit operator disposition and declared coverage retained; no investment brief or actual no-event completeness is inferred.'}
    else:
        response = research.brief(assembled)
    return plan, response


def compare_selected_records(full_document, incremental_document, selection):
    _require(_stamp(full_document['as_of']) == _stamp(incremental_document['as_of']), 'INCREMENTAL_CUTOFF_MISMATCH')
    def view(document):
        normalized = market_sources.normalize({'schema_version': 1, 'as_of': document['as_of'],
                                               'records': document['records']})
        chosen = _selected(normalized['records'], selection)
        eligible = [row for row in chosen if next(r for r in normalized['records'] if r['id'] == row['id']).get('eligible')]
        return sorted(eligible, key=lambda r: (str(r.get('id')), _bytes(r))), normalized['issues']
    full, full_issues = view(full_document)
    incremental, incremental_issues = view(incremental_document)
    equal = _bytes(full) == _bytes(incremental)
    return {'status': 'SELECTED_ELIGIBLE_RECORDS_EQUAL' if equal else 'SELECTED_ELIGIBLE_RECORDS_DIFFER',
            'equal': equal, 'as_of': full_document['as_of'], 'selection': selection,
            'full_selected_eligible': full, 'incremental_selected_eligible': incremental,
            'full_issues': full_issues, 'incremental_issues': incremental_issues,
            'limitation': 'Equality of retained selected evidence at this cutoff; not source completeness or proof of an unchanged unobserved history.'}


def process(root_value, run_id, document_raw):
    root = _root(root_value)
    _require(type(document_raw) is bytes and len(document_raw) <= MAX_JSON_BYTES, 'EXACT_INPUT_BYTES_REQUIRED')
    def action():
        config, registration = _registration(root)
        run, identity = _run(root, run_id, registration)
        assembled, collection, supplied = _assemble(run, identity, config, json.loads(document_raw.decode('utf-8-sig')))
        folder = _directory(run, 'process')
        research._publish(folder / 'input-original.json', document_raw)
        _publish(folder / 'assembled-input.json', assembled)
        plan, brief = _calculate(assembled)
        _publish(folder / 'plan.json', plan)
        _publish(folder / 'brief-first.json', brief)
        journal = _directory(run, 'journal')
        research._record(journal, 'workflow-protocol-v1', 'protocol', _bytes(config['workflow']), {'config_sha256': registration['config_sha256']})
        research._record(journal, 'first-response-v1', 'first_response', _read(folder / 'brief-first.json'),
                         {'input_sha256': _sha(document_raw), 'assembled_input_sha256': _sha(_bytes(assembled)),
                          'config_sha256': registration['config_sha256'], 'parent_id': 'workflow-protocol-v1'})
        normalized = market_sources.normalize(assembled)
        eligible = sum(r['eligible'] for r in normalized['records'])
        status = 'PROCESSED_FOR_SUPERVISED_REVIEW'
        if assembled.get('run_outcome'):
            status = 'RECORDED_' + assembled['run_outcome']['disposition']
        elif eligible == 0:
            status = 'ABSTENTION_NO_ELIGIBLE_EVIDENCE'
        elif collection['status'] == 'NO_CONFIGURED_SOURCES':
            status = 'PROCESSED_SUPPLIED_ONLY_WITH_COVERAGE_GAPS'
        elif collection['coverage_gaps']:
            status = 'PROCESSED_WITH_SOURCE_GAPS'
        artifacts = {name: _sha(_read(folder / name)) for name in
                     ('input-original.json', 'assembled-input.json', 'plan.json', 'brief-first.json')}
        summary = {'schema_version': 1, 'run_id': run_id, 'status': status, 'as_of': assembled['as_of'],
                   'config_sha256': registration['config_sha256'], 'collection_sha256': _sha(_bytes(collection)),
                   'input_sha256': _sha(document_raw), 'artifacts_sha256': artifacts,
                   'selected_records': len(assembled['records']), 'selected_eligible_records': eligible,
                   'supplied_unacquired_record_ids': supplied, 'selection': assembled['selection'],
                   'coverage_gaps': collection['coverage_gaps'], 'source_failures': collection['failures'],
                   'first_response_recorded_at': _load(journal / 'entries/first-response-v1.json')['recorded_at'],
                   'run_outcome': deepcopy(assembled.get('run_outcome')),
                   'execution_authorized': False,
                   'limitation': 'Info cutoff and actual journal time are separate; this does not attest an actual human decision, source rights or elapsed investment effectiveness.'}
        _publish(folder / 'summary.json', summary)
        return summary
    return _locked(root, 'process', run_id, action)


def _verify_journal(run, summary):
    journal = run / 'journal'
    for entry_id in ('workflow-protocol-v1', 'first-response-v1'):
        entry_raw = _read(journal / 'entries' / (entry_id + '.json'))
        entry = json.loads(entry_raw)
        transaction = _load(journal / 'transactions' / (entry_id + '.json'))
        commit = _load(journal / 'commits' / (entry_id + '.json'))
        stable = {k: v for k, v in entry.items() if k != 'recorded_at'}
        _require(_bytes(transaction['entry']) == _bytes(entry)
                 and transaction['idempotency_key'] == research._digest(stable), 'JOURNAL_TRANSACTION_MISMATCH')
        _require(commit['entry_sha256'] == _sha(entry_raw) and commit['object_sha256'] == entry['object_sha256'], 'JOURNAL_COMMIT_MISMATCH')
        raw = _read(journal / 'objects' / (entry['object_sha256'] + '.bin'))
        _require(_sha(raw) == entry['object_sha256'], 'JOURNAL_OBJECT_HASH_MISMATCH')
        if entry_id == 'first-response-v1':
            _require(_sha(raw) == summary['artifacts_sha256']['brief-first.json'], 'FIRST_RESPONSE_ARTIFACT_MISMATCH')


def verify(root_value, run_id, incremental_document=None):
    root = _root(root_value)
    def action():
        config, registration = _registration(root)
        run, identity = _run(root, run_id, registration)
        folder = run / 'process'
        summary = _load(folder / 'summary.json')
        _require(all(_sha(_read(folder / name)) == digest for name, digest in summary['artifacts_sha256'].items()), 'PROCESS_ARTIFACT_HASH_MISMATCH')
        original = _load(folder / 'input-original.json')
        assembled, collection, _ = _assemble(run, identity, config, original)
        _require(_bytes(assembled) == _read(folder / 'assembled-input.json')
                 and _sha(_bytes(collection)) == summary['collection_sha256'], 'PROCESS_SOURCE_RECONCILIATION_MISMATCH')
        plan, response = _calculate(assembled)
        _require(_bytes(plan) == _read(folder / 'plan.json')
                 and _bytes(response) == _read(folder / 'brief-first.json'), 'PROCESS_REPLAY_MISMATCH')
        _verify_journal(run, summary)
        result = {'status': 'RETAINED_RESEARCH_RUN_VERIFIED', 'run_id': run_id, 'as_of': assembled['as_of'],
                  'config_sha256': registration['config_sha256'], 'execution_authorized': False,
                  'process_status': summary['status'], 'coverage_gaps': summary['coverage_gaps'],
                  'source_failures': summary['source_failures']}
        if incremental_document is not None:
            result['incremental_comparison'] = compare_selected_records(assembled, incremental_document, assembled['selection'])
            if not result['incremental_comparison']['equal']:
                result['status'] = 'INCREMENTAL_SELECTED_EVIDENCE_MISMATCH'
        return result
    return _locked(root, 'verify', run_id, action)


def status(root_value, as_of):
    root = _root(root_value)
    cutoff = _stamp(as_of)
    config, registration = _registration(root, False)
    runs = []
    failures = []
    if (root / 'failures').exists():
        failures.extend(_load(p) for p in (root / 'failures').glob('*.json'))
    for path in sorted((root / 'runs').iterdir()) if (root / 'runs').exists() else []:
        run, identity = _run(root, path.name, registration)
        collection, sources = _collection(run, identity, config, False)
        for source in sources:
            at = source.get('available_at')
            age = (cutoff - _stamp(at)).total_seconds() if at else None
            source['capture_age_seconds'] = age
            source['freshness'] = ('CAPTURE_UNAVAILABLE' if age is None else 'NOT_AVAILABLE_AT_CUTOFF' if age < 0 else
                                   'FRESH_UNDER_DECLARED_CAPTURE_AGE' if age <= config['freshness']['max_capture_age_seconds'] else 'STALE_CAPTURE')
        failures.extend(dict(failure, run_id=path.name,
            recorded_at=failure.get('recorded_at', failure.get('finished_at', failure.get('started_at'))))
            for failure in _source_failures(sources))
        runs.append({'run_id': path.name, 'collection_status': collection['status'],
                     'sources': [{k: v for k, v in s.items() if k != 'records'} for s in sources],
                     'process': _load(run / 'process/summary.json') if (run / 'process/summary.json').exists() else None,
                     'coverage_gaps': collection['coverage_gaps']})
    latest_failure = max(failures, key=lambda f: f.get('recorded_at') or '') if failures else None
    return {'status': 'NO_CONFIGURED_SOURCES' if not config['sources'] else 'DECLARED_LOCAL_OPERATIONS_STATUS',
            'workflow_id': config['workflow']['id'], 'as_of': as_of, 'runs': runs,
            'last_failure': latest_failure, 'failures': failures,
            'software_binding_matches': registration['software_sha256'] == _software(),
            'coverage_gaps': ['No automatic sources configured; supplied records are not a complete live feed.'] if not config['sources'] else [],
            'lock_present': (root / '.institutional.lock').exists(), 'execution_authorized': False,
            'limitation': 'Local observed state and declared capture-age checks; not actual continuous uptime, complete market coverage or another-host acceptance.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('register'); item.add_argument('--root', required=True); item.add_argument('--config', required=True)
    item = sub.add_parser('collect'); item.add_argument('--root', required=True); item.add_argument('--run-id', required=True); item.add_argument('--retry-failed', action='store_true')
    for name in ('process', 'recover'):
        item = sub.add_parser(name); item.add_argument('--root', required=True); item.add_argument('--run-id', required=True); item.add_argument('--input', required=True)
    item = sub.add_parser('verify'); item.add_argument('--root', required=True); item.add_argument('--run-id', required=True); item.add_argument('--incremental-input')
    item = sub.add_parser('status'); item.add_argument('--root', required=True); item.add_argument('--as-of', required=True)
    item = sub.add_parser('release-lock'); item.add_argument('--root', required=True); item.add_argument('--expected-lock-sha256', required=True); item.add_argument('--operator-confirmed-stopped', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'register':
        result = register(args.root, _load(args.config))
    elif args.command == 'collect':
        result = collect(args.root, args.run_id, args.retry_failed)
    elif args.command in ('process', 'recover'):
        result = process(args.root, args.run_id, _read(args.input))
    elif args.command == 'verify':
        result = verify(args.root, args.run_id, _load(args.incremental_input) if args.incremental_input else None)
    elif args.command == 'status':
        result = status(args.root, args.as_of)
    else:
        result = research._release_lock(_root(args.root), args.expected_lock_sha256, args.operator_confirmed_stopped)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 2 if result['status'] in ('INCREMENTAL_SELECTED_EVIDENCE_MISMATCH',
                                    'COLLECTED_WITH_GAPS', 'NO_CONFIGURED_SOURCES') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'ERROR', 'error': str(error), 'execution_authorized': False}), file=sys.stderr)
        raise SystemExit(2)
