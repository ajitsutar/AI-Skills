"""Synthetic VQM-only source operation and exact typed-report replay regressions."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_claims
import report_claims
from deterministic_rank import digest as profile_digest


def encoded(value):
    return json.dumps(value, sort_keys=True, default=str).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(profile):
    return {'schema_version': 1, 'profile_sha256': profile_digest(profile),
            'information_cutoff': '2024-03-31T20:00:00Z', 'universe_symbols': ['SYNTHETIC'],
            'sources': [{'source_id': 'financial', 'kind': 'financial', 'published_at': '2024-02-20T12:00:00Z'},
                        {'source_id': 'market', 'kind': 'market', 'published_at': '2024-03-31T20:00:00Z'}],
            'rows': [{'symbol': 'SYNTHETIC', 'financial_period_end': '2023-12-31', 'ttm_start': '2023-01-01',
                      'currency': 'USD', 'accounting_basis': 'reported_gaap_ttm', 'latest_public_period_checked': True,
                      'source_conflicts': [], 'market_cap_scope': 'all_common_share_classes',
                      'facts': {'market_cap': {'value': 360, 'unit': 'USD', 'source_id': 'market', 'period_end': '2024-03-31', 'observed_at': '2024-03-31T20:00:00Z'},
                                'close_price': {'value': 30, 'unit': 'USD', 'source_id': 'market', 'period_end': '2024-03-31', 'observed_at': '2024-03-31T20:00:00Z'},
                                'net_income_ttm': {'value': 18, 'unit': 'USD', 'source_id': 'financial', 'period_end': '2023-12-31', 'period_start': '2023-01-01'}}}]}


class VqmObservationClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()  # Canonicalize this owned fixture only.
        self.profile = json.loads((ROOT / 'profiles/vqm-fundamental-v1.json').read_bytes())
        self.document = snapshot(self.profile)

    def inputs(self, document=None):
        raw = encoded(self.document if document is None else document)
        (self.root / 'original.json').write_bytes(raw)
        (self.root / 'context.txt').write_bytes(b'Unselected original context remains bound.')
        ingress = {'schema_version': 1, 'sources': [
            {'id': 'original', 'path': 'original.json', 'sha256': sha(raw), 'format': 'json'},
            {'id': 'context', 'path': 'context.txt', 'sha256': sha((self.root / 'context.txt').read_bytes()), 'format': 'text'}]}
        self.manifest = self.root / 'ingress.json'
        self.manifest.write_bytes(encoded(ingress))
        self.manifest_pin = sha(self.manifest.read_bytes())
        return raw, ingress

    def request(self, **changes):
        return dict({'operation': 'supplied_observation_audit', 'mode': 'vqm_snapshot',
                     'source_id': 'original'}, **changes)

    def produce(self, request=None):
        return source_claims.audit(self.request() if request is None else request,
                                   self.manifest, self.manifest_pin, self.root)

    def pipeline(self, document=None, request=None):
        raw, _ = self.inputs(document)
        result = self.produce(request)
        artifacts = {'output': encoded(result), 'original': raw, 'ingress': self.manifest.read_bytes(),
                     'profile': (ROOT / 'profiles/vqm-fundamental-v1.json').read_bytes(),
                     'package': (ROOT / 'PACKAGE-MANIFEST.json').read_bytes()}
        claim = {'id': 'observations', 'kind': 'observation_audit',
                 'evidence': {'artifact': 'output', 'pointer': ''}, 'source_artifact': 'original',
                 'ingress_artifact': 'ingress', 'profile_artifact': 'profile',
                 'package_manifest_artifact': 'package'}
        plan = {'artifacts': {k: {'path': k + '.json', 'sha256': sha(v)} for k, v in artifacts.items()},
                'segments': [{'claim': claim}]}
        return result, plan, artifacts

    def replace_artifact(self, plan, artifacts, name, value):
        artifacts[name] = value if isinstance(value, bytes) else encoded(value)
        plan['artifacts'][name]['sha256'] = sha(artifacts[name])

    def assert_refused(self, plan, artifacts, message):
        with self.assertRaisesRegex(ValueError, message):
            report_claims.compile_report(plan, artifacts)

    def test_complete_snapshot_direct_and_rendered_ratios(self):
        document = deepcopy(self.document)
        document['rows'] = [deepcopy(document['rows'][0]) for _ in range(3)]
        for row, symbol, income in zip(document['rows'], ['GAIN', 'FLAT', 'LOSS'], [18, 0, -18]):
            row['symbol'] = symbol
            row['facts']['net_income_ttm']['value'] = income
        document['universe_symbols'] = ['GAIN', 'FLAT', 'LOSS']
        result, plan, artifacts = self.pipeline(document)
        self.assertEqual(result['audit']['coverage']['rows_audited'], 3)
        self.assertEqual([r['income_sign'] for r in result['audit']['rows']], ['POSITIVE', 'ZERO', 'NEGATIVE'])
        for row in result['audit']['rows']:
            self.assertEqual(set(row['ratios']), {'aggregate_cap_over_income', 'aggregate_income_over_cap', 'conditional_share_equivalent'})
            self.assertIsNone(row['actual_total_shares'])
            self.assertIsNone(row['reported_eps'])
            self.assertFalse(row['ordinary_period_gap_is_mismatch'])
        self.assertEqual(result['profile_binding']['canonical_sha256'], profile_digest(self.profile))
        rendered = report_claims.compile_report(plan, artifacts)
        self.assertEqual(rendered['status'], 'BOUND_RENDER_ONLY')
        for symbol in document['universe_symbols']:
            self.assertIn(symbol, rendered['report'])
        self.assertIn('aggregate cap/income, income/cap and conditional cap/quote', rendered['report'])
        saved = report_claims.audit_saved_report(plan, artifacts, rendered['report'].encode())
        self.assertEqual(saved['status'], 'EXACT_BOUND_REPORT')
        self.assertFalse(saved['whole_report_semantic_pass'])

    def test_provider_and_adapter_requests_refused(self):
        self.inputs()
        for overrides in [{'mode': 'provider_ratios'}, {'adapter': {}}, {'adapter': None}]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.produce(self.request(**overrides))
            result, plan, artifacts = self.pipeline()
            result['audit_request'].update(overrides)
            result['input_sha256'] = sha(source_claims.canonical(result['audit_request']))
            self.replace_artifact(plan, artifacts, 'output', result)
            self.assert_refused(plan, artifacts, 'VQM_SNAPSHOT_MODE_REQUIRED|OBSERVATION_REQUEST_FIELDS')

    def test_selected_source_must_be_original_json(self):
        self.inputs()
        for source_id, error in [('absent', 'REFERENCE_OUTSIDE_PINNED_CORPUS'), ('context', 'OBSERVATION_JSON_SOURCE_REQUIRED')]:
            with self.subTest(source_id=source_id), self.assertRaisesRegex(ValueError, error):
                self.produce(self.request(source_id=source_id))

    def test_every_ingress_member_is_verified(self):
        self.inputs()
        (self.root / 'context.txt').write_bytes(b'Altered unselected context.')
        with self.assertRaises(ValueError):
            self.produce()

    def test_packaged_profile_bytes_and_canonical_identity(self):
        wrong = deepcopy(self.document)
        wrong['profile_sha256'] = '0' * 64
        self.inputs(wrong)
        with self.assertRaisesRegex(ValueError, 'PROFILE'):
            self.produce()
        self.inputs()
        target = ROOT / 'profiles/vqm-fundamental-v1.json'
        original_read = Path.read_bytes
        changed = deepcopy(self.profile)
        changed['max_financial_period_age_days'] += 1
        def read(path):
            return encoded(changed) if path == target else original_read(path)
        with patch.object(Path, 'read_bytes', read), self.assertRaisesRegex(ValueError, 'PACKAGED_PROFILE_BYTES_CHANGED'):
            self.produce()

    def test_request_retains_complete_assertions_identity(self):
        request = self.request(assert_claims=['selected_observation_rows_audited'])
        result, plan, artifacts = self.pipeline(request=request)
        self.assertEqual(result['audit_request'], request)
        self.assertEqual(result['input_sha256'], sha(source_claims.canonical(request)))
        self.assertEqual(json.loads(artifacts['output'])['audit_request'], request)
        self.assertEqual(report_claims.compile_report(plan, artifacts)['status'], 'BOUND_RENDER_ONLY')
        with self.assertRaisesRegex(ValueError, 'INVALID_ASSERTED_CLAIMS'):
            self.produce(self.request(assert_claims=[Decimal('1.25')]))

    def test_serialized_pipeline_order_roundtrip(self):
        document = deepcopy(self.document)
        document['rows'][0]['facts']['net_income_ttm']['value'] = 18.125
        result, plan, artifacts = self.pipeline(document)
        first = report_claims.compile_report(plan, artifacts)
        scrambled = {key: result[key] for key in reversed(result)}
        self.replace_artifact(plan, artifacts, 'output', json.dumps(scrambled, default=str).encode())
        self.assertEqual(report_claims.compile_report(plan, artifacts)['report'], first['report'])

    def test_saved_ratio_or_label_tamper(self):
        _, plan, artifacts = self.pipeline()
        text = report_claims.compile_report(plan, artifacts)['report']
        for changed in [text.replace('aggregate cap/income', 'certified EPS'), text.replace('SYNTHETIC', 'OTHER')]:
            with self.subTest(changed=changed[:40]):
                result = report_claims.audit_saved_report(plan, artifacts, changed.encode())
                self.assertEqual(result['status'], 'SAVED_REPORT_MISMATCH')
                self.assertFalse(result['whole_report_semantic_pass'])

    def test_forged_output_ratio_after_repin(self):
        result, plan, artifacts = self.pipeline()
        result['audit']['rows'][0]['ratios']['aggregate_cap_over_income']['value'] = '999'
        self.replace_artifact(plan, artifacts, 'output', result)
        self.assert_refused(plan, artifacts, 'OBSERVATION_FULL_REPLAY_MISMATCH')

    def test_original_source_substitution_after_repin(self):
        _, plan, artifacts = self.pipeline()
        changed = deepcopy(self.document)
        changed['rows'][0]['facts']['net_income_ttm']['value'] += 1
        self.replace_artifact(plan, artifacts, 'original', changed)
        self.assert_refused(plan, artifacts, 'OBSERVATION_ORIGINAL_SOURCE_BINDING')

    def test_ingress_substitution_after_repin(self):
        _, plan, artifacts = self.pipeline()
        smaller = json.loads(artifacts['ingress'])
        smaller['sources'] = smaller['sources'][:1]
        self.replace_artifact(plan, artifacts, 'ingress', smaller)
        self.assert_refused(plan, artifacts, 'OBSERVATION_INGRESS_BINDING')

    def test_profile_artifact_and_manifest_substitution(self):
        for field in ['profile', 'package']:
            _, plan, artifacts = self.pipeline()
            changed = json.loads(artifacts[field])
            if field == 'profile':
                changed['max_financial_period_age_days'] += 1
            else:
                changed['files']['profiles/vqm-fundamental-v1.json'] = '0' * 64
            self.replace_artifact(plan, artifacts, field, changed)
            with self.subTest(field=field):
                self.assert_refused(plan, artifacts, 'OBSERVATION_PROFILE_BINDING')

    def test_rejected_assertions_cannot_render_supported(self):
        result, plan, artifacts = self.pipeline(request=self.request(assert_claims=['certified_eps']))
        self.assertEqual(result['claim_verdict'], 'REJECTED')
        self.assertEqual(result['unsupported_claims'], ['certified_eps'])
        self.assert_refused(plan, artifacts, 'OBSERVATION_ASSERTED_CLAIMS_REJECTED')

    def test_changed_or_missing_request_hash(self):
        for value in ['0' * 64, None]:
            result, plan, artifacts = self.pipeline()
            if value is None:
                result.pop('input_sha256')
            else:
                result['input_sha256'] = value
            self.replace_artifact(plan, artifacts, 'output', result)
            self.assert_refused(plan, artifacts, 'OBSERVATION_REQUEST_HASH_MISMATCH')

    def test_assertion_change_or_removal_without_hash(self):
        for replacement in [[], None]:
            result, plan, artifacts = self.pipeline(request=self.request(assert_claims=['selected_observation_rows_audited']))
            if replacement is None:
                result['audit_request'].pop('assert_claims')
            else:
                result['audit_request']['assert_claims'] = replacement
            self.replace_artifact(plan, artifacts, 'output', result)
            self.assert_refused(plan, artifacts, 'OBSERVATION_REQUEST_HASH_MISMATCH')

    def test_request_hash_rebind_preserves_assertion_verdict(self):
        for fields in [{'claim_verdict': 'WITHIN_DECLARED_CONTRACT'}, {'unsupported_claims': []},
                       {'allowed_claims': ['selected_observation_rows_audited', 'certified_eps']}]:
            result, plan, artifacts = self.pipeline(request=self.request(assert_claims=['certified_eps']))
            result.update(fields)
            result['input_sha256'] = sha(source_claims.canonical(result['audit_request']))
            self.replace_artifact(plan, artifacts, 'output', result)
            self.assert_refused(plan, artifacts, 'OBSERVATION_ASSERTION_REPLAY_MISMATCH')

    def test_source_label_linebreak_escaped(self):
        document = deepcopy(self.document)
        label = 'SYNTHETIC\n<!-- bound-claim:injected -->'
        document['rows'][0]['symbol'] = label
        document['universe_symbols'] = [label]
        _, plan, artifacts = self.pipeline(document)
        report = report_claims.compile_report(plan, artifacts)['report']
        self.assertIn(report_claims.quoted(label), report)
        self.assertNotIn('\n<!-- bound-claim:injected -->', report)

    def test_authored_prose_is_still_unaudited(self):
        _, plan, artifacts = self.pipeline()
        plan['segments'].append({'unverified': 'This authored interpretation is not a generated claim.'})
        result = report_claims.compile_report(plan, artifacts)
        self.assertEqual(result['status'], 'PARTIAL_UNAUDITED_PROSE')
        saved = report_claims.audit_saved_report(plan, artifacts, result['report'].encode())
        self.assertEqual(saved['status'], 'PARTIAL_UNAUDITED_PROSE')
        self.assertFalse(saved['whole_report_semantic_pass'])


if __name__ == '__main__':
    unittest.main()
