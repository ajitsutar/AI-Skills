"""IBKR shared-public shortstock intake and one explicitly requested capture.

``parse`` is pure. Optional ``acquire`` is restricted to the documented public
usa.txt route and shared read-only login; it has no user-account or order API.
Rate units and the provider's BOF timezone stay unknown; retrieval is the
observation clock, not proof of inventory freshness or an approved locate.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import ftplib
import hashlib
import json
import math
import os
from pathlib import Path
import re

MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 200000
HEADERS = ('#SYM', 'CUR', 'NAME', 'CON', 'ISIN', 'REBATERATE', 'FEERATE', 'AVAILABLE', 'FIGI', '')
PUBLIC_URL = 'ftp://ftp2.interactivebrokers.com/usa.txt'
PUBLIC_HOST = 'ftp2.interactivebrokers.com'
PUBLIC_LOGIN = 'shortstock'
PUBLIC_PASSWORD = ''  # Officially published shared-public value, not a user credential.
PUBLIC_INSTRUCTIONS = 'https://www.interactivebrokers.com/support/faq/content/monitoring-stock-loan-availability-1163250499'


def allowed_public_url(url):
    """Accept this one exact credential-free public provenance/capture URL."""
    if type(url) is not str or url != PUBLIC_URL:
        raise ValueError('Only the exact documented public IBKR usa.txt URL is supported')
    return PUBLIC_HOST


def acquire(url, output_dir, source_id, rights='unknown', max_bytes=8 * 1024 * 1024,
            timeout=15, retries=0):
    """Capture one public file with at most one RETR and no listing or retries.

    Transfer completion means an actual FTP 226 reply and SIZE parity when SIZE
    is supported. It establishes neither upstream freshness/completeness nor
    unrestricted redistribution rights. A bounded failed prefix remains raw.
    This FTP transport is plaintext public data, not authenticated issuer data.
    """
    allowed_public_url(url)
    if type(source_id) is not str or not source_id.strip():
        raise ValueError('source_id required')
    if type(rights) is not str or not rights.strip():
        raise ValueError('Retain a rights declaration or unknown')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError('Invalid byte bound')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('timeout must be 0..30 seconds')
    if type(retries) is not int or retries != 0:
        raise ValueError('This public FTP capture requires zero retries')
    target = Path(output_dir)
    target.mkdir(parents=False, exist_ok=False)
    raw_path = target / 'attempt-01.raw'
    digest, count = hashlib.sha256(), 0
    entry = {'attempt': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
             'transport': 'FTP', 'raw_file': raw_path.name, 'retained_bytes': 0,
             'raw_sha256': digest.hexdigest(), 'raw_complete': False,
             'final_url': url, 'retr_commands': 0}
    manifest = {'schema_version': 1, 'kind': 'MARKET_SOURCE_ACQUISITION', 'status': 'FAILED',
        'transport': 'FTP', 'request_url': url, 'method': 'RETR', 'source_id': source_id,
        'access': 'public', 'rights': rights, 'raw_complete': False, 'max_bytes': max_bytes, 'timeout_seconds': timeout,
        'retries_limit': 0, 'attempts': [entry], 'execution_authorized': False,
        'public_access_instructions': PUBLIC_INSTRUCTIONS, 'personal_account_access': False,
        'limitations': ['Indicative single-provider shared-public inventory; not an approved locate.',
                        'Public FTP is plaintext and does not authenticate source content.',
                        'Observed retrieval does not verify BOF timezone, rates, freshness or complete market supply.',
                        'Public access does not establish unrestricted redistribution or commercial rights.']}
    ftp, retrieved_at = None, None
    try:
        with raw_path.open('xb') as output:
            def retain(chunk):
                nonlocal count
                remaining = max_bytes - count
                prefix = chunk[:remaining]
                output.write(prefix)
                digest.update(prefix)
                count += len(prefix)
                entry.update(raw_sha256=digest.hexdigest(), retained_bytes=count)
                if len(chunk) > remaining:
                    raise ValueError('BODY_LIMIT_EXCEEDED_PARTIAL_PREFIX_RETAINED')
            try:
                ftp = ftplib.FTP()
                entry['connect_response'] = ftp.connect(PUBLIC_HOST, 21, timeout=timeout)
                entry['login_response'] = ftp.login(PUBLIC_LOGIN, PUBLIC_PASSWORD)
                ftp.voidcmd('TYPE I')
                size_explicitly_unsupported = False
                try:
                    declared_size = ftp.size('usa.txt')
                except ftplib.error_perm as error:
                    # Explicit unsupported-command replies alone allow unknown SIZE.
                    if str(error)[:3] not in ('500', '502', '504'):
                        raise
                    size_explicitly_unsupported = True
                    declared_size = None
                    entry['size_unavailable_response'] = str(error)[:1000]
                if declared_size is None and not size_explicitly_unsupported:
                    raise ValueError('FTP_SIZE_UNEXPLAINED_NONE_NO_RETR')
                if declared_size is not None and (type(declared_size) is not int or declared_size < 0):
                    raise ValueError('INVALID_FTP_SIZE')
                entry['declared_size_bytes'] = declared_size
                if declared_size is not None and declared_size > max_bytes:
                    raise ValueError('DECLARED_SIZE_EXCEEDS_BODY_LIMIT_NO_RETR')
                entry['retr_commands'] += 1
                response = ftp.retrbinary('RETR usa.txt', retain, blocksize=65536)
                entry['ftp_response'] = response
                code = int(response[:3]) if isinstance(response, str) and re.match(r'^\d{3}(?:\s|$)', response) else None
                entry['ftp_response_code'] = code
                if code != 226:
                    raise ValueError('FTP_TRANSFER_NOT_226_COMPLETE')
                if declared_size is not None and declared_size != count:
                    raise ValueError('FTP_SIZE_MISMATCH_PARTIAL_RETAINED')
                retrieved_at = datetime.now(timezone.utc).isoformat()
                entry.update(raw_complete=True, finished_at=retrieved_at)
            finally:
                output.flush()
                os.fsync(output.fileno())
    except (OSError, EOFError, ftplib.Error, ValueError) as error:
        entry['error'] = type(error).__name__ + ': ' + str(error)[:1000]
    finally:
        if ftp is not None:
            try:
                entry['quit_response'] = ftp.quit()
            except (OSError, EOFError, ftplib.Error) as error:
                entry['quit_error'] = type(error).__name__ + ': ' + str(error)[:1000]
            finally:
                try:
                    ftp.close()
                    entry['ftp_control_socket_closed'] = ftp.sock is None
                except OSError as error:
                    entry['ftp_control_socket_closed'] = False
                    entry['close_error'] = type(error).__name__ + ': ' + str(error)[:1000]
        else:
            entry['ftp_control_socket_closed'] = True  # No owned client was created.
        entry.update(raw_sha256=digest.hexdigest(), retained_bytes=count)
        entry.setdefault('finished_at', datetime.now(timezone.utc).isoformat())
    if entry['raw_complete'] and entry['ftp_control_socket_closed'] and 'error' not in entry:
        manifest.update(status='ACQUIRED', raw_file=raw_path.name, raw_sha256=digest.hexdigest(),
            available_at=retrieved_at, raw_complete=True,
            source={'id': source_id, 'url': url, 'retrieved_at': retrieved_at,
                    'published_at': None, 'observed_at': retrieved_at, 'available_at': retrieved_at,
                    'availability_basis': 'first_observed_snapshot', 'access': 'public',
                    'rights': rights, 'transport': 'FTP', 'raw_complete': True})
    manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
    with (target / 'manifest.json').open('x', encoding='utf8') as output:
        json.dump(manifest, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    return manifest


def _clock(value):
    if not isinstance(value, str) or not re.search(r'T\d{2}:\d{2}', value):
        raise ValueError('precise timestamp with timezone required')
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('invalid timestamp') from error
    if instant.utcoffset() is None:
        raise ValueError('timestamp timezone required')
    return instant.astimezone(timezone.utc)


def _rate_valid(value):
    if value == 'NA':
        return True
    if len(value) > 128 or not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', value):
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def parse(document, text):
    """Return (ordered rows, metadata, issues), retaining failed candidate rows.

    Each output row is kind/ticker/payload plus optional parse_error. The caller
    supplies standard record IDs and performs common clock/cutoff normalization.
    Unknown or malformed controls qualify the whole retained snapshot; malformed
    data and duplicate provider symbols qualify all affected copies.
    """
    if type(document) is not dict or type(text) is not str:
        raise ValueError('Borrow intake requires an object and retained text')
    if len(text.encode('utf8')) > MAX_BYTES:
        raise ValueError('Borrow source text exceeds byte bound')
    lines = text.lstrip('\ufeff').splitlines()
    controls = {'#BOF': [], '#SYM': [], '#EOF': []}
    for index, line in enumerate(lines):
        marker = line.split('|', 1)[0]
        if marker in controls:
            controls[marker].append(index)
    nonempty = [index for index, line in enumerate(lines) if line.strip()]
    global_errors, issues = [], []

    def global_issue(code):
        if code not in global_errors:
            global_errors.append(code)
            issues.append({'code': code})

    if not nonempty:
        global_issue('IBKR_EMPTY_SOURCE')
    for marker, code in [('#BOF', 'BOF'), ('#SYM', 'HEADER'), ('#EOF', 'TRAILER')]:
        if len(controls[marker]) != 1:
            global_issue('IBKR_' + code + '_MISSING_OR_DUPLICATED')
    bof_index = controls['#BOF'][0] if len(controls['#BOF']) == 1 else None
    header_index = controls['#SYM'][0] if len(controls['#SYM']) == 1 else None
    eof_index = controls['#EOF'][0] if len(controls['#EOF']) == 1 else None
    if (not nonempty or bof_index != nonempty[0] or len(nonempty) < 2
            or header_index != nonempty[1] or eof_index != nonempty[-1]):
        global_issue('IBKR_CONTROL_LINE_ORDER_INVALID')
    headers = lines[header_index].split('|') if header_index is not None else None
    if headers is not None and tuple(headers) != HEADERS:
        global_issue('IBKR_HEADER_SCHEMA_UNSUPPORTED')
    bof_raw = lines[bof_index] if bof_index is not None else None
    bof_date, bof_time = None, None
    if bof_raw is not None:
        parts = bof_raw.split('|')
        try:
            if len(parts) != 3 or not re.fullmatch(r'\d{4}\.\d{2}\.\d{2}', parts[1]) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}', parts[2]):
                raise ValueError('BOF shape')
            datetime.strptime(parts[1] + ' ' + parts[2], '%Y.%m.%d %H:%M:%S')
            bof_date, bof_time = parts[1], parts[2]
        except ValueError:
            global_issue('IBKR_BOF_DATE_OR_TIME_INVALID')

    source = document.get('source')
    source = source if type(source) is dict else {}
    retrieval = source.get('retrieved_at')
    try:
        retrieved_clock = _clock(retrieval)
    except ValueError:
        retrieved_clock = None
        global_issue('IBKR_PRECISE_SNAPSHOT_RETRIEVAL_REQUIRED')
    if document.get('available_at') is not None:
        try:
            available = _clock(document['available_at'])
            if retrieved_clock is not None and available < retrieved_clock:
                global_issue('IBKR_AVAILABILITY_BEFORE_SNAPSHOT_RETRIEVAL')
        except ValueError:
            global_issue('IBKR_AVAILABLE_AT_INVALID')
    declarations = {}
    if 'raw_complete' in document:
        declarations['raw_complete'] = deepcopy(document['raw_complete'])
    if 'raw_complete' in source:
        declarations['source.raw_complete'] = deepcopy(source['raw_complete'])
    invalid_completion = any(value is not None and type(value) is not bool for value in declarations.values())
    completion_values = {value for value in declarations.values() if type(value) is bool}
    completion = next(iter(completion_values)) if len(completion_values) == 1 and not invalid_completion else None
    if invalid_completion:
        global_issue('IBKR_CAPTURE_COMPLETENESS_DECLARATION_INVALID')
    if len(completion_values) > 1:
        global_issue('IBKR_CAPTURE_COMPLETENESS_CONFLICT')
    if completion is False:
        global_issue('IBKR_CAPTURE_DECLARED_INCOMPLETE')

    known_controls = {position for positions in controls.values() for position in positions}
    inside_start = header_index if header_index is not None else (bof_index if bof_index is not None else -1)
    inside_end = eof_index if eof_index is not None else len(lines)
    data_lines = [(index, line) for index, line in enumerate(lines) if index not in known_controls
                  and (line.strip() or inside_start < index < inside_end)]
    if len(data_lines) > MAX_ROWS:
        raise ValueError('Borrow source row count exceeds bound; no subset emitted')
    rows, symbols = [], {}
    quantity_counts = Counter()
    malformed_rows = 0
    for ordinal, (line_index, raw_line) in enumerate(data_lines):
        fields = raw_line.split('|')
        payload = {'source_format': 'ibkr_shortstock', 'provider': 'Interactive Brokers',
            'provider_scope': 'Indicative shared-public inventory snapshot; not market-wide supply or an approved locate',
            'observed_at': retrieval if retrieved_clock is not None else None,
            'observed_at_basis': 'actual_retrieval_snapshot',
            'provider_snapshot_date_raw': bof_date, 'provider_snapshot_time_raw': bof_time,
            'provider_snapshot_timezone': None, 'provider_freshness_verified': False,
            'fee_rate_annual_percent': None, 'rebate_rate_annual_percent': None,
            'reported_rate_unit': 'UNKNOWN', 'shares_available': None,
            'shares_available_lower_bound': None, 'shares_available_relation': 'UNKNOWN',
            'issuer_share_class_identity_verified': False, 'borrow_or_locate_approved': False,
            'raw_line': raw_line, 'raw_fields': fields, 'source_row_index': ordinal,
            'source_line_number': line_index + 1}
        row = {'kind': 'borrow', 'ticker': None, 'payload': payload}
        errors = []
        if len(fields) != len(HEADERS) or fields[-1] != '':
            errors.append('IBKR_ROW_FIELD_COUNT_OR_TERMINATOR_INVALID')
        else:
            symbol, currency, name, contract, isin, rebate, fee, available, figi, _ = fields
            payload.update(provider_symbol=symbol, currency=currency, provider_security_name=name,
                provider_contract_id_raw=contract, isin_raw=isin, figi_raw=figi,
                reported_rebate_rate_raw=rebate, reported_fee_rate_raw=fee,
                shares_available_raw=available,
                isin_identity_status='UNKNOWN_OR_MASKED' if not isin or isin.startswith('X') else 'REPORTED_NOT_VERIFIED')
            if not symbol or symbol != symbol.strip() or len(symbol) > 64 or any(ord(char) < 32 for char in symbol):
                errors.append('IBKR_PROVIDER_SYMBOL_INVALID')
            else:
                row['ticker'] = symbol
                symbols.setdefault(symbol, []).append(ordinal)
            if not re.fullmatch(r'[A-Z]{3}', currency):
                errors.append('IBKR_CURRENCY_INVALID')
            if not name.strip():
                errors.append('IBKR_PROVIDER_SECURITY_NAME_MISSING')
            if not re.fullmatch(r'\d{1,32}', contract) or int(contract) <= 0:
                errors.append('IBKR_PROVIDER_CONTRACT_ID_INVALID')
            if not _rate_valid(rebate) or not _rate_valid(fee):
                errors.append('IBKR_REPORTED_RATE_TOKEN_INVALID')
            if re.fullmatch(r'\d{1,32}', available):
                payload.update(shares_available=int(available), shares_available_relation='exact_reported_integer')
                quantity_counts['exact_reported_integer'] += 1
            elif re.fullmatch(r'>\d{1,32}', available):
                payload.update(shares_available_lower_bound=int(available[1:]), shares_available_relation='strictly_greater_than')
                quantity_counts['strictly_greater_than'] += 1
            elif available == 'NA':
                quantity_counts['unknown_NA'] += 1
            else:
                errors.append('IBKR_SHARES_AVAILABLE_TOKEN_INVALID')
        if errors:
            malformed_rows += 1
            row['parse_error'] = '; '.join(errors)
            issues.append({'code': 'IBKR_ROW_PARSE_ERROR', 'row': ordinal, 'line': line_index + 1,
                           'detail': row['parse_error']})
        rows.append(row)
    duplicate_rows = 0
    for symbol, positions in symbols.items():
        if len(positions) > 1:
            duplicate_rows += len(positions)
            issues.append({'code': 'IBKR_DUPLICATE_PROVIDER_SYMBOL', 'symbol': symbol, 'rows': positions})
            for position in positions:
                rows[position]['parse_error'] = '; '.join(filter(None, [rows[position].get('parse_error'), 'IBKR_DUPLICATE_PROVIDER_SYMBOL']))

    trailer_raw = lines[eof_index] if eof_index is not None else None
    declared_count = None
    if trailer_raw is not None:
        fields = trailer_raw.split('|')
        if len(fields) == 2 and re.fullmatch(r'\d{1,9}', fields[1]):
            declared_count = int(fields[1])
        else:
            global_issue('IBKR_TRAILER_COUNT_INVALID')
    count_matches = declared_count is not None and declared_count == len(rows)
    if declared_count is not None and not count_matches:
        global_issue('IBKR_TRAILER_COUNT_MISMATCH')
    terminal_newline = text.endswith(('\n', '\r'))
    no_newline_qualified = not terminal_newline and completion is True and not global_errors and not malformed_rows and not duplicate_rows
    if not terminal_newline and not no_newline_qualified:
        global_issue('IBKR_TERMINAL_NEWLINE_MISSING_POSSIBLE_TRUNCATION')
    for row in rows:
        if global_errors:
            row['parse_error'] = '; '.join(filter(None, [row.get('parse_error'), *global_errors]))
    failed_rows = sum(bool(row.get('parse_error')) for row in rows)
    metadata = {'source_format': 'ibkr_shortstock', 'source_rows': len(rows),
        'source_data_rows': len(rows), 'field_valid_rows': len(rows) - malformed_rows,
        'malformed_rows': malformed_rows, 'duplicate_provider_symbol_rows': duplicate_rows,
        'duplicate_provider_symbols': sum(len(positions) > 1 for positions in symbols.values()),
        'rows_with_parser_failures': failed_rows, 'rows_without_parser_failures': len(rows) - failed_rows,
        'source_headers': headers, 'bof_raw': bof_raw, 'bof_date_raw': bof_date, 'bof_time_raw': bof_time,
        'bof_timezone': None, 'source_clock_convention_verified': False,
        'snapshot_observed_at': retrieval if retrieved_clock is not None else None,
        'snapshot_observation_basis': 'actual_retrieval_snapshot',
        'reported_rate_unit': 'UNKNOWN', 'annual_rate_conversion_performed': False,
        'availability_semantics_counts': dict(quantity_counts),
        'trailer_raw': trailer_raw, 'trailer_declared_rows': declared_count,
        'trailer_count_reconciled': count_matches,
        'raw_control_lines': [{'line': index + 1, 'raw_line': lines[index]} for index in sorted(known_controls)],
        'outside_blank_line_numbers': [index + 1 for index, line in enumerate(lines) if not line.strip()
                                       and not inside_start < index < inside_end],
        'transport_completion_declarations': declarations, 'transport_complete_declared': completion,
        'terminal_newline_present': terminal_newline,
        'terminal_newline_qualification': ('PRESENT' if terminal_newline else
            'ABSENT_WITH_COMPLETE_TRANSPORT_DECLARATION' if no_newline_qualified else 'ABSENT_POSSIBLE_TRUNCATION'),
        'global_qualification_errors': list(global_errors),
        'status': 'RETAINED_PUBLIC_INVENTORY_WITH_GAPS' if global_errors or failed_rows else 'RETAINED_PUBLIC_INVENTORY_READY_FOR_REVIEW',
        'eligibility_at_cutoff_evaluated': False, 'provider_inventory_freshness_verified': False,
        'upstream_inventory_completeness_verified': False, 'issuer_share_class_identity_verified': False,
        'scope': 'All retained candidate data lines of one provider file; no complete U.S.-listed universe, all-market lending supply or broker approval.'}
    return rows, metadata, issues
