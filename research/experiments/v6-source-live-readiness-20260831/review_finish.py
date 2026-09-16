"""Post-exit evidence/coverage review of the fixed16hand live probe; no API calls."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import subprocess
import sys
import run_probe as probe

BASE,ROOT=probe.BASE,probe.ROOT


def main():
    import psutil
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('Preserve prior review')
    execution=probe.read(BASE/'execution.json')
    assert execution['status']=='COMPLETED' and not psutil.pid_exists(execution['pid'])
    assert len(execution['children'])==2 and all(r['exit_code']==0 and not psutil.pid_exists(r['pid']) for r in execution['children'])
    probe.verify()
    analysis=probe.read(BASE/'analysis.json')
    combined=probe.read(BASE/'combined_audit.json')
    assert analysis['status']=='PASS' and analysis['evaluation_hands']==analysis['slumbot_hands']==16
    assert combined['status']=='PASS' and combined['sessions']==2 and combined['successful_hands']==16
    assert combined['model_sha256']==probe.SOURCE_SHA and combined['token_chains_disjoint'] and not combined['server_rng_independence_proven']
    hands=[]
    for i,result in enumerate(combined['results'],1):
        directory=BASE/'sessions'/f's{i:02d}'
        summary=probe.read(directory/'summary.json')
        assert result['session_id']==f'v6_source_live_20260831_s{i:02d}' and result['policy_seed']==2026092800+i
        assert result['successful_hands']==8 and result['status']=='PASS' and summary['status']=='COMPLETED'
        assert summary['model_sha256']==probe.SOURCE_SHA and summary['error_type'] is None
        assert probe.sha(directory/'journal.jsonl')==summary['journal_sha256']==result['journal_sha256']
        assert probe.sha(directory/'hands.jsonl')==summary['hands_sha256']==result['hands_sha256']
        assert not result['pending_request_id'] and not result['protocol_failures'] and not result['committed_without_raw']
        assert not result['partial_journal'] and not result['partial_hands']
        assert all(probe.sha(p)==h for p,h in summary['runtime_sha256'].items())
        rows=probe.lines(directory/'hands.jsonl')
        assert [r['successful_hand'] for r in rows]==list(range(1,9))
        assert all(r['model_sha256']==probe.SOURCE_SHA and r['terminal_validation']['status']=='PASS' for r in rows)
        assert result['decision_replays']==sum(len(r['decisions']) for r in rows)
        hands+=rows
    coverage=dict(terminal_kind=dict(Counter(r['terminal_validation']['terminal_kind'] for r in hands)),
                  seat=dict(Counter(str(r['terminal_response']['client_pos']) for r in hands)),
                  board_cards=dict(Counter(str(len(r['terminal_response']['board'])) for r in hands)),
                  full_stack_action_hands=sum('b20000' in r['terminal_response']['action'] for r in hands))
    report=dict(status='PASS',reviewed_at=datetime.now(timezone.utc).isoformat(),decision='OBSERVED_LIVE_PROTOCOL_READY',
                new_training_hands=0,evaluation_hands=16,slumbot_hands=16,real_api_requests=sum(r['request_count'] for r in combined['results']),
                unique_saved_decisions_replayed=sum(r['decision_replays'] for r in combined['results']),coverage=coverage,
                checkpoint_sha256=probe.SOURCE_SHA,strength_qualified=False,qualification_admitted=False,
                server_rng_independence_proven=False,probe_source_pairs_verified=len(probe.read(BASE/'execution_code/copy_manifest.json')),
                protected_matrix_source_pairs_verified=77,offline_readiness_source_pairs_verified=76)
    directory=BASE/'review_code'
    directory.mkdir(exist_ok=False)
    relative=Path(__file__).resolve().relative_to(ROOT).as_posix()
    probe.capture_code_provenance(ROOT,directory,[relative])
    target=directory/'source_files'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,target)
    probe.write(directory/'copy_manifest.json',[dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=probe.sha(target))])
    probe.write(BASE/'reviewed_analysis.json',report)
    text='# Corrected-v6 source live protocol readiness\n\n'
    text+='Two fresh eight-hand sessions completed without retries, replacements or unknown requests. Both clients exited0; full independent journal/RNG/terminal/frozen-model replay and cross-session token-chain audits passed.\n\n'
    text+=f'Observed {report["real_api_requests"]}real API requests and {report["unique_saved_decisions_replayed"]}unique saved model decisions. Coverage: {json.dumps(coverage)}.\n\n'
    text+='This establishes only observed live protocol readiness for these16hands, not universal API compatibility, independence of server RNG, policy strength or100k qualification. No win-rate selection or confidence interval was made. Keep these16hands excluded from any later baseline. Existing league matrix evidence/configuration and all77captured source pairs remain unchanged.\n'
    (BASE/'result_summary.md').write_text(text)
    probe.log('--command',f'python research/experiments/{BASE.name}/review_finish.py',
        *[v for path in [BASE/'reviewed_analysis.json',BASE/'result_summary.md',directory/'source_manifest.json',directory/'code.patch',directory/'copy_manifest.json'] for v in ['--artifact',path]])
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
        '--summary','Exactly16real source hands/2fresh sessions passed journaled live protocol and frozen-model replay; no strength inference.',
        '--conclusion','Observed live protocol evidence is valid; coverage is limited and server RNG independence/100k strength remain unproven.',
        '--decision','OBSERVED_LIVE_PROTOCOL_READY','--next-step','Preregister a separate fixed fresh corrected-v6 source Slumbot baseline; exclude all16probe hands and keep active league matrix unchanged.',
        '--count','new_training_hands=0','--count','evaluation_hands=16','--count','slumbot_hands=16'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__=='__main__': main()
