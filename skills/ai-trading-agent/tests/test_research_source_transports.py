import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import borrow_intake
import research_operations as operations
from test_research_operations import config, private_directory


BODY = ('#BOF|2026.11.12|23:48:07\n'
        '#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|\n'
        'DEMO|USD|FICTIONAL COMPANY|1|XXXX|-1.5|0.25|100|FIGI|\n#EOF|1\n').encode()


def configured():
    result = config()
    result['sources'] = [dict(id='public-borrow', url=borrow_intake.PUBLIC_URL,
                             adapter='ibkr_shortstock', rights='Fictional test only', retries=0)]
    return result


def client():
    ftp = MagicMock(); ftp.sock = object()
    ftp.connect.return_value = '220 Public FTP'
    ftp.login.return_value = '230 Public login'
    ftp.quit.return_value = '221 Goodbye'
    ftp.size.return_value = len(BODY)
    def retrieve(command, callback, blocksize):
        callback(BODY)
        return '226 Transfer complete.'
    ftp.retrbinary.side_effect = retrieve
    ftp.close.side_effect = lambda: setattr(ftp, 'sock', None)
    return ftp


class SourceTransportTests(unittest.TestCase):
    def collected(self, folder):
        root = Path(folder) / 'private'; root.mkdir()
        operations.register(root, configured())
        return root

    def test_configured_public_ftp_collect_reuses_one_capture_and_records_actual_protocol(self):
        with private_directory() as folder:
            root = self.collected(folder)
            ftp = client()
            with patch.object(borrow_intake.ftplib, 'FTP', return_value=ftp) as create:
                first = operations.collect(root, 'public-file')
                second = operations.collect(root, 'public-file')
            self.assertEqual(first, second)
            self.assertEqual(first['sources'][0]['status'], 'PARSED')
            self.assertEqual(first['sources'][0]['eligible_records'], 1)
            create.assert_called_once_with()
            ftp.retrbinary.assert_called_once()
            path = operations._root(root) / 'runs/public-file/captures/public-borrow/attempt-0001/download/manifest.json'
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest['transport'], 'FTP')
            self.assertNotIn('http_status', manifest['attempts'][0])
            self.assertEqual(manifest['attempts'][0]['ftp_response_code'], 226)

    def test_other_routes_retries_and_source_types_do_not_gain_ftp_access(self):
        for variant in ('retry', 'other-url', 'wrong-adapter'):
            d = configured()
            if variant == 'retry': d['sources'][0]['retries'] = 1
            elif variant == 'other-url': d['sources'][0]['url'] += '?other=1'
            else: d['sources'][0]['adapter'] = 'sec_company_tickers'
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                operations._config(d)

    def test_tampered_protocol_fields_are_not_accepted_as_complete(self):
        variants = [('transport', 'HTTPS'), ('ftp_response_code', 200), ('retr_commands', True),
                    ('ftp_control_socket_closed', False), ('declared_size_bytes', len(BODY) + 1)]
        for field, value in variants:
            with self.subTest(field=field), private_directory() as folder:
                root = self.collected(folder)
                with patch.object(borrow_intake.ftplib, 'FTP', return_value=client()):
                    operations.collect(root, 'tamper')
                path = operations._root(root) / 'runs/tamper/captures/public-borrow/attempt-0001/download/manifest.json'
                manifest = json.loads(path.read_text()); manifest['attempts'][0][field] = value
                path.write_text(json.dumps(manifest))
                value = operations.collect(root, 'tamper')
                self.assertEqual(value['sources'][0]['status'], 'INTEGRITY_ERROR')

    def test_failed_capture_never_substitutes_empty_or_current_inventory(self):
        with private_directory() as folder:
            root = self.collected(folder); ftp = client()
            ftp.retrbinary.side_effect = OSError('fictional interrupted transfer')
            with patch.object(borrow_intake.ftplib, 'FTP', return_value=ftp) as create:
                first = operations.collect(root, 'failed')
                second = operations.collect(root, 'failed')
            self.assertEqual(first, second)
            create.assert_called_once_with()
            self.assertEqual(first['sources'][0]['status'], 'ACQUISITION_FAILED')
            self.assertTrue(first['coverage_gaps'])
            self.assertFalse(first['execution_authorized'])

    def test_ftp_manifest_contradictions_do_not_replay_as_success(self):
        for variant in ('unknown-size', 'manifest-incomplete', 'source-incomplete', 'multiple-attempts',
                        'source-transport', 'retained-error'):
            with self.subTest(variant=variant), private_directory() as folder:
                root = self.collected(folder)
                with patch.object(borrow_intake.ftplib, 'FTP', return_value=client()):
                    operations.collect(root, 'contradiction')
                path = operations._root(root) / 'runs/contradiction/captures/public-borrow/attempt-0001/download/manifest.json'
                manifest = json.loads(path.read_text())
                if variant == 'unknown-size': manifest['attempts'][0]['declared_size_bytes'] = None
                elif variant == 'manifest-incomplete': manifest['raw_complete'] = False
                elif variant == 'source-incomplete': manifest['source']['raw_complete'] = False
                elif variant == 'multiple-attempts': manifest['attempts'].append(copy.deepcopy(manifest['attempts'][0]))
                elif variant == 'source-transport': manifest['source']['transport'] = 'HTTPS'
                else: manifest['attempts'][0]['error'] = 'fictional contradictory failure'
                path.write_text(json.dumps(manifest))
                self.assertEqual(operations.collect(root, 'contradiction')['sources'][0]['status'], 'INTEGRITY_ERROR')


if __name__ == '__main__':
    unittest.main()
