"""Keep the qualitative sentiment workflow installable and discoverable."""
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SentimentPackagingTests(unittest.TestCase):
    def test_distribution_retains_workflow_and_behavior_tests(self):
        manifest = json.loads((ROOT / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
        for name in ('scripts/sentiment_review.py', 'tests/test_sentiment_review.py',
                     'tests/test_sentiment_packaging.py'):
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file())
                self.assertEqual(manifest['files'][name],
                                 hashlib.sha256((ROOT / name).read_bytes()).hexdigest())

    def test_entrypoints_reach_the_documented_helper(self):
        guide = 'references/news-and-guidance.md'
        text = (ROOT / guide).read_text(encoding='utf-8')
        for entry in ('SKILL.md', 'README.md'):
            with self.subTest(entry=entry):
                links = re.findall(r'\]\(([^)]+)\)', (ROOT / entry).read_text(encoding='utf-8'))
                routes = [link for link in links if link.startswith(guide + '#')
                          and 'sentiment' in link.split('#', 1)[1]]
                self.assertTrue(routes, 'Entry point must route to the sentiment workflow')
                headings = [re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
                            for heading in re.findall(r'^#+ (.+)$', text, re.MULTILINE)]
                self.assertTrue(any(link.split('#', 1)[1] in headings for link in routes))
        self.assertIn('scripts/sentiment_review.py', text)
        self.assertTrue((ROOT / 'scripts/sentiment_review.py').is_file())


if __name__ == '__main__':
    unittest.main()
