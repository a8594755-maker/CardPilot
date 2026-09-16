"""Hash-bound offline qualification of the one-shot terminal prerequisite chain."""
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_completed as review


def main():
    output, xml = HERE / 'followthrough_qualification.json', HERE / 'followthrough_tests.xml'
    for path in (output, xml):
        review.r.protocol.require(not path.exists(), 'preserve earlier qualification')
    sources = [Path(__file__), HERE / 'terminal_followthrough.py', HERE / 'test_terminal_followthrough.py',
               HERE / 'review_completed.py', review.BASE / 'run_pair.py']
    sources += [HERE / 'launch_followthrough.ps1', HERE / 'README.md',
        review.BASE / 'launch_spec.json', review.BASE / 'session_commands.json', review.BASE / 'preregistration.md']
    hashes = {str(path): review.r.sha(path) for path in sources}
    template = review.ROOT / 'research/experiments/v6-preflop-actor-route-two-seed-external-fresh80k-20260906/post_analysis'
    earlier = review.r.read(template / 'followthrough_qualification.json')
    review.r.protocol.require(earlier['passed'] and earlier['exit_code'] == 0, 'template prerequisite chain not qualified')
    review.r.check_hashes(earlier['source_sha256'])
    hashes.update(earlier['source_sha256'])
    hashes[str(template / 'followthrough_qualification.json')] = review.r.sha(template / 'followthrough_qualification.json')
    argv = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            str(HERE / 'test_terminal_followthrough.py'), f'--junitxml={xml}']
    started = time.monotonic()
    result = subprocess.run(argv, cwd=review.ROOT, capture_output=True, text=True, timeout=60)
    review.r.check_hashes(hashes)
    value = {'passed': result.returncode == 0, 'created_at': datetime.now(timezone.utc).isoformat(),
        'outer_argv': [sys.executable, *sys.orig_argv[1:]], 'pytest_argv': argv,
        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
        'wall_seconds': time.monotonic() - started, 'source_sha256': hashes,
        'xml_sha256': review.r.sha(xml), 'readiness': review.readiness(),
        'network_requests': 0, 'model_queries': 0, 'new_hands': 0,
        'current_rewards_read': False, 'logger_deferred_until_exact_owner_exit': True}
    review.r.write_new(output, value)
    print(json.dumps(value))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
