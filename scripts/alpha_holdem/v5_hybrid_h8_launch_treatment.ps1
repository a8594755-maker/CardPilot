param([switch]$ValidateOnly)
$ErrorActionPreference='Stop'
$Repo=(Resolve-Path '.').Path
$controlId='v5_hybrid_h8_control_kles003_nocatch_same32617_20m_r1_20260714'
$runId='v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714'
$controlDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$controlId"
$runDir=Join-Path $Repo "models/alpha_holdem_v5_hybrid/$runId"
$source=(Resolve-Path 'models/alpha_holdem_v5_hybrid/v5_hybrid_h7_treatment_kles003_same31400_20m_r1_20260713/h7_treatment_endpoint.pt').Path
$prereg=(Resolve-Path 'reports/v5_hybrid_h8_preregistration_20260714.json').Path
$lock=(Resolve-Path 'reports/v5_hybrid_h8_design_lock_v5_20260714.json').Path
$expected='298daa368585af79586f3ba24b7fde1ae862de41a8221cdf46c0825d041957c6'
$sourceHash=(Get-FileHash $source -Algorithm SHA256).Hash; if (-not $sourceHash.Equals('948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149',[StringComparison]::OrdinalIgnoreCase)) { throw "source hash actual=$sourceHash" }
$preregHash=(Get-FileHash $prereg -Algorithm SHA256).Hash; if (-not $preregHash.Equals('ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713',[StringComparison]::OrdinalIgnoreCase)) { throw "prereg hash actual=$preregHash" }
$lockHash=(Get-FileHash $lock -Algorithm SHA256).Hash; if (-not $lockHash.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) { throw "lock hash actual=$lockHash" }
$endpoint=Get-Content (Join-Path $controlDir 'h8_control_endpoint_status.json') -Raw|ConvertFrom-Json
$protocol=Get-Content (Join-Path $controlDir 'h8_control_protocol_status.json') -Raw|ConvertFrom-Json
$controlManifest=Get-Content (Join-Path $controlDir 'run_manifest.json') -Raw|ConvertFrom-Json
$controlProcess=Get-Process -Id ([int]$controlManifest.process_id) -ErrorAction SilentlyContinue
$path1=Get-Process -Id 37656 -ErrorAction SilentlyContinue
$mirrorDir=Resolve-Path 'reports/h8_mirror_001_20260714'
$unexpectedMirror=@(Get-ChildItem $mirrorDir|Where-Object{$_.Name -notin @('manifest.json','measurement_lock.json')})
$ready=$endpoint.overall -eq 'PASS' -and $endpoint.state -eq 'ARM_ENDPOINT_FROZEN' -and $protocol.overall -eq 'PASS' -and $protocol.first60.status -eq 'PASS_CONTROL_BASELINE_FROZEN' -and (-not $controlProcess) -and $path1 -and $path1.PriorityClass -eq 'BelowNormal' -and $unexpectedMirror.Count -eq 0 -and (-not (Test-Path $runDir))
if($ValidateOnly){[pscustomobject]@{ready=[bool]$ready;endpoint=$endpoint.state;protocol=$protocol.state;control_process_alive=[bool]$controlProcess;run_dir_absent=(-not(Test-Path $runDir));path1_alive=[bool]$path1;unexpected_mirror_outputs=$unexpectedMirror.Count}|ConvertTo-Json;exit $(if($ready){0}else{3})}
if(-not $ready){throw 'H8 treatment not ready'}
New-Item -ItemType Directory -Path $runDir|Out-Null
$prov=Join-Path $runDir 'opponent_assignment_provenance.jsonl'
$out=Join-Path $runDir 'latest.pt'
$args=@('-u','scripts/alpha_holdem/train_v5.py','--resume',$source,'--allow-resume','--no-reset-optimizer','--run-id',$runId,'--run-dir',$runDir,'--out',$out,'--total-hands','556001286','--device','cuda','--workers','22','--hands-per-iter','16384','--rollout-mode','multi','--rollout-envs-per-worker','16','--inference-min-batch-slots','256','--inference-batch-deadline-us','1000','--ppo-epochs','4','--ppo-target-kl','0.03','--mini-batch-size','1024','--lr','0.0003','--gamma','0.999','--entropy-coef','0.05','--entropy-floor','0.3','--seed','20260703','--worker-seed-base','73000','--fixed-training-deal-stream','--opponent-assignment','per-iteration','--opponent-assignment-provenance-file',$prov,'--pool-strategy','loss-kbest','--k-best','5','--opponent-groups','5','--self-play-fraction','0.2','--mirror-self-play-deals','--allin-runout-ev','--allin-runout-ev-max-runouts','200','--preflop-action-prior-coef','0.01','--preflop-action-prior-target','0.24,0.36,0.38,0.02','--postflop-action-prior-coef','0.02','--postflop-action-prior-target','0.15,0.30,0.52,0.03','--critic-contract','critic_v1','--value-coef','0.5','--save-interval','1','--snapshot-every','200','--h8-window-arm','treatment','--h8-value-head-catchup-after-kl-stop','--h8-preregistration',$prereg,'--h8-preregistration-sha256','ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713','--h8-design-lock',$lock,'--h8-design-lock-sha256',$expected)
$trainer=Start-Process python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $runDir 'console.out.log') -RedirectStandardError (Join-Path $runDir 'console.err.log') -WindowStyle Hidden -PassThru
$deadline=(Get-Date).AddSeconds(180)
while(-not(Test-Path(Join-Path $runDir 'run_manifest.json'))){
 if((Get-Date)-gt$deadline){Stop-Process -Id $trainer.Id -Force;throw 'manifest timeout'}
 if($trainer.HasExited){throw"trainer exited $($trainer.ExitCode): $((Get-Content (Join-Path $runDir 'console.err.log') -Raw -ErrorAction SilentlyContinue))"}
 Start-Sleep 1
}
$manifest=Get-Content (Join-Path $runDir 'run_manifest.json') -Raw|ConvertFrom-Json
if($manifest.run_id -ne $runId -or $manifest.config.h8_window_arm -ne 'treatment' -or (-not [bool]$manifest.config.h8_value_head_catchup_after_kl_stop) -or $manifest.config.h8_design_lock_sha256 -ne $expected){Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw 'manifest H8 treatment identity'}
try{powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alpha_holdem/v5_rearm_watchers.ps1 -RunDir $runDir;if($LASTEXITCODE -ne 0){throw 'rearm failed'}}catch{Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue;throw}
[pscustomobject]@{status='H8_TREATMENT_LAUNCHED_REARM_PASS';trainer_pid=$trainer.Id;run_id=$runId;design_lock_sha256=$expected;path1_pid=37656}|ConvertTo-Json
