"""Offline qualification of recovered terminal review; never touches live outcomes or logger."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import recovery_chain as chain
import review_recovered
import curve_recovered


def main():
    here, base = chain.HERE, chain.BASE
    output, xml = here / 'qualification.json', here / 'review_tests.xml'
    chain.require(not output.exists() and not xml.exists(), 'preserve existing qualification')
    started = time.monotonic()
    previous_path = base / 'post_analysis/qualification.json'
    previous = chain.read(previous_path)
    chain.require(previous['passed'] and previous['terminal_review_executed'] is False, 'original review not qualified')
    inputs = {**previous['source_sha256'], str(previous_path): chain.sha(previous_path)}
    for suite in previous['suites']:
        inputs[suite['xml_path']] = suite['xml_sha256']
    chain.require(all(chain.sha(p) == h for p, h in inputs.items()), 'qualified original math/tests changed')
    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               str(here / 'test_recovery_chain.py'), str(here / 'test_review_recovered.py'), '--junitxml=' + str(xml)]
    tests = subprocess.run(command, cwd=base.parents[2], capture_output=True, text=True, encoding='utf-8', timeout=60)
    if tests.returncode:
        with (here / 'qualification_failure.json').open('x', encoding='utf-8') as handle:
            json.dump({'command': command, 'stdout': tests.stdout, 'stderr': tests.stderr}, handle, indent=2)
        raise ValueError(tests.stdout + tests.stderr)
    suites = list(ET.parse(xml).getroot().iter('testsuite'))
    count = sum(int(s.get('tests', 0)) for s in suites)
    chain.require(count >= 40 and all(all(int(s.get(k, 0)) == 0 for k in ('failures', 'errors', 'skipped')) for s in suites),
                  'incomplete recovered review coverage')
    # Bind local imported helper sources as well as the entry points; do not bind
    # mutable live checkpoints, logs or the experiment record in this qualification.
    sources = set(here.glob('*.py'))
    root = base.parents[2]
    for module in list(sys.modules.values()):
        value = getattr(module, '__file__', None)
        if value:
            path = Path(value).resolve()
            if path.suffix == '.py' and path.is_relative_to(root) and path.is_file():
                sources.add(path)
    inputs = chain.merge_hashes(inputs, {str(p): chain.sha(p) for p in sources}, {str(xml): chain.sha(xml)})
    chain.require(all(chain.sha(p) == h for p, h in inputs.items()), 'qualification inputs changed')
    result = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
              'tests_command': command, 'tests_cwd': str(root), 'test_count': count,
              'tests_stdout': tests.stdout, 'tests_stderr': tests.stderr, 'input_sha256': inputs,
              'wall_seconds': time.monotonic() - started, 'new_training_or_evaluation_hands': 0,
              'current_outcomes_read': False, 'logger_writes': 0, 'terminal_review_executed': False,
              'qualified_scope': 'Original raw CI/gradient/counter/Adam math unchanged; recovery-aware endpoint, pending-prefix and actual-state chain, job admission, count and wall-bound interpretation.'}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
