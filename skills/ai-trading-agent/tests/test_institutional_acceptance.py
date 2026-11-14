"""Actual offline component composition and adversarial evidence/metric boundaries."""
from copy import deepcopy
from decimal import getcontext, localcontext, ROUND_DOWN, Inexact
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'scripts'))
import institutional_acceptance as module
from test_review_packet import ReviewPacketTests
from test_source_strategy_readiness import fixture as data_fixture
from test_platform_readiness import complete as platform_fixture


class InstitutionalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.packet = ReviewPacketTests('test_complete_packet_seals_exact_arm_bytes_and_replays_idempotently')
        self.packet.setUp()
        self.addCleanup(self.packet.doCleanups)
        self.root = self.packet.root
        self.data = data_fixture()
        request = self.data['study_request']
        request['study_modes'] = ['historical_membership']
        request['decisions'] = request['decisions'][-1:]
        request['requirements'] = [request['requirements'][0]]
        request['requirements'][0]['lookback_sessions'] = 1
        self.scope = {'id': 'fictional-scope', 'description': 'Fictional internal research evidence only.',
            'host_id': 'fictional-host', 'mode': 'research', 'asset_classes': ['stocks'],
            'package_sha256': 'a' * 64, 'runtime_sha256': 'b' * 64,
            'intended_use': 'commercial_internal', 'claimed_benefits': ['automated_quality'],
            'data_contract_sha256': module.digest(request), 'universe_mode': 'historical_membership',
            'data_policy': 'strict_observed', 'source_rights_map': {'identity':'rights-identity',
                'features':'rights-features', 'prices':'rights-prices'},
            'review_protocol_sha256': '0' * 64, 'value_protocol_sha256': '0' * 64}
        protocol = json.loads(self.packet.sources['protocol']['raw'])
        protocol.update({'scope_id': self.scope['id'], 'host_id': self.scope['host_id'],
            'package_sha256': self.scope['package_sha256'], 'runtime_sha256': self.scope['runtime_sha256'],
            'data_contract_sha256': self.scope['data_contract_sha256']})
        self.packet.add('protocol', protocol)
        pin = self.packet.sources['protocol']['sha256']
        self.scope['review_protocol_sha256'] = pin
        self.packet.request['adopted_protocol_sha256'] = pin
        for sid in ('roster', 'criteria'):
            body = json.loads(self.packet.sources[sid]['raw'])
            body['protocol_sha256'] = pin
            self.packet.add(sid, body)
        self.prepared = self.packet.prepare()
        self.packet_reference = {'packets':[{'packet_directory':str(Path(self.prepared['packet_directory']).relative_to(self.root)).replace('\\','/'),
            'packet_sha256':self.prepared['packet_sha256']}]}
        self.common = self.put('common.json', self.prepared['participants']['source_only'])
        before = self.put('baseline.txt', b'Fictional baseline: one material error in two assessed claims.')
        after = self.put('assisted.txt', b'Fictional assisted output: zero material errors in the same two claims.')
        def arm(ref, errors, checks, seconds):
            return {'captured_at':'2026-10-02T15:02:00Z',
                'common_input_sha256':self.prepared['common_input_sha256'], 'output':ref,
                'reviewed_unit_ids':['claim-one','claim-two'], 'material_errors':errors,
                'decision_checks':checks, 'work_seconds':str(seconds), 'review_seconds':'10',
                'correction_seconds':'0', 'cost_usd':None}
        self.value = {'schema_version':1, 'protocol':{'id':'fixed-value-study',
            'scope_sha256':module.digest(module.value_scope_identity(self.scope)),
            'review_protocol_sha256':pin, 'registered_at':'2026-10-01T12:00:00Z',
            'measurement_kind':'automated_proxy', 'expected_case_ids':['synthetic-case'],
            'evaluation_units':{'synthetic-case':['claim-one','claim-two']},
            'criterion':{'metric':'material_errors','direction':'lower','minimum_improvement':'1'}},
            'observations':[{'id':'synthetic-case','reviewer':'fictional-reviewer',
                'review_packet_sha256':self.prepared['packet_sha256'], 'common_inputs':self.common,
                'packet_frozen_at':'2026-10-02T15:01:00Z',
                'baseline':arm(before,1,1,30), 'assisted':arm(after,0,2,10)}]}
        self.repin_value()
        self.as_of = '2028-02-09T12:00:00Z'
        self.platform = platform_fixture('stocks', 'research')
        self.platform['as_of'] = self.as_of
        self.platform['requests'][0]['scope_description'] = self.scope['description']
        for record in self.platform['evidence']:
            receipt = record['receipt']
            receipt['scope_sha256'] = module.digest(self.platform['requests'][0])
            receipt['observed_at'] = '2028-02-08T12:00:00Z'
            receipt['valid_until'] = '2028-02-10T12:00:00Z'
            record['receipt_sha256'] = module.digest(receipt)
        self.rights = {'schema_version':1,'as_of':self.as_of,'intended_use':'commercial_internal','sources':[]}
        for sid in ('identity','features','prices'):
            self.rights['sources'].append({'id':'rights-'+sid,'provider':'fictional-'+sid,
                'artifact_kind':'market_data','source_url':'urn:fictional:'+sid,
                'terms_url':'https://example.invalid/fictional-terms','terms_sha256':'c'*64,
                'terms_observed_at':'2028-02-08T12:00:00Z','valid_until':'2028-02-10T12:00:00Z',
                'permitted_uses':['commercial_internal'],'review_status':'permitted',
                'reviewer':'fictional-rights-reviewer','attribution':'Fictional test only',
                'retention_days':1,'evidence_ref':'fictional rights record'})
        self.values = {'platform':self.platform,'data':self.data,'rights':self.rights,
            'review_packet':self.packet_reference,'governance':self.controls(module.GOVERNANCE_CHECKS),
            'operations':self.controls(module.OPERATING_CHECKS),'value':self.value}
        self.doc = self.build()

    def put(self, name, value):
        raw = value if isinstance(value, bytes) else (json.dumps(value,indent=2)+'\n').encode()
        path = self.root / name; path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return {'path':name,'sha256':hashlib.sha256(raw).hexdigest()}

    def repin_value(self):
        self.value['protocol']['scope_sha256'] = module.digest(module.value_scope_identity(self.scope))
        self.scope['value_protocol_sha256'] = module.digest(self.value['protocol'])

    def controls(self, checks):
        log = self.put('control-log.txt',b'Fictional offline drill evidence, not a firm deployment.')
        return {'schema_version':1,'scope_sha256':module.digest(self.scope),
            'package_sha256':self.scope['package_sha256'],'runtime_sha256':self.scope['runtime_sha256'],
            'observed_at':'2028-02-08T12:00:00Z','valid_until':'2028-02-10T12:00:00Z',
            'owner':'fictional-operations-owner',
            'checks':[{'id':name,'outcome':'pass','reviewer':'fictional-reviewer','evidence':[log]} for name in checks]}

    def build(self):
        return {'schema_version':1,'as_of':self.as_of,'scope':deepcopy(self.scope),
            'components':[{'kind':kind,'artifact':self.put(kind+'.json',value)} for kind,value in self.values.items()]}

    def assess(self):
        return module.assess(self.doc,self.root)

    def result(self, kind, out=None):
        return next(row for row in (out or self.assess())['components'] if row['kind']==kind)

    def value_result(self):
        return module.value_comparison(self.value,self.scope,module.clock(self.as_of),self.root,self.packet_reference)

    def test_complete_fixture_replays_real_components_but_never_certifies_enterprise(self):
        result = self.assess()
        self.assertTrue(result['catalog_evidence_complete'],result)
        self.assertFalse(result['production_readiness_certified'])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['profitability_established'])
        value = self.result('value',result)['result']
        self.assertEqual(value['mean_declared_improvement'],'1')
        self.assertTrue(value['declared_criterion_met'])
        self.assertFalse(value['human_activity_authenticated'])

    def test_missing_components_are_gaps_not_a_vacuous_pass(self):
        self.doc['components']=[]
        result=self.assess();self.assertFalse(result['catalog_evidence_complete'])
        self.assertEqual(len(result['missing_components']),7)

    def test_wrong_host_and_failed_drill_stay_failed(self):
        self.platform['host']['id']='another-host'
        self.values['operations']['checks'][0]['outcome']='not_run';self.doc=self.build()
        out=self.assess();self.assertIn('MISMATCH',self.result('platform',out)['error'])
        self.assertFalse(self.result('operations',out)['result']['complete'])
        self.assertEqual(self.result('data',out)['status'],'RETAINED_SCOPE_EVIDENCE_COMPLETE')

    def test_future_data_cannot_qualify_an_earlier_cutoff(self):
        self.doc['as_of']='2027-01-01T00:00:00Z'
        self.assertIn('FUTURE_DATA_STUDY_CUTOFF',self.result('data')['error'])

    def test_unrelated_rights_cannot_qualify_used_data(self):
        self.rights['sources'][0]['source_url']='urn:fictional:unrelated'
        self.doc=self.build();out=self.assess()
        self.assertEqual(self.result('rights',out)['status'],'RETAINED_SCOPE_EVIDENCE_COMPLETE')
        self.assertIn('IDENTITY_MISMATCH',self.result('data_rights_binding',out)['error'])
        self.assertFalse(out['catalog_evidence_complete'])

    def test_scope_and_artifact_mutations_are_detected(self):
        (self.root/'governance.json').write_bytes(b'{}')
        self.assertIn('HASH_MISMATCH',self.result('governance')['error'])
        self.doc=self.build();self.values['governance']['scope_sha256']='0'*64;self.doc=self.build()
        self.assertIn('DIFFERENT_SCOPE',self.result('governance')['error'])

    def test_future_verified_packet_cannot_qualify(self):
        self.doc['as_of']='2026-09-01T00:00:00Z'
        self.assertIn('FUTURE_REVIEW_PACKET',self.result('review_packet')['error'])

    def test_unpinned_protocol_roster_or_criterion_changes_are_refused(self):
        for key,value in [('expected_case_ids',['another-case']),('criterion',{'metric':'material_errors','direction':'lower','minimum_improvement':'0'})]:
            original=deepcopy(self.value['protocol']);self.value['protocol'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'VALUE_PROTOCOL_PIN_MISMATCH'):
                self.value_result()
            self.value['protocol']=original

    def test_rehashed_value_plan_still_must_match_review_roster(self):
        self.value['protocol']['expected_case_ids']=['another-case'];self.repin_value()
        with self.assertRaisesRegex(ValueError,'VALUE_REVIEW_ROSTER_MISMATCH'):self.value_result()

    def test_unequal_review_coverage_never_becomes_error_improvement(self):
        arm=self.value['observations'][0]['assisted'];arm['reviewed_unit_ids']=['claim-one'];arm['decision_checks']=1
        out=self.value_result();self.assertFalse(out['complete']);self.assertIsNone(out['declared_criterion_met'])
        self.assertEqual(out['cases'][0]['comparison_status'],'INCOMPARABLE_REVIEW_COVERAGE')
        self.assertEqual(out['cases'][0]['reviewed_units'],{'baseline':2,'assisted':1})

    def test_error_or_check_counts_cannot_exceed_fixed_denominator(self):
        self.value['observations'][0]['baseline']['material_errors']=3
        with self.assertRaisesRegex(ValueError,'REVIEW_COUNTS_EXCEED_DENOMINATOR'):self.value_result()

    def test_inverted_benefit_direction_is_rejected(self):
        self.value['protocol']['criterion']['direction']='higher';self.repin_value()
        with self.assertRaisesRegex(ValueError,'BENEFIT_METRIC_DIRECTION'):self.value_result()

    def test_human_productivity_requires_human_time_or_cost_metric(self):
        self.scope['claimed_benefits']=['human_productivity'];self.value['protocol']['measurement_kind']='human_reported';self.repin_value()
        result=self.value_result();self.assertFalse(result['complete']);self.assertIsNone(result['declared_criterion_met'])
        self.value['protocol']['criterion'].update(metric='total_seconds',minimum_improvement='1');self.repin_value()
        result=self.value_result();self.assertTrue(result['complete']);self.assertEqual(result['mean_declared_improvement'],'20')
        self.assertFalse(result['causal_time_saving_established'])

    def test_unmeasured_review_phase_is_not_zero(self):
        self.scope['claimed_benefits']=['human_productivity'];self.value['protocol']['measurement_kind']='human_reported'
        self.value['protocol']['criterion'].update(metric='total_seconds',minimum_improvement='1');self.repin_value()
        self.value['observations'][0]['assisted']['review_seconds']=None
        result=self.value_result();self.assertEqual(result['comparable_cases'],0)
        self.assertIsNone(result['cases'][0]['assisted']['total_seconds'])
        self.assertIsNone(result['mean_declared_improvement'])

    def test_missing_and_extra_cases_do_not_change_registered_mean(self):
        extra=deepcopy(self.value['observations'][0]);extra['id']='unexpected';self.value['observations'].append(extra)
        result=self.value_result();self.assertEqual(result['mean_declared_improvement'],'1')
        self.assertEqual(result['unexpected_ids_excluded'],['unexpected'])
        self.value['observations']=[];result=self.value_result()
        self.assertEqual(result['missing_ids'],['synthetic-case']);self.assertIsNone(result['declared_criterion_met'])

    def test_future_or_different_common_input_capture_refused(self):
        arm=self.value['observations'][0]['assisted'];arm['captured_at']='2029-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'VALUE_CAPTURE_OUTSIDE_PROTOCOL'):self.value_result()
        arm['captured_at']='2026-10-02T15:02:00Z';arm['common_input_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'VALUE_ARM_INPUT_MISMATCH'):self.value_result()

    def test_same_numeric_result_across_host_contexts_and_flags(self):
        self.scope['claimed_benefits']=['human_productivity'];self.value['protocol']['measurement_kind']='human_reported'
        self.value['protocol']['criterion'].update(metric='total_seconds',minimum_improvement='0.01');self.repin_value()
        observation=self.value['observations'][0]
        for name,amount in [('baseline','1000000.01'),('assisted','1000000')]:
            observation[name].update(work_seconds=amount,review_seconds='0',correction_seconds='0')
        with localcontext() as context:
            context.prec=6;context.rounding=ROUND_DOWN;context.traps[Inexact]=True
            before=context.copy();out=self.value_result()
            self.assertEqual(out['mean_declared_improvement'],'0.01')
            self.assertEqual(context.prec,before.prec);self.assertEqual(context.flags,before.flags)

    def test_missing_and_negative_evidence_do_not_establish_value(self):
        self.value['observations'][0]['assisted']['material_errors']=2
        result=self.value_result();self.assertTrue(result['complete']);self.assertFalse(result['declared_criterion_met'])
        self.assertEqual(result['mean_declared_improvement'],'-1')

    def test_tampered_packet_and_unrelated_protocol_fail(self):
        self.scope['review_protocol_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'REVIEW_PROTOCOL_BINDING_MISMATCH'):
            module._packets(self.packet_reference,self.scope,module.clock(self.as_of),self.root)

    def test_deep_json_is_isolated_as_failed_component(self):
        raw=('['*1100+'0'+']'*1100).encode();ref=self.put('deep.json',raw)
        next(r for r in self.doc['components'] if r['kind']=='governance')['artifact']=ref
        result=self.assess();self.assertIn('NESTING_LIMIT',self.result('governance',result)['error'])
        self.assertEqual(self.result('operations',result)['status'],'RETAINED_SCOPE_EVIDENCE_COMPLETE')

    def test_named_private_paths_include_selected_root_and_ancestors(self):
        secret=self.root/'private-runtime';secret.mkdir();ref=self.put('private-runtime/note.bin',b'Not an actual credential.')
        with self.assertRaisesRegex(ValueError,'PRIVATE_CONTACT_CONFIGURATION_EXCLUDED'):module.artifact(self.root,ref,False)
        with self.assertRaisesRegex(ValueError,'PRIVATE_CONTACT_CONFIGURATION_EXCLUDED'):
            module.artifact(secret,{'path':'note.bin','sha256':ref['sha256']},False)

    def test_duplicate_keys_and_sensitive_configuration_refused(self):
        ref=self.put('duplicate.json',b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'):module.artifact(self.root,ref)
        ref=self.put('configuration.json',{'user_agent':'Fictional forbidden configuration'})
        with self.assertRaisesRegex(ValueError,'CONTACT_OR_CREDENTIAL'):module.artifact(self.root,ref)

    def test_traversal_hash_and_unsupported_numeric_range(self):
        with self.assertRaisesRegex(ValueError,'PATH_ESCAPE'):
            module.artifact(self.root,{'path':'../escape','sha256':'0'*64})
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
            module.artifact(self.root,{'path':'baseline.txt','sha256':'0'*64})
        self.value['observations'][0]['baseline']['work_seconds']='1e100'
        with self.assertRaisesRegex(ValueError,'SUPPORTED_METRIC_PRECISION_OR_RANGE'):self.value_result()

    def test_cli_preserves_inputs_and_records_gaps_without_side_effects(self):
        self.doc['components']=[];ref=self.put('input.json',self.doc);output=self.root/'acceptance.json'
        command=[sys.executable,'-B',str(ROOT/'scripts/institutional_acceptance.py'),str(self.root/ref['path']),
            '--evidence-root',str(self.root),'--output',str(output)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr)
        self.assertEqual(hashlib.sha256((self.root/ref['path']).read_bytes()).hexdigest(),ref['sha256'])
        self.assertEqual(json.loads(output.read_bytes())['status'],'DEPLOYMENT_EVIDENCE_GAPS')
        again=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(again.returncode,0)


if __name__=='__main__':
    unittest.main()
