param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$Repo=(Resolve-Path '.').Path
$runId='v5_hybrid_h9_control_catchmse_same33834_20m_r1_20260714'
$runDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$runId"
$source=(Resolve-Path 'models/alpha_holdem_v5_hybrid/v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714/h8_treatment_endpoint.pt').Path
$prereg=(Resolve-Path 'reports/v5_hybrid_h9_preregistration_20260714.json').Path
$lock=(Resolve-Path 'reports/v5_hybrid_h9_design_lock_20260714.json').Path
$preflight=(Resolve-Path 'reports/v5_hybrid_h9_preflight_20260714.json').Path
$expected='30071df4fa72ddf9c4244eace4e9ed4cbe8186d7e3c53d93fde0f2044687d81e'
$sourceHash=(Get-FileHash $source -Algorithm SHA256).Hash; if (-not $sourceHash.Equals('7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438',[StringComparison]::OrdinalIgnoreCase)) { throw "source hash actual=$sourceHash" }
$preregHash=(Get-FileHash $prereg -Algorithm SHA256).Hash; if (-not $preregHash.Equals('05bcb04a34cff546cce2159ecdee3e31850c54e0f8a9f37accb30090a100f84b',[StringComparison]::OrdinalIgnoreCase)) { throw "prereg hash actual=$preregHash" }
$lockHash=(Get-FileHash $lock -Algorithm SHA256).Hash; if (-not $lockHash.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) { throw "lock hash actual=$lockHash" }
$preflightHash=(Get-FileHash $preflight -Algorithm SHA256).Hash; if (-not $preflightHash.Equals('79d84c38264153f37ed53c88a4f05818788a9aacec62647fcb0f62dd97f6aac6',[StringComparison]::OrdinalIgnoreCase)) { throw "preflight hash actual=$preflightHash" }
$pf=Get-Content $preflight -Raw|ConvertFrom-Json
$path1=Get-Process -Id 37656 -ErrorAction SilentlyContinue
$ready=$pf.overall -eq 'PASS_READY_H9_CONTROL_LAUNCH' -and $pf.design_lock_sha256 -eq $expected -and $path1 -and $path1.PriorityClass -eq 'BelowNormal' -and (-not(Test-Path $runDir))
if($ValidateOnly){[pscustomobject]@{ready=[bool]$ready;run_dir_absent=(-not(Test-Path $runDir));path1_alive=[bool]$path1;path1_priority=if($path1){[string]$path1.PriorityClass}else{$null};preflight=$pf.overall}|ConvertTo-Json;exit $(if($ready){0}else{3})}
if(-not $ready){throw 'H9 control not ready'}
New-Item -ItemType Directory -Path $runDir|Out-Null
$prov=Join-Path $runDir 'opponent_assignment_provenance.jsonl'
$out=Join-Path $runDir 'latest.pt'
$args=@('-u','scripts/alpha_holdem/train_v5.py','--resume',$source,'--allow-resume','--no-reset-optimizer','--run-id',$runId,'--run-dir',$runDir,'--out',$out,'--total-hands','576011085','--device','cuda','--workers','22','--hands-per-iter','16384','--rollout-mode','multi','--rollout-envs-per-worker','16','--inference-min-batch-slots','256','--inference-batch-deadline-us','1000','--ppo-epochs','4','--ppo-target-kl','0.03','--mini-batch-size','1024','--lr','0.0003','--gamma','0.999','--entropy-coef','0.05','--entropy-floor','0.3','--seed','20260703','--worker-seed-base','73000','--fixed-training-deal-stream','--opponent-assignment','per-iteration','--opponent-assignment-provenance-file',$prov,'--pool-strategy','loss-kbest','--k-best','5','--opponent-groups','5','--self-play-fraction','0.2','--mirror-self-play-deals','--allin-runout-ev','--allin-runout-ev-max-runouts','200','--preflop-action-prior-coef','0.01','--preflop-action-prior-target','0.24,0.36,0.38,0.02','--postflop-action-prior-coef','0.02','--postflop-action-prior-target','0.15,0.30,0.52,0.03','--critic-contract','critic_v1','--value-coef','0.5','--save-interval','1','--snapshot-every','200','--h9-window-arm','control','--h8-value-head-catchup-after-kl-stop','--h9-catchup-loss','mse','--h9-catchup-smooth-l1-beta','1.0','--h9-preregistration',$prereg,'--h9-preregistration-sha256','05bcb04a34cff546cce2159ecdee3e31850c54e0f8a9f37accb30090a100f84b','--h9-design-lock',$lock,'--h9-design-lock-sha256',$expected)
$trainer=Start-Process python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $runDir 'console.out.log') -RedirectStandardError (Join-Path $runDir 'console.err.log') -WindowStyle Hidden -PassThru
$deadline=(Get-Date).AddSeconds(180)
while(-not(Test-Path(Join-Path $runDir 'run_manifest.json'))){
 if((Get-Date)-gt$deadline){Stop-Process -Id $trainer.Id -Force;throw 'manifest timeout'}
 if($trainer.HasExited){throw"trainer exited $($trainer.ExitCode): $((Get-Content (Join-Path $runDir 'console.err.log') -Raw -ErrorAction SilentlyContinue))"}
 Start-Sleep 1
}
$manifest=Get-Content (Join-Path $runDir 'run_manifest.json') -Raw|ConvertFrom-Json
if($manifest.run_id -ne $runId -or $manifest.config.h9_window_arm -ne 'control' -or (-not [bool]$manifest.config.h8_value_head_catchup_after_kl_stop) -or $manifest.config.h9_catchup_loss -ne 'mse' -or $manifest.config.h9_design_lock_sha256 -ne $expected){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw 'manifest H9 control identity'}
try{powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alpha_holdem/v5_rearm_watchers.ps1 -RunDir $runDir;if($LASTEXITCODE -ne 0){throw 'rearm failed'}}catch{Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw}
[pscustomobject]@{status='H9_CONTROL_LAUNCHED_REARM_PASS';trainer_pid=$trainer.Id;run_id=$runId;design_lock_sha256=$expected;path1_pid=37656}|ConvertTo-Json
