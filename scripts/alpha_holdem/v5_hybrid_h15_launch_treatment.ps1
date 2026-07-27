param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$Repo=(Resolve-Path '.').Path
$controlId='v5_hybrid_h15_control_catchmse_same35051_20m_r1_20260719'
$runId='v5_hybrid_h15_treatment_catchsmoothl1b1_same35051_20m_r1_20260719'
$controlDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$controlId"
$runDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$runId"
$source=(Resolve-Path 'models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt').Path
$prereg=(Resolve-Path 'reports/v5_hybrid_h15_preregistration_20260719.json').Path
$lock=(Resolve-Path 'reports/v5_hybrid_h15_design_lock_v3_20260719.json').Path
$expected=(Get-FileHash $lock -Algorithm SHA256).Hash.ToLowerInvariant()
$sentinel=Join-Path $Repo 'reports/v5_active_window.json'
$sourceHash=(Get-FileHash $source -Algorithm SHA256).Hash; if (-not $sourceHash.Equals('96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13',[StringComparison]::OrdinalIgnoreCase)) { throw "source hash actual=$sourceHash" }
$preregHash=(Get-FileHash $prereg -Algorithm SHA256).Hash; if (-not $preregHash.Equals('5631c27c29f1379ea16c5b246dccc312e830a2e50d5335dfac531798c882582c',[StringComparison]::OrdinalIgnoreCase)) { throw "prereg hash actual=$preregHash" }
$lockHash=(Get-FileHash $lock -Algorithm SHA256).Hash; if (-not $lockHash.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) { throw "lock hash actual=$lockHash" }
$endpoint=Get-Content (Join-Path $controlDir 'h15_control_endpoint_status.json') -Raw|ConvertFrom-Json
$protocol=Get-Content (Join-Path $controlDir 'h15_control_protocol_status.json') -Raw|ConvertFrom-Json
$controlManifest=Get-Content (Join-Path $controlDir 'run_manifest.json') -Raw|ConvertFrom-Json
$controlProcess=Get-Process -Id ([int]$controlManifest.process_id) -ErrorAction SilentlyContinue
$path1Rows=@(Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $c=[string]$_.CommandLine; $c -like '*solve-v3-parallel.ts*' -and $c -like '*pipeline_srp_v3_200bb*' -and $c -like '*pipeline_v3_hu_srp_200bb_legalallin_v2*' })
$path1Pid=if($path1Rows.Count -eq 1){[int]$path1Rows[0].ProcessId}else{-1}
$path1=if($path1Pid -gt 0){Get-Process -Id $path1Pid -ErrorAction SilentlyContinue}else{$null}
$path1Workers=if($path1Pid -gt 0){@(Get-CimInstance Win32_Process | Where-Object { $c=([string]$_.CommandLine).Replace('\','/'); [int]$_.ParentProcessId -eq $path1Pid -and $c -like '*cfr-solver/src/orchestration/solve-worker.ts*' })}else{@()}
$mirrorDir=Resolve-Path 'reports/h15_mirror_001_v3_20260719'
$unexpectedMirror=@(Get-ChildItem $mirrorDir|Where-Object{$_.Name -notin @('manifest.json','measurement_lock.json')})
$controlOrdered=Get-CimInstance Win32_Process | Where-Object { ([string]$_.CommandLine) -like '*v5_hybrid_h15_ordered_rearm.py*' -and ([string]$_.CommandLine) -like '*--arm control*' }
$ready=$endpoint.overall -eq 'PASS' -and $endpoint.state -eq 'ARM_ENDPOINT_FROZEN' -and $protocol.overall -eq 'PASS' -and $protocol.first60.status -eq 'PASS_CONTROL_BASELINE_FROZEN' -and (-not $controlProcess) -and (-not $controlOrdered) -and $path1 -and $path1.PriorityClass -eq 'BelowNormal' -and $path1Workers.Count -eq 6 -and $unexpectedMirror.Count -eq 0 -and (-not (Test-Path $runDir))
if($ValidateOnly){[pscustomobject]@{ready=[bool]$ready;endpoint=$endpoint.state;protocol=$protocol.state;control_process_alive=[bool]$controlProcess;control_ordered_supervisor_alive=[bool]$controlOrdered;run_dir_absent=(-not(Test-Path $runDir));path1_pid=$path1Pid;path1_workers=$path1Workers.Count;unexpected_mirror_outputs=$unexpectedMirror.Count}|ConvertTo-Json;exit $(if($ready){0}else{3})}
if(-not $ready){throw 'H15 treatment not ready'}
$controlPerf=Join-Path $Repo 'reports/v5_hybrid_h15_control_perf_cal_20260719.json'
$perf=Join-Path $Repo 'reports/v5_hybrid_h15_treatment_perf_cal_20260719.json'
$perfAudit=Join-Path $Repo 'reports/v5_hybrid_h15_treatment_perf_cal_audit_20260719.json'
if(-not(Test-Path $controlPerf)){throw 'H15 treatment requires immutable control PERF-CAL baseline'}
if(-not(Test-Path $perf)){
 python scripts/alpha_holdem/v5_hybrid_h15_perf_cal.py --source $source --source-sha256 '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13' --arm treatment --control-baseline $controlPerf --seed 2026071906 --batch-size 1024 --warmup 10 --steps 40 --repeats 3 --device cuda --path1-pid $path1Pid --path1-workers 6 --out $perf
 if($LASTEXITCODE -ne 0){throw 'H15 treatment PERF-CAL failed closed'}
}
if(-not(Test-Path $perfAudit)){
 python scripts/alpha_holdem/v5_hybrid_h15_perf_cal_audit.py --artifact $perf --tool scripts/alpha_holdem/v5_hybrid_h15_perf_cal.py --control-baseline $controlPerf --out $perfAudit
 if($LASTEXITCODE -ne 0){throw 'H15 treatment PERF-CAL audit failed closed'}
}
$perfValue=Get-Content $perf -Raw|ConvertFrom-Json
$perfAuditValue=Get-Content $perfAudit -Raw|ConvertFrom-Json
$perfHash=(Get-FileHash $perf -Algorithm SHA256).Hash.ToLowerInvariant()
if($perfValue.overall -ne 'PASS' -or $perfValue.arm -ne 'treatment' -or [double]$perfValue.timing.smooth_l1_over_mse_throughput_ratio -lt 0.95 -or [double]$perfValue.timing.common_mse_baseline_match_ratio -lt 0.95 -or $perfAuditValue.overall -ne 'PASS' -or $perfAuditValue.artifact_sha256 -ne $perfHash){throw 'H15 treatment immutable PERF-CAL evidence invalid'}
python scripts/alpha_holdem/v5_hybrid_h15_active_window.py activate --sentinel $sentinel --design-lock $lock --expected-lock-sha256 $expected --arm treatment --run-id $runId
if($LASTEXITCODE -ne 0){throw 'H15 treatment active-window activation failed'}
New-Item -ItemType Directory -Path $runDir|Out-Null
$prov=Join-Path $runDir 'opponent_assignment_provenance.jsonl'
$out=Join-Path $runDir 'latest.pt'
$args=@('-u','scripts/alpha_holdem/train_v5.py','--resume',$source,'--allow-resume','--no-reset-optimizer','--run-id',$runId,'--run-dir',$runDir,'--out',$out,'--total-hands','596021901','--device','cuda','--workers','22','--hands-per-iter','16384','--rollout-mode','multi','--rollout-envs-per-worker','16','--inference-min-batch-slots','256','--inference-batch-deadline-us','1000','--ppo-epochs','4','--ppo-target-kl','0.03','--mini-batch-size','1024','--lr','0.0003','--gamma','0.999','--entropy-coef','0.05','--entropy-floor','0.3','--seed','20260703','--worker-seed-base','73000','--fixed-training-deal-stream','--opponent-assignment','per-iteration','--opponent-assignment-provenance-file',$prov,'--pool-strategy','loss-kbest','--k-best','5','--opponent-groups','5','--self-play-fraction','0.2','--mirror-self-play-deals','--allin-runout-ev','--allin-runout-ev-max-runouts','200','--preflop-action-prior-coef','0.01','--preflop-action-prior-target','0.24,0.36,0.38,0.02','--postflop-action-prior-coef','0.02','--postflop-action-prior-target','0.15,0.30,0.52,0.03','--critic-contract','critic_v1','--value-coef','0.5','--save-interval','1','--snapshot-every','200','--h15-window-arm','treatment','--h8-value-head-catchup-after-kl-stop','--h15-catchup-loss','smooth_l1','--h15-catchup-smooth-l1-beta','1.0','--h15-preregistration',$prereg,'--h15-preregistration-sha256','5631c27c29f1379ea16c5b246dccc312e830a2e50d5335dfac531798c882582c','--h15-design-lock',$lock,'--h15-design-lock-sha256',$expected)
$trainer=Start-Process python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $runDir 'console.out.log') -RedirectStandardError (Join-Path $runDir 'console.err.log') -WindowStyle Hidden -PassThru
$deadline=(Get-Date).AddSeconds(180)
while(-not(Test-Path(Join-Path $runDir 'run_manifest.json'))){
 if((Get-Date)-gt$deadline){Stop-Process -Id $trainer.Id -Force;throw 'manifest timeout'}
 if($trainer.HasExited){throw"trainer exited $($trainer.ExitCode): $((Get-Content (Join-Path $runDir 'console.err.log') -Raw -ErrorAction SilentlyContinue))"}
 Start-Sleep 1
}
$manifest=Get-Content (Join-Path $runDir 'run_manifest.json') -Raw|ConvertFrom-Json
if($manifest.run_id -ne $runId -or $manifest.config.h15_window_arm -ne 'treatment' -or (-not [bool]$manifest.config.h8_value_head_catchup_after_kl_stop) -or $manifest.config.h15_catchup_loss -ne 'smooth_l1' -or $manifest.config.h15_design_lock_sha256 -ne $expected){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw 'manifest H15 treatment identity'}
$priorCompletion=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $command=[string]$_.CommandLine
    $command -like '*v5_hybrid_h15_completion_watch.py*' -and $command -like "*$controlId*"
})
if($priorCompletion.Count -gt 1){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw "multiple prior H15 completion supervisors: $($priorCompletion.ProcessId -join ',')"}
$retiredCompletionPid=$null
if($priorCompletion.Count -eq 1){
    $retiredCompletionPid=[int]$priorCompletion[0].ProcessId
    Stop-Process -Id $retiredCompletionPid -Force -ErrorAction Stop
    Start-Sleep -Milliseconds 300
    if(Get-Process -Id $retiredCompletionPid -ErrorAction SilentlyContinue){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw 'prior H15 completion supervisor did not exit'}
}
try{
 powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alpha_holdem/v5_rearm_watchers.ps1 -RunDir $runDir
 if($LASTEXITCODE -ne 0){throw 'rearm failed'}
 $rearmStatus=Get-Content (Join-Path $runDir 'watcher_rearm_status.json') -Raw|ConvertFrom-Json
 if(-not [bool]$rearmStatus.survival_pass){throw 'rearm survival_pass=false'}
 $orderedPath=Join-Path $runDir 'h15_ordered_rearm_status.json';$orderedDeadline=(Get-Date).AddSeconds(190);$ordered=$null
 while((Get-Date)-lt$orderedDeadline){if(Test-Path $orderedPath){$ordered=Get-Content $orderedPath -Raw|ConvertFrom-Json;if($ordered.overall -eq 'PASS' -and $ordered.state -eq 'ORDERED_REARM_PASS_SUPERVISING'){break};if($ordered.overall -in @('FAIL','FAIL_CLOSED')){throw "ordered rearm failed: $($ordered.error)"}};if($trainer.HasExited){throw "trainer exited before ordered rearm readiness"};Start-Sleep 1}
 if($null -eq $ordered -or $ordered.state -ne 'ORDERED_REARM_PASS_SUPERVISING'){throw 'ordered rearm readiness timeout'}
}catch{Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw}
[pscustomobject]@{status='H15_TREATMENT_LAUNCHED_REARM_PASS';trainer_pid=$trainer.Id;run_id=$runId;design_lock_sha256=$expected;path1_pid=$path1Pid;ordered_rearm_state=$ordered.state;retired_control_completion_pid=$retiredCompletionPid}|ConvertTo-Json
