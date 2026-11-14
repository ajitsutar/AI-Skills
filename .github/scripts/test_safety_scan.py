#!/usr/bin/env python3
"""Check that preserving a public upstream notice does not weaken export scanning."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import safety_scan


class PublicNoticeTests(unittest.TestCase):
    def setUp(self):
        self.name = next(iter(safety_scan.PUBLIC_LICENSE_EMAIL_EXCEPTIONS))
        self.notice = (safety_scan.ROOT / self.name).read_text(encoding="utf-8")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / self.name
        self.path.parent.mkdir(parents=True)

    def findings(self, text):
        self.path.write_text(text, encoding="utf-8")
        with patch.object(safety_scan, "ROOT", self.root):
            return safety_scan.scan()

    def test_exact_reviewed_notice_is_allowed(self):
        self.assertEqual(self.findings(self.notice), [])

    def test_windows_line_endings_are_allowed(self):
        self.path.write_bytes(self.notice.replace("\n", "\r\n").encode())
        with patch.object(safety_scan, "ROOT", self.root):
            self.assertEqual(safety_scan.scan(), [])

    def test_modified_notice_does_not_inherit_email_exception(self):
        extra = "\nprivate" + "@" + "example.invalid\n"
        self.assertTrue(any("personal email" in s for s in self.findings(self.notice + extra)))

    def test_same_content_at_other_path_is_not_exempt(self):
        (self.root / "unreviewed.txt").write_text(self.notice, encoding="utf-8")
        with patch.object(safety_scan, "ROOT", self.root):
            self.assertTrue(any("personal email" in s for s in safety_scan.scan()))

    def test_email_exception_never_disables_secret_detection(self):
        modified = self.notice + "\n" + "sk-" + "a" * 24 + "\n"
        digest = hashlib.sha256(modified.encode()).hexdigest()
        with patch.dict(safety_scan.PUBLIC_LICENSE_EMAIL_EXCEPTIONS, {self.name: digest}):
            self.assertTrue(any("OpenAI-style key" in s for s in self.findings(modified)))


class SbomIdentifierTests(unittest.TestCase):
    def test_only_consistent_structured_identifiers_are_recognized(self):
        component = {'name': 'python-dateutil', 'version': '2.9.0.post0',
                     'bom-ref': 'python-dateutil' + '@' + '2.9.0.post0',
                     'purl': 'pkg:pypi/python-dateutil' + '@' + '2.9.0.post0'}
        doc = {'bomFormat': 'CycloneDX', 'components': [component]}
        path = 'skills/ai-trading-agent/environments/windows-cp312-core/sbom.cdx.json'
        text = json.dumps(doc)
        self.assertEqual(len(safety_scan.sbom_package_identifier_spans(text, path)), 2)
        self.assertEqual(safety_scan.sbom_package_identifier_spans(text, 'other.json'), [])
        component['version'] = 'example.invalid'
        self.assertEqual(safety_scan.sbom_package_identifier_spans(json.dumps(doc), path), [])

    def test_real_email_and_secret_remain_findings_inside_sbom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'skills/ai-trading-agent/environments/windows-cp312-core/sbom.cdx.json'
            path.parent.mkdir(parents=True)
            doc = {'bomFormat': 'CycloneDX', 'components': [],
                   'note': 'private' + '@' + 'example.invalid', 'secret': 'sk-' + 'a' * 24}
            path.write_text(json.dumps(doc), encoding='utf-8')
            with patch.object(safety_scan, 'ROOT', root):
                findings = safety_scan.scan()
            self.assertTrue(any('personal email' in row for row in findings))
            self.assertTrue(any('OpenAI-style key' in row for row in findings))


class PythonFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scan_number = 0

    def findings(self, text, name='skills/ai-trading-agent/tests/test_fixture.py'):
        self.scan_number += 1
        root = self.root / str(self.scan_number)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        with patch.object(safety_scan, 'ROOT', root):
            return safety_scan.scan()

    def email_findings(self, text, name='skills/ai-trading-agent/tests/test_fixture.py'):
        return [row for row in self.findings(text, name) if 'personal email' in row]

    def test_empty_python_password_is_not_a_credential(self):
        key = 'PUBLIC_' + 'PASSWORD'
        self.assertEqual(self.findings(key + " = ''\n", 'scripts/public_feed.py'), [])

    def test_nonempty_dynamic_and_expression_passwords_remain_blocked(self):
        key = 'pass' + 'word'
        for value in ("'synthetic-secret'", "'' or 'synthetic-secret'", 'read_value()', 'None'):
            with self.subTest(value=value):
                self.assertTrue(any('password assignment' in row for row in self.findings(key + ' = ' + value + '\n')))

    def test_empty_assignment_does_not_hide_other_assignment_or_comment(self):
        key = 'pass' + 'word'
        for text in (key + " = ''; other_" + key + " = 'synthetic-secret'\n",
                     key + " = ('' # " + key + " = synthetic-secret\n '')\n"):
            with self.subTest(text=text):
                self.assertTrue(any('password assignment' in row for row in self.findings(text)))

    def test_empty_nonpython_assignment_is_still_scanned(self):
        self.assertTrue(self.findings('pass' + 'word' + " = ''\n", 'settings.txt'))

    def test_reserved_domains_are_allowed_only_as_test_string_literals(self):
        for domain in ('example.invalid', 'example.com', 'example.net', 'example.org'):
            with self.subTest(domain=domain):
                value = 'fictional' + '@' + domain
                self.assertEqual(self.email_findings('value = ' + repr(value) + '\n'), [])

    def test_reserved_address_outside_tests_or_in_comment_remains_blocked(self):
        value = 'fictional' + '@' + 'example.invalid'
        self.assertTrue(self.email_findings('# ' + value + '\n'))
        self.assertTrue(self.email_findings('value = ' + repr(value), 'scripts/client.py'))

    def test_personal_contact_patterns_and_domain_lookalikes_remain_blocked(self):
        for domain in ('company.test', 'example.com.evil.test', 'sub.example.invalid', 'notexample.com'):
            with self.subTest(domain=domain):
                self.assertTrue(self.email_findings('value = ' + repr('person' + '@' + domain)))

    def test_fstrings_and_invalid_python_do_not_receive_exceptions(self):
        value = 'fictional' + '@' + 'example.invalid'
        self.assertTrue(self.email_findings('value = f' + repr(value)))
        self.assertTrue(self.email_findings('broken (\nvalue = ' + repr(value)))

    def test_unicode_prefix_and_multiline_string_offsets_are_exact(self):
        reserved = 'fictional' + '@' + 'example.invalid'
        contact = 'person' + '@' + 'company.test'
        text = "label = 'é'; value = " + repr(reserved) + '; contact = ' + repr(contact) + '\n'
        self.assertEqual(len(self.email_findings(text)), 1)
        text = 'value = """line one\n' + reserved + '\n' + contact + '\n"""\n'
        self.assertEqual(len(self.email_findings(text)), 1)

    def fixture(self, filename, class_name, method, value):
        name = 'skills/ai-trading-agent/tests/' + filename
        text = 'class ' + class_name + ':\n    def ' + method + '(self):\n        value = ' + repr(value) + '\n'
        return name, text

    def test_exact_public_host_rejection_fixtures_are_recognized(self):
        cases = [
            ('test_borrow_intake.py', 'BorrowCaptureTests',
             'test_exact_route_rejects_credentials_queries_redirects_and_other_files',
             'ftp://shortstock' + '@' + 'ftp2.interactivebrokers.com/usa.txt'),
            ('test_borrow_intake.py', 'BorrowCaptureTests',
             'test_exact_route_rejects_credentials_queries_redirects_and_other_files',
             'ftp://shortstock:password' + '@' + 'ftp2.interactivebrokers.com/usa.txt'),
            ('test_market_sources.py', 'SecDailyIndexTests',
             'test_exact_index_url_requires_consistent_calendar_and_no_proxy_query_or_redirect',
             'user' + '@' + 'www.sec.gov'),
            ('test_sec_identity.py', 'SecIdentityTests',
             'test_exact_https_identity_families_and_narrow_ftp_provenance',
             'ftp://secret' + '@' + 'ftp2.interactivebrokers.com/usa.txt'),
        ]
        for case in cases:
            with self.subTest(case=case):
                name, text = self.fixture(*case)
                self.assertEqual(self.email_findings(text, name), [])

    def test_changed_rejection_value_or_context_is_not_exempt(self):
        value = 'ftp://secret' + '@' + 'ftp2.interactivebrokers.com/usa.txt'
        filename, cls = 'test_sec_identity.py', 'SecIdentityTests'
        method = 'test_exact_https_identity_families_and_narrow_ftp_provenance'
        for args in ((filename, cls, method, value.replace('secret', 'different-secret')),
                     (filename, cls, 'test_other', value),
                     (filename, 'OtherTests', method, value),
                     ('test_other.py', cls, method, value)):
            with self.subTest(args=args):
                name, text = self.fixture(*args)
                self.assertTrue(self.email_findings(text, name))

    def public_header(self):
        return ('Description:           Master Index of EDGAR Dissemination Feed\n'
                'Last Data Received:    November 12, 2026\nComments:              webmaster' + '@' + 'sec.gov\n\n'
                'CIK|Company Name|Form Type|Date Filed|Filename\n'
                '--------------------------------------------------------------------------------\n')

    def test_public_header_requires_exact_value_assignment_class_and_path(self):
        header = self.public_header()
        name = 'skills/ai-trading-agent/tests/test_market_sources.py'
        text = 'class SecDailyIndexTests:\n    PREFIX = ' + repr(header) + '\n'
        self.assertEqual(self.email_findings(text, name), [])
        for changed in (text.replace('PREFIX', 'CONTACT'), text.replace('SecDailyIndexTests', 'OtherTests'),
                        text.replace('webmaster', 'different')):
            with self.subTest(changed=changed):
                self.assertTrue(self.email_findings(changed, name))

    def test_exact_header_never_exempts_extra_contacts_or_adjacent_comments(self):
        header = self.public_header()
        contact = 'person' + '@' + 'company.test'
        name = 'skills/ai-trading-agent/tests/test_market_sources.py'
        base = 'class SecDailyIndexTests:\n    PREFIX = '
        self.assertTrue(self.email_findings(base + repr(header + contact), name))
        text = base + '(' + repr(header) + ' # ' + contact + "\n        '')\n"
        self.assertEqual(len(self.email_findings(text, name)), 1)

    def test_fixture_exceptions_do_not_suppress_other_secret_detectors(self):
        value = 'fictional' + '@' + 'example.invalid'
        text = 'value = ' + repr(value) + '\nsecret = ' + repr('sk-' + 'a' * 24) + '\n'
        found = self.findings(text)
        self.assertTrue(any('OpenAI-style key' in row for row in found))
        self.assertFalse(any('personal email' in row for row in found))


if __name__ == "__main__":
    unittest.main()
