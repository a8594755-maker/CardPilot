# Wait for a V5 gate to pass, then execute the guarded continuation cutover.
#
# This script is intentionally stricter than the dry-run watcher:
# - it requires an explicit OldTrainingPid
# - it re-runs the strict gate check until PASS
# - it delegates the actual cutover to v5_continue_after_gate.ps1 without
#   SkipGateCheck, so the gate is verified again immediately before launch
# - it starts next-gate, health, throughput, dashboard, cadence, internal,
#   archive, and gated Slumbot watchers for the continuation

param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [string]$SourceRunDir = "models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445",
    [int]$TargetIteration = 1600,
    [int]$ExpectedPoolSnapshots = 5,
    [object]$RequireCurrentPoolSnapshot = $true,
    [int]$PollSeconds = 60,
    [int]$TimeoutSeconds = 14400,
    [string]$NewRunId = "",
    [string]$NewRunDir = "",
    [string]$Python = "python",
    [int]$Workers = 28,
    [int]$OldTrainingPid = 0,
    [int]$NextGateIteration = 1700,
    [int]$NextGateExpectedPoolSnapshots = 5,
    [int]$GateSequenceMaxIteration = 5000,
    [int]$GateSequenceStep = 100,
    [int]$GateSequencePollSeconds = 60,
    [int]$GateSequenceTimeoutSeconds = 86400,
    [string]$PoolStrategy = "loss-kbest",
    [int]$PoolHistoryLimit = 200,
    [double]$PostflopActionPriorCoef = 0.0,
    [string]$PostflopActionPriorTarget = "0.15,0.30,0.52,0.03",
    [double]$PreflopActionPriorCoef = 0.0,
    [string]$PreflopActionPriorTarget = "0.30,0.25,0.43,0.02",
    [switch]$SkipSlumbotQuick5kWatcher,
    [int]$SlumbotQuick5kPollSeconds = 120,
    [int]$SlumbotQuick5kMaxHealthAgeSeconds = 900,
    [int64]$SlumbotPromotion20kMinTrainingHands = 250000000,
    [int]$SlumbotPromotion20kPollSeconds = 600,
    [int]$SlumbotPromotion20kMaxHealthAgeSeconds = 1200,
    [int64]$SlumbotFormal100kMinTrainingHands = 250000000,
    [int]$SlumbotFormal100kPollSeconds = 600,
    [int]$SlumbotFormal100kMaxHealthAgeSeconds = 1200,
    [double]$StderrRecentMinutes = 5.0,
    [string]$ReportPath = "reports\v5_zero_l6_fixedenv_launch.md",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

function Convert-ToBool([object]$Value) {
    if ($Value -is [bool]) {
        return $Value
    }
    if ($null -eq $Value) {
        return $false
    }
    $text = ([string]$Value).Trim()
    if ($text -match '^(?i:\$?true|1)$') {
        return $true
    }
    if ($text -match '^(?i:\$?false|0)$') {
        return $false
    }
    return [System.Convert]::ToBoolean($Value)
}

$RequireCurrentPoolSnapshot = Convert-ToBool $RequireCurrentPoolSnapshot

if ($OldTrainingPid -le 0) {
    throw "OldTrainingPid is required for execute watcher"
}

if ([string]::IsNullOrWhiteSpace($NewRunId)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $NewRunId = "v5_zero_l6_fixedenv_after${TargetIteration}_periter_${stamp}"
}
if ([string]::IsNullOrWhiteSpace($NewRunDir)) {
    $NewRunDir = Join-Path "models\alpha_holdem_v5_from_zero" $NewRunId
}
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $SourceRunDir "post_gate_${TargetIteration}_execute_watch.log"
}

function Write-WatchLog([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogPath -Value $line
}

function Run-GateCheck {
    $argsList = @(
        "-u",
        "scripts\alpha_holdem\v5_gate_watch.py",
        "--run-dir", $SourceRunDir,
        "--target-iteration", "$TargetIteration",
        "--expected-pool-snapshots", "$ExpectedPoolSnapshots",
        "--poll-seconds", "1",
        "--timeout-seconds", "0",
        "--refresh-health",
        "--python", $Python
    )
    if ($RequireCurrentPoolSnapshot) {
        $argsList += "--require-current-pool-snapshot"
    }
    $output = & $Python @argsList 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) {
        Write-WatchLog "gate-check: $line"
    }
    return $code
}

function Run-GuardedCutover {
    $argsList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts\alpha_holdem\v5_continue_after_gate.ps1",
        "-Repo", $Repo,
        "-SourceRunDir", $SourceRunDir,
        "-TargetIteration", "$TargetIteration",
        "-ExpectedPoolSnapshots", "$ExpectedPoolSnapshots",
        "-NewRunId", $NewRunId,
        "-NewRunDir", $NewRunDir,
        "-Python", $Python,
        "-Workers", "$Workers",
        "-Execute",
        "-StopOldTraining",
        "-OldTrainingPid", "$OldTrainingPid",
        "-StartNextGateWatcher",
        "-NextGateIteration", "$NextGateIteration",
        "-NextGateExpectedPoolSnapshots", "$NextGateExpectedPoolSnapshots",
        "-NextGateExpectedPoolStrategy", $PoolStrategy,
        "-StartGateSequenceWatcher",
        "-GateSequenceMaxIteration", "$GateSequenceMaxIteration",
        "-GateSequenceStep", "$GateSequenceStep",
        "-GateSequencePollSeconds", "$GateSequencePollSeconds",
        "-GateSequenceTimeoutSeconds", "$GateSequenceTimeoutSeconds",
        "-PoolStrategy", $PoolStrategy,
        "-PoolHistoryLimit", "$PoolHistoryLimit",
        "-PostflopActionPriorCoef", "$PostflopActionPriorCoef",
        "-PostflopActionPriorTarget", $PostflopActionPriorTarget,
        "-PreflopActionPriorCoef", "$PreflopActionPriorCoef",
        "-PreflopActionPriorTarget", $PreflopActionPriorTarget,
        "-StartHealthWatcher",
        "-StderrRecentMinutes", "$StderrRecentMinutes",
        "-StartThroughputWatcher",
        "-StartDashboardWatcher",
        "-StartEvalCadenceWatcher",
        "-StartSlumbotPromotion20kWatcher",
        "-SlumbotPromotion20kMinTrainingHands", "$SlumbotPromotion20kMinTrainingHands",
        "-SlumbotPromotion20kPollSeconds", "$SlumbotPromotion20kPollSeconds",
        "-SlumbotPromotion20kMaxHealthAgeSeconds", "$SlumbotPromotion20kMaxHealthAgeSeconds",
        "-StartSlumbotFormal100kWatcher",
        "-SlumbotFormal100kMinTrainingHands", "$SlumbotFormal100kMinTrainingHands",
        "-SlumbotFormal100kPollSeconds", "$SlumbotFormal100kPollSeconds",
        "-SlumbotFormal100kMaxHealthAgeSeconds", "$SlumbotFormal100kMaxHealthAgeSeconds",
        "-StartInternalStrengthWatcher",
        "-StartCheckpointArchiveWatcher",
        "-ReportPath", $ReportPath
    )
    if (-not $SkipSlumbotQuick5kWatcher) {
        $argsList += @(
            "-StartSlumbotQuick5kWatcher",
            "-SlumbotQuick5kPollSeconds", "$SlumbotQuick5kPollSeconds",
            "-SlumbotQuick5kMaxHealthAgeSeconds", "$SlumbotQuick5kMaxHealthAgeSeconds"
        )
    }
    if (-not $RequireCurrentPoolSnapshot) {
        $argsList += @("-RequireCurrentPoolSnapshot", "`$false")
    }

    $output = & powershell @argsList 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) {
        Write-WatchLog "cutover: $line"
    }
    return $code
}

Write-WatchLog "post-gate execute watcher started"
Write-WatchLog "source=$SourceRunDir target_iteration=$TargetIteration expected_pool=$ExpectedPoolSnapshots"
Write-WatchLog "new_run_id=$NewRunId new_run_dir=$NewRunDir old_training_pid=$OldTrainingPid"
Write-WatchLog "postflop_action_prior_coef=$PostflopActionPriorCoef postflop_action_prior_target=$PostflopActionPriorTarget"
Write-WatchLog "preflop_action_prior_coef=$PreflopActionPriorCoef preflop_action_prior_target=$PreflopActionPriorTarget"
Write-WatchLog "skip_slumbot_quick5k_watcher=$SkipSlumbotQuick5kWatcher"

$start = Get-Date
while ($true) {
    $gateCode = Run-GateCheck
    if ($gateCode -eq 0) {
        Write-WatchLog "gate PASS; running guarded cutover"
        $cutoverCode = Run-GuardedCutover
        Write-WatchLog "guarded cutover exit code: $cutoverCode"
        exit $cutoverCode
    }
    if ($gateCode -ne 2) {
        Write-WatchLog "gate check returned non-pending exit code: $gateCode; refusing cutover"
        exit $gateCode
    }

    if ($TimeoutSeconds -gt 0) {
        $elapsed = [int]((Get-Date) - $start).TotalSeconds
        if ($elapsed -ge $TimeoutSeconds) {
            Write-WatchLog "timeout after ${elapsed}s"
            exit 2
        }
    }
    Start-Sleep -Seconds $PollSeconds
}
