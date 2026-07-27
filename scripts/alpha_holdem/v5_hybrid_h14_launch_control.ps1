param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$Repo=(Resolve-Path '.').Path
$runId='v5_hybrid_h14_control_catchmse_same35051_20m_r1_20260717'
$runDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$runId"
$source=(Resolve-Path 'models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt').Path
$prereg=(Resolve-Path 'reports/v5_hybrid_h14_preregistration_20260717.json').Path
$lock=(Resolve-Path 'reports/v5_hybrid_h14_design_lock_v6_20260717.json').Path
$preflight=(Resolve-Path 'reports/v5_hybrid_h14_preflight_v6_20260717.json').Path
$expected=(Get-FileHash $lock -Algorithm SHA256).Hash.ToLowerInvariant()
$sentinel=Join-Path $Repo 'reports/v5_active_window.json'
$sourceHash=(Get-FileHash $source -Algorithm SHA256).Hash; if (-not $sourceHash.Equals('96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13',[StringComparison]::OrdinalIgnoreCase)) { throw "source hash actual=$sourceHash" }
$preregHash=(Get-FileHash $prereg -Algorithm SHA256).Hash; if (-not $preregHash.Equals('822b0de748eea8fa360cfdf64b09677fd159cb01179e3cd8620e6527b70fa35d',[StringComparison]::OrdinalIgnoreCase)) { throw "prereg hash actual=$preregHash" }
$lockHash=(Get-FileHash $lock -Algorithm SHA256).Hash; if (-not $lockHash.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) { throw "lock hash actual=$lockHash" }
$pf=Get-Content $preflight -Raw|ConvertFrom-Json
$path1=Get-Process -Id 23720 -ErrorAction SilentlyContinue
$ready=$pf.overall -eq 'PASS_READY_H14_CONTROL_LAUNCH' -and $pf.design_lock_sha256 -eq $expected -and $path1 -and $path1.PriorityClass -eq 'BelowNormal' -and (-not(Test-Path $runDir))
if($ValidateOnly){[pscustomobject]@{ready=[bool]$ready;run_dir_absent=(-not(Test-Path $runDir));path1_alive=[bool]$path1;path1_priority=if($path1){[string]$path1.PriorityClass}else{$null};preflight=$pf.overall}|ConvertTo-Json;exit $(if($ready){0}else{3})}
if(-not $ready){throw 'H14 control not ready'}
$perf=Join-Path $Repo 'reports/v5_hybrid_h14_control_perf_cal_20260717.json'
$perfAudit=Join-Path $Repo 'reports/v5_hybrid_h14_control_perf_cal_audit_20260717.json'
if(-not(Test-Path $perf)){
 python scripts/alpha_holdem/v5_hybrid_h14_perf_cal.py --source $source --source-sha256 '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13' --arm control --seed 2026071703 --batch-size 1024 --warmup 10 --steps 40 --repeats 3 --device cuda --path1-pid 23720 --path1-workers 6 --out $perf
 if($LASTEXITCODE -ne 0){throw 'H14 control PERF-CAL failed closed'}
}
if(-not(Test-Path $perfAudit)){
 python scripts/alpha_holdem/v5_hybrid_h14_perf_cal_audit.py --artifact $perf --tool scripts/alpha_holdem/v5_hybrid_h14_perf_cal.py --out $perfAudit
 if($LASTEXITCODE -ne 0){throw 'H14 control PERF-CAL audit failed closed'}
}
$perfValue=Get-Content $perf -Raw|ConvertFrom-Json
$perfAuditValue=Get-Content $perfAudit -Raw|ConvertFrom-Json
$perfHash=(Get-FileHash $perf -Algorithm SHA256).Hash.ToLowerInvariant()
if($perfValue.overall -ne 'PASS' -or $perfValue.arm -ne 'control' -or [double]$perfValue.timing.smooth_l1_over_mse_throughput_ratio -lt 0.95 -or $perfAuditValue.overall -ne 'PASS' -or $perfAuditValue.artifact_sha256 -ne $perfHash){throw 'H14 control immutable PERF-CAL evidence invalid'}
python scripts/alpha_holdem/v5_hybrid_h14_active_window.py activate --sentinel $sentinel --design-lock $lock --expected-lock-sha256 $expected --arm control --run-id $runId
if($LASTEXITCODE -ne 0){throw 'H14 control active-window activation failed'}
New-Item -ItemType Directory -Path $runDir|Out-Null
$prov=Join-Path $runDir 'opponent_assignment_provenance.jsonl'
$out=Join-Path $runDir 'latest.pt'
$args=@('-u','scripts/alpha_holdem/train_v5.py','--resume',$source,'--allow-resume','--no-reset-optimizer','--run-id',$runId,'--run-dir',$runDir,'--out',$out,'--total-hands','596021901','--device','cuda','--workers','22','--hands-per-iter','16384','--rollout-mode','multi','--rollout-envs-per-worker','16','--inference-min-batch-slots','256','--inference-batch-deadline-us','1000','--ppo-epochs','4','--ppo-target-kl','0.03','--mini-batch-size','1024','--lr','0.0003','--gamma','0.999','--entropy-coef','0.05','--entropy-floor','0.3','--seed','20260703','--worker-seed-base','73000','--fixed-training-deal-stream','--opponent-assignment','per-iteration','--opponent-assignment-provenance-file',$prov,'--pool-strategy','loss-kbest','--k-best','5','--opponent-groups','5','--self-play-fraction','0.2','--mirror-self-play-deals','--allin-runout-ev','--allin-runout-ev-max-runouts','200','--preflop-action-prior-coef','0.01','--preflop-action-prior-target','0.24,0.36,0.38,0.02','--postflop-action-prior-coef','0.02','--postflop-action-prior-target','0.15,0.30,0.52,0.03','--critic-contract','critic_v1','--value-coef','0.5','--save-interval','1','--snapshot-every','200','--h14-window-arm','control','--h8-value-head-catchup-after-kl-stop','--h14-catchup-loss','mse','--h14-catchup-smooth-l1-beta','1.0','--h14-preregistration',$prereg,'--h14-preregistration-sha256','822b0de748eea8fa360cfdf64b09677fd159cb01179e3cd8620e6527b70fa35d','--h14-design-lock',$lock,'--h14-design-lock-sha256',$expected)
$trainer=Start-Process python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $runDir 'console.out.log') -RedirectStandardError (Join-Path $runDir 'console.err.log') -WindowStyle Hidden -PassThru
$deadline=(Get-Date).AddSeconds(180)
while(-not(Test-Path(Join-Path $runDir 'run_manifest.json'))){
 if((Get-Date)-gt$deadline){Stop-Process -Id $trainer.Id -Force;throw 'manifest timeout'}
 if($trainer.HasExited){throw"trainer exited $($trainer.ExitCode): $((Get-Content (Join-Path $runDir 'console.err.log') -Raw -ErrorAction SilentlyContinue))"}
 Start-Sleep 1
}
$manifest=Get-Content (Join-Path $runDir 'run_manifest.json') -Raw|ConvertFrom-Json
if($manifest.run_id -ne $runId -or $manifest.config.h14_window_arm -ne 'control' -or (-not [bool]$manifest.config.h8_value_head_catchup_after_kl_stop) -or $manifest.config.h14_catchup_loss -ne 'mse' -or $manifest.config.h14_design_lock_sha256 -ne $expected){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw 'manifest H14 control identity'}
try{
 powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alpha_holdem/v5_rearm_watchers.ps1 -RunDir $runDir
 if($LASTEXITCODE -ne 0){throw 'rearm failed'}
 $rearmStatus=Get-Content (Join-Path $runDir 'watcher_rearm_status.json') -Raw|ConvertFrom-Json
 if(-not [bool]$rearmStatus.survival_pass){throw 'rearm survival_pass=false'}
}catch{Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw}
[pscustomobject]@{status='H14_CONTROL_LAUNCHED_REARM_PASS';trainer_pid=$trainer.Id;run_id=$runId;design_lock_sha256=$expected;path1_pid=23720}|ConvertTo-Json
