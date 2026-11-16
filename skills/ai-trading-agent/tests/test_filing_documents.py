"""Fictional filing documents; no private case evidence or network required."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import filing_documents as fd


URL = 'https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/report.htm'
EIGHT_K = b'''<!DOCTYPE html><html><head><title>Fictional 8-K</title></head><body>
<ix:hidden>Item 1.01 Fake hidden item</ix:hidden><script>guidance 999</script>
<p><b>Item 2.02.</b> Results of Operations and Financial Condition.</p>
<p>On November 2, 2026, Fable Devices announced quarterly results. See Exhibit 99.1.</p>
<p>Item 7.01 Regulation FD Disclosure</p>
<p>The company withdrew the earlier full-year outlook; no replacement was provided.</p>
<p>Item 9.01 Financial Statements and Exhibits.</p><table><tr><td>99.1</td>
<td><a href="ex99-1.htm">Exhibit 99.1</a></td><td>Earnings press release</td></tr></table>
<div>SIGNATURES</div><p>Fictional CEO</p></body></html>'''


def schedule(kind='13D', amendment=False, second_person=False):
    form = 'SCHEDULE ' + kind + ('/A' if amendment else '')
    namespace = 'http://www.sec.gov/edgar/schedule13D' if kind == '13D' else 'http://www.sec.gov/edgar/schedule13g'
    if kind == '13D':
        event = '<dateOfEvent>11/01/2026</dateOfEvent>'
        cik = '<issuerCIK>0000123456</issuerCIK>'
        person = '''<reportingPersonInfo><reportingPersonName>Fable Fund</reportingPersonName>
        <soleVotingPower>0</soleVotingPower><sharedVotingPower>1200000.00</sharedVotingPower>
        <aggregateAmountOwned>1200000.00</aggregateAmountOwned><percentOfClass>6.25</percentOfClass>
        <isAggregateExcludeShares>Y</isAggregateExcludeShares><commentContent>Includes shares deemed owned; see Item 5.</commentContent>
        </reportingPersonInfo>'''
        people = '<reportingPersons>' + person + (person.replace('Fable Fund', 'Fable Manager') if second_person else '') + '</reportingPersons>'
    else:
        event = '<eventDateRequiresFilingThisStatement>11/01/2026</eventDateRequiresFilingThisStatement>'
        cik = '<issuerCik>0000123456</issuerCik>'
        people = '''<coverPageHeaderReportingPersonDetails><reportingPersonName>Fable Index</reportingPersonName>
        <reportingPersonBeneficiallyOwnedNumberOfShares><soleVotingPower>800000</soleVotingPower>
        <sharedVotingPower>0</sharedVotingPower></reportingPersonBeneficiallyOwnedNumberOfShares>
        <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>900000</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
        <classPercent>4.7</classPercent><aggregateAmountExcludesCertainSharesFlag>N</aggregateAmountExcludesCertainSharesFlag>
        <comments>Different voting and dispositive holdings.</comments></coverPageHeaderReportingPersonDetails>'''
    amendment_xml = '<amendmentNo>2</amendmentNo>' if amendment else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <edgarSubmission xmlns="{namespace}"><schemaVersion>X0202</schemaVersion>
    <headerData><submissionType>{form}</submissionType><filerInfo><contact>NOT_FOR_NORMALIZED_OUTPUT</contact></filerInfo></headerData>
    <formData><coverPageHeader>{amendment_xml}<securitiesClassTitle>Class B common shares</securitiesClassTitle>
    {event}<issuerInfo>{cik}<issuerName>Fable Devices</issuerName><issuerCusips>
    <issuerCusipNumber>000000AA1</issuerCusipNumber><issuerCusipNumber>000000AA2</issuerCusipNumber>
    </issuerCusips></issuerInfo></coverPageHeader>{people}<items><item5><commentText>
    This amendment supplements prior disclosures and is not a complete restatement.</commentText></item5></items>
    </formData></edgarSubmission>'''.encode()


class ExtractionTests(unittest.TestCase):
    def extract(self, raw, form='8-K', **kwargs):
        return fd.extract_document(raw, source_id='fictional-doc', form_type=form,
                                   source_url=URL, **kwargs)

    def test_html_items_links_hidden_and_reconstructable_spans(self):
        report = self.extract(EIGHT_K)
        self.assertEqual([x['item'] for x in report['item_passages']], ['2.02', '7.01', '9.01'])
        self.assertNotIn('Fake hidden', report['normalized_text'])
        self.assertNotIn('999', report['normalized_text'])
        self.assertNotIn('Fictional CEO', report['item_passages'][-1]['passage']['text'])
        for item in report['item_passages']:
            span = item['passage']
            self.assertEqual(report['normalized_text'][span['start']:span['end']], span['text'])
        self.assertEqual(report['exhibit_links'][0]['url'], URL.replace('report.htm', 'ex99-1.htm'))
        self.assertEqual(report['exhibit_links'][0]['status'], 'discovered_not_fetched_or_verified')
        self.assertEqual(report['exhibit_links'][0]['href_as_reported'], 'ex99-1.htm')
        self.assertEqual(report['exhibit_links'][0]['resolution_status'], 'resolved_https')
        self.assertEqual(report['raw_sha256'], hashlib.sha256(EIGHT_K).hexdigest())

    def test_supplied_relative_exhibit_stays_discoverable_without_file_or_network_read(self):
        raw = b'<html><body><a href="latest-exhibit99-1.html">Exhibit 99.1</a></body></html>'
        with patch.object(fd, 'build_opener') as opener, patch.object(fd.Path, 'open') as file_open:
            report = fd.extract_document(raw, source_id='supplied-8k', form_type='8-K')
            opener.assert_not_called()
            file_open.assert_not_called()
        self.assertEqual(len(report['exhibit_links']), 1)
        link = report['exhibit_links'][0]
        self.assertEqual(link['href_as_reported'], 'latest-exhibit99-1.html')
        self.assertEqual(link['resolution_status'], 'unresolved_without_https_base')
        self.assertEqual(link['status'], 'discovered_unresolved_not_fetchable')
        self.assertNotIn('url', link)

    def test_unsafe_exhibit_schemes_are_excluded_with_warning(self):
        for href in ('javascript:alert(1)', 'file:///neighbor.html', 'http://example.invalid/release.htm',
                     'https://' + '@www.sec.gov/release.htm',
                     'https://:synthetic' + '@www.sec.gov/release.htm'):
            raw = f'<html><body><a href="{href}">Exhibit 99.1</a></body></html>'.encode()
            report = self.extract(raw)
            self.assertEqual(report['exhibit_links'], [])
            self.assertIn('UNSUPPORTED_EXHIBIT_LINK_SCHEME_OR_AUTHORITY_NOT_FETCHABLE', report['limitations'])

    def test_withdrawn_guidance_is_candidate_never_numeric_fact_or_semantic_pass(self):
        release = b'<html><body><h2>Business outlook</h2><p>We withdraw guidance of $8 to $9 EPS for FY2026.</p><p>No replacement has been provided.</p></body></html>'
        report = self.extract(release, 'EX-99.1')
        self.assertEqual(report['ownership_facts'], [])
        self.assertEqual(len(report['candidate_passages']), 1)
        self.assertIn('withdraw guidance', report['candidate_passages'][0]['passage']['text'])
        self.assertIn('No replacement', report['candidate_passages'][0]['passage']['text'])
        self.assertEqual(report['candidate_passages'][0]['status'], 'lexical_candidate_requires_semantic_review')

    def test_repeated_toc_or_duplicate_item_is_not_silently_disambiguated(self):
        text = b'Item 2.02 Results\nItem 9.01 Exhibits\nItem 2.02 Results\nActual body\nItem 9.01 Exhibits'
        report = self.extract(text)
        self.assertEqual(report['item_passages'], [])
        self.assertIn('AMBIGUOUS_REPEATED_ITEM_HEADINGS_NO_AUTOMATIC_SECTION_BOUNDARIES', report['limitations'])

    def test_inline_mention_is_not_item_boundary(self):
        report = self.extract(b'We discuss Item 2.02 and guidance in this sentence.')
        self.assertEqual(report['item_passages'], [])

    def test_cyber_incident_error_language_is_preserved_not_access_denial(self):
        raw = b'''<html><body><p>Item 1.05 Material Cybersecurity Incidents</p>
        <p>Customer systems displayed an Access Denied error during the outage. We continue to investigate.</p></body></html>'''
        report = self.extract(raw)
        self.assertEqual([item['item'] for item in report['item_passages']], ['1.05'])
        self.assertIn('Access Denied error during the outage', report['normalized_text'])
        self.assertNotIn('ACCESS_DENIAL_OR_HUMAN_CHECK_NOT_FILING_EVIDENCE', report['limitations'])

    def test_quoted_challenge_language_in_exhibit_is_not_a_denial_page(self):
        for phrase in ('Access Denied', 'Verify you are human', 'Request Rate Threshold Exceeded'):
            raw = f'<html><body><h1>Fable operational update</h1><p>Customers reported the message "{phrase}" during the incident.</p></body></html>'.encode()
            report = self.extract(raw, 'EX-99.1')
            self.assertIn(phrase, report['normalized_text'])

    def test_actual_denial_page_shell_remains_unsupported(self):
        pages = [b'<html><body><h1>Access Denied</h1><p>You do not have permission to access this server.</p></body></html>',
                 b'<html><body><p>Access Denied You don\'t have permission to access this server.</p></body></html>',
                 b'<html><body><h1>Your Request Originates from an Undeclared Automated Tool</h1><p>Please declare your traffic.</p></body></html>',
                 b'Verify you are human\nComplete the challenge before continuing.']
        for raw in pages:
            with self.subTest(raw=raw):
                report = self.extract(raw)
                self.assertEqual(report['normalized_text'], '')
                self.assertIn('ACCESS_DENIAL_OR_HUMAN_CHECK_NOT_FILING_EVIDENCE', report['limitations'])

    def test_combined_item_headings_withhold_automatic_boundaries(self):
        headings = ['Item 2.02 Results of Operations and Financial Condition and Item 7.01 Regulation FD Disclosure.',
                    'Items 2.02 and 7.01 Results and FD Disclosure.',
                    'Item 2.02/7.01 Results and FD Disclosure.']
        for heading in headings:
            raw = f'<html><body><p>{heading}</p><p>The release is furnished under both Items.</p><p>Item 9.01 Financial Statements and Exhibits.</p></body></html>'.encode()
            with self.subTest(heading=heading):
                report = self.extract(raw)
                self.assertEqual(report['item_passages'], [])
                self.assertIn('furnished under both Items', report['normalized_text'])
                self.assertIn('AMBIGUOUS_COMBINED_ITEM_HEADING_NO_AUTOMATIC_SECTION_BOUNDARIES', report['limitations'])

    def test_13d_per_person_no_double_count_or_missing_zero(self):
        report = self.extract(schedule(second_person=True), 'SC 13D')
        self.assertEqual(len(report['ownership_facts']), 2)
        person = report['ownership_facts'][0]
        self.assertEqual(person['issuer']['share_class'], 'Class B common shares')
        self.assertEqual(len(person['issuer']['cusips']), 2)
        self.assertEqual(person['fields']['aggregate_shares']['value_as_reported'], '1200000.00')
        self.assertEqual(person['fields']['soleVotingPower']['value_as_reported'], '0')
        self.assertIsNone(person['fields']['soleDispositivePower']['value_as_reported'])
        self.assertEqual(person['fields']['soleDispositivePower']['status'], 'missing_unknown')
        self.assertNotIn('NOT_FOR_NORMALIZED_OUTPUT', report['normalized_text'])
        locator = person['fields']['aggregate_shares']['locator']
        self.assertIn('reportingPersonInfo[1]/aggregateAmountOwned', locator['path'])
        self.assertEqual(locator['namespace'], 'http://www.sec.gov/edgar/schedule13D')
        tree = ET.fromstring(schedule(second_person=True))
        relative = '/'.join('s:' + component for component in locator['path'].split('/')[2:])
        located = tree.find(relative, {'s': locator['namespace']})
        self.assertEqual(located.text, person['fields']['aggregate_shares']['value_as_reported'])

    def test_13g_distinct_schema_and_event_clock(self):
        report = self.extract(schedule('13G', amendment=True), 'SCHEDULE 13G/A',
                              accepted_at='2026-11-02T17:00:00-05:00', retrieved_at='2026-11-03T00:00:00Z')
        person = report['ownership_facts'][0]
        self.assertEqual(person['fields']['aggregate_shares']['value_as_reported'], '900000')
        self.assertEqual(person['fields']['percent_of_class']['value_as_reported'], '4.7')
        self.assertEqual(person['fields']['soleVotingPower']['value_as_reported'], '800000')
        self.assertEqual(report['ownership_metadata']['event_date_as_reported'], '11/01/2026')
        self.assertEqual(report['ownership_metadata']['amendment_number_as_reported'], '2')
        self.assertEqual(report['amendment_status'], 'amendment_requires_prior_filings')
        self.assertIsNone(report['ownership_metadata']['previous_accession_as_reported'])

    def test_declared_form_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DECLARED_AND_XML_FORM_MISMATCH'):
            self.extract(schedule(amendment=True), '13D')

    def test_duplicate_scalar_not_first_value_wins(self):
        raw = schedule().replace(b'<percentOfClass>6.25</percentOfClass>', b'<percentOfClass>6.25</percentOfClass><percentOfClass>99</percentOfClass>')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_OWNERSHIP_FIELD'):
            self.extract(raw, '13D')

    def test_foreign_namespace_is_not_structured_ownership(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_OWNERSHIP_XML_NAMESPACE'):
            self.extract(schedule().replace(b'http://www.sec.gov/edgar/schedule13D', b'https://example.invalid/fake'), '13D')

    def test_xml_external_entity_rejected(self):
        raw = schedule().replace(b'<edgarSubmission', b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///never-read">]><edgarSubmission', 1)
        with self.assertRaisesRegex(ValueError, 'DTD_OR_ENTITY'):
            self.extract(raw, '13D')

    def test_legacy_text_pdf_and_denial_remain_unsupported(self):
        self.assertEqual(self.extract(b'Name of reporting person Fable; percent 6.5%', 'SC 13D')['ownership_facts'], [])
        for raw in (b'%PDF fictional', b'<html><p>Access Denied</p></html>'):
            report = self.extract(raw)
            self.assertEqual(report['normalized_text'], '')
            self.assertEqual(report['item_passages'], [])

    def test_complete_submission_is_not_conflated_with_one_document(self):
        report = self.extract(b'<SEC-DOCUMENT>fake.txt\n<DOCUMENT>\n<TYPE>8-K\n<TEXT>\nItem 2.02 Results\n</TEXT>\n</DOCUMENT>')
        self.assertEqual(report['item_passages'], [])
        self.assertIn('COMPLETE_SUBMISSION_SGML_REQUIRES_EXPLICIT_DOCUMENT_SELECTION', report['limitations'])

    def test_encoding_is_not_silently_corrupted(self):
        with self.assertRaisesRegex(ValueError, 'TEXT_ENCODING_REQUIRED'):
            self.extract(b'outlook \x96 $2')
        report = self.extract(b'outlook \x96 $2', content_type='text/plain; charset=windows-1252')
        self.assertIn('\u2013', report['normalized_text'])

    def test_byte_and_candidate_bounds(self):
        with self.assertRaisesRegex(ValueError, 'NONEMPTY_BYTES'):
            self.extract(b'x' * (fd.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'PASSAGE_TERMS_MUST_BE_LIST'):
            self.extract(b'outlook', passage_terms='outlook')


class AcquisitionTests(unittest.TestCase):
    def test_preserve_original_immutable_directory_even_after_extract_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.xml'
            raw = schedule(amendment=True)
            source.write_bytes(raw)
            output = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'FORM_MISMATCH'):
                fd.ingest_document(source, output, source_id='x', form_type='13D')
            self.assertEqual((output / 'original.bin').read_bytes(), raw)
            self.assertEqual(json.loads((output / 'acquisition.json').read_text())['raw_sha256'], hashlib.sha256(raw).hexdigest())
            with self.assertRaises(FileExistsError):
                fd.ingest_document(source, output, source_id='x', form_type='13D/A')

    def test_supplied_ingest_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'input.htm'
            source.write_bytes(EIGHT_K)
            output = Path(temp) / 'run'
            report = fd.ingest_document(source, output, source_id='x', form_type='8-K')
            self.assertEqual((output / 'original.bin').read_bytes(), EIGHT_K)
            self.assertEqual(json.loads((output / 'extraction.json').read_text(encoding='utf-8')), report)

    def test_output_cannot_write_installed_skill(self):
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_INSTALLED_SKILL'):
            fd._output_dir(fd.SKILL_ROOT / 'not-created-by-test')

    def test_url_restrictions(self):
        self.assertEqual(fd.validate_sec_url(URL), URL)
        bad = [URL.replace('https:', 'http:'), URL.replace('www.sec.gov', 'www.sec.gov.evil.invalid'),
               URL + '?next=evil', URL + '#fragment', URL.replace('report.htm', '../report.htm'),
               URL.replace('report.htm', '%2e%2e/report.htm'), URL.replace('https://www.sec.gov', 'https://user' + '@www.sec.gov'),
               URL.replace('https://www.sec.gov', 'https://' + '@www.sec.gov'),
               URL.replace('www.sec.gov', 'www.sec.gov:444'), 'https://www.sec.gov/ixviewer/doc/action']
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                fd.validate_sec_url(url)

    def test_contact_and_offline_fail_before_network_or_output(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(fd, 'build_opener') as opener:
            output = Path(temp) / 'run'
            with patch.dict(fd.os.environ, {'AI_TRADING_SEC_USER_AGENT': ''}):
                with self.assertRaisesRegex(ValueError, 'PRIVATE_IDENTIFYING'):
                    fd.fetch_document(URL, output, source_id='x', form_type='8-K')
            with patch.dict(fd.os.environ, {'AI_TRADING_NETWORK_MODE': 'offline'}):
                with self.assertRaisesRegex(ValueError, 'NETWORK_DISABLED'):
                    fd.fetch_document(URL, output, source_id='x', form_type='8-K', user_agent='Example private@example.invalid')
            opener.assert_not_called()
            self.assertFalse(output.exists())

    def test_fetch_bounds_and_no_contact_persistence(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/html; charset=utf-8'}
            def geturl(self):
                return URL
        with tempfile.TemporaryDirectory() as temp, patch.object(fd, 'build_opener') as opener:
            opener.return_value.open.return_value = Response(EIGHT_K)
            output = Path(temp) / 'run'
            fd.fetch_document(URL, output, source_id='x', form_type='8-K', user_agent='Filing Research private@example.invalid')
            opener.return_value.open.assert_called_once()
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 30)
            self.assertEqual((output / 'original.bin').read_bytes(), EIGHT_K)
            self.assertNotIn('private@example.invalid', ''.join(p.read_text(errors='replace') for p in output.iterdir()))

    def test_http_denial_no_retry_or_private_error(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(fd, 'build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError(URL, 403, 'private@example.invalid', {}, None)
            output = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'SEC_HTTP_ERROR_403_NO_RETRY') as raised:
                fd.fetch_document(URL, output, source_id='x', form_type='8-K', user_agent='Filing Research private@example.invalid')
            self.assertNotIn('private@example.invalid', str(raised.exception))
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertEqual(json.loads((output / 'failure.json').read_text())['http_status'], 403)

    def test_redirect_refused_without_following_new_host(self):
        with self.assertRaisesRegex(ValueError, 'REDIRECT_NOT_FOLLOWED'):
            fd._NoRedirect().redirect_request(None, None, 302, 'Moved', {}, 'https://evil.invalid/')

    def test_oversized_response_stops_before_extracting_or_retrying(self):
        class Response(io.BytesIO):
            headers = {'Content-Type': 'text/plain'}
            def geturl(self):
                return URL
        with tempfile.TemporaryDirectory() as temp, patch.object(fd, 'MAX_BYTES', 100), patch.object(fd, 'build_opener') as opener:
            opener.return_value.open.return_value = Response(b'x' * 101)
            output = Path(temp) / 'run'
            with self.assertRaisesRegex(ValueError, 'FETCH_POLICY_STOP'):
                fd.fetch_document(URL, output, source_id='x', form_type='8-K', user_agent='Filing Research private@example.invalid')
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertFalse((output / 'extraction.json').exists())
            self.assertEqual(json.loads((output / 'failure.json').read_text())['status'], 'fetch_policy_stop')


if __name__ == '__main__':
    unittest.main()
