"""Default quant/report replay must bind executed REIT source dependencies."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import quant_workbench as workbench
import report_facts as facts


class ReitImplementationClosureTests(unittest.TestCase):
    def test_source_dependency_changes_invalidate_both_default_route_hashes(self):
        with tempfile.TemporaryDirectory(prefix='reit-closure-') as temp:
            root = Path(temp)
            (root / 'scripts').mkdir()
            shutil.copytree(workbench.ROOT / 'profiles', root / 'profiles')
            (root / 'references').mkdir()
            shutil.copyfile(workbench.ROOT / 'references/market-source-catalog.json',
                            root / 'references/market-source-catalog.json')
            for name in set(workbench.MODULES) | set(facts.QUANT_FILES) | {'reit_sources.py', 'source_lineage.py'}:
                shutil.copyfile(workbench.ROOT / 'scripts' / name, root / 'scripts' / name)
            with patch.object(workbench, 'ROOT', root), patch.object(facts, 'ROOT', root):
                initial = workbench.implementation_hash(), facts.quant_hash()
                self.assertEqual(initial[0], initial[1])
                for name in ('reit_sources.py', 'source_lineage.py'):
                    with self.subTest(dependency=name):
                        path = root / 'scripts' / name
                        original = path.read_bytes()
                        path.write_bytes(original + b'\n# Synthetic implementation change\n')
                        changed = workbench.implementation_hash(), facts.quant_hash()
                        self.assertNotEqual(changed[0], initial[0])
                        self.assertNotEqual(changed[1], initial[1])
                        self.assertEqual(changed[0], changed[1])
                        path.write_bytes(original)
                        self.assertEqual((workbench.implementation_hash(), facts.quant_hash()), initial)


if __name__ == '__main__':
    unittest.main()
