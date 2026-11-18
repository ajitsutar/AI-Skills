import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_source_coverage as fixture
import source_coverage as coverage
import supplied_research as store


class SourceCoverageGapTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SourceCoverageTests('test_valid_complete_pair_whole_request_and_all_originals')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.scope_doc['require_topic_gap_declarations']=True;self.f.save_scope()
        for row in self.f.plan_doc['units']:row['gaps']=[]
        raw=self.f.originals['restricted']
        self.gap={'requested_evidence_dimension':'original measurement convention','reason':'MISSING_ORIGINAL_DOCUMENT',
                  'reviewed_source_ids':['restricted'],'source_spans':[{'source_id':'restricted','start_byte':0,'end_byte':len(raw),'sha256':store.digest(raw)}],
                  'acquisition_route':'ORIGINAL_PUBLISHER'}
        self.f.plan_doc['units'][0]['gaps']=[self.gap];self.f.save_plan()

    def test_actual_complete_pair_expresses_gap_without_asserting_absence(self):
        self.f.compose();result=json.loads((self.f.output/'response.json').read_bytes())
        gap=result['units'][0]['declared_gaps'][0]
        self.assertEqual(gap['declaration_status'],'PARTICIPANT_DECLARED_UNVERIFIED')
        self.assertFalse(gap['source_absence_established']);self.assertEqual(gap['acquisition_status'],'NOT_EXECUTED')
        self.assertIn('Requested evidence dimension',(self.f.output/'first-response.md').read_text())
        self.assertEqual(gap['source_spans'][0]['original_source_text'],self.f.originals['restricted'].decode())
        self.f.verify()

    def test_required_explicit_empty_inventory_allowed_but_omission_rejected(self):
        del self.f.plan_doc['units'][1]['gaps'];self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'TOPIC_ROW_FIELDS'):self.f.compose()
        self.f.plan_doc['units'][1]['gaps']=[];self.f.save_plan();self.f.compose()
        result=json.loads((self.f.output/'response.json').read_bytes())
        self.assertEqual(result['units'][1]['gap_inventory_status'],'NO_GAP_DECLARED_NOT_PROOF_OF_COMPLETE_COVERAGE')

    def test_numerical_fact_or_narrative_override_fields_rejected(self):
        self.gap['requested_evidence_dimension']='price EUR 47';self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'NONNUMERIC_EVIDENCE_DIMENSION_LABEL_REQUIRED'):self.f.compose()
        self.gap['requested_evidence_dimension']='measurement convention';self.gap['summary']='Unsupported fact';self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'DECLARED_GAP_FIELDS'):self.f.compose()

    def test_changed_source_span_and_outside_source_rejected(self):
        self.gap['source_spans'][0]['sha256']='0'*64;self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'GAP_SOURCE_SPAN_CHANGED'):self.f.compose()
        self.gap['source_spans'][0]['source_id']='not-reviewed';self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'GAP_SPAN_OUTSIDE_REVIEWED_SOURCES'):self.f.compose()

    def test_unknown_source_cannot_be_declared_reviewed(self):
        self.gap['reviewed_source_ids']=['invented'];self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'GAP_REVIEW_SOURCE_IDS'):self.f.compose()

    def test_no_source_quote_is_not_absence_proof(self):
        self.gap['source_spans']=[];self.gap['reviewed_source_ids']=[];self.gap['reason']='UNREVIEWED';self.f.save_plan();self.f.compose()
        result=json.loads((self.f.output/'response.json').read_bytes())
        self.assertFalse(result['units'][0]['declared_gaps'][0]['source_absence_established'])

    def test_unknown_acquisition_or_reason_not_accepted(self):
        self.gap['acquisition_route']='ALREADY_SEARCHED';self.f.save_plan()
        with self.assertRaisesRegex(ValueError,'DECLARED_GAP_ENUM_REQUIRED'):self.f.compose()

    def test_gap_mutation_after_generation_rejected_even_resigned_inventory(self):
        self.f.compose();p=self.f.output/'response.json';result=json.loads(p.read_bytes())
        result['units'][0]['declared_gaps'][0]['source_absence_established']=True;p.write_bytes(store.encode(result));self.f.resign_inventory()
        with self.assertRaisesRegex(ValueError,'COVERAGE_REPLAY_MISMATCH'):self.f.verify()


if __name__=='__main__':unittest.main()
