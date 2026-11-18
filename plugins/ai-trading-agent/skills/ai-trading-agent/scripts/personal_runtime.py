"""Optional research workspace and dependency diagnostics; no execution gates."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from execution_handoff import handoff, redact_private

ROOT = Path(__file__).resolve().parents[1]

def initialize(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('evidence', 'reports'):
        (directory/name).mkdir(exist_ok=True)
    return {'runtime':str(directory), 'purpose':'OPTIONAL_RESEARCH_WORKSPACE',
            'existing_files_preserved':True, 'skill_execution_gates':[]}

def doctor(directory=None):
    checks, warnings = {}, []
    for dependency in ('numpy','scipy','exchange_calendars','yfinance','jsonschema','requests','tzdata','arch'):
        try:
            checks[dependency] = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            checks[dependency] = 'NOT_INSTALLED'
            warnings.append('MISSING_DEPENDENCY:' + dependency)
    checks['garch_capability'] = 'AVAILABLE' if checks['arch'] != 'NOT_INSTALLED' else 'SKIPPED_MISSING_DEPENDENCIES'
    checks['skill_version'] = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    return {'local_checks_passed':True, 'failures':[], 'warnings':warnings, 'checks':checks,
            'advisory_only':True, 'skill_execution_gates':[], 'execution_owner':'native_host_and_broker'}

def dispatch(directory, operation, request):
    if operation == 'risk':
        from risk_engine import evaluate
        policy = request.get('policy')
        if policy is None:
            path = Path(directory)/'policy.json'
            if not path.is_file():
                return {'within_research_limits':None,'diagnostic_status':'DATA_UNAVAILABLE',
                        'reasons':['OPTIONAL_SCENARIO_POLICY_NOT_SUPPLIED'],
                        'advisory_only':True,'enforces_execution':False}
            policy = json.loads(path.read_text(encoding='utf-8-sig'))
        if not {'snapshot','order'} <= set(request):
            return {'within_research_limits':None,'diagnostic_status':'DATA_UNAVAILABLE',
                    'reasons':['OPTIONAL_SCENARIO_INPUTS_NOT_SUPPLIED'],
                    'advisory_only':True,'enforces_execution':False}
        result = evaluate(policy, request['snapshot'], request['order'])
        result.update(advisory_only=True, enforces_execution=False)
        return result
    if operation == 'unresolved':
        from execution_ledger import ExecutionLedger
        ledger = ExecutionLedger(Path(directory)/'execution.db')
        return {'historical_local_records_only':True, 'advisory_only':True, 'skill_execution_gates':[],
                'orders':ledger.unresolved(), 'incidents':ledger.unresolved_incidents(),
                'cancellations':ledger.unresolved_cancellations()}
    return handoff(request, source='personal_runtime.' + operation + '_retired')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation')
    parser.add_argument('runtime', type=Path, nargs='?', default=Path('.'))
    args = parser.parse_args()
    if args.operation == 'init':
        result = initialize(args.runtime)
    elif args.operation == 'doctor':
        result = doctor(args.runtime)
    else:
        raw = '' if args.operation == 'unresolved' else sys.stdin.read()
        result = dispatch(args.runtime, args.operation, json.loads(raw) if raw.strip() else {})
    print(json.dumps(redact_private(result),indent=2,allow_nan=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
