param([switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path '.').Path
$runId = 'v5_hybrid_h6_treatment_kles003_same31400_20m_r1_20260713'
$runDir = Join-Path $Repo "models/alpha_holdem_v5_hybrid/$runId"
$source = (Resolve-Path 'models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709/v5_exp005_cutover_gate31400_checkpoint.pt').Path
$control = (Resolve-Path 'models/alpha_holdem_v5_hybrid/v5_hybrid_h2_control_allinonly_same31400_20m_r1_20260713/h2_control_endpoint.pt').Path
$prereg = (Resolve-Path 'reports/v5_hybrid_h6_preregistration_20260713.json').Path
$lock = (Resolve-Path 'reports/v5_hybrid_h6_design_lock_20260713.json').Path
$preflight = (Resolve-Path 'reports/v5_hybrid_h6_preflight_20260713.json').Path
$expectedLockSha = 'd74b5018476f65cba17fde2c0434d7b616d41ed22b5b5bbf1d8e72c281ed2854'
if ((Get-FileHash $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e') { throw 'source hash mismatch' }
if ((Get-FileHash $control -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b') { throw 'control hash mismatch' }
if ((Get-FileHash $prereg -Algorithm SHA256).Hash.ToLowerInvariant() -ne '6b8ba0e4b396d74e1daf15bc9cb93a1018b671ec064f2ad591957c897ea46225') { throw 'prereg hash mismatch' }
if ((Get-FileHash $lock -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedLockSha) { throw 'design lock hash mismatch' }
$preflightValue = Get-Content -LiteralPath $preflight -Raw | ConvertFrom-Json
if ($preflightValue.overall -ne 'PASS_READY_TREATMENT_LAUNCH' -or $preflightValue.design_lock_sha256 -ne $expectedLockSha) { throw 'preflight is not exact PASS' }
$active = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*train_v5.py*' -and $_.CommandLine -like '*v5_hybrid_h6_*' }
$ready = (-not $active) -and (-not (Test-Path -LiteralPath $runDir))
$state = [pscustomobject]@{ ready = $ready; run_dir_absent = (-not (Test-Path -LiteralPath $runDir)); active_h6_trainers = @($active).Count; design_lock_sha256 = $expectedLockSha; preflight = $preflightValue.overall }
if ($ValidateOnly) { $state | ConvertTo-Json -Depth 5; exit $(if ($ready) { 0 } else { 3 }) }
if (-not $ready) { throw 'H6 launch is not duplicate-safe ready' }

$mirrorDir = (Resolve-Path 'reports/h6_mirror_001_20260713').Path
$mirrorManifest = Join-Path $mirrorDir 'manifest.json'
$mirrorLock = Join-Path $mirrorDir 'measurement_lock.json'
$mirrorLockSha = (Get-FileHash $mirrorLock -Algorithm SHA256).Hash.ToLowerInvariant()
$controlOut = Join-Path $mirrorDir 'control_pairs.jsonl'
if (Test-Path -LiteralPath $controlOut) { throw 'H6 control mirror output already exists' }
$mirrorArgs = @('-u','scripts/alpha_holdem/v5_hybrid_h6_mirror.py','run-arm','--manifest',$mirrorManifest,'--endpoint',$control,'--arm','control','--out',$controlOut,'--device','cpu','--priority','below-normal','--torch-threads','1','--torch-interop-threads','1','--measurement-lock',$mirrorLock,'--expected-lock-sha256',$mirrorLockSha)
$mirror = Start-Process python -ArgumentList $mirrorArgs -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $mirrorDir 'control.out.log') -RedirectStandardError (Join-Path $mirrorDir 'control.err.log') -WindowStyle Hidden -PassThru

New-Item -ItemType Directory -Path $runDir | Out-Null
$provenance = Join-Path $runDir 'opponent_assignment_provenance.jsonl'
$out = Join-Path $runDir 'latest.pt'
$trainerArgs = @(
    '-u','scripts/alpha_holdem/train_v5.py',
    '--resume',$source,'--allow-resume','--reset-optimizer',
    '--run-id',$runId,'--run-dir',$runDir,'--out',$out,'--total-hands','535989661',
    '--device','cuda','--workers','22','--hands-per-iter','16384',
    '--rollout-mode','multi','--rollout-envs-per-worker','16','--inference-min-batch-slots','256','--inference-batch-deadline-us','1000',
    '--ppo-epochs','4','--ppo-target-kl','0.03','--mini-batch-size','1024','--lr','0.0003','--gamma','0.999',
    '--entropy-coef','0.05','--entropy-floor','0.3','--seed','20260703','--worker-seed-base','73000','--fixed-training-deal-stream',
    '--opponent-assignment','per-iteration','--opponent-assignment-provenance-file',$provenance,'--pool-strategy','loss-kbest','--k-best','5','--opponent-groups','5','--self-play-fraction','0.2',
    '--mirror-self-play-deals','--allin-runout-ev','--allin-runout-ev-max-runouts','200',
    '--preflop-action-prior-coef','0.01','--preflop-action-prior-target','0.24,0.36,0.38,0.02',
    '--postflop-action-prior-coef','0.02','--postflop-action-prior-target','0.15,0.30,0.52,0.03',
    '--critic-contract','critic_v1','--value-coef','0.5','--save-interval','1','--snapshot-every','200',
    '--h6-window-arm','treatment','--h6-preregistration',$prereg,'--h6-preregistration-sha256','6b8ba0e4b396d74e1daf15bc9cb93a1018b671ec064f2ad591957c897ea46225',
    '--h6-design-lock',$lock,'--h6-design-lock-sha256',$expectedLockSha
)
$trainer = Start-Process python -ArgumentList $trainerArgs -WorkingDirectory $Repo -RedirectStandardOutput (Join-Path $runDir 'console.out.log') -RedirectStandardError (Join-Path $runDir 'console.err.log') -WindowStyle Hidden -PassThru
$deadline = (Get-Date).AddSeconds(120)
while (-not (Test-Path -LiteralPath (Join-Path $runDir 'run_manifest.json'))) {
    if ((Get-Date) -gt $deadline) { Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue; throw 'H6 treatment manifest timeout' }
    if ($trainer.HasExited) { throw "H6 trainer exited before manifest: $($trainer.ExitCode)" }
    Start-Sleep -Seconds 1
}
try {
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/alpha_holdem/v5_rearm_watchers.ps1 -RunDir $runDir
    if ($LASTEXITCODE -ne 0) { throw 'canonical rearm failed' }
} catch {
    Stop-Process -Id $trainer.Id -Force -ErrorAction SilentlyContinue
    throw
}
[pscustomobject]@{ status = 'H6_TREATMENT_LAUNCHED_REARM_PASS'; trainer_pid = $trainer.Id; mirror_control_pid = $mirror.Id; run_id = $runId; design_lock_sha256 = $expectedLockSha } | ConvertTo-Json
