param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [string]$ControlEndpointStatus = "reports\v5_exp005c_control_endpoint_freeze_status.json",
    [int]$PollSeconds = 30,
    [int]$PostLaunchIdentityTimeoutSeconds = 90,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
Set-Location $Repo
$LockPath = "reports\v5_exp005c_design_lock_v2_20260710.json"
$LockSha = "2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007"
$SourceRun = "models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709"
$SourceCheckpoint = "$SourceRun\v5_exp005_cutover_gate31400_checkpoint.pt"
$SourceSha = "bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e"
$RunId = "v5_zero_l6_exp005c_treatment_pergroup5_same31400_20m_r1_20260710"
$RunDir = "models\alpha_holdem_v5_from_zero\$RunId"
$StatusPath = "reports\v5_exp005c_treatment_launch_watch_status.json"

function Read-Json([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return Get-Content $Path -Raw | ConvertFrom-Json } catch { return $null }
}
function Write-Status([string]$Overall, [string]$State, [hashtable]$Extra=@{}) {
    $p=[ordered]@{checked_at=[DateTimeOffset]::UtcNow.ToString('o');overall=$Overall;state=$State;design_lock_sha256=$LockSha;treatment_run_id=$RunId}
    foreach($k in $Extra.Keys){$p[$k]=$Extra[$k]}
    $p|ConvertTo-Json -Depth 8|Set-Content $StatusPath -Encoding UTF8
}
function Get-Trainers {
    return @(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'scripts[\\/]alpha_holdem[\\/]train_v5\.py'})
}
function Wait-TreatmentIdentity {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds([Math]::Max(10, $PostLaunchIdentityTimeoutSeconds))
    do {
        $m = Read-Json (Join-Path $RunDir 'run_manifest.json')
        $ts = @(Get-Trainers | Where-Object { $_.CommandLine -match [regex]::Escape($RunId) })
        $valid = ($null -ne $m -and [string]$m.run_id -eq $RunId -and
            [string]$m.status -eq 'running' -and
            [string]$m.config.opponent_assignment -eq 'per-group' -and
            [int]$m.config.opponent_groups -eq 5 -and
            [int64]$m.config.total_hands -eq 535989661 -and
            [bool]$m.config.fixed_training_deal_stream -and
            [int]$m.config.worker_seed_base -eq 73000 -and
            $ts.Count -eq 1 -and [int]$m.process_id -eq [int]$ts[0].ProcessId)
        if ($valid) { return [pscustomobject]@{ valid = $true; manifest = $m; trainers = $ts } }
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return [pscustomobject]@{ valid = $false; manifest = $m; trainers = $ts }
}
function Assert-Static {
    if((Get-FileHash $LockPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $LockSha){throw 'lock SHA mismatch'}
    if((Get-FileHash $SourceCheckpoint -Algorithm SHA256).Hash.ToLowerInvariant() -ne $SourceSha){throw 'source SHA mismatch'}
    $l=Read-Json $LockPath
    if([string]$l.status -ne 'LOCKED' -or [int]$l.lock_revision -ne 2){throw 'lock identity mismatch'}
    if([string]$l.arms.treatment.run_id -ne $RunId -or [string]$l.arms.treatment.expected_config.opponent_assignment -ne 'per-group'){throw 'treatment lock mismatch'}
}
Assert-Static
if($ValidateOnly){Write-Status PASS VALIDATE_ONLY_STATIC_CONTRACT_PASS;exit 0}

while($true){
    $control=Read-Json $ControlEndpointStatus
    if($null -eq $control -or [string]$control.overall -ne 'PASS' -or [string]$control.state -ne 'ARM_ENDPOINT_FROZEN'){
        if($null -ne $control -and [string]$control.overall -eq 'FAIL'){Write-Status FAIL CONTROL_ENDPOINT_FAILED;exit 1}
        Write-Status PENDING WAITING_FOR_CONTROL_ENDPOINT_FREEZE
        Start-Sleep -Seconds ([Math]::Max(1,$PollSeconds));continue
    }
    if([string]$control.arm -ne 'control' -or [string]$control.design_lock_sha256 -ne $LockSha -or [int64]$control.hands -lt 535989661 -or [int64]$control.hands -gt 536039661){
        Write-Status FAIL CONTROL_ENDPOINT_IDENTITY_MISMATCH;exit 1
    }
    if(-not (Test-Path ([string]$control.checkpoint_path)) -or (Get-FileHash ([string]$control.checkpoint_path) -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$control.checkpoint_sha256){
        Write-Status FAIL CONTROL_ENDPOINT_HASH_MISMATCH;exit 1
    }
    $trainers=Get-Trainers
    if($trainers.Count -ne 0){Write-Status FAIL ANOTHER_TRAINER_ALREADY_ALIVE @{trainer_pids=@($trainers.ProcessId)};exit 1}
    if(Test-Path $RunDir){Write-Status FAIL TREATMENT_RUN_DIR_ALREADY_EXISTS_REFUSE_DUPLICATE;exit 1}
    Write-Status PENDING LOCKED_TREATMENT_CUTOVER_STARTING
    $a=@(
      '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\alpha_holdem\v5_continue_after_gate.ps1','-SkipGateCheck',
      '-SourceRunDir',$SourceRun,'-SourceCheckpointPath',$SourceCheckpoint,'-DesignLockPath',$LockPath,'-ExpectedDesignLockSha256',$LockSha,'-DesignArm','treatment',
      '-TargetIteration','31400','-ExpectedPoolSnapshots','5','-RequireCurrentPoolSnapshot','true','-NewRunId',$RunId,'-NewRunDir',$RunDir,
      '-Device','cuda','-Workers','22','-HandsPerIter','16384','-TotalHands','535989661','-StartingStack','200','-EnvVersion','v55','-Lr','0.0003','-PpoEpochs','4','-MiniBatchSize','1024','-Epsilon','0','-Seed','20260703','-WorkerSeedBase','73000','-FixedTrainingDealStream',
      '-Gamma','0.999','-Delta1','3','-EntropyCoef','0.05','-EntropyFloor','0.3','-PostflopActionPriorCoef','0.02','-PostflopActionPriorTarget','0.15,0.30,0.52,0.03','-PreflopActionPriorCoef','0.01','-PreflopActionPriorTarget','0.24,0.36,0.38,0.02',
      '-PreflopSbOpenActionPriorCoef','0','-PreflopSbOpenActionPriorTarget','0.15,0.20,0.63,0.02','-PreflopBbVsOpenActionPriorCoef','0','-PreflopBbVsOpenActionPriorTarget','0.25,0.55,0.18,0.02','-KBest','5','-PoolStrategy','loss-kbest','-PoolHistoryLimit','200','-SelfPlayFraction','0.2',
      '-OpponentAssignment','per-group','-OpponentGroups','5','-OpponentAssignmentProvenanceFile',("$Repo\$RunDir\opponent_assignment_provenance.jsonl"),'-SnapshotEvery','200','-SaveInterval','1','-RolloutMode','multi','-RolloutEnvsPerWorker','16','-InferenceMinBatchSlots','256','-InferenceBatchDeadlineUs','1000','-MirrorSelfPlayDeals','-AllinRunoutEv','-AllinRunoutEvMaxRunouts','200','-Execute','-StopOldTraining')
    & powershell @a
    if($LASTEXITCODE -ne 0){Write-Status FAIL LOCKED_TREATMENT_CUTOVER_FAILED @{exit_code=$LASTEXITCODE};exit 1}
    $identity=Wait-TreatmentIdentity;$m=$identity.manifest;$ts=@($identity.trainers)
    if(-not $identity.valid){
        Write-Status FAIL POST_LAUNCH_IDENTITY_FAILURE @{trainer_pids=@($ts.ProcessId);timeout_seconds=$PostLaunchIdentityTimeoutSeconds};exit 1
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\alpha_holdem\v5_rearm_watchers.ps1 -RunDir $RunDir
    if($LASTEXITCODE -ne 0){Write-Status FAIL TREATMENT_LAUNCHED_BUT_CANONICAL_REARM_FAILED @{trainer_pid=$ts[0].ProcessId};exit 1}
    $time=Get-Date -Format 'yyyy-MM-dd HH:mm';$ledger=(Resolve-Path 'reports\v5_experiment_ledger.md').Path
    $row="`n| $time | EXP005-C clean treatment arm launched after control endpoint freeze | Control endpoint freeze/audit PASS under design-lock v2; no trainer remained and treatment directory was absent. Existing immutable-lock verifier launched $RunId from the same gate31400 bytes with only assignment per-group/5 differing from control, fixed20M actual hands, fixed deal stream and provenance. Canonical rearm invoked; no MEAS/Slumbot/strength authority. [event_id=v5-exp005c-treatment-launched-after-control-freeze] |`n"
    [IO.File]::AppendAllText($ledger,$row,[Text.UTF8Encoding]::new($false));Write-Status PASS TREATMENT_LAUNCHED @{trainer_pid=$ts[0].ProcessId;control_checkpoint_sha256=[string]$control.checkpoint_sha256};exit 0
}
