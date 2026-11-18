"""Explicit synthetic retrospective paper demo; never a live prospective pilot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', required=True, help='Existing private directory outside the package')
    args = parser.parse_args(argv)
    package = Path(__file__).resolve().parents[1]
    root = Path(args.output_root).resolve()
    if not root.is_dir() or root == package or package in root.parents:
        raise ValueError('Existing private output directory outside package required')
    sys.path.insert(0, str(package / 'scripts'))
    import institutional_research as research
    input_path = package / 'examples/institutional-event-input.json'
    document = json.loads(input_path.read_text(encoding='utf-8'))
    document['include_flow_analysis'] = True
    research._publish(root / 'brief-input.json', research._bytes(document) + b'\n')
    protocol = research.plan(document)
    first = research.brief(document)
    for name, value in [('protocol.json', protocol), ('brief-first.json', first)]:
        research._publish(root / name, research._bytes(value) + b'\n')
    response = (root / 'brief-first.json').read_bytes()
    evaluation_input = json.loads((package / 'examples/institutional-evaluation-input.json').read_text(encoding='utf-8'))
    if evaluation_input.get('pilot') != document['pilot']:
        raise ValueError('SYNTHETIC_PILOT_PROTOCOL_MISMATCH')
    retained = evaluation_input['evaluation']['cases'][0]['first_response']
    retained.update(text=response.decode('utf-8'), sha256=hashlib.sha256(response).hexdigest())
    evaluation = research.evaluate(evaluation_input)
    research._publish(root / 'evaluation-input.json', research._bytes(evaluation_input) + b'\n')
    research._publish(root / 'evaluation.json', research._bytes(evaluation) + b'\n')
    cli = [sys.executable, '-X', 'utf8', '-B', str(package / 'scripts/institutional_research.py')]
    clock_path = root / 'capture-clock.json'
    if not clock_path.exists():
        research._publish(clock_path, research._bytes({'first_demo_capture_at': datetime.now(timezone.utc).isoformat()}) + b'\n')
    capture_at = json.loads(clock_path.read_text(encoding='utf-8'))['first_demo_capture_at']
    commands = [
        ['capture', '--root', str(root), '--entry-id', 'synthetic-source-v1', '--input', str(root / 'brief-input.json'),
         '--available-at', capture_at, '--source-id', 'synthetic-fixture', '--rights', 'synthetic_fixture_only'],
        ['journal', '--root', str(root), '--entry-id', 'synthetic-protocol-v1', '--kind', 'protocol', '--input', str(root / 'protocol.json')],
        ['journal', '--root', str(root), '--entry-id', 'synthetic-first-v1', '--kind', 'first_response', '--input', str(root / 'brief-first.json')],
        ['journal', '--root', str(root), '--entry-id', 'synthetic-evaluation-v1', '--kind', 'evaluation', '--input', str(root / 'evaluation.json'), '--parent-id', 'synthetic-first-v1'],
        ['recover', '--root', str(root), '--entry-id', 'synthetic-first-v1']]
    for command in commands:
        subprocess.run(cli + command, check=True, stdout=subprocess.DEVNULL)
    summary = {'status': 'SYNTHETIC_SOFTWARE_DEMO_COMPLETED', 'synthetic': True,
               'output_root': str(root), 'first_response_sha256': hashlib.sha256(response).hexdigest(),
               'flow_kind': first['flow']['kind'], 'squeeze_kind': first['squeeze']['kind'],
               'usefulness_cases': evaluation['usefulness']['included_cases'],
               'paper_return_cases': evaluation['returns']['included_cases'],
               'declared_pilot_sha256': protocol['pilot_sha256'],
               'evaluation_pilot_sha256': evaluation['protocol_reconciliation']['pilot_sha256'],
               'protocol_reconciliation_status': evaluation['protocol_reconciliation']['status'],
               'real_prospective_pilot_completed': False, 'profitability_established': False,
               'execution_authorized': False,
               'limitation': 'Fictitious October clocks and outcomes exercise software retrospectively; actual journal timestamps show this later demo execution.'}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
