# Wait for a V5 gate to pass, then run a non-destructive continuation dry-run.
#
# This script never launches a continuation trainer because it deliberately does
# not pass -Execute to v5_continue_after_gate.ps1. It is meant to prove that a
# post-gate cutover command is ready while preserving the active trainer.

param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [string]$SourceRunDir = "models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445",
    [int]$TargetIteration = 1600,
    [int]$ExpectedPoolSnapshots = 5,
    [bool]$RequireCurrentPoolSnapshot = $true,
    [int]$PollSeconds = 60,
    [int]$TimeoutSeconds = 14400,
    [string]$NewRunId = "",
    [string]$NewRunDir = "",
    [string]$Python = "python",
    [double]$PostflopActionPriorCoef = 0.0,
    [string]$PostflopActionPriorTarget = "0.15,0.30,0.52,0.03",
    [double]$PreflopActionPriorCoef = 0.0,
    [string]$PreflopActionPriorTarget = "0.30,0.25,0.43,0.02",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $SourceRunDir "post_gate_${TargetIteration}_dryrun_watch.log"
}

function Write-WatchLog([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogPath -Value $line
}

function Run-GateCheck {
    $argsList = @(
        "scripts\alpha_holdem\v5_gate_watch.py",
        "--run-dir", $SourceRunDir,
        "--target-iteration", "$TargetIteration",
        "--expected-pool-snapshots", "$ExpectedPoolSnapshots",
        "--poll-seconds", "1",
        "--timeout-seconds", "0"
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

function Run-ContinuationDryRun {
    $argsList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts\alpha_holdem\v5_continue_after_gate.ps1",
        "-SourceRunDir", $SourceRunDir,
        "-TargetIteration", "$TargetIteration",
        "-ExpectedPoolSnapshots", "$ExpectedPoolSnapshots",
        "-Python", $Python,
        "-PostflopActionPriorCoef", "$PostflopActionPriorCoef",
        "-PostflopActionPriorTarget", $PostflopActionPriorTarget,
        "-PreflopActionPriorCoef", "$PreflopActionPriorCoef",
        "-PreflopActionPriorTarget", $PreflopActionPriorTarget
    )
    if (-not $RequireCurrentPoolSnapshot) {
        $argsList += @("-RequireCurrentPoolSnapshot", "`$false")
    }
    if (-not [string]::IsNullOrWhiteSpace($NewRunId)) {
        $argsList += @("-NewRunId", $NewRunId)
    }
    if (-not [string]::IsNullOrWhiteSpace($NewRunDir)) {
        $argsList += @("-NewRunDir", $NewRunDir)
    }

    $output = & powershell @argsList 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) {
        Write-WatchLog "dry-run: $line"
    }
    return $code
}

Write-WatchLog "post-gate dry-run watcher started"
Write-WatchLog "source=$SourceRunDir target_iteration=$TargetIteration expected_pool=$ExpectedPoolSnapshots"
Write-WatchLog "postflop_action_prior_coef=$PostflopActionPriorCoef postflop_action_prior_target=$PostflopActionPriorTarget"
Write-WatchLog "preflop_action_prior_coef=$PreflopActionPriorCoef preflop_action_prior_target=$PreflopActionPriorTarget"

$start = Get-Date
while ($true) {
    $gateCode = Run-GateCheck
    if ($gateCode -eq 0) {
        Write-WatchLog "gate PASS; running continuation dry-run"
        $dryRunCode = Run-ContinuationDryRun
        Write-WatchLog "continuation dry-run exit code: $dryRunCode"
        exit $dryRunCode
    }
    if ($gateCode -ne 2) {
        Write-WatchLog "gate check returned non-pending exit code: $gateCode; stopping"
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
