"""Fixed original Seed1 4M external calibration using unchanged evidence runners."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / 'research/experiments/v6-static-current-kl-4m-scale-20260904/seed1/latest.pt'
SOURCE_SHA = '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'
RUNTIME = BASE / 'prepared_runtime/scripts'
HELPER = ROOT / 'research/experiments/v6-integrated-seed1-2m-greedy-fresh20k-slumbot-20260903/run_pilot.py'
PARENT = ROOT / 'research/experiments/v6-actor-raw-greedy-fresh20k-slumbot-20260901/run_pilot.py'
HELPER_SHA = '7e984946a9d73e94ef25682ae711a45735df909c72aada30dd2aad145550e4a0'
PARENT_SHA = '81612065ee3d38299c66095a20fee2aefb647ef852df38214f3c4b808105c1a7'
sys.path.insert(0, str(BASE))
from pilot_stats import summarize


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def session_id(index):
    return f'v6_static_seed1_4m_greedy_fresh20k_20260904_s{index:02d}'


def session_seed(index):
    return 2026330100 + index


def load_helper():
    if sha(HELPER) != HELPER_SHA or sha(PARENT) != PARENT_SHA:
        raise ValueError('Historical evidence helper source changed')
    spec = importlib.util.spec_from_file_location('static4m_unchanged_bridge_helper', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.BASE, helper.ROOT = BASE, ROOT
    helper.SOURCE, helper.SOURCE_SHA, helper.RUNTIME = SOURCE, SOURCE_SHA, RUNTIME
    helper.session_id, helper.session_seed = session_id, session_seed
    return helper


def session_command(index):
    return load_helper().session_command(index)


def development_write(original, path, value):
    if Path(path).name == 'completed_analysis.json':
        value = dict(value)
        value['decision'] = 'EXTERNAL_DEVELOPMENT_CALIBRATION_REVIEW_REQUIRED'
        value['automatic_formal_test_authorized'] = False
        value['goal_achieved'] = False
    return original(path, value)


def verify_handoff():
    import psutil
    integration = ROOT / 'research/experiments/v6-managed-trainer-resume-integration-20260904'
    record = json.loads((integration / 'experiment.json').read_text(encoding='utf-8'))
    report = json.loads((integration / 'gpu_current_recipe_v1/summary.json').read_text(encoding='utf-8'))
    if record['status'] != 'COMPLETED' or not report['all_mechanics_passed']:
        raise RuntimeError('Managed production/GPU qualification is not finished')
    for proc in psutil.process_iter(['pid', 'cmdline']):
        if any(Path(arg).name in ('gpu_qualification_v2_handoff.py', 'run_gpu_resume_qualification.py')
               for arg in proc.info['cmdline'] or []):
            raise RuntimeError(f'GPU qualification owner still live: {proc.pid}')
    if sha(SOURCE) != SOURCE_SHA:
        raise ValueError('Original Seed1 checkpoint changed')


def main():
    verify_handoff()
    helper = load_helper()
    impl = helper.load_parent()
    original_log, original_write = impl.log, impl.write
    impl.log = lambda *args: helper.batched_log(original_log, *args)
    impl.write = lambda path, value: development_write(original_write, path, value)
    impl.BASE, impl.SOURCE, impl.SOURCE_SHA = BASE, SOURCE, SOURCE_SHA
    impl.RUNTIME = RUNTIME
    impl.CLIENT = RUNTIME / 'alpha_holdem/play_slumbot_v6_journaled.py'
    impl.AUDITOR = BASE / 'audit_bridge_cli.py'
    impl.summarize = summarize
    impl.session_id, impl.session_seed = session_id, session_seed
    impl.session_command, impl.raw_sessions = helper.session_command, helper.raw_sessions
    impl.main()


if __name__ == '__main__':
    main()
