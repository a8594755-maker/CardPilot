"""Qualified-candidate regression run with complete dependency and failure evidence."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
CANDIDATE = BASE / 'candidate'


def main():
    output = BASE / 'regression_report_v2.json'
    xml = BASE / 'regression_tests_v2.xml'
    log = BASE / 'regression_output_v2.log'
    assert not any(p.exists() for p in (output,xml,log)), 'preserve earlier attempt'
    assert json.loads((BASE / 'experiment.json').read_text())['status'] == 'RUNNING'
    assert (BASE / 'dependency_preparation.json').is_file()
    os.chdir(CANDIDATE)
    sys.path.insert(0,str(CANDIDATE))
    sys.path.insert(0,str(CANDIDATE / 'scripts'))
    sys.path.insert(0,str(CANDIDATE / 'scripts/alpha_holdem'))
    import pytest
    started = time.monotonic()
    argv = ['-q','-p','no:cacheprovider',str(CANDIDATE / 'scripts/alpha_holdem'),f'--junitxml={xml}']
    with log.open('x',encoding='utf-8') as handle, redirect_stdout(handle), redirect_stderr(handle):
        code = pytest.main(argv)
    modules, binding_errors = {}, []
    for name,module in list(sys.modules.items()):
        if name.startswith(('scripts.alpha_holdem.', 'alpha_holdem.', 'deep_cfr.')) and getattr(module,'__file__',None):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(CANDIDATE):
                binding_errors.append([name,str(path)])
            modules[name] = {'path':str(path), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    trainer_exercised = any(name.endswith('.train_v5') for name in modules)
    suites = list(ET.parse(xml).getroot().iter('testsuite')) if xml.exists() else []
    counts = {key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
    passed = code == 0 and trainer_exercised and not binding_errors and bool(suites) and not any(counts[k] for k in ('failures','errors','skipped'))
    report = {'passed':passed,'created_at':datetime.now(timezone.utc).isoformat(),
              'command':sys.orig_argv,'pytest_argv':argv,'cwd':str(CANDIDATE),
              'wall_seconds':time.monotonic()-started,'counts':counts,'exit_code':int(code),
              'candidate_module_bindings':modules,'binding_errors':binding_errors,
              'trainer_exercised':trainer_exercised,
              'xml_sha256':hashlib.sha256(xml.read_bytes()).hexdigest() if xml.exists() else None,
              'training_hands':0,'slumbot_hands':0,'goal_achieved':False}
    with output.open('x',encoding='utf-8') as handle:
        json.dump(report,handle,indent=2)
    print(json.dumps({k:report[k] for k in ('passed','counts','exit_code','wall_seconds','binding_errors')}))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
