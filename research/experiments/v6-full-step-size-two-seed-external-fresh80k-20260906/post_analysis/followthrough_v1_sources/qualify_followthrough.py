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
    hashes = {str(path): review.r.sha(path) for path in sources}
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
