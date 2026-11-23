import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_contracts as contracts


class StrategyAnswerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name).resolve()
        self.name = 'studies.json'
        self.record = {'family': 'weekly volume', 'variants': ['raw', 'scaled'], 'execution': 'next publication',
                       'label/with~escapes': ['odd`text\n# heading', 7, True]}
        self.source = self.directory / self.name
        self.source.write_text(json.dumps({'strategies': [self.record], 'other': {'budget': 'OUTSIDE_RECORD'}}),
                               encoding='utf-8')
        self.request = {'strategy_source': {'source_id': 'study', 'pointer': '/strategies/0'},
                        'allowlist': [self.name], 'sources': [{'id': 'study', 'path': self.name, 'role': 'specification',
                        'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest()}], 'design_kind': 'research_contract',
                        'design_terms': {'benchmark': {'proposal': 'equal weight sector comparator'},
                                         'evaluation_window': {'proposal': 'predeclared held-out sessions'},
                                         'execution_convention': {'record_pointer': '/execution'},
                                         'development_validation_split': {'proposal': 'lock at end of training'}},
                        'proposed_decision_rules': [self.rule('performance'), self.rule('risk')],
                        'answer_controls': {'initial_state': 'flat, retain prior regime on a tie',
                            'session_basis': 'actual publication calendar', 'warmup': 'consecutive valid releases',
                            'variants': {'mode': 'fixed_primary', 'primary': {'record_pointer': '/variants/0'}},
                            'sample': {'minimum_observations': 40, 'observation_unit': 'paired sessions',
                                       'minimum_events': 5, 'event_unit': 'completed cycles', 'rationale': 'rare signal'},
                            'uncertainty': {'performance_rule': 0, 'confidence': 0.9, 'method': 'paired block bootstrap',
                                            'dependence_treatment': 'nonoverlapping blocks of four sessions'}}}

    def rule(self, purpose):
        return {'purpose': purpose, 'measure': purpose + ' measure', 'units': 'fraction', 'measurement_window': 'untouched sessions',
                'comparison': '>', 'threshold': 0, 'on_failure': 'hold', 'if_unmeasurable': 'inconclusive'}

    def export(self):
        output = self.directory/'bundle'
        contracts.export_run('strategy-answer', json.dumps(self.request).encode(), self.directory, output)
        return output

    def test_cli_text_and_envelope_readback_are_scoped_after_source_loss(self):
        request = self.directory/'request.json'
        request.write_text(json.dumps(self.request), encoding='utf-8')
        output = self.directory/'bundle'
        cli = [sys.executable, '-B', str(ROOT/'scripts/research_contracts.py')]
        subprocess.run(cli + ['strategy-answer', str(request), '--source-root', str(self.directory),
                              '--private-output', str(output)], check=True)
        self.source.unlink()
        answer = self.directory/'response.md'
        answer.write_bytes((output/'answer.md').read_bytes())
        rows = json.loads((output/'answer-rows.json').read_bytes())
        final = self.directory/'final.json'
        final.write_text(json.dumps({'rows': rows, 'host': 'offline'}), encoding='utf-8')
        subprocess.run(cli + ['verify', str(output), '--answer', str(answer), '--rows', str(final)], check=True)
        self.assertEqual(rows[0]['supplied_strategy'], self.record)
        self.assertEqual(rows[0]['primary_specification'], {'basis': 'supplied','record_pointer': '/variants/0','value': 'raw'})
        wording = answer.read_text(encoding='utf-8')
        self.assertNotIn('OUTSIDE_RECORD', wording)
        self.assertIn('label~1with~0escapes', wording)
        self.assertNotIn('\n# heading', wording)
        self.assertIn('lower confidence bound', wording)
        answer.write_bytes(answer.read_bytes() + b'Additional budget claim.')
        with self.assertRaisesRegex(ValueError, 'FINAL_STRATEGY_ANSWER_DIFFERS'):
            contracts.verify(output,answer,final)
        final.write_text(json.dumps({'rows': rows+[{'budget': 3}]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'FINAL_STRATEGY_ROWS_DIFFER'):
            contracts.verify(output,rows=final)

    def test_rehashed_answer_and_typed_rows_do_not_verify(self):
        output = self.export()
        for name, change in [('answer.md', b'modified'), ('answer-rows.json', b'[]')]:
            with self.subTest(name=name):
                p = output/name
                original = p.read_bytes()
                receipt = output/'receipt.json'
                before = receipt.read_bytes()
                doc = json.loads(before)
                p.write_bytes(change)
                doc['files'][name]=hashlib.sha256(change).hexdigest()
                receipt.write_text(json.dumps(doc),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):
                    contracts.verify(output)
                p.write_bytes(original)
                receipt.write_bytes(before)

    def test_structured_delivery_cli_and_actual_destination_readback(self):
        export = self.export()
        self.source.unlink()
        metadata = self.directory / 'metadata.json'
        metadata.write_bytes(b'{"runtime":{"model":"unexposed"},"limitations":["offline"],"value":0.1234567890123456789}')
        target = self.directory / 'delivery'
        cli = [sys.executable, '-B', str(ROOT / 'scripts/research_contracts.py')]
        def execute(*args):
            return subprocess.run(cli + [str(arg) for arg in args], capture_output=True, text=True)
        only = json.loads(execute('verify', export).stdout)
        self.assertEqual(only['checks'], {'retained_export': True})
        self.assertFalse(only['submission_observed'])
        self.assertIn('deliver-strategy', only['next_for_structured_delivery'])
        delivered = execute('deliver-strategy', export, '--metadata', metadata, '--private-output', target)
        self.assertEqual(delivered.returncode, 0, delivered.stderr)
        saved = json.loads(delivered.stdout)
        for name, expected in saved['local_files_sha256'].items():
            self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), expected)
        answer = self.directory / 'submitted.md'
        envelope = self.directory / 'submitted.json'
        answer.write_bytes((target / 'files/first-response.md').read_bytes())
        envelope.write_bytes((target / 'files/response.json').read_bytes())
        self.assertEqual(answer.read_bytes(), (export / 'answer.md').read_bytes())
        data = contracts.binding_json.strict_json(envelope.read_bytes())
        self.assertEqual(data.pop('rows'), contracts.binding_json.strict_json((export / 'answer-rows.json').read_bytes()))
        self.assertEqual(data.pop('first_response_sha256'), hashlib.sha256(answer.read_bytes()).hexdigest())
        self.assertEqual(data, contracts.binding_json.strict_json(metadata.read_bytes()))
        args = ('verify', export, '--answer', answer, '--rows', envelope, '--metadata', metadata)
        check = execute(*args)
        self.assertEqual(check.returncode, 0, check.stderr)
        checks = json.loads(check.stdout)['checks']
        self.assertEqual((checks['markdown'], checks['rows']), ('provided_file', 'provided_file'))
        self.assertEqual(checks['declared_metadata_sha256'], hashlib.sha256(metadata.read_bytes()).hexdigest())
        internal = json.loads(execute('verify', export, '--answer', export / 'answer.md').stdout)
        self.assertEqual(internal['checks']['markdown'], 'export_member')
        self.assertNotIn('rows', internal['checks'])
        original = envelope.read_bytes()
        envelope.write_bytes(original.replace(b'unexposed', b'changed'))
        self.assertNotEqual(execute(*args).returncode, 0)
        envelope.write_bytes(original.replace(b'"rows":[', b'"rows":[{},'))
        self.assertNotEqual(execute(*args).returncode, 0)
        envelope.write_bytes(original)
        answer.write_bytes(answer.read_bytes() + b'Drift.')
        self.assertNotEqual(execute(*args).returncode, 0)
        self.assertNotEqual(execute('verify', export, '--answer', answer, '--metadata', metadata).returncode, 0)

    def test_delivery_refuses_reserved_metadata_incomplete_write_and_existing_outputs(self):
        import supplied_research
        export = self.export()
        metadata = self.directory / 'meta.json'
        output = self.directory / 'delivery'
        for invalid in (b'[]', b'{"rows":[]}', b'{"first_response_sha256":"old"}', b'{"x":1,"x":2}'):
            metadata.write_bytes(invalid)
            with self.assertRaises(ValueError):
                contracts.deliver_strategy(export, metadata, output)
            self.assertFalse(output.exists())
        metadata.write_bytes(b'{}')
        write = supplied_research.write
        def interrupted(root, name, raw):
            if name == 'response.json':
                raise OSError('simulated interrupted stage')
            write(root, name, raw)
        with patch.object(supplied_research, 'write', interrupted), self.assertRaises(OSError):
            contracts.deliver_strategy(export, metadata, output)
        self.assertFalse(output.exists())
        for protected in (export, export / 'nested', ROOT / 'unused-delivery'):
            with self.assertRaises(ValueError):
                contracts.deliver_strategy(export, metadata, protected)
        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(contracts.deliver_strategy, export, metadata, output) for _ in range(2)]
        self.assertEqual(sum(attempt.exception() is None for attempt in attempts), 1)
        before = {p.name: p.read_bytes() for p in (output / 'files').iterdir()}
        with self.assertRaises(ValueError):
            contracts.deliver_strategy(export, metadata, output)
        self.assertEqual({p.name: p.read_bytes() for p in (output / 'files').iterdir()}, before)

    def test_delivery_rejects_dotted_destination_and_reparse_parent(self):
        export = self.export()
        metadata = self.directory / 'metadata.json'
        metadata.write_bytes(b'{}')
        dest = self.directory / 'new'
        with self.assertRaises(ValueError):
            contracts.deliver_strategy(export, metadata, self.directory / '..' / self.directory.name / dest.name)
        original = self.directory / 'ordinary'
        original.mkdir()
        link = self.directory / 'alias'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(original), str(link))
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(original, target_is_directory=True)
        with self.assertRaises(ValueError):
            contracts.deliver_strategy(export, metadata, link / dest.name)
        self.assertFalse(dest.exists())
        self.assertFalse((original / dest.name).exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows short-name spelling')
    def test_delivery_rejects_noncanonical_real_short_alias(self):
        import ctypes
        from ctypes import wintypes
        owned = self.directory / 'Long name for delivery path tests'
        owned.mkdir()
        get_short = ctypes.WinDLL('kernel32', use_last_error=True).GetShortPathNameW
        get_short.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        get_short.restype = wintypes.DWORD
        buf = ctypes.create_unicode_buffer(32768)
        size = get_short(str(owned), buf, len(buf))
        self.assertTrue(0 < size < len(buf))
        short = Path(buf.value)
        if short == owned:
            self.skipTest('No distinct filesystem short name')
        self.assertEqual(short.resolve(), owned)
        metadata = self.directory / 'meta.json'
        metadata.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'CANONICAL_DELIVERY_PATH_REQUIRED'):
            contracts.deliver_strategy(self.export(), metadata, short / 'new')
        self.assertFalse((owned / 'new').exists())

    def test_rejects_sibling_primary_and_incomplete_decision_policies(self):
        for section, changes in [('variants', {'primary': {'record_pointer': '/other/budget'}}),
                                 ('variants', {'mode': 'development_selection'}),
                                 ('sample', {'minimum_observations': 1}), ('sample',{'minimum_events': True}),
                                 ('uncertainty', {'confidence': 1}), ('uncertainty',{'performance_rule': 1}),
                                 ('uncertainty',{'dependence_treatment': ''})]:
            with self.subTest(section=section,changes=changes):
                req = copy.deepcopy(self.request)
                req['answer_controls'][section].update(changes)
                with self.assertRaises((ValueError,KeyError)):
                    contracts.strategy_answer(req,self.directory)
        self.request['design_terms']['variant_treatment']={'proposal':'pick the best afterwards'}
        with self.assertRaisesRegex(ValueError,'USE_STRUCTURED_VARIANT_POLICY'):
            contracts.strategy_answer(self.request,self.directory)

    def test_forward_journal_and_development_selection_have_distinct_outputs(self):
        self.request['design_kind']='forward_paper'
        terms=self.request['design_terms']
        del terms['development_validation_split']
        terms.update(variant_decision_record={'proposal': 'all session decisions'},
                     quote_order_fill_reconciliation={'proposal': 'reconcile daily independent statements'})
        self.request['proposed_decision_rules'].append(self.rule('operations'))
        self.request['answer_controls']['variants'].update(mode='development_selection',selection_measure='maximum net ratio',
            tie_break='first declared',multiplicity_adjustment='joint block-bootstrap critical value',lock_before='open of the first validation session')
        self.request['proposed_decision_rules'][0]['comparison']='<'
        output = self.export()
        wording = (output / 'answer.md').read_text(encoding='utf-8')
        row = json.loads((output / 'answer-rows.json').read_bytes())[0]
        policy = row['forward_reconciliation']
        self.assertEqual(policy['status'], 'DESIGN_ONLY_NO_OBSERVATIONS')
        self.assertEqual(row['proposed_decision_rules'], self.request['proposed_decision_rules'])
        for statement in [*policy['populations'].values(), *policy['dispositions'].values()]:
            self.assertIn(statement, wording)
        self.assertEqual(contracts.verify(output)['operation'], 'strategy-answer')
        path = output / 'receipt.json'
        receipt = json.loads(path.read_bytes())
        self.assertEqual(receipt['schema_version'], 2)
        receipt['schema_version'] = 1
        path.write_text(json.dumps(receipt), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'REPLAY_REPORT_MISMATCH'):
            contracts.verify(output)
        for fragment in ['multiplicity adjustment','upper confidence bound','order ID','quote IDs','execution IDs',
                         'rejection','cancellation','positions to independent original statements']:
            self.assertIn(fragment,wording)
