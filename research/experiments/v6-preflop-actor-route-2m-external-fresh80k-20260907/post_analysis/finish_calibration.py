"""Same-record terminal closure; no poker, inference or prior review rerun."""
from pathlib import Path
import json
import subprocess
import sys
import review_completed as review

r = review.r
BASE, ROOT, HERE = review.BASE, review.ROOT, review.HERE

def exact(argv):
    return subprocess.list2cmdline([str(x) for x in argv])

def log(args):
    argv = [sys.executable, '-B', str(ROOT/'research/experiment_log.py'), *args]
    done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    r.protocol.require(done.returncode == 0, done.stdout + done.stderr)
    return done.stdout

def main():
    record = r.read(BASE/'experiment.json')
    r.protocol.require(record['status'] == 'RUNNING' and review.readiness()['ready'], 'not terminal pending closure')
    follow = r.read(HERE/'followthrough_execution.json')
    r.protocol.require(not r.live_identity(follow) and not r.live_identity(follow['review_child']) and
        follow['review_child']['exit_code'] == 0, 'helper still owns review')
    r.protocol.require(r.sha(BASE/'post_terminal_review.json') == follow['review_sha256'], 'review changed')
    report = r.read(BASE/'post_terminal_review.json')
    curve = r.read(HERE/'cross_dose_comparison.json')
    r.protocol.require(report['passed'] and curve['passed'], 'analysis incomplete')
    r.check_hashes(curve['input_sha256'])
    commands = [exact(sys.orig_argv), exact(curve['command']), exact(follow['command']),
                exact(follow['review_child']['command'])]
    for name in ('qualification.json', 'followthrough_qualification.json'):
        q = r.read(HERE/name)
        r.protocol.require(q['passed'] and q['exit_code'] == 0, 'qualification changed')
        r.check_hashes(q['source_sha256'])
        commands += [exact(q['outer_argv']), exact(q['pytest_argv'])]
    commands += [f'powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/{BASE.name}/post_analysis/launch_followthrough.ps1']
    artifacts = {p.resolve() for p in HERE.iterdir() if p.is_file()}
    artifacts.update(p.resolve() for p in BASE.glob('controller*') if p.is_file())
    artifacts.update((BASE/name).resolve() for name in ('result_summary.md','post_terminal_review.json'))
    counts = dict(new_training_hands=0,evaluation_hands=80000,slumbot_hands=80000,
                  final_qualification_hands=0,lineage_training_hands=12596243)
    metrics = dict(terminal_review_passed=True,current_decision_replays=244034,
        controller_execution_wall_seconds=report['execution_wall_seconds'],
        external_statistics=report['statistics'],cross_dose_changes=curve['changes_2m_minus_1m'],goal_achieved=False)
    payload = []
    for flag, mapping in (('--count',counts),('--metric',metrics)):
        for key,value in mapping.items():
            payload += [flag,key+'='+json.dumps(value,separators=(',',':'),allow_nan=False)]
    seen = {row['command'] for row in record['commands']}
    for command in dict.fromkeys(commands):
        if command not in seen: payload += ['--command',command]
    existing = {Path(p).resolve() for p in record['artifacts']}
    for path in sorted(artifacts):
        if path not in existing: payload += ['--artifact',path.relative_to(ROOT).as_posix()]
    payload += ['--note','All32 clients and8 audits plus1 prerun test completed exactly once; one-shot independent reviewer passed. Deferred post-analysis commands and hashes attached after exact owners terminal. Cross-dose comparison only reread retained raw payouts, no replay inference or new requests. Maximum single inherited lineage counter is not a sum or new training. Logger wall includes later analysis; execution wall2835.188s. No model promotion, final qualification or automatic additional training.']
    while payload:
        chunk=[]
        while payload and len(exact([sys.executable,ROOT/'research/experiment_log.py','update',BASE.name,*chunk,*payload[:2]]))<24000:
            chunk += payload[:2]
            del payload[:2]
        r.protocol.require(bool(chunk),'oversized item')
        log(['update',BASE.name,*chunk])
    log(['finish',BASE.name,
         '--summary','Fixed four-policy2M fresh80k complete,41 jobs exit0,244034 decision replays and independent review passed. S1 detached/connected -14.3350/-15.7566; S3 -29.1175/-26.5116 bb100.',
         '--conclusion','No positive endpoint or confirmed replicated actor-route gain. Connected-minus-detached -1.4216/+2.6059; connected2M-minus1M -2.0733/+6.7226. All contrast intervals include0. Internal relative advantage did not obtain external confirmation, but opposite causal effects and long-run impossibility are not established.',
         '--decision','Finish valid calibration without policy promotion, extra Slumbot hands, final test or automatic larger training allocation. Current evidence does not justify unchanged-regimen scale on strength grounds; preserve all endpoints and uncertainty.',
         '--next-step','Inspect retained current-family training opponent coverage and realized update allocation, reusing existing audits and metrics before selecting one general opponent-distribution/objective change with matched control. No Slumbot action-label training or benchmark rules; do not redo completed gradient audits.'])
    final=r.read(BASE/'experiment.json')
    r.protocol.require(final['status']=='COMPLETED','finish failed')
    audit=BASE/'post_finish_audit.json'
    r.protocol.require(not audit.exists(),'preserve audit')
    args=['audit','--since',final['created_at'],'--out-json',str(audit),'--fail-on-warning']
    first=log(args)
    log(['update',BASE.name,'--artifact',audit.relative_to(ROOT).as_posix(),
         '--command',exact([sys.executable,'-B',ROOT/'research/experiment_log.py',*args])])
    last=log(['audit','--since',final['created_at'],'--fail-on-warning'])
    print(json.dumps({'completed':True,'audit':first,'attachment_audit':last,'new_hands':0}))

if __name__=='__main__': main()
