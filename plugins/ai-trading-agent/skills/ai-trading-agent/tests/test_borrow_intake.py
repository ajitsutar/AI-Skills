"""Synthetic portable controls; no provider rows, contact data or live requests."""
import copy
import ftplib
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import borrow_intake as intake

BOF = '#BOF|2026.11.12|23:48:07'
HEADER = '#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|'


def record(symbol='DEMO', available='100', currency='USD', rebate='-1.2000', fee='0.2500'):
    return '|'.join([symbol, currency, 'FICTIONAL SAMPLE COMPANY', '42',
                     'XXXXXXX00001', rebate, fee, available, 'BBG000DEMO01', ''])


def text(rows=None, newline=True, count=None):
    rows = [record()] if rows is None else rows
    return '\n'.join([BOF, HEADER, *rows, '#EOF|' + str(len(rows) if count is None else count)]) + ('\n' if newline else '')


def document():
    return {'schema_version': 1, 'source': {'id': 'fictional-public-borrow',
        'url': 'ftp://ftp2.interactivebrokers.com/usa.txt',
        'retrieved_at': '2026-11-13T04:55:54Z', 'published_at': None},
        'as_of': '2026-11-13T05:00:00Z'}


class BorrowCaptureTests(unittest.TestCase):
    def client(self, body=None):
        body = text().encode('utf8') if body is None else body
        ftp = MagicMock()
        ftp.sock = object()
        ftp.connect.return_value = '220 Public FTP'
        ftp.login.return_value = '230 Shared public login'
        ftp.size.return_value = len(body)
        def retrieve(command, callback, blocksize):
            for start in range(0, len(body), 7):
                callback(body[start:start + 7])
            return '226 Transfer complete.'
        ftp.retrbinary.side_effect = retrieve
        ftp.quit.return_value = '221 Goodbye.'
        def close():
            ftp.sock = None
        ftp.close.side_effect = close
        return ftp

    def capture(self, ftp, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'capture'
            with patch.object(intake.ftplib, 'FTP', return_value=ftp) as constructor:
                result = intake.acquire(intake.PUBLIC_URL, target, 'fictional-public-borrow',
                                        rights='Public qualification only; rights unresolved', **kwargs)
            raw = (target / 'attempt-01.raw').read_bytes()
            retained_manifest = json.loads((target / 'manifest.json').read_text(encoding='utf8'))
        self.assertEqual(result, retained_manifest)
        constructor.assert_called_once_with()
        ftp.close.assert_called_once_with()
        self.assertTrue(result['attempts'][0]['ftp_control_socket_closed'])
        self.assertNotIn('http_status', json.dumps(result))
        return result, raw

    def test_exact_route_rejects_credentials_queries_redirects_and_other_files(self):
        self.assertEqual(intake.allowed_public_url(intake.PUBLIC_URL), intake.PUBLIC_HOST)
        for value in [intake.PUBLIC_URL + '?x=1', intake.PUBLIC_URL + '#x',
                      'ftp://shortstock@ftp2.interactivebrokers.com/usa.txt',
                      'ftp://shortstock:password@ftp2.interactivebrokers.com/usa.txt',
                      'https://ftp2.interactivebrokers.com/usa.txt',
                      'ftp://ftp2.interactivebrokers.com:21/usa.txt',
                      'ftp://ftp2.interactivebrokers.com/other.txt',
                      'ftp://ftp2.interactivebrokers.com.evil.test/usa.txt',
                      'ftp://ftp2.interactivebrokers.com/../usa.txt',
                      'ftp://ftp2.interactivebrokers.com/%75sa.txt', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                intake.allowed_public_url(value)

    def test_success_is_one_public_retr_actual_226_hash_and_finish_observation(self):
        ftp = self.client()
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'ACQUIRED')
        self.assertTrue(result['raw_complete'])
        self.assertEqual(result['transport'], 'FTP')
        self.assertEqual(result['method'], 'RETR')
        ftp.connect.assert_called_once_with(intake.PUBLIC_HOST, 21, timeout=15)
        ftp.login.assert_called_once_with('shortstock', '')
        ftp.voidcmd.assert_called_once_with('TYPE I')
        ftp.size.assert_called_once_with('usa.txt')
        self.assertEqual(ftp.retrbinary.call_count, 1)
        self.assertEqual(ftp.retrbinary.call_args.args[0], 'RETR usa.txt')
        ftp.nlst.assert_not_called()
        ftp.dir.assert_not_called()
        ftp.cwd.assert_not_called()
        ftp.quit.assert_called_once_with()
        attempt = result['attempts'][0]
        self.assertEqual(attempt['ftp_response_code'], 226)
        self.assertEqual(attempt['retained_bytes'], len(raw))
        self.assertEqual(attempt['raw_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(attempt['final_url'], intake.PUBLIC_URL)
        self.assertEqual(result['raw_sha256'], attempt['raw_sha256'])
        source = result['source']
        self.assertEqual(source['retrieved_at'], attempt['finished_at'])
        self.assertEqual(source['observed_at'], result['available_at'])
        self.assertEqual(source['available_at'], result['available_at'])
        self.assertEqual(source['availability_basis'], 'first_observed_snapshot')
        self.assertIsNone(source['published_at'])
        rows, _, issues = intake.parse({'source': source, 'raw_complete': result['raw_complete']}, raw.decode())
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)

    def test_only_explicit_unsupported_size_can_be_unknown(self):
        for reply in ['500 Unknown command', '502 Not implemented', '504 Unsupported SIZE']:
            ftp = self.client()
            ftp.size.side_effect = ftplib.error_perm(reply)
            result, raw = self.capture(ftp)
            self.assertEqual(result['status'], 'ACQUIRED')
            self.assertIsNone(result['attempts'][0]['declared_size_bytes'])
            self.assertEqual(result['attempts'][0]['size_unavailable_response'], reply)
            self.assertTrue(raw)
        ftp = self.client()
        ftp.size.side_effect = ftplib.error_perm('550 File unavailable')
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(raw, b'')
        ftp.retrbinary.assert_not_called()

    def test_size_mismatch_preserves_body_and_actual_response_without_completeness(self):
        ftp = self.client()
        ftp.size.return_value += 1
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['raw_complete'])
        self.assertEqual(result['attempts'][0]['ftp_response_code'], 226)
        self.assertFalse(result['attempts'][0]['raw_complete'])
        self.assertIn('FTP_SIZE_MISMATCH', result['attempts'][0]['error'])
        self.assertEqual(raw, text().encode())
        self.assertNotIn('source', result)

    def test_unexplained_none_size_is_not_an_unsupported_command_or_complete_capture(self):
        # ftplib.size may implicitly return None after a non-213 successful reply.
        # No explicit 500/502/504 response means that SIZE is still unresolved.
        ftp = self.client()
        ftp.size.return_value = None
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['raw_complete'])
        self.assertFalse(result['attempts'][0]['raw_complete'])
        self.assertIn('FTP_SIZE_UNEXPLAINED_NONE', result['attempts'][0]['error'])
        self.assertNotIn('size_unavailable_response', result['attempts'][0])
        self.assertEqual(result['attempts'][0]['retr_commands'], 0)
        self.assertEqual(raw, b'')
        self.assertNotIn('source', result)
        ftp.retrbinary.assert_not_called()
        ftp.quit.assert_called_once_with()

    def test_non_226_does_not_become_a_success_or_http_code(self):
        ftp = self.client()
        ftp.retrbinary.side_effect = lambda command, callback, blocksize: (callback(b''), '250 Requested action okay')[1]
        ftp.size.return_value = 0
        result, _ = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['attempts'][0]['ftp_response_code'], 250)
        self.assertFalse(result['attempts'][0]['raw_complete'])

    def test_oversize_is_bounded_with_or_without_supported_size(self):
        ftp = self.client(b'abcdef')
        result, raw = self.capture(ftp, max_bytes=3)
        self.assertEqual(raw, b'')
        self.assertEqual(result['attempts'][0]['retr_commands'], 0)
        ftp.retrbinary.assert_not_called()
        ftp = self.client(b'abcdef')
        ftp.size.side_effect = ftplib.error_perm('502 SIZE unsupported')
        result, raw = self.capture(ftp, max_bytes=3)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(raw, b'abc')
        self.assertEqual(result['attempts'][0]['retained_bytes'], 3)
        self.assertIn('BODY_LIMIT', result['attempts'][0]['error'])
        self.assertEqual(ftp.retrbinary.call_count, 1)

    def test_partial_timeout_retains_prefix_and_always_closes(self):
        ftp = self.client()
        def partial(command, callback, blocksize):
            callback(b'partial')
            raise TimeoutError('Synthetic transfer timeout')
        ftp.retrbinary.side_effect = partial
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(raw, b'partial')
        self.assertIn('TimeoutError', result['attempts'][0]['error'])
        self.assertNotIn('ftp_response_code', result['attempts'][0])
        ftp.quit.assert_called_once_with()

    def test_login_failure_and_quit_failure_still_close_without_account_fallback(self):
        ftp = self.client()
        ftp.login.side_effect = ftplib.error_perm('530 Access denied')
        ftp.quit.side_effect = EOFError('Disconnected')
        result, raw = self.capture(ftp)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(raw, b'')
        ftp.retrbinary.assert_not_called()
        self.assertIn('quit_error', result['attempts'][0])
        self.assertEqual(ftp.login.call_count, 1)
        ftp = self.client()
        ftp.quit.side_effect = EOFError('Disconnected after transfer')
        result, _ = self.capture(ftp)
        self.assertEqual(result['status'], 'ACQUIRED')
        self.assertIn('quit_error', result['attempts'][0])

    def test_invalid_arguments_fail_before_filesystem_or_network(self):
        for changes in [{'retries': 1}, {'retries': True}, {'max_bytes': True},
                        {'max_bytes': 0}, {'max_bytes': intake.MAX_BYTES + 1},
                        {'timeout': True}, {'timeout': 0}, {'timeout': 31},
                        {'timeout': float('nan')}, {'timeout': float('inf')},
                        {'rights': ''}, {'source_id': ''}]:
            args = dict(url=intake.PUBLIC_URL, output_dir='must-not-create', source_id='fictional', rights='unknown')
            args.update(changes)
            with self.subTest(changes=changes), patch.object(intake.ftplib, 'FTP') as constructor, patch.object(Path, 'mkdir') as mkdir:
                with self.assertRaises(ValueError):
                    intake.acquire(**args)
                constructor.assert_not_called()
                mkdir.assert_not_called()

    def test_existing_output_is_not_overwritten_or_used_for_another_attempt(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(intake.ftplib, 'FTP') as constructor:
            with self.assertRaises(FileExistsError):
                intake.acquire(intake.PUBLIC_URL, directory, 'fictional')
            constructor.assert_not_called()


class BorrowIntakeTests(unittest.TestCase):
    def parse(self, value=None, raw=None):
        return intake.parse(document() if value is None else value, text() if raw is None else raw)

    def test_valid_snapshot_preserves_raw_fields_unknown_units_and_provider_scope(self):
        rows, metadata, issues = self.parse()
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)
        self.assertNotIn('parse_error', rows[0])
        self.assertEqual(rows[0]['kind'], 'borrow')
        self.assertEqual(rows[0]['ticker'], 'DEMO')
        payload = rows[0]['payload']
        self.assertEqual(payload['provider'], 'Interactive Brokers')
        self.assertEqual(payload['raw_line'], record())
        self.assertEqual(payload['raw_fields'], record().split('|'))
        self.assertEqual(payload['shares_available'], 100)
        self.assertEqual(payload['reported_rebate_rate_raw'], '-1.2000')
        self.assertEqual(payload['reported_fee_rate_raw'], '0.2500')
        self.assertIsNone(payload['fee_rate_annual_percent'])
        self.assertIsNone(payload['rebate_rate_annual_percent'])
        self.assertEqual(payload['reported_rate_unit'], 'UNKNOWN')
        self.assertEqual(payload['observed_at'], document()['source']['retrieved_at'])
        self.assertEqual(payload['observed_at_basis'], 'actual_retrieval_snapshot')
        self.assertFalse(payload['borrow_or_locate_approved'])
        self.assertFalse(payload['issuer_share_class_identity_verified'])
        self.assertEqual(metadata['source_rows'], 1)
        self.assertEqual(metadata['source_headers'], HEADER.split('|'))
        self.assertTrue(metadata['trailer_count_reconciled'])
        self.assertIsNone(metadata['bof_timezone'])
        self.assertFalse(metadata['annual_rate_conversion_performed'])

    def test_exact_lower_bound_unknown_and_zero_inventory_are_distinct(self):
        rows, metadata, _ = self.parse(raw=text([record('EXACT', '100'), record('FLOOR', '>100'),
                                               record('UNKNOWN', 'NA'), record('ZERO', '0')]))
        exact, floor, unknown, zero = [row['payload'] for row in rows]
        self.assertEqual(exact['shares_available'], 100)
        self.assertEqual(floor['shares_available_lower_bound'], 100)
        self.assertEqual(floor['shares_available_relation'], 'strictly_greater_than')
        self.assertIsNone(floor['shares_available'])
        self.assertIsNone(unknown['shares_available'])
        self.assertEqual(unknown['shares_available_relation'], 'UNKNOWN')
        self.assertEqual(zero['shares_available'], 0)
        self.assertEqual(metadata['availability_semantics_counts'],
                         {'exact_reported_integer': 2, 'strictly_greater_than': 1, 'unknown_NA': 1})

    def test_unknown_or_signed_rates_do_not_become_annual_percentages(self):
        for rebate, fee in [('NA', 'NA'), ('-2.5', '+0.25'), ('0', '-0.5')]:
            rows, _, _ = self.parse(raw=text([record(rebate=rebate, fee=fee)]))
            self.assertNotIn('parse_error', rows[0])
            self.assertEqual(rows[0]['payload']['reported_fee_rate_raw'], fee)
            self.assertEqual(rows[0]['payload']['reported_rebate_rate_raw'], rebate)
            self.assertIsNone(rows[0]['payload']['fee_rate_annual_percent'])

    def test_invalid_availability_is_retained_and_only_affected_row_is_unusable(self):
        for value in ['-1', '>-1', '1e3', '1.5', '1,000', '100+', '> 100', '', 'N/A']:
            rows, metadata, _ = self.parse(raw=text([record('GOOD'), record('BAD', value)]))
            self.assertNotIn('parse_error', rows[0])
            self.assertIn('IBKR_SHARES_AVAILABLE_TOKEN_INVALID', rows[1]['parse_error'])
            self.assertEqual(rows[1]['payload']['shares_available_raw'], value)
            self.assertEqual(metadata['source_rows'], 2)

    def test_invalid_rate_keeps_independently_parsed_quantity_and_raw_value(self):
        for value in ['NaN', 'Infinity', '1e9999', '0,25', '']:
            rows, _, _ = self.parse(raw=text([record('GOOD'), record('BAD', fee=value)]))
            self.assertNotIn('parse_error', rows[0])
            self.assertIn('IBKR_REPORTED_RATE_TOKEN_INVALID', rows[1]['parse_error'])
            self.assertEqual(rows[1]['payload']['shares_available'], 100)
            self.assertEqual(rows[1]['payload']['reported_fee_rate_raw'], value)

    def test_ragged_rows_or_missing_final_delimiter_do_not_disappear(self):
        for bad in [record('BAD').rstrip('|'), record('BAD') + 'EXTRA|', 'BAD|USD']:
            rows, metadata, _ = self.parse(raw=text([record('GOOD'), bad]))
            self.assertEqual(len(rows), 2)
            self.assertEqual(metadata['source_rows'], 2)
            self.assertEqual(rows[1]['payload']['raw_line'], bad)
            self.assertEqual(rows[1]['payload']['raw_fields'], bad.split('|'))
            self.assertIn('parse_error', rows[1])
            self.assertNotIn('parse_error', rows[0])

    def test_duplicate_provider_symbols_exclude_every_copy_without_priority(self):
        rows, metadata, _ = self.parse(raw=text([record('DUP', '1'), record('OTHER'), record('DUP', '2')]))
        self.assertIn('IBKR_DUPLICATE_PROVIDER_SYMBOL', rows[0]['parse_error'])
        self.assertIn('IBKR_DUPLICATE_PROVIDER_SYMBOL', rows[2]['parse_error'])
        self.assertNotIn('parse_error', rows[1])
        self.assertEqual(metadata['duplicate_provider_symbol_rows'], 2)
        self.assertEqual([row['payload']['source_row_index'] for row in rows], [0, 1, 2])
        self.assertEqual([row['payload']['source_line_number'] for row in rows], [3, 4, 5])

    def test_unknown_or_duplicate_headers_fail_the_snapshot_without_column_priority(self):
        for header in [HEADER.replace('|CUR|NAME|', '|CUR|CUR|'), HEADER.replace('|CUR|', '|Currency|')]:
            rows, metadata, _ = self.parse(raw=text().replace(HEADER, header))
            self.assertIn('IBKR_HEADER_SCHEMA_UNSUPPORTED', rows[0]['parse_error'])
            self.assertEqual(metadata['source_headers'], header.split('|'))
        rows, metadata, _ = self.parse(raw=text().replace(HEADER, HEADER + '\n' + HEADER))
        self.assertEqual(len(rows), 1)
        self.assertIn('IBKR_HEADER_MISSING_OR_DUPLICATED', rows[0]['parse_error'])
        self.assertEqual(len(metadata['raw_control_lines']), 4)

    def test_missing_control_lines_preserve_the_actual_data_row(self):
        for control in [BOF, HEADER, '#EOF|1']:
            raw = text().replace(control + '\n', '')
            rows, metadata, _ = self.parse(raw=raw)
            self.assertTrue(any(row['payload']['raw_line'] == record() for row in rows))
            self.assertTrue(all(row.get('parse_error') for row in rows))
            self.assertTrue(metadata['global_qualification_errors'])

    def test_duplicate_or_reordered_control_lines_qualify_all_rows(self):
        for raw in [text().replace(BOF, BOF + '\n' + BOF), text().replace('#EOF|1', '#EOF|1\n#EOF|1'),
                    text().replace(BOF + '\n' + HEADER, HEADER + '\n' + BOF)]:
            rows, metadata, _ = self.parse(raw=raw)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get('parse_error'))
            self.assertTrue(metadata['global_qualification_errors'])

    def test_invalid_or_mismatched_trailer_count_qualifies_entire_snapshot(self):
        for trailer in ['#EOF|-1', '#EOF|1.0', '#EOF|2', '#EOF|1|extra']:
            rows, metadata, _ = self.parse(raw=text().replace('#EOF|1', trailer))
            self.assertTrue(rows[0].get('parse_error'))
            self.assertFalse(metadata['trailer_count_reconciled'])
            self.assertEqual(metadata['trailer_raw'], trailer)

    def test_data_after_trailer_is_retained_and_not_called_complete(self):
        raw = text() + record('TAIL') + '\n'
        rows, metadata, _ = self.parse(raw=raw)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['payload']['raw_line'], record('TAIL'))
        self.assertTrue(all(row.get('parse_error') for row in rows))
        self.assertIn('IBKR_CONTROL_LINE_ORDER_INVALID', metadata['global_qualification_errors'])

    def test_no_newline_requires_explicit_complete_transport_and_valid_controls(self):
        rows, metadata, _ = self.parse(raw=text(newline=False))
        self.assertIn('IBKR_TERMINAL_NEWLINE_MISSING_POSSIBLE_TRUNCATION', rows[0]['parse_error'])
        value = document(); value['raw_complete'] = True
        rows, metadata, _ = self.parse(value, text(newline=False))
        self.assertNotIn('parse_error', rows[0])
        self.assertEqual(metadata['terminal_newline_qualification'], 'ABSENT_WITH_COMPLETE_TRANSPORT_DECLARATION')
        rows, metadata, _ = self.parse(value, text(newline=False).replace('#EOF|1', 'TRUNCATED'))
        self.assertTrue(all(row.get('parse_error') for row in rows))
        self.assertFalse(metadata['trailer_count_reconciled'])

    def test_partial_and_conflicting_transport_flags_fail_closed_with_both_declarations(self):
        for top, nested in [(True, False), (False, True), (None, False), (False, None)]:
            value = document(); value['raw_complete'] = top; value['source']['raw_complete'] = nested
            rows, metadata, _ = self.parse(value)
            self.assertTrue(rows[0].get('parse_error'))
            self.assertEqual(metadata['transport_completion_declarations'], {'raw_complete': top, 'source.raw_complete': nested})
            if top is True or nested is True:
                self.assertIn('IBKR_CAPTURE_COMPLETENESS_CONFLICT', rows[0]['parse_error'])
                self.assertIsNone(metadata['transport_complete_declared'])

    def test_redundant_complete_flags_and_unknowns_are_reconciled_without_priority(self):
        for top, nested, expected in [(True, True, True), (None, True, True), (True, None, True), (None, None, None)]:
            value = document(); value['raw_complete'] = top; value['source']['raw_complete'] = nested
            rows, metadata, _ = self.parse(value)
            self.assertNotIn('parse_error', rows[0])
            self.assertIs(metadata['transport_complete_declared'], expected)
            self.assertFalse(metadata['upstream_inventory_completeness_verified'])

    def test_invalid_flag_type_cannot_hide_behind_true(self):
        for top, nested in [(True, 1), ('false', True), (True, []), (0, True)]:
            value = document(); value['raw_complete'] = top; value['source']['raw_complete'] = nested
            rows, metadata, _ = self.parse(value)
            self.assertIn('IBKR_CAPTURE_COMPLETENESS_DECLARATION_INVALID', rows[0]['parse_error'])
            self.assertIsNone(metadata['transport_complete_declared'])

    def test_precise_retrieval_is_required_and_publication_cannot_replace_it(self):
        for retrieved in [None, '2026-11-13', '2026-11-13T04:55:54', 'invalid']:
            value = document(); value['source']['retrieved_at'] = retrieved
            value['source']['published_at'] = '2026-11-12T20:00:00Z'
            rows, metadata, _ = self.parse(value)
            self.assertIn('IBKR_PRECISE_SNAPSHOT_RETRIEVAL_REQUIRED', rows[0]['parse_error'])
            self.assertIsNone(rows[0]['payload']['observed_at'])
            self.assertIsNone(metadata['snapshot_observed_at'])

    def test_declared_availability_cannot_precede_retrieval_or_move_observation(self):
        value = document(); value['available_at'] = '2026-11-13T04:00:00Z'
        rows, _, _ = self.parse(value)
        self.assertIn('IBKR_AVAILABILITY_BEFORE_SNAPSHOT_RETRIEVAL', rows[0]['parse_error'])
        value['available_at'] = '2026-11-13T06:00:00Z'
        rows, _, _ = self.parse(value)
        self.assertNotIn('parse_error', rows[0])
        self.assertEqual(rows[0]['payload']['observed_at'], value['source']['retrieved_at'])

    def test_bof_time_is_retained_without_timezone_or_publication_invention(self):
        value = document(); value['source']['retrieved_at'] = '2026-11-12T23:55:54-05:00'
        rows, metadata, _ = self.parse(value)
        self.assertNotIn('parse_error', rows[0])
        self.assertEqual(rows[0]['payload']['observed_at'], value['source']['retrieved_at'])
        self.assertIsNone(metadata['bof_timezone'])
        self.assertEqual(metadata['bof_date_raw'], '2026.11.12')
        self.assertEqual(metadata['bof_time_raw'], '23:48:07')
        self.assertFalse(metadata['provider_inventory_freshness_verified'])
        for malformed in ['#BOF|2026.11.31|23:48:07', '#BOF|2026.11.12|25:00:00', '#BOF|2026-11-12|23:48:07']:
            rows, _, _ = self.parse(raw=text().replace(BOF, malformed))
            self.assertIn('IBKR_BOF_DATE_OR_TIME_INVALID', rows[0]['parse_error'])

    def test_provider_symbols_and_currencies_are_preserved_without_identity_or_FX_claim(self):
        rows, _, _ = self.parse(raw=text([record('DEMO-A', currency='EUR'), record('DEMO.B', currency='CAD')]))
        self.assertEqual([row['ticker'] for row in rows], ['DEMO-A', 'DEMO.B'])
        self.assertEqual([row['payload']['currency'] for row in rows], ['EUR', 'CAD'])
        self.assertTrue(all(not row['payload']['issuer_share_class_identity_verified'] for row in rows))
        self.assertTrue(all(row['payload']['isin_identity_status'] == 'UNKNOWN_OR_MASKED' for row in rows))

    def test_interior_empty_or_unknown_lines_are_retained_as_failed_candidate_rows(self):
        for middle in ['', '#UNKNOWN|metadata']:
            rows, metadata, _ = self.parse(raw=text([record('FIRST'), middle, record('LAST')]))
            self.assertEqual(metadata['source_rows'], 3)
            self.assertEqual(rows[1]['payload']['raw_line'], middle)
            self.assertIn('parse_error', rows[1])
            self.assertNotIn('parse_error', rows[0])
            self.assertNotIn('parse_error', rows[2])

    def test_pure_parse_never_opens_files_or_network_and_does_not_mutate_input(self):
        value = document(); before = copy.deepcopy(value)
        with patch('builtins.open', side_effect=AssertionError('filesystem forbidden')), \
                patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            rows, _, _ = self.parse(value, '\ufeff' + text())
        self.assertNotIn('parse_error', rows[0])
        self.assertEqual(value, before)

    def test_input_bounds_fail_explicitly_without_emitting_a_silent_subset(self):
        with patch.object(intake, 'MAX_ROWS', 1), self.assertRaisesRegex(ValueError, 'no subset emitted'):
            self.parse(raw=text([record('ONE'), record('TWO')]))
        with patch.object(intake, 'MAX_BYTES', 1), self.assertRaisesRegex(ValueError, 'byte bound'):
            self.parse()
        with self.assertRaises(ValueError):
            intake.parse({}, b'not text')
        with self.assertRaises(ValueError):
            intake.parse([], text())

    def test_empty_source_is_a_visible_gap_and_cutoff_eligibility_is_callers_job(self):
        rows, metadata, issues = self.parse(raw='')
        self.assertEqual(rows, [])
        self.assertIn('IBKR_EMPTY_SOURCE', metadata['global_qualification_errors'])
        self.assertTrue(issues)
        value = document(); value['as_of'] = '2026-01-01T00:00:00Z'
        rows, metadata, _ = self.parse(value)
        self.assertNotIn('eligible', rows[0])
        self.assertFalse(metadata['eligibility_at_cutoff_evaluated'])


if __name__ == '__main__':
    unittest.main()
