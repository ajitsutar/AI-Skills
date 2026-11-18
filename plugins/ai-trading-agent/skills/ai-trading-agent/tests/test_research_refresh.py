"""Fictional research updates; no live data, broker, network or model calls."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import research_refresh as module
import research_session as session
import test_research_session as ordinary

CUTOFF = '2030-07-16T18:00:00Z'
CHECKED = '2030-07-16T18:10:00Z'
DRAFTED = '2030-07-16T18:20:00Z'
REVIEWED = '2030-07-16T18:30:00Z'


class ResearchRefreshTests(unittest.TestCase):
    def setUp(self):
        self.base = ordinary.ResearchSessionTests()
        self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.root = self.base.root
        for spec in self.base.sources:
            spec['metadata'] = {'available_at': '2030-07-15T17:00:00Z', 'retrieved_at': ordinary.T0,
                                'source_url': 'https://issuer.example.test/retained-fictional-source'}
        self.base.start(); packet = self.base.packet()
        self.base.review(packet,
                         b'Prior research: revenue USD 110 million, FY2030 adjusted EPS guidance USD 2.00, '
                         b'USD 50 quote and 25x guidance multiple. Supply constraints remain a risk.\n')
        self.parent_head = module.revision.verify(self.base.run / 'review')['head_sha256']
        self.before = module._tree(self.base.run)
        self.run = self.root / 'updated-research'
        self.request = b'Update this research. Explain earnings and guidance, valuation, and main risks.\n'
        self.check = self.root / 'source-index.txt'
        self.check.write_bytes(b'Fictional issuer index checked through July 16: revised EPS outlook and quote; prior release amended.\n')
        self.new_release = self.base.release.replace(b'USD 2.00', b'USD 2.50')
        self.new_quote = self.base.quote.replace(b'"price":50', b'"price":55').replace(b'2030-07-15T17:00:00Z', b'2030-07-16T17:00:00Z')
        value = json.loads(self.base.normalized)
        value['earnings_basis']['document']['as_of'] = CUTOFF
        value['earnings_basis']['document']['quote'] = json.loads(self.new_quote)
        value['earnings_basis']['document']['estimates'][0]['eps'] = 2.5
        value['earnings_basis']['document']['estimates'][0]['available_at'] = '2030-07-16T16:00:00Z'
        self.normalized = session.encode(value)
        self.decisions = []
        for sid, raw in [('release', self.new_release), ('quote', self.new_quote), ('normalized', self.normalized)]:
            old = next(r for r in self.base.sources if r['id'] == sid)
            path = self.root / ('updated-' + sid + '.txt'); path.write_bytes(raw)
            replacement = {**copy.deepcopy(old), 'path': str(path),
                           'metadata': {'available_at': '2030-07-16T17:00:00Z', 'retrieved_at': CHECKED}}
            self.decisions.append({'id': sid, 'status': 'revised',
                'reason': 'Retained fictional revision or rebuilt input through the requested cutoff.',
                'check': self.check_spec(), 'replacement': replacement})

    def check_spec(self):
        return {'path': str(self.check), 'scope': 'Fictional Helio FY2030 release, revisions and quote',
                'checked_at': CHECKED, 'coverage_through': CUTOFF}

    def begin(self, **changes):
        kwargs = {'parent_root': self.base.run, 'expected_parent_session_sha256': self.base.pin,
                  'expected_parent_head_sha256': self.parent_head, 'as_of': CUTOFF, 'checked_at': CHECKED,
                  'decisions': self.decisions, 'additions': [], 'tasks': self.base.tasks}
        kwargs.update(changes)
        self.started = module.begin_refresh(self.run, self.request, **kwargs)
        return self.started

    def prepare(self, dependencies=None, calculation=True):
        job = {'schema_version': 1, 'network_mode': 'offline',
            'contract': {'prompt': self.request.decode(), 'purpose': 'Updated earnings and guidance research',
                         'base_currency': 'USD', 'horizon_id': 'FY2030', 'as_of': CUTOFF},
            'jobs': [{'id': 'guidance-multiple', 'operation': 'analyst.earnings_basis',
                      'inputs_source': {'path': 'normalized.bin', 'sha256': session.sha(self.normalized), 'pointer': '/earnings_basis'}}]}
        supported = {row['id'] for row in self.decisions if row['status'] in ('verified_unchanged', 'revised')}
        dispositions = [{'id': t['id'], 'status': 'supported' if set(t['required_source_ids']) <= supported else 'limited',
                         'reason': 'Host reviewed retained source mapping; preserve unsupported dependencies.',
                         'evidence_ids': [sid for sid in t['required_source_ids'] if sid in supported]} for t in self.base.tasks]
        dependencies = dependencies if dependencies is not None else [
            {'id': 'guidance-multiple', 'status': 'recomputed', 'new_job_id': 'guidance-multiple',
             'reason': 'New cutoff, revised guidance and quote require rerunning the existing earnings-basis producer.'}]
        self.prepared = module.prepare_refresh(self.run, expected_refresh_sha256=self.started['refresh_sha256'],
            dispositions=dispositions, dependencies=dependencies, calculation=job if calculation else None)
        return self.prepared

    def finish(self, *, bypass_refresh_review=False):
        if bypass_refresh_review:
            review = session.start_review(self.run / 'current', expected_session_sha256=self.started['session_sha256'],
                expected_packet_sha256=self.prepared['session_packet_sha256'], adopted_at=CHECKED)
        else:
            review = module.start_review(self.run, expected_refresh_sha256=self.started['refresh_sha256'],
                expected_refresh_packet_sha256=self.prepared['refresh_packet_sha256'], adopted_at=CHECKED)
        self.answer = (b'Updated through July 16: Helio FY2030 adjusted diluted EPS guidance is USD 2.50 '
            b'versus the prior USD 2.00. The retained quote is USD 55 versus USD 50. Recalculation gives '
            b'22x guidance versus 25x previously [release; quote; guidance-multiple]. This reflects both '
            b'a changed price and revised forward-looking guidance, not established fair value. Revenue remains '
            b'USD 110 million versus USD 100 million in the supplied release; supply constraints remain a risk. '
            b'The fictional index-check scope and source timestamps are host declarations. New actual results, '
            b'a guidance withdrawal or changed supply constraints could alter the thesis. No live action is authorized.\n')
        draft = session.freeze_draft(self.run / 'current', self.answer, session.encode({'answer': self.answer.decode()}),
            DRAFTED, expected_session_sha256=self.started['session_sha256'], expected_head_sha256=review['head_sha256'])
        base = self.run / 'current/review'
        protocol = json.loads((base / review['protocol']['path']).read_bytes())
        originals = {r['id']: (base / r['artifact']['path']).read_bytes() for r in protocol['sources']}
        document = {'schema_version': 1, 'protocol': review['protocol'], 'reviewed_at': REVIEWED,
            'reviewer': {'id': 'fictional-native-self-review', 'kind': 'automated'}, 'delivery': draft['delivery'], 'reviews': []}
        for unit in protocol['units']:
            document['reviews'].append({'unit_id': unit['id'], 'status': 'SATISFIED', 'material_error': False, 'issues': [],
                'rationale': 'Fictional exercise: host checked original request, exact old/new answer, source deltas and recalculated 22x.',
                'answer_spans': [{'artifact': 'first_response', 'span': ordinary.span(self.answer)}],
                'source_reviews': [{'source_id': sid, 'status': 'REVIEWED', 'spans': [ordinary.span(originals[sid])]}
                                   for sid in unit['required_source_ids']]})
        if not bypass_refresh_review:
            self.assertIn('extra-refresh-delta', protocol['units'][-1]['required_source_ids'])
        reviewed = session.record_review(self.run / 'current', document, expected_session_sha256=self.started['session_sha256'],
            reviewer_mode='self_native', expected_head_sha256=draft['head_sha256'])
        final = session.select_final(self.run / 'current', draft['draft_id'], expected_session_sha256=self.started['session_sha256'],
            expected_head_sha256=reviewed['head_sha256'])
        self.finished = module.complete_refresh(self.run, expected_refresh_sha256=self.started['refresh_sha256'],
            expected_refresh_packet_sha256=self.prepared['refresh_packet_sha256'], expected_head_sha256=final['head_sha256'])
        return final

    def test_practical_update_reopens_preserves_old_answer_and_recalculates_whole_delivery(self):
        self.begin(); packet = self.prepare(); final = self.finish()
        self.assertTrue(packet['packet']['result_delta'][0]['recomputation_verified'])
        self.assertEqual(packet['packet']['result_delta'][0]['comparison_status'], 'CHANGED')
        self.assertEqual(packet['packet']['result_delta'][0]['affected_by_source_ids'], ['normalized', 'quote', 'release'])
        results = json.loads((self.run / 'current/calculation/run/result.json').read_bytes())
        self.assertEqual(results['jobs'][0]['result']['results'][0]['multiple'], 22)
        self.assertEqual(module._tree(self.base.run), self.before)
        reopened = module.verify_refresh(self.run, self.started['refresh_sha256'],
            expected_packet_sha256=self.prepared['refresh_packet_sha256'],
            expected_completion_sha256=self.finished['completion_sha256'])
        self.assertEqual(reopened['archive_integrity'], 'VERIFIED')
        self.assertFalse(reopened['source_authenticity_verified'])
        self.assertEqual((self.run / 'current/review' / final['delivery']['first_response']['path']).read_bytes(), self.answer)
        self.assertIn(b'25x', (self.run / 'previous-answer.md').read_bytes())

    def test_unchanged_requires_retained_scoped_check_and_preserves_original_retrieval_clock(self):
        self.decisions[0] = {'id': 'release', 'status': 'verified_unchanged', 'reason': 'Index checked; original release still latest.'}
        with self.assertRaisesRegex(ValueError, 'RETAINED_SOURCE_CHECK_REQUIRED'):
            self.begin()
        self.decisions[0]['check'] = self.check_spec(); self.begin()
        doc = session.load(self.run / 'current/session.json')
        release = next(r for r in doc['sources'] if r['id'] == 'release')
        self.assertEqual(release['metadata']['retrieved_at'], ordinary.T0)
        self.assertEqual((self.run / 'current/sources/release.bin').read_bytes(), self.base.release)
        self.assertEqual(self.started['source_delta'][0]['status'], 'verified_unchanged')

    def test_unchecked_and_unavailable_are_archival_only_and_job_stays_unsupported(self):
        self.decisions = [{'id': r['id'], 'status': 'unchecked' if i == 0 else 'unavailable',
                           'reason': 'Source could not be checked in this request.'} for i, r in enumerate(self.base.sources)]
        tasks = copy.deepcopy(self.base.tasks)
        for task in tasks:
            task['required_source_ids'] = []
        self.begin(tasks=tasks)
        current_ids = {r['id'] for r in session.load(self.run / 'current/session.json')['sources']}
        self.assertTrue({'release', 'quote', 'normalized'}.isdisjoint(current_ids))
        packet = self.prepare([{'id': 'guidance-multiple', 'status': 'unsupported',
                               'reason': 'Current compatible guidance and quote unavailable.'}], calculation=False)
        self.assertEqual(packet['packet']['status'], 'REFRESH_WITH_LIMITATIONS')
        self.assertFalse(packet['packet']['result_delta'][0]['recomputation_verified'])

    def test_retracted_dependency_cannot_be_smuggled_into_new_derived_input(self):
        self.decisions[0] = {'id': 'release', 'status': 'retracted', 'reason': 'Issuer withdrew this release.', 'check': self.check_spec()}
        with self.assertRaisesRegex(ValueError, 'UNAVAILABLE_OR_RETRACTED_DEPENDENCY'):
            self.begin()

    def test_cutoff_availability_and_source_check_chronology_are_not_interchangeable(self):
        self.decisions[0]['replacement']['metadata']['available_at'] = '2030-07-17T17:00:00Z'
        with self.assertRaisesRegex(ValueError, 'SOURCE_AVAILABLE_AFTER_REQUESTED_CUTOFF'):
            self.begin()
        self.decisions[0]['replacement']['metadata']['available_at'] = '2030-07-16T17:00:00Z'
        self.decisions[0]['check']['coverage_through'] = ordinary.T0
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHECK_COVERAGE_CHRONOLOGY'):
            self.begin()

    def test_derived_input_cannot_predate_available_originals_or_be_reused_as_unchanged(self):
        self.decisions[-1]['replacement']['metadata']['available_at'] = '2030-07-15T17:00:00Z'
        with self.assertRaisesRegex(ValueError, 'DERIVATION_PRECEDES_SOURCE_AVAILABILITY'):
            self.begin()
        self.decisions[-1] = {'id': 'normalized', 'status': 'verified_unchanged', 'reason': 'Attempted cache reuse.', 'check': self.check_spec()}
        with self.assertRaisesRegex(ValueError, 'DERIVED_INPUTS_REQUIRE_REBUILD'):
            self.begin()

    def test_missing_mutated_or_rewritten_parent_fails_external_pins(self):
        path = self.base.run / 'sources/release.bin'; path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SESSION_INPUT_CHANGED'):
            self.begin()
        path.write_bytes(self.base.release)
        path = self.base.run / 'session.json'; path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_SESSION_PIN_MISMATCH'):
            self.begin()

    def test_parent_archive_and_current_mutations_fail_after_reopen(self):
        self.begin()
        path = self.run / 'parent-archive/sources/release.bin'; original = path.read_bytes(); path.write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'Archived bytes changed'):
            module.verify_refresh(self.run, self.started['refresh_sha256'])
        path.write_bytes(original)
        (self.run / 'current/sources/quote.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'BOUNDED_EXPLICIT_FILE_REQUIRED'):
            module.verify_refresh(self.run, self.started['refresh_sha256'])

    def test_prior_calculation_must_be_accounted_for_and_actually_executed(self):
        self.begin()
        with self.assertRaisesRegex(ValueError, 'EXACT_PREVIOUS_JOB_DISPOSITIONS_REQUIRED'):
            self.prepare(dependencies=[])
        with self.assertRaisesRegex(ValueError, 'RECOMPUTED_JOB_MUST_BE_EXECUTED'):
            self.prepare(calculation=False)

    def test_completed_current_bytes_and_external_completion_pin_are_required(self):
        self.begin(); self.prepare(); self.finish()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_COMPLETION_PIN_REQUIRED'):
            module.verify_refresh(self.run, self.started['refresh_sha256'])
        (self.run / 'current/packet-plan.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'Archived bytes changed'):
            module.verify_refresh(self.run, self.started['refresh_sha256'],
                                  expected_completion_sha256=self.finished['completion_sha256'])

    def test_unrelated_folder_file_is_rejected_before_copy(self):
        (self.base.run / 'unrelated.txt').write_bytes(b'Not selected research evidence.')
        with self.assertRaisesRegex(ValueError, 'UNRECOGNIZED_RESEARCH_ARCHIVE_MEMBER'):
            self.begin()
        self.assertFalse(self.run.exists())

    def test_generic_review_cannot_bypass_pinned_refresh_delta_at_completion(self):
        self.begin(); self.prepare()
        with self.assertRaisesRegex(ValueError, 'PINNED_REFRESH_DELTA_REVIEW_REQUIRED'):
            self.finish(bypass_refresh_review=True)
        self.assertFalse((self.run / 'completion.json').exists())

    def test_next_refresh_preserves_entire_completed_previous_refresh_with_its_pins(self):
        self.begin(); self.prepare(); self.finish()
        before = module._tree(self.run)
        next_cutoff, next_checked = '2030-07-17T18:00:00Z', '2030-07-17T18:10:00Z'
        decisions = []
        for row in self.decisions:
            check = {**self.check_spec(), 'coverage_through': next_cutoff, 'checked_at': next_checked}
            if row['id'] != 'normalized':
                decisions.append({'id': row['id'], 'status': 'verified_unchanged',
                                  'reason': 'Retained check shows no new release or quote through new cutoff.', 'check': check})
            else:
                value = json.loads(self.normalized); value['earnings_basis']['document']['as_of'] = next_cutoff
                path = self.root / 'next-normalized.json'; path.write_bytes(session.encode(value))
                spec = copy.deepcopy(row['replacement']); spec['path'] = str(path)
                spec['metadata']['retrieved_at'] = next_checked
                decisions.append({'id': row['id'], 'status': 'revised', 'reason': 'Rebuilt normalized inputs for new cutoff.',
                                  'check': check, 'replacement': spec})
        second = self.root / 'second-refresh'
        receipt = module.begin_refresh(second, self.request, parent_root=self.run,
            expected_parent_session_sha256=self.started['session_sha256'],
            expected_parent_head_sha256=self.finished['completion']['head_sha256'],
            expected_parent_refresh_sha256=self.started['refresh_sha256'],
            expected_parent_completion_sha256=self.finished['completion_sha256'],
            as_of=next_cutoff, checked_at=next_checked, decisions=decisions, additions=[], tasks=self.base.tasks)
        self.assertEqual(module._tree(self.run), before)
        self.assertTrue((second / 'parent-archive/parent-archive/sources/release.bin').is_file())
        module.verify_refresh(second, receipt['refresh_sha256'])


if __name__ == '__main__':
    unittest.main()
