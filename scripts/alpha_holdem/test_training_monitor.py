import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('training_monitor.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_partial_tail_and_physical_rate(tmp_path):
    training = tmp_path/'training'
    training.mkdir()
    rows = [dict(recorded_at=f'2026-09-09T00:00:{sec:02d}+00:00',
                 environment_hand_accounting=dict(completed_hands=hands), hands=hands-5)
            for sec, hands in [(0, 100), (10, 210)]]
    (training/'h1_training_metrics.jsonl').write_text('\n'.join(map(json.dumps, rows))+'\n{"partial":', encoding='utf-8')
    s = m.status(tmp_path)
    assert s['actual_hands'] == 210
    assert s['physical_hands_per_second'] == 11
    assert s['eta_utc'] is None
    assert s['state'].startswith('STOPPED')


def test_completed_is_not_inferred_from_counter(tmp_path):
    (tmp_path/'train10m').mkdir()
    assert m.status(tmp_path)['state'].startswith('STOPPED')
    (tmp_path/'train10m/result.json').write_text(json.dumps(dict(physical_hands=10000123)), encoding='utf-8')
    assert m.status(tmp_path)['state'] == 'COMPLETED'
    assert m.status(tmp_path)['actual_hands'] == 10000123
