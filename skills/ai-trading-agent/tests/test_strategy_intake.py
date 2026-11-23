"""Original strategy declaration, executable delivery and preserved legacy evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import research_contracts as contracts
import test_strategy_economics as economics
from strategy_intake import original_contract


class StrategyIntakeTests(unittest.TestCase):
    def setUp(self):
        case = economics.StrategyEconomicsTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.old = case.base.legacy
        self.options = case.options
        self.directory = case.base.directory.resolve()
        self.source = case.base.source.resolve()
        self.prompt = self.source.parent/'PROMPT.txt'
        self.prompt.write_text('Study studies.json#/strategies/0 before proposing a decision.', encoding='utf8')
        self.protocol = self.source.parent/'PROTOCOL.txt'
        self.protocol.write_text('Write response.json containing rows, provider and observations.', encoding='utf8')
        inventory = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.prompt,self.protocol)}
        (self.source.parent/'HASHES.json').write_text(json.dumps(inventory), encoding='utf8')

    def build(self, options, name):
        choices = self.directory/(name+'.json')
        choices.write_text(json.dumps({k:v for k,v in options.items() if k not in ('allowlist','sources','strategy_source')}))
        out = self.directory/name
        cmd = [sys.executable,'-B',str(SCRIPTS/'research_preflight.py'),'--request',str(self.prompt),
               '--source-root',str(self.source.parent),'--source',self.source.name,'--design',str(choices),
               '--private-output',str(out)]
        result = subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return out, json.loads(result.stdout)

    def test_original_contract_auto_checked_on_delivery_and_readback(self):
        self.options['strategy_registration']['uncertainty']['estimator'] = {
            'name':'circular_moving_block_percentile','block_observations':3,'replicates':5000,'seed':7}
        root, status = self.build(self.options,'current')
        self.assertEqual(status['delivery_scope'],'current_registered_strategy')
        meta = self.directory/'host.json'
        meta.write_text('{"provider":"local"}')
        out = self.directory/'delivery'
        with self.assertRaisesRegex(ValueError,'MISSING_REQUIRED_RESPONSE_FIELDS'):
            contracts.deliver_strategy(root,meta,out)
        self.assertFalse(out.exists())
        meta.write_text('{"provider":"local","observations":[]}')
        result = contracts.deliver_strategy(root,meta,out)
        self.assertEqual(result['checks']['response_contract']['contract_sha256'],hashlib.sha256(self.protocol.read_bytes()).hexdigest())
        check = contracts.verify(root,out/'files/first-response.md',out/'files/response.json',meta)
        self.assertEqual(check['checks']['response_contract'],result['checks']['response_contract'])
        weaker = self.directory/'weaker.json'
        weaker.write_text('{"required":["rows"]}')
        with self.assertRaisesRegex(ValueError,'ORIGINAL_RESPONSE_DECLARATION_CHANGED'):
            contracts.verify(root,out/'files/first-response.md',out/'files/response.json',meta,weaker)

    def test_authored_low_level_draft_and_incomplete_original_are_distinct(self):
        with self.assertRaisesRegex(ValueError,'USE_ORIGINAL_REQUEST'):
            contracts.export_run('strategy-answer',json.dumps(self.old).encode(),self.source.parent,self.directory/'derived')
        draft, status = self.build(self.old,'draft')
        self.assertEqual(status['delivery_scope'],'scoped_incomplete')
        meta = self.directory/'metadata.json'
        meta.write_text('{"provider":"local","observations":[]}')
        with self.assertRaisesRegex(ValueError,'SCOPED_INCOMPLETE'):
            contracts.deliver_strategy(draft,meta,self.directory/'published')
        self.assertFalse((self.directory/'published').exists())
        self.assertEqual(contracts.verify(draft)['delivery_scope'],'scoped_incomplete')

    def test_ordinary_request_contract_and_manifest_integrity(self):
        alternate = self.directory/'standalone-input'
        alternate.mkdir()
        inline = b'Study deeply. Write response.json containing rows and assumptions.'
        self.assertEqual(original_contract(inline,alternate),inline)
        explicit = self.directory/'contract.json'
        explicit.write_text('{"required":["assumptions","rows"]}')
        self.assertEqual(original_contract(inline,alternate,explicit),inline)
        self.assertIsNone(original_contract(b'Describe the study.',alternate))
        self.protocol.write_text('Write response.json containing rows.')
        with self.assertRaisesRegex(ValueError,'ORIGINAL_PROMPT_OR_PROTOCOL_HASH_CHANGED'):
            original_contract(self.prompt.read_bytes(),self.source.parent)
