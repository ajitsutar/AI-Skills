"""Render the maintained prompt catalog and reject stale release documentation.

This checks freshness and structure, not whether prose describes a capability
truthfully. A maintainer reviews the README and capability coverage before generate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'references/example-prompts.json'
OUTPUT = 'EXAMPLE-PROMPTS.md'
STATE = 'DOCS-STATE.json'


def text_hash(data):
    # Documentation freshness must survive Git's LF/CRLF checkout conversion.
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def checked_path(root, name):
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError('Missing or unsafe documentation resource: ' + name)
    return path


def load_catalog(root):
    catalog = json.loads(checked_path(root, CATALOG).read_text(encoding='utf-8'))
    if catalog.get('schema_version') != 1 or not catalog.get('sections'):
        raise ValueError('Expected a nonempty prompt catalog with schema_version 1')
    titles, prompts, sections = set(), set(), set()
    for section in catalog['sections']:
        key = section['id']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key) or key in sections:
            raise ValueError('Invalid or duplicate section ID: ' + key)
        sections.add(key)
        for field in ('title', 'audience'):
            if not isinstance(section[field], str) or not section[field].strip() or '\n' in section[field]:
                raise ValueError('Section title/audience must be nonempty single-line text')
        if not section.get('guides') or not section.get('prompts'):
            raise ValueError('Every capability group needs actual guides and examples')
        for guide in section['guides']:
            checked_path(root, guide)
        for example in section['prompts']:
            for field, seen in (('title', titles), ('prompt', prompts)):
                value = example[field]
                if not isinstance(value, str) or not value.strip() or '\n' in value:
                    raise ValueError('Examples must have nonempty single-line titles and prompts')
                key = ' '.join(value.lower().split())
                if key in seen:
                    raise ValueError('Duplicate example ' + field + ': ' + value)
                seen.add(key)
    return catalog


def slug(title):
    return re.sub(r'[^\w\- ]', '', title.lower()).replace(' ', '-')


def render(catalog):
    count = sum(len(s['prompts']) for s in catalog['sections'])
    out = ['# ' + catalog['title'], '',
           '<!-- Generated from references/example-prompts.json with scripts/release_docs.py. -->', '',
           f'{count} examples across {len(catalog["sections"])} workflows, from first-time investing to quantitative research.', '',
           'Start any prompt with **Use the robinhood-ai-trading-agent skill.** Replace',
           'bracketed inputs with your own data. Choose a section below; you do not need to',
           'read or run the entire catalog. Examples describe requests you can make, not',
           'additional investment rules or permission to trade.', '',
           'Research and paper calculations are broader than live execution support.',
           'Live examples require actual broker capabilities, appropriate authorization',
           'and supervision. Some advanced examples produce a research plan or a gap',
           'assessment because the required data, model or validated adapter is absent.',
           'Read the linked workflow for each section and the [README](README.md) for scope.', '',
           '## Choose a workflow', '', '| Workflow | Audience | Examples |', '|---|---|---:|']
    for section in catalog['sections']:
        out.append(f'| [{section["title"]}](#{slug(section["title"])}) | {section["audience"]} | {len(section["prompts"])} |')
    index = 0
    for section in catalog['sections']:
        links = ', '.join(f'[{Path(g).stem.replace("-", " ")}]({g})' for g in section['guides'])
        out += ['', '## ' + section['title'], '', '**Audience:** ' + section['audience'] + '. Guides: ' + links + '.', '']
        for example in section['prompts']:
            index += 1
            out += [f'### {index}. {example["title"]}', '', '> ' + example['prompt'], '']
    out += ['## Keeping this catalog current', '',
            'Examples are reviewed against the current capabilities and regenerated for',
            'every package update. There is no fixed count: add distinct useful workflows,',
            'revise changed behavior and remove claims the skill cannot support. See the',
            '[maintenance procedure](references/maintaining-the-skill.md).', '']
    return '\n'.join(out)


def input_fingerprint(root):
    names = {'SKILL.md', 'README.md', 'VERSION', 'INSTALL.md', CATALOG,
             'LICENSE', 'PROVENANCE.md', 'SOURCES.md', 'THIRD-PARTY-NOTICES.md',
             'ARCH-LICENSE.txt'}
    for directory in ('scripts', 'references', 'profiles', 'templates', 'agents', 'examples'):
        for path in (root / directory).rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.md', '.json', '.yaml', '.yml', '.txt', '.csv'):
                if '__pycache__' not in path.parts:
                    names.add(path.relative_to(root).as_posix())
    for path in root.glob('requirements*.txt'):
        names.add(path.name)
    entries = {name: text_hash(checked_path(root, name).read_bytes()) for name in sorted(names)}
    payload = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return text_hash(payload), len(entries)


def expected(root, catalog, rendered):
    fingerprint, count = input_fingerprint(root)
    return {'schema_version': 1, 'skill_version': checked_path(root, 'VERSION').read_text(encoding='utf-8').strip(),
            'input_fingerprint_sha256': fingerprint, 'input_file_count': count,
            'catalog_sha256': text_hash((root / CATALOG).read_bytes()),
            'readme_sha256': text_hash((root / 'README.md').read_bytes()),
            'examples_sha256': text_hash(rendered.encode('utf-8')),
            'section_count': len(catalog['sections']),
            'example_count': sum(len(s['prompts']) for s in catalog['sections']),
            'hash_basis': 'UTF-8 files with LF/CRLF normalized; excludes generated state and package manifest'}


def run(root, mode, reviewed=False):
    root = Path(root).resolve()
    catalog = load_catalog(root)
    rendered = render(catalog)
    want = expected(root, catalog, rendered)
    if mode == 'generate':
        if not reviewed:
            raise ValueError('Review current README/capabilities and update the catalog, then pass --reviewed')
        (root / OUTPUT).write_text(rendered, encoding='utf-8', newline='\n')
        (root / STATE).write_text(json.dumps(want, indent=2)+'\n', encoding='utf-8', newline='\n')
        return dict(status='GENERATED', **want)
    actual = json.loads(checked_path(root, STATE).read_text(encoding='utf-8'))
    if actual != want or text_hash(checked_path(root, OUTPUT).read_bytes()) != want['examples_sha256']:
        raise ValueError('STALE_DOCUMENTATION: review README and current capability coverage, then regenerate examples before packaging')
    return dict(status='CURRENT', **want)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('generate', 'check'))
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--reviewed', action='store_true', help='Confirm README and prompt coverage were reviewed against current capabilities')
    a = p.parse_args()
    try:
        print(json.dumps(run(a.root, a.mode, a.reviewed), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
