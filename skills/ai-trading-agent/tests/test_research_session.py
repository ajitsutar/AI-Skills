"""Ordinary-request assistant path; fictional public-source artifacts only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_session as module

T0 = '2030-07-15T18:00:00Z'
T1 = '2030-07-15T18:10:00Z'
T2 = '2030-07-15T18:20:00Z'


def span(raw, needle=None):
    needle = raw[:min(32, len(raw))] if needle is None else needle
    start = raw.index(needle)
    return {'start_byte': start, 'end_byte': start + len(needle), 'sha256': module.sha(needle)}


class ResearchSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'ordinary-earnings'
        self.request = ("Review Helio Devices' earnings and guidance. "
                        "Explain valuation and the main risks.\n").encode('utf8')
        self.release = b'''<html><body><h1>Helio Devices 8-K</h1>
        <h2>Item 2.02 Results of Operations and Financial Condition</h2>
        <p>Revenue was USD 110 million versus USD 100 million a year earlier.
        FY2030 adjusted diluted EPS guidance is USD 2.00. Supply constraints
        could delay shipments. This outlook is forward-looking.</p>
        <h2>Item 9.01 Financial Statements and Exhibits</h2>
        <p>Exhibit 99.1 Earnings release</p></body></html>'''
        self.quote = b'{"symbol":"HLIO","price":50,"currency":"USD","share_basis":"diluted","available_at":"2030-07-15T17:00:00Z"}\n'
        inputs = {'as_of': T0, 'quote': json.loads(self.quote), 'estimates': [
            {'id': 'issuer-guidance', 'source': 'release, FY2030 outlook paragraph', 'eps': 2,
             'available_at': '2030-07-15T16:00:00Z', 'period_start': '2030-01-01',
             'period_end': '2030-12-31', 'period_type': 'fiscal', 'accounting_basis': 'adjusted',
             'share_basis': 'diluted', 'currency': 'USD'}]}
        self.normalized = module.encode({'earnings_basis': {'document': inputs}})
        self.sources = []
        for sid, raw, origin in [('release', self.release, 'supplied'), ('quote', self.quote, 'host_collected'),
                                 ('normalized', self.normalized, 'host_derived')]:
            path = self.root / (sid + '.txt'); path.write_bytes(raw)
            spec = {'id': sid, 'path': str(path), 'role': sid + ' evidence', 'origin': origin}
            if sid == 'normalized':
                spec['derived_from'] = ['release', 'quote']
            self.sources.append(spec)
        self.tasks = [
            {'id': 'earnings', 'requirement': 'Explain reported earnings and guidance with period and accounting basis.',
             'request_excerpt': 'earnings and guidance', 'required_source_ids': ['release']},
            {'id': 'valuation', 'requirement': 'Calculate a guidance-based multiple without treating it as fair value.',
             'request_excerpt': 'valuation', 'required_source_ids': ['release', 'quote', 'normalized']},
            {'id': 'risks', 'requirement': 'Explain the principal risks and limitations.',
             'request_excerpt': 'main risks', 'required_source_ids': ['release']}]

    def start(self, **changes):
        kwargs = {'workflow': 'earnings_guidance', 'sources': self.sources, 'tasks': self.tasks, 'as_of': T0}
        kwargs.update(changes)
        receipt = module.start_session(self.run, self.request, **kwargs)
        self.pin = receipt['session_sha256']
        return receipt

    def packet(self, *, calculation=True, filings=True, dispositions=None):
        dispositions = dispositions or [{'id': task['id'], 'status': 'supported',
            'reason': 'Retained issuer statements and explicit compatible guidance/quote inputs support the stated scope.',
            'evidence_ids': task['required_source_ids']} for task in self.tasks]
        job = {'schema_version': 1, 'network_mode': 'offline',
               'contract': {'prompt': self.request.decode(), 'purpose': 'Earnings and guidance research',
                            'base_currency': 'USD', 'horizon_id': 'FY2030', 'as_of': T0},
               'jobs': [{'id': 'guidance-multiple', 'operation': 'analyst.earnings_basis',
                         'inputs_source': {'path': 'normalized.bin', 'sha256': module.sha(self.normalized),
                                           'pointer': '/earnings_basis'}}]}
        return module.prepare_packet(self.run, expected_session_sha256=self.pin, dispositions=dispositions,
                filings=[{'source_id': 'release', 'options': {'form_type': '8-K',
                          'content_type': 'text/html', 'passage_terms': ['guidance']}}] if filings else [],
                calculation=job if calculation else None)

    def review(self, packet, markdown, statuses=None, *, direct_revision_record=False):
        created = module.start_review(self.run, expected_session_sha256=self.pin,
                                     expected_packet_sha256=packet['packet_sha256'], adopted_at=T0)
        draft = module.freeze_draft(self.run, markdown, module.encode({'answer': markdown.decode()}), T1,
                    expected_session_sha256=self.pin, expected_head_sha256=created['head_sha256'])
        base = self.run / 'review'
        protocol = json.loads((base / created['protocol']['path']).read_bytes())
        source_bytes = {r['id']: (base / r['artifact']['path']).read_bytes() for r in protocol['sources']}
        document = {'schema_version': 1, 'protocol': created['protocol'], 'reviewed_at': T2,
                    'reviewer': {'id': 'native-host-review', 'kind': 'automated'},
                    'delivery': draft['delivery'], 'reviews': []}
        for unit in protocol['units']:
            status = (statuses or {}).get(unit['id'], 'SATISFIED')
            document['reviews'].append({'unit_id': unit['id'], 'status': status,
                'material_error': False, 'issues': [] if status == 'SATISFIED' else ['source_status'],
                'rationale': 'Fictional native reviewer declaration based on retained source and complete draft.',
                'answer_spans': [{'artifact': 'first_response', 'span': span(markdown)}],
                'source_reviews': [{'source_id': sid, 'status': 'REVIEWED', 'spans': [span(source_bytes[sid])]}
                                   for sid in unit['required_source_ids']]})
        if direct_revision_record:
            import research_revision
            reviewed = research_revision.record_review(self.run / 'review', document,
                        reviewer_mode='self_native', expected_head_sha256=draft['head_sha256'])
        else:
            reviewed = module.record_review(self.run, document, reviewer_mode='self_native',
                        expected_session_sha256=self.pin, expected_head_sha256=draft['head_sha256'])
        final = module.select_final(self.run, draft['draft_id'], expected_session_sha256=self.pin,
                                     expected_head_sha256=reviewed['head_sha256'])
        return draft, reviewed, final

    def test_complete_ordinary_request_to_actual_filing_calculation_review_and_exact_answer(self):
        self.start()
        self.assertEqual((self.run / 'request.txt').read_bytes(), self.request)
        self.assertEqual((self.run / 'sources/release.bin').read_bytes(), self.release)
        packet = self.packet()
        # The existing producer keeps COMPUTED_EXPLICIT_BASIS as a nested
        # diagnostic. A useful answer retains that scope rather than upgrading it.
        self.assertEqual(packet['packet']['status'], 'EVIDENCE_WITH_LIMITATIONS')
        self.assertEqual(packet['packet']['calculation_completion']['status'], 'COMPLETED_WITH_DIAGNOSTICS')
        self.assertEqual(packet['packet']['calculation_completion']['jobs'][0]['computation_status'], 'COMPUTED')
        result = json.loads((self.run / 'calculation/run/result.json').read_bytes())
        multiple = result['jobs'][0]['result']['results'][0]['multiple']
        self.assertEqual(multiple, 25)
        extraction = json.loads((self.run / 'filings/release.json').read_bytes())
        self.assertIn('USD 110 million', extraction['normalized_text'])
        answer = ("Helio reported revenue of USD 110 million versus USD 100 million a year earlier "
                  "[release, Item 2.02]. FY2030 adjusted diluted EPS guidance is USD 2.00; it is "
                  "forward-looking and uses an adjusted basis [release]. At the retained USD 50 quote, "
                  "the existing earnings-basis calculation gives 25x that guidance, not a fair-value estimate "
                  "[quote; calculation/run/result.json, guidance-multiple]. Supply constraints could delay "
                  "shipments. A scenario based on issuer guidance can miss actual earnings [release].\n").encode()
        draft, reviewed, final = self.review(packet, answer)
        self.assertEqual(final['disposition']['final_status'], 'REVIEWED_DELIVERY')
        self.assertFalse(reviewed['assessment']['whole_answer_correctness_verified'])
        self.assertEqual((self.run / 'review' / final['delivery']['first_response']['path']).read_bytes(), answer)
        notice = (self.run / 'review' / final['delivery_notice']['path']).read_text()
        self.assertIn('self', notice.lower())

    def test_event_research_missing_evidence_delivers_complete_limited_answer(self):
        self.request = b'Explain the proposed merger and its closing risk.\n'
        self.tasks = [{'id': 'merger', 'requirement': 'Explain merger terms and closing risk.',
                       'request_excerpt': 'proposed merger and its closing risk', 'required_source_ids': []}]
        self.start(workflow='event_research', sources=[])
        dispositions = [{'id': 'merger', 'status': 'unsupported', 'reason':
                         'No merger agreement, announcement, financing or regulatory evidence was available.',
                         'evidence_ids': []}]
        packet = self.packet(calculation=False, filings=False, dispositions=dispositions)
        self.assertEqual(packet['packet']['status'], 'EVIDENCE_WITH_LIMITATIONS')
        answer = (b'The merger terms and probability of closing remain unresolved: no agreement, issuer announcement, '
                  b'financing evidence or regulatory status was available. An event-driven recommendation cannot be '
                  b'supported. The next research step is to obtain the issuer announcement and agreement, then '
                  b'examine conditions, termination rights, financing and approvals.\n')
        _, _, final = self.review(packet, answer, {'merger': 'UNSUPPORTED'})
        self.assertEqual(final['disposition']['final_status'], 'DELIVERED_WITH_LIMITATIONS')
        notice = (self.run / 'review' / final['delivery_notice']['path']).read_text()
        self.assertIn('merger', notice)
        self.assertIn('UNSUPPORTED', notice)

    def test_failed_explicit_source_is_preserved_and_does_not_scan_for_replacement(self):
        self.sources[0]['path'] = str(self.root / 'missing-release.html')
        with self.assertRaisesRegex(ValueError, 'BOUNDED_EXPLICIT_FILE_REQUIRED'):
            self.start()
        self.assertEqual((self.run / 'request.txt').read_bytes(), self.request)
        self.assertTrue((self.run / 'start-failure.json').is_file())
        self.assertFalse((self.run / 'session.json').exists())

    def test_input_tampering_and_rewritten_manifest_fail_external_pin(self):
        self.start()
        (self.run / 'sources/release.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SESSION_INPUT_CHANGED'):
            self.packet()
        doc = json.loads((self.run / 'session.json').read_bytes())
        doc['sources'][0]['artifact']['sha256'] = module.sha(b'changed')
        (self.run / 'session.json').write_bytes(module.encode(doc))
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_SESSION_PIN_MISMATCH'):
            self.packet()

    def test_wrong_packet_pin_and_changed_calculation_annex_rejected(self):
        self.start(); packet = self.packet()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_PACKET_PIN_MISMATCH'):
            module.start_review(self.run, expected_session_sha256=self.pin,
                                expected_packet_sha256='0' * 64, adopted_at=T0)
        (self.run / 'calculation/answer-facts.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'CALCULATION_OUTPUT_CHANGED'):
            module.start_review(self.run, expected_session_sha256=self.pin,
                                expected_packet_sha256=packet['packet_sha256'], adopted_at=T0)

    def test_failed_real_calculator_stays_visible_in_packet(self):
        broken = json.loads(self.normalized); broken['earnings_basis']['document']['quote']['price'] = -50
        self.normalized = module.encode(broken)
        (self.root / 'normalized.txt').write_bytes(self.normalized)
        self.start(); packet = self.packet()
        self.assertEqual(packet['packet']['status'], 'EVIDENCE_WITH_LIMITATIONS')
        self.assertNotEqual(packet['packet']['calculation_completion']['status'], 'COMPLETED_LOCAL_WORKFLOW')
        self.assertIn('PRICE_RANGE', (self.run / 'calculation/run/result.json').read_text())

    def test_missing_material_task_disposition_preserves_failure(self):
        self.start()
        with self.assertRaisesRegex(ValueError, 'EXACT_MATERIAL_TASK_DISPOSITIONS_REQUIRED'):
            self.packet(dispositions=[{'id': 'earnings', 'status': 'unsupported', 'reason': 'Missing.', 'evidence_ids': []}])
        self.assertTrue((self.run / 'packet-failure.json').exists())
        with self.assertRaisesRegex(ValueError, 'PACKET_ALREADY_ATTEMPTED'):
            self.packet()

    def test_cyclic_host_derived_lineage_rejected_without_losing_originals(self):
        self.sources[0].update(origin='host_derived', derived_from=['normalized'])
        with self.assertRaisesRegex(ValueError, 'CYCLIC_SOURCE_LINEAGE'):
            self.start()
        self.assertEqual((self.run / 'sources/release.bin').read_bytes(), self.release)
        self.assertTrue((self.run / 'start-failure.json').exists())

    def test_real_filing_parser_failure_is_retained_as_limited_packet(self):
        self.start()
        dispositions = [{'id': task['id'], 'status': 'limited', 'reason': 'The requested filing parser job needs correction.',
                         'evidence_ids': task['required_source_ids']} for task in self.tasks]
        result = module.prepare_packet(self.run, expected_session_sha256=self.pin, dispositions=dispositions,
                                       filings=[{'source_id': 'release', 'options': {}}])
        self.assertEqual(result['packet']['status'], 'EVIDENCE_WITH_LIMITATIONS')
        self.assertIn('form_type', result['packet']['filing_errors'][0]['reason'])
        self.assertTrue((self.run / 'filings/release-failure.json').exists())
        self.assertEqual((self.run / 'sources/release.bin').read_bytes(), self.release)

    def binary_case(self, *, linked=True, readable=b'Page 1, issuer outlook: FY2030 adjusted diluted EPS guidance USD 2.00.\n'):
        self.request = b'Explain the attached filing.\n'
        self.tasks = [{'id': 'filing', 'requirement': 'Explain the filing and retain evidence limitations.',
                       'request_excerpt': 'attached filing', 'required_source_ids': ['original']}]
        self.pdf = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n'
        binary = self.root / 'native-original.pdf'; binary.write_bytes(self.pdf)
        self.sources = [{'id': 'original', 'path': str(binary), 'role': 'Original binary filing', 'origin': 'supplied'}]
        if linked:
            projection = self.root / 'native-extraction.txt'; projection.write_bytes(readable)
            self.sources[0]['metadata'] = {'readable_projection_source_id': 'readable'}
            self.sources.append({'id': 'readable', 'path': str(projection), 'role': 'Page-located native extraction',
                                 'origin': 'host_derived', 'derived_from': ['original']})

    def test_binary_original_and_linked_utf8_projection_use_actual_review_without_invented_spans(self):
        self.binary_case(); self.start()
        packet = self.packet(calculation=False, filings=False)
        answer = (b'The retained native extraction reports FY2030 adjusted diluted EPS guidance USD 2.00 '
                  b'[readable, Page 1]. The original binary is retained unchanged. Projection fidelity and '
                  b'visual inspection are native reviewer declarations, not verified by the helper.\n')
        _, reviewed, final = self.review(packet, answer)
        self.assertEqual(final['disposition']['final_status'], 'REVIEWED_DELIVERY')
        self.assertEqual((self.run / 'sources/original.bin').read_bytes(), self.pdf)
        provenance = json.loads((self.run / 'review/sources/original.bin').read_bytes())
        self.assertEqual(provenance['representation'], 'PROVENANCE_ONLY_NOT_ORIGINAL_BINARY_CONTENT')
        self.assertEqual(provenance['retained_original']['sha256'], module.sha(self.pdf))
        self.assertEqual(provenance['readable_projection_source_id'], 'readable')
        unit = next(u for u in reviewed['assessment']['units'] if u['id'] == 'filing')
        self.assertIn('readable', unit['required_source_ids'])
        self.assertFalse(reviewed['assessment']['whole_answer_correctness_verified'])

    def test_binary_without_projection_retains_explicit_unsupported_delivery(self):
        self.binary_case(linked=False); self.start()
        packet = self.packet(calculation=False, filings=False)
        answer = (b'The binary filing is retained, but no linked readable extraction was available. '
                  b'Its contents and issuer outlook remain unresolved; reviewing provenance metadata alone '
                  b'does not establish the original binary content.\n')
        _, _, final = self.review(packet, answer, {'filing': 'UNSUPPORTED', 'session-whole-answer': 'UNSUPPORTED'})
        self.assertEqual(final['disposition']['final_status'], 'DELIVERED_WITH_LIMITATIONS')
        self.assertEqual((self.run / 'sources/original.bin').read_bytes(), self.pdf)
        notice = (self.run / 'review' / final['delivery_notice']['path']).read_text()
        self.assertIn('Binary evidence without linked readable projections', notice)

    def test_unprojected_binary_cannot_get_satisfied_metadata_only_review(self):
        self.binary_case(linked=False); self.start()
        packet = self.packet(calculation=False, filings=False)
        with self.assertRaisesRegex(ValueError, 'UNPROJECTED_BINARY_EVIDENCE_REMAINS_UNRESOLVED'):
            self.review(packet, b'Original binary content has not been reviewed.\n')

    def test_direct_revision_record_cannot_bypass_session_binary_final_policy(self):
        self.binary_case(linked=False); self.start()
        packet = self.packet(calculation=False, filings=False)
        with self.assertRaisesRegex(ValueError, 'UNPROJECTED_BINARY_EVIDENCE_REMAINS_UNRESOLVED'):
            self.review(packet, b'Original binary content has not been reviewed.\n', direct_revision_record=True)

    def test_binary_projection_must_be_explicit_retained_utf8_text(self):
        self.binary_case(readable=b'\xff\xfe not UTF8')
        with self.assertRaisesRegex(ValueError, 'UTF8_READABLE_PROJECTION_REQUIRED'):
            self.start()
        self.assertEqual((self.run / 'sources/original.bin').read_bytes(), self.pdf)

    def test_dense_shared_ancestry_lineage_visits_are_linear_in_vertices_and_edges(self):
        self.request = b'Inspect the supplied sources.\n'
        self.tasks = [{'id': 'sources', 'requirement': 'Inspect the supplied source lineage.',
                       'request_excerpt': 'supplied sources', 'required_source_ids': ['s16']}]
        self.sources = []
        for index in range(17):
            path = self.root / f'dag-{index}.txt'; path.write_text(f'Fictional source {index}.', encoding='utf8')
            self.sources.append({'id': f's{index}', 'path': str(path), 'role': 'Explicit lineage test',
                                 'origin': 'supplied' if index == 0 else 'host_derived',
                                 'derived_from': [f's{prior}' for prior in range(index)]})
        visits = []
        previous = sys.getprofile()
        def count_calls(frame, event, arg):
            if event == 'call' and frame.f_code.co_name == 'lineage' and frame.f_code.co_filename == module.__file__:
                visits.append(frame.f_locals['sid'])
        try:
            sys.setprofile(count_calls)
            self.start()
        finally:
            sys.setprofile(previous)
        self.assertLessEqual(len(visits), 17 + 136)

    def test_additional_review_evidence_is_retained_and_required_by_whole_answer(self):
        self.start()
        packet = self.packet(calculation=False)
        raw = b'Previous guidance was withdrawn; this is a change from the retained prior answer.'
        result = module.start_review(self.run, expected_session_sha256=self.pin,
                                     expected_packet_sha256=packet['packet_sha256'], adopted_at=T0,
                                     additional_review_sources={'extra-refresh-delta': raw})
        protocol = module.load(self.run / 'review/protocol.json')
        whole = next(u for u in protocol['units'] if u['id'] == 'session-whole-answer')
        self.assertIn('extra-refresh-delta', whole['required_source_ids'])
        self.assertEqual((self.run / 'review/sources/extra-refresh-delta.bin').read_bytes(), raw)
        import research_revision
        research_revision.verify(self.run / 'review', result['head_sha256'])
        (self.run / 'review/sources/extra-refresh-delta.bin').write_bytes(b'Changed evidence')
        with self.assertRaises(ValueError):
            research_revision.verify(self.run / 'review', result['head_sha256'])

    def test_additional_review_evidence_rejects_reserved_ids_and_binary_content(self):
        self.start()
        packet = self.packet(calculation=False)
        for extras in ({'session-packet': b'override'}, {'extra-binary': b'%PDF-1.7 binary'},
                       {'extra-invalid': b'\xff'}, {'extra-empty': b''}):
            with self.subTest(extras=list(extras)), self.assertRaises(ValueError):
                module.start_review(self.run, expected_session_sha256=self.pin,
                                    expected_packet_sha256=packet['packet_sha256'], adopted_at=T0,
                                    additional_review_sources=extras)
            self.assertFalse((self.run / 'review').exists())

    def test_safe_members_and_unsupported_workflow(self):
        for name in ('../outside.txt', '/absolute', 'C:/private', 'sources\\release.bin', './session.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'SAFE_SESSION_MEMBER_REQUIRED'):
                module.member(self.root, name)
        with self.assertRaisesRegex(ValueError, 'SUPPORTED_WORKFLOW_REQUIRED'):
            self.start(workflow='all-natural-language')
        self.assertFalse(self.run.exists())


if __name__ == '__main__':
    unittest.main()
