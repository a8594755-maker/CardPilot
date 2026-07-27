param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [string]$PilotRunDir = "models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710",
    [string]$PilotStopStatus = "",
    [int]$PollSeconds = 30,
    [int]$PostLaunchIdentityTimeoutSeconds = 90,
    [switch]$ValidateOnly,
    [switch]$RecoverPostLaunchIdentity
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

$LockPath = "reports\v5_exp005c_design_lock_v2_20260710.json"
$LockSha = "2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007"
$SourceRun = "models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709"
$SourceCheckpoint = "$SourceRun\v5_exp005_cutover_gate31400_checkpoint.pt"
$ControlRunId = "v5_zero_l6_exp005c_control_periter_same31400_20m_r1_20260710"
$ControlRun = "models\alpha_holdem_v5_from_zero\$ControlRunId"
$StatusPath = "reports\v5_exp005c_control_launch_watch_status.json"
$ExpectedSourceSha = "bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e"

if ([string]::IsNullOrWhiteSpace($PilotStopStatus)) {
    $PilotStopStatus = Join-Path $PilotRunDir "pilot_endpoint_stop_status.json"
}

function Write-Status([string]$Overall, [string]$State, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        checked_at = [DateTimeOffset]::UtcNow.ToString("o")
        overall = $Overall
        state = $State
        design_lock_sha256 = $LockSha
        control_run_id = $ControlRunId
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $StatusPath -Encoding UTF8
}

function Read-Json([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return Get-Content $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-Trainers {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'scripts[\\/]alpha_holdem[\\/]train_v5\.py'
    })
}

function Get-ControlIdentity {
    $manifest = Read-Json (Join-Path $ControlRun 'run_manifest.json')
    $controlTrainers = @(Get-Trainers | Where-Object { $_.CommandLine -match [regex]::Escape($ControlRunId) })
    $valid = ($null -ne $manifest -and [string]$manifest.run_id -eq $ControlRunId -and
        [string]$manifest.status -eq 'running' -and
        [string]$manifest.config.opponent_assignment -eq 'per-iteration' -and
        [int]$manifest.config.opponent_groups -eq 5 -and
        [int64]$manifest.config.total_hands -eq 535989661 -and
        [bool]$manifest.config.fixed_training_deal_stream -and
        [int]$manifest.config.worker_seed_base -eq 73000 -and
        $controlTrainers.Count -eq 1 -and
        [int]$manifest.process_id -eq [int]$controlTrainers[0].ProcessId)
    return [pscustomobject]@{ valid = $valid; manifest = $manifest; trainers = $controlTrainers }
}

function Wait-ControlIdentity {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds([Math]::Max(10, $PostLaunchIdentityTimeoutSeconds))
    do {
        $identity = Get-ControlIdentity
        if ($identity.valid) { return $identity }
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return (Get-ControlIdentity)
}

function Assert-StaticContract {
    if (-not (Test-Path $LockPath -PathType Leaf)) { throw "design lock missing" }
    if (-not (Test-Path $SourceCheckpoint -PathType Leaf)) { throw "source checkpoint missing" }
    $actualLockSha = (Get-FileHash $LockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualSourceSha = (Get-FileHash $SourceCheckpoint -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualLockSha -ne $LockSha) { throw "design lock SHA mismatch" }
    if ($actualSourceSha -ne $ExpectedSourceSha) { throw "source checkpoint SHA mismatch" }
    $lock = Read-Json $LockPath
    if ($null -eq $lock -or [string]$lock.status -ne 'LOCKED' -or [int]$lock.lock_revision -ne 2) {
        throw "design lock identity/status mismatch"
    }
    if ([string]$lock.arms.control.run_id -ne $ControlRunId) { throw "control run id mismatch" }
    if ([string]$lock.arms.control.expected_config.opponent_assignment -ne 'per-iteration') {
        throw "control assignment mismatch"
    }
    if ([int64]$lock.arms.control.expected_config.total_hands -ne 535989661) {
        throw "control total-hands mismatch"
    }
}

Assert-StaticContract
if ($RecoverPostLaunchIdentity) {
    $prior = Read-Json $StatusPath
    $pilot = Read-Json $PilotStopStatus
    if ($null -eq $prior -or [string]$prior.overall -ne 'FAIL' -or
        [string]$prior.state -ne 'POST_LAUNCH_IDENTITY_FAILURE') {
        throw 'recovery refused: prior status is not the exact post-launch false-negative state'
    }
    if ($null -eq $pilot -or [string]$pilot.overall -ne 'PASS' -or
        [string]$pilot.state -ne 'PILOT_STOPPED_AT_ENDPOINT' -or
        [int]$pilot.target_iteration -ne 32700 -or [int64]$pilot.checkpoint_hands -lt 535989661 -or
        [string]$pilot.method_judgment -ne 'FORBIDDEN_EXPLORATORY_PILOT' -or
        (Get-Process -Id 30224 -ErrorAction SilentlyContinue)) {
        throw 'recovery refused: pilot endpoint identity is not proven'
    }
    $identity = Wait-ControlIdentity
    if (-not $identity.valid -or @(Get-Trainers).Count -ne 1) {
        throw 'recovery refused: exact single control trainer identity did not stabilize'
    }
    $provenancePath = Join-Path $ControlRun 'opponent_assignment_provenance.jsonl'
    if (-not (Test-Path $provenancePath -PathType Leaf)) { throw 'recovery refused: provenance missing' }
    $first = Get-Content $provenancePath -First 1 | ConvertFrom-Json
    if ([int]$first.applies_to_iteration -ne 31401 -or
        [string]$first.assignment_mode -ne 'per-iteration' -or
        [int64]$first.total_hands_before_iteration -ne 515989661 -or
        [string]$first.run_id -ne $ControlRunId) {
        throw 'recovery refused: first provenance row does not bind the locked start'
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\alpha_holdem\v5_rearm_watchers.ps1 -RunDir $ControlRun
    if ($LASTEXITCODE -ne 0) { throw 'recovery refused: canonical rearm failed' }
    $eventTime = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $ledger = (Resolve-Path 'reports\v5_experiment_ledger.md').Path
    $row = "`n| $eventTime | EXP005-C control post-launch identity false-negative recovered fail-closed | The original fixed 8-second check emitted POST_LAUNCH_IDENTITY_FAILURE while the manifest was still stabilizing. Recovery retained the sole existing trainer without restart only after immutable lock/source SHA, pilot exact gate32700 PASS, PID30224 dead, exact control run/config/PID, fixed deal stream, worker seed, and first provenance row at iter31401/hands515,989,661 all passed. Canonical watcher rearm invoked; no duplicate trainer, MEAS, Slumbot, or method judgment. [event_id=v5-exp005c-control-postlaunch-race-recovered] |`n"
    [IO.File]::AppendAllText($ledger, $row, [Text.UTF8Encoding]::new($false))
    Write-Status 'PASS' 'CONTROL_LAUNCHED_RECOVERED' @{ trainer_pid = $identity.trainers[0].ProcessId; pilot_checkpoint_sha256 = [string]$pilot.checkpoint_sha256 }
    exit 0
}
if ($ValidateOnly) {
    Write-Status "PASS" "VALIDATE_ONLY_STATIC_CONTRACT_PASS"
    exit 0
}

while ($true) {
    $pilot = Read-Json $PilotStopStatus
    if ($null -eq $pilot -or [string]$pilot.overall -ne 'PASS' -or [string]$pilot.state -ne 'PILOT_STOPPED_AT_ENDPOINT') {
        if ($null -ne $pilot -and [string]$pilot.overall -eq 'FAIL' -and
            [string]$pilot.state -eq 'IDENTITY_OR_PROTOCOL_FAILURE') {
            Write-Status "PENDING" "WAITING_FOR_CANONICAL_PILOT_WATCHER_REARM" @{ pilot_state = [string]$pilot.state }
            Start-Sleep -Seconds ([Math]::Max(1, $PollSeconds))
            continue
        }
        if ($null -ne $pilot -and [string]$pilot.overall -eq 'FAIL') {
            Write-Status "FAIL" "PILOT_STOP_FAILED_OR_INVALID" @{ pilot_state = [string]$pilot.state }
            exit 1
        }
        Write-Status "PENDING" "WAITING_FOR_PILOT_ENDPOINT_STOP"
        Start-Sleep -Seconds ([Math]::Max(1, $PollSeconds))
        continue
    }
    if ([int]$pilot.target_iteration -ne 32700 -or [int64]$pilot.checkpoint_hands -lt 535989661 -or
        [string]$pilot.method_judgment -ne 'FORBIDDEN_EXPLORATORY_PILOT') {
        Write-Status "FAIL" "PILOT_STOP_IDENTITY_MISMATCH"
        exit 1
    }
    if (Get-Process -Id 30224 -ErrorAction SilentlyContinue) {
        Write-Status "FAIL" "PILOT_PID_STILL_ALIVE_AFTER_PASS_STATUS"
        exit 1
    }
    $trainers = Get-Trainers
    if ($trainers.Count -ne 0) {
        Write-Status "FAIL" "ANOTHER_TRAINER_ALREADY_ALIVE" @{ trainer_pids = @($trainers.ProcessId) }
        exit 1
    }
    if (Test-Path $ControlRun) {
        Write-Status "FAIL" "CONTROL_RUN_DIR_ALREADY_EXISTS_REFUSE_DUPLICATE"
        exit 1
    }

    Write-Status "PENDING" "LOCKED_CONTROL_CUTOVER_STARTING"
    $args = @(
        '-NoProfile','-ExecutionPolicy','Bypass','-File','scripts\alpha_holdem\v5_continue_after_gate.ps1',
        '-SkipGateCheck','-SourceRunDir',$SourceRun,'-SourceCheckpointPath',$SourceCheckpoint,
        '-DesignLockPath',$LockPath,'-ExpectedDesignLockSha256',$LockSha,'-DesignArm','control',
        '-TargetIteration','31400','-ExpectedPoolSnapshots','5','-RequireCurrentPoolSnapshot','true',
        '-NewRunId',$ControlRunId,'-NewRunDir',$ControlRun,
        '-Device','cuda','-Workers','22','-HandsPerIter','16384','-TotalHands','535989661',
        '-StartingStack','200','-EnvVersion','v55','-Lr','0.0003','-PpoEpochs','4',
        '-MiniBatchSize','1024','-Epsilon','0','-Seed','20260703','-WorkerSeedBase','73000',
        '-FixedTrainingDealStream','-Gamma','0.999','-Delta1','3','-EntropyCoef','0.05','-EntropyFloor','0.3',
        '-PostflopActionPriorCoef','0.02','-PostflopActionPriorTarget','0.15,0.30,0.52,0.03',
        '-PreflopActionPriorCoef','0.01','-PreflopActionPriorTarget','0.24,0.36,0.38,0.02',
        '-PreflopSbOpenActionPriorCoef','0','-PreflopSbOpenActionPriorTarget','0.15,0.20,0.63,0.02',
        '-PreflopBbVsOpenActionPriorCoef','0','-PreflopBbVsOpenActionPriorTarget','0.25,0.55,0.18,0.02',
        '-KBest','5','-PoolStrategy','loss-kbest','-PoolHistoryLimit','200','-SelfPlayFraction','0.2',
        '-OpponentAssignment','per-iteration','-OpponentGroups','5',
        '-OpponentAssignmentProvenanceFile',("$Repo\$ControlRun\opponent_assignment_provenance.jsonl"),
        '-SnapshotEvery','200','-SaveInterval','1','-RolloutMode','multi','-RolloutEnvsPerWorker','16',
        '-InferenceMinBatchSlots','256','-InferenceBatchDeadlineUs','1000','-MirrorSelfPlayDeals',
        '-AllinRunoutEv','-AllinRunoutEvMaxRunouts','200','-Execute','-StopOldTraining'
    )
    & powershell @args
    if ($LASTEXITCODE -ne 0) {
        Write-Status "FAIL" "LOCKED_CONTROL_CUTOVER_FAILED" @{ exit_code = $LASTEXITCODE }
        exit 1
    }
    $identity = Wait-ControlIdentity
    $controlTrainers = @($identity.trainers)
    if (-not $identity.valid) {
        Write-Status "FAIL" "POST_LAUNCH_IDENTITY_FAILURE" @{ trainer_pids = @($controlTrainers.ProcessId); timeout_seconds = $PostLaunchIdentityTimeoutSeconds }
        exit 1
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\alpha_holdem\v5_rearm_watchers.ps1 -RunDir $ControlRun
    if ($LASTEXITCODE -ne 0) {
        Write-Status "FAIL" "CONTROL_LAUNCHED_BUT_CANONICAL_REARM_FAILED" @{ trainer_pid = $controlTrainers[0].ProcessId }
        exit 1
    }
    $eventTime = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $ledger = (Resolve-Path 'reports\v5_experiment_ledger.md').Path
    $row = "`n| $eventTime | EXP005-C clean control arm launched after pilot endpoint stop | Pilot endpoint status PASS bound exact gate32700 and at least535,989,661 hands with method judgment forbidden; pilot PID30224 confirmed dead and no other trainer existed. Immutable design-lock v2 SHA$LockSha and continuation verifier passed exact gate31400 source/config/tool/test/ledger checks before launching control run $ControlRunId with per-iteration assignment, fixed20M actual-hand target, fixed deal stream and assignment provenance. Canonical watcher rearm invoked; no Slumbot/MEAS launch or strength claim. [event_id=v5-exp005c-control-launched-after-pilot-stop] |`n"
    [IO.File]::AppendAllText($ledger, $row, [Text.UTF8Encoding]::new($false))
    Write-Status "PASS" "CONTROL_LAUNCHED" @{ trainer_pid = $controlTrainers[0].ProcessId; pilot_checkpoint_sha256 = [string]$pilot.checkpoint_sha256 }
    exit 0
}
