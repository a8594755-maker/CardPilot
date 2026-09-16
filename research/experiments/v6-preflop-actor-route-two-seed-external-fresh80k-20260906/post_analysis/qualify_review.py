"""Exclusive offline reviewer qualification; does not acquire the live logger."""
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
    output, xml = HERE / 'qualification.json', HERE / 'tests.xml'
    for path in (output, xml):
        review.r.protocol.require(not path.exists(), 'preserve earlier qualification')
    sources = (Path(__file__), HERE / 'review_completed.py', HERE / 'test_review_completed.py',
        review.BASE / 'run_pair.py', review.BASE / 'pair_protocol.py')
    hashes = {str(path): review.r.sha(path) for path in sources}
    template = review.ROOT / 'research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906/post_analysis'
    earlier = review.r.read(template / 'qualification.json')
    review.r.protocol.require(earlier['passed'] and earlier['exit_code'] == 0, 'template reviewer not qualified')
    review.r.check_hashes(earlier['source_sha256'])
    hashes.update(earlier['source_sha256'])
    hashes[str(template / 'qualification.json')] = review.r.sha(template / 'qualification.json')
    argv = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        str(HERE / 'test_review_completed.py'), f'--junitxml={xml}']
    start = time.monotonic()
    result = subprocess.run(argv, cwd=review.ROOT, capture_output=True, text=True, timeout=90)
    review.r.check_hashes(hashes)
    readiness = review.readiness() if (review.BASE / 'execution.json').exists() else {
        'ready': False, 'reason': 'no controller attempt yet; outcomes do not exist'}
    report = {'passed': result.returncode == 0, 'created_at': datetime.now(timezone.utc).isoformat(),
        'outer_argv': sys.orig_argv, 'pytest_argv': argv, 'exit_code': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'wall_seconds': time.monotonic() - start,
        'source_sha256': hashes, 'xml_sha256': review.r.sha(xml), 'readiness': readiness,
        'network_requests': 0, 'model_queries': 0, 'new_hands': 0, 'current_rewards_read': False,
        'logger_deferred_until_exact_owner_exit': True}
    review.r.write_new(output, report)
    print(json.dumps(report))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
