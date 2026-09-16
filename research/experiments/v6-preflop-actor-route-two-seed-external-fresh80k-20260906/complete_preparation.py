"""Complete the interrupted OFFLINE preparation without overwriting prior evidence."""
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import run_pair as r

BASE = Path(__file__).resolve().parent
OLD = r.ROOT / 'research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906'


def main():
    started = time.monotonic()
    for name in ('launch_spec.json', 'environment.json', 'preparation_report.json', 'execution.json'):
        r.protocol.require(not (BASE / name).exists(), 'preserve earlier preparation/attempt:' + name)
    r.training_ready()
    binding, derivation = r.read(BASE / 'binding_qualification.json'), r.read(BASE / 'source_derivation.json')
    r.protocol.require(binding['passed'] is True and binding['exit_code'] == 0 and derivation['passed'] is True,
        'initial offline qualification was not successful')
    r.check_hashes(binding['source_sha256'])
    suites = list(ET.parse(BASE / 'preparation_tests.xml').getroot().iter('testsuite'))
    r.protocol.require(sum(int(s.get('tests', '0')) for s in suites) == 80 and
        all(int(s.get(key,'0')) == 0 for s in suites for key in ('failures','errors','skipped')),
        'qualified80 test evidence changed')
    failure = r.read(BASE / 'endpoint_parity_failure.json')
    r.protocol.require(failure['network_requests'] == failure['new_hands'] == 0 and
        not failure['models_completed'] and "obs_version='v6', found 'v4'" in failure['traceback'],
        'unexpected initial parity failure')
    r.check_hashes(failure['input_sha256'])
    parity = r.read(BASE / 'endpoint_parity.json')
    r.protocol.require(parity['passed'] and parity['retained_input_rows'] == 256 and
        parity['network_requests'] == parity['optimizer_updates'] == 0, 'correct bridge parity incomplete')
    r.check_hashes(parity['input_sha256'])
    prior, unreadable = r.prior_initial_sessions(r.ROOT / 'research/experiments', BASE)
    r.check_unused_session_identifiers(prior)
    r.check_prior_prefixes(prior)
    r.protocol.require(r.sha(OLD / 'launch_spec.json') == derivation['old_launch_spec_sha256'] ==
        '94445fa3f0e98b0a44f5a54bc29ca5ca253826b4ae1342a0ecbf378f1b37772c',
        'template qualification binding changed')
    versions = {name: metadata.version(name) for name in ('torch','numpy','scipy','requests','psutil','pytest')}
    r.write_new(BASE / 'environment.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(), 'packages': versions,
        'launch_environment': {'PYTHONDONTWRITEBYTECODE':'1', 'OMP_NUM_THREADS':'1',
            'MKL_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1'},
        'purpose':'Frozen CPU greedy bridge external development; zero training or requests during preparation'})
    sources = list(binding['source_sha256'])
    sources += [str(BASE / name) for name in ('endpoint_parity_v2.py', 'complete_preparation.py',
        'endpoint_parity.json', 'endpoint_parity_failure.json', 'source_derivation.json',
        'binding_qualification.json', 'preparation_tests.xml', 'environment.json')]
    sources += [value['template_path'] for value in derivation['templates'].values()]
    sources += [str(OLD / 'launch_spec.json')]
    spec = {'schema':'cardpilot.actor_route.four_policy_external.v1', 'development_only':True,
        'schedule':r.protocol.schedule(),
        'models':{arm:{'path':str(path), 'sha256':digest} for arm,(path,digest) in r.EXPECTED_MODELS.items()},
        'runtime_source':str(r.RUNTIME_SOURCE),
        'runtime_sha256':{str(p):r.sha(p) for p in r.RUNTIME_SOURCE.rglob('*.py') if '__pycache__' not in p.parts},
        'training_report_sha256':r.sha(r.REPORT), 'preregistration_sha256':r.sha(BASE/'preregistration.md'),
        'code_sha256':{p:r.sha(p) for p in sources}}
    r.write_new(BASE/'launch_spec.json',spec)
    r.preflight(BASE)
    r.write_new(BASE/'preparation_report.json', {'passed':True, 'created_at':datetime.now(timezone.utc).isoformat(),
        'wall_seconds':time.monotonic()-started, 'outer_argv':sys.orig_argv,
        'network_requests':0, 'new_hands':0, 'planned_sessions':32, 'planned_hands':80000,
        'retained_endpoint_parity_rows':256, 'offline_tests':80,
        'prior_initial_sessions_checked':len(prior), 'unreadable_prior_initial_records':unreadable,
        'planned_session_ids_and_seeds_unused':True, 'launch_spec_sha256':r.sha(BASE/'launch_spec.json'),
        'frozen_offline_tests_will_rerun_before_first_request':True,
        'preparation_deviation':'Initial parity accidentally used native-v6 loader and failed before forward or network; original code/failure preserved; v2 uses actual frozen client legacy-v4 bridge loader. No policy or schedule change.',
        'passed_initial_tests_not_rerun_to_complete_preparation':True})
    argv = [sys.executable,'-B',str(r.ROOT/'research/experiment_log.py'),'update',BASE.name,
        '--metric','offline_preflight_passed=true','--metric','endpoint_forward_parity_passed=true',
        '--metric','preparation_added_hands=0',
        '--command',subprocess.list2cmdline(binding['argv']),
        '--command',subprocess.list2cmdline(failure['command'])]
    for name in ('launch_spec.json','environment.json','preparation_report.json','source_derivation.json',
        'binding_qualification.json','preparation_tests.xml','endpoint_parity_failure.json','endpoint_parity.json'):
        argv += ['--artifact',str(BASE/name)]
    subprocess.run(argv,cwd=r.ROOT,check=True)
    print('Offline completion PASS: corrected actual bridge parity, original80 tests retained, zero requests.')


if __name__ == '__main__':
    main()
