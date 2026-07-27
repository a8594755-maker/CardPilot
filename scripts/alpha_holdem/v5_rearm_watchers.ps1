<#
v5_rearm_watchers.ps1
Trainer-preserving re-arm of V5 watchers after reboot or down state.
Uses VERBATIM arg blocks from v5_continue_after_gate.ps1 (per strategist rec).
Does NOT touch or restart the trainer.
Adds post-launch survival gate + err log check.
Logs to {RunDir}/watcher_rearm_status.json with survival_pass.

Usage:
  powershell -File scripts\alpha_holdem\v5_rearm_watchers.ps1 -RunDir "models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_r1_20260707"

Gate/internal coverage is derived from current live/checkpoint progress and the
next live gate. Historical range overrides are refused before any watcher action.
For throughput, uses parent call36_r1 as baseline (EXP-004 lineage), current as candidate.
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$RunDir,
    [int]$GateStartIteration = 0,
    [int]$GateMaxIteration = 0,
    [int]$InternalStartIteration = 0,
    [int]$InternalMaxIteration = 0,
    [int]$WatcherRangeSpanIterations = 1100,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path ".").Path
$Python = "python"
$RunDirAbs = (Resolve-Path $RunDir).Path
if (-not (Test-Path (Join-Path $RunDirAbs "run_manifest.json"))) {
    throw "Invalid RunDir: $RunDirAbs (no run_manifest.json)"
}

$timestamp = (Get-Date).ToString("o")
$rearmLog = Join-Path $RunDirAbs "watcher_rearm.log"
$statusJson = Join-Path $RunDirAbs "watcher_rearm_status.json"

function Log($msg) {
    $line = "[$timestamp] $msg"
    Write-Host $line
    Add-Content -Path $rearmLog -Value $line -Encoding UTF8
}

function Resolve-RepoPath([string]$PathText) {
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return $PathText
    }
    return Join-Path $Repo $PathText
}

$script:preservedSlumbotWatchers = @()
$script:preservedExp003BundleWatcher = $null
$script:exp003BundleLaunchAttempted = $false

function Read-JsonFile($path, [switch]$Quiet) {
    if (-not (Test-Path $path)) { return $null }
    try {
        return Get-Content $path -Raw | ConvertFrom-Json
    } catch {
        if (-not $Quiet) {
            Log "WARN: failed to parse ${path}: $($_.Exception.Message)"
        }
        return $null
    }
}

# The re-arm script used to carry a continuation-specific 12900..14000 default.
# On a later continuation that range creates historical gate/internal reports. Do
# not infer a range from old watcher status files: derive it from the current run's
# high-water live/checkpoint state, then accept only an adjacent current next gate.
# This entire resolution path is intentionally before the idempotency PID sweep.
function Get-RearmJsonInteger {
    param(
        [object]$Json,
        [string[]]$Path
    )
    $current = $Json
    foreach ($part in $Path) {
        if ($null -eq $current) { return $null }
        $property = $current.PSObject.Properties[$part]
        if ($null -eq $property) { return $null }
        $current = $property.Value
    }
    if ($null -eq $current) { return $null }
    try {
        $value = [Convert]::ToInt32($current, [System.Globalization.CultureInfo]::InvariantCulture)
        if ($value -gt 0) { return $value }
    } catch {
        return $null
    }
    return $null
}

function Get-RearmIterationEvidence {
    param([string]$CurrentRunDir)

    $dashboard = Read-JsonFile (Join-Path $CurrentRunDir "v5_dashboard_watch_status.json") -Quiet
    $progress = Read-JsonFile (Join-Path $CurrentRunDir "progress_status.json") -Quiet
    $health = Read-JsonFile (Join-Path $CurrentRunDir "health_status.json") -Quiet
    $queue = Read-JsonFile (Join-Path $CurrentRunDir "v5_next_action_queue.json") -Quiet
    $records = @()
    $candidates = @(
        [pscustomobject]@{ kind = "live"; source = "dashboard.live_iteration"; value = (Get-RearmJsonInteger $dashboard @("live_iteration")) },
        [pscustomobject]@{ kind = "checkpoint"; source = "dashboard.checkpoint_iteration"; value = (Get-RearmJsonInteger $dashboard @("checkpoint_iteration")) },
        [pscustomobject]@{ kind = "live"; source = "dashboard.brief_live_iteration"; value = (Get-RearmJsonInteger $dashboard @("brief_live_iteration")) },
        [pscustomobject]@{ kind = "checkpoint"; source = "dashboard.brief_checkpoint_iteration"; value = (Get-RearmJsonInteger $dashboard @("brief_checkpoint_iteration")) },
        [pscustomobject]@{ kind = "live"; source = "progress.latest.iteration"; value = (Get-RearmJsonInteger $progress @("latest", "iteration")) },
        [pscustomobject]@{ kind = "checkpoint"; source = "progress.checkpoint.iteration"; value = (Get-RearmJsonInteger $progress @("checkpoint", "iteration")) },
        [pscustomobject]@{ kind = "live"; source = "health.latest.iteration"; value = (Get-RearmJsonInteger $health @("latest", "iteration")) },
        [pscustomobject]@{ kind = "live"; source = "queue.training.live_iteration"; value = (Get-RearmJsonInteger $queue @("training", "live_iteration")) },
        [pscustomobject]@{ kind = "checkpoint"; source = "queue.training.checkpoint_iteration"; value = (Get-RearmJsonInteger $queue @("training", "checkpoint_iteration")) }
    )
    foreach ($candidate in $candidates) {
        if ($null -ne $candidate.value) {
            $records += [pscustomobject]@{
                kind = [string]$candidate.kind
                source = [string]$candidate.source
                iteration = [int]$candidate.value
            }
        }
    }
    return $records
}

function Test-RearmSamePath {
    param(
        [string]$Left,
        [string]$Right
    )
    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) { return $false }
    try {
        return [string]::Equals(
            [System.IO.Path]::GetFullPath($Left),
            [System.IO.Path]::GetFullPath($Right),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    } catch {
        return $false
    }
}

function Get-RearmGateStatusInteger {
    param(
        [object]$Json,
        [string]$Field
    )
    $property = $null
    if ($null -ne $Json) { $property = $Json.PSObject.Properties[$Field] }
    if ($null -eq $property) {
        return [pscustomobject]@{ present = $false; valid = $false; value = $null }
    }
    $raw = $property.Value
    if ($null -eq $raw -or ($raw -is [bool])) {
        return [pscustomobject]@{ present = $true; valid = $false; value = $null }
    }
    $isIntegralRuntimeType = (
        ($raw -is [sbyte]) -or ($raw -is [byte]) -or
        ($raw -is [int16]) -or ($raw -is [uint16]) -or
        ($raw -is [int32]) -or ($raw -is [uint32]) -or
        ($raw -is [int64]) -or ($raw -is [uint64])
    )
    if ($raw -is [string]) {
        if ([string]$raw -notmatch '^[1-9][0-9]*$') {
            return [pscustomobject]@{ present = $true; valid = $false; value = $null }
        }
    } elseif (-not $isIntegralRuntimeType) {
        # JSON float/decimal values and booleans are never legal gate identities.
        return [pscustomobject]@{ present = $true; valid = $false; value = $null }
    }
    try {
        $value = [Convert]::ToInt64($raw, [System.Globalization.CultureInfo]::InvariantCulture)
        if (($value -le 0) -or ($value -gt [int]::MaxValue)) {
            return [pscustomobject]@{ present = $true; valid = $false; value = $null }
        }
        return [pscustomobject]@{ present = $true; valid = $true; value = [int]$value }
    } catch {
        return [pscustomobject]@{ present = $true; valid = $false; value = $null }
    }
}

function Get-RearmGateStatusEvidence {
    param(
        [string]$CurrentRunDir,
        [int]$TargetIteration
    )
    $statusPath = Join-Path $CurrentRunDir ("gate_{0}_status.json" -f $TargetIteration)
    if (-not (Test-Path $statusPath)) {
        return [pscustomobject]@{ target_iteration = $TargetIteration; state = "MISSING"; usable = $true; path = $statusPath }
    }
    $status = Read-JsonFile $statusPath -Quiet
    if ($null -eq $status) {
        return [pscustomobject]@{ target_iteration = $TargetIteration; state = "INVALID_JSON"; usable = $false; path = $statusPath }
    }
    $reportedTarget = Get-RearmGateStatusInteger $status "target_iteration"
    if ((-not $reportedTarget.valid) -or ($reportedTarget.value -ne $TargetIteration)) {
        return [pscustomobject]@{ target_iteration = $TargetIteration; state = "MISMATCHED_TARGET"; usable = $false; path = $statusPath }
    }
    if (-not (Test-RearmSamePath ([string]$status.run_dir) $CurrentRunDir)) {
        return [pscustomobject]@{ target_iteration = $TargetIteration; state = "FOREIGN_RUN_DIR"; usable = $false; path = $statusPath }
    }
    $manifest = Read-JsonFile (Join-Path $CurrentRunDir "run_manifest.json") -Quiet
    $expectedRunId = [string]$manifest.run_id
    if ([string]::IsNullOrWhiteSpace($expectedRunId) -or ([string]$status.run_id -ne $expectedRunId)) {
        return [pscustomobject]@{ target_iteration = $TargetIteration; state = "FOREIGN_RUN_ID"; usable = $false; path = $statusPath }
    }
    $overall = ([string]$status.overall).ToUpperInvariant()
    # A gate watcher writes PENDING before its target checkpoint exists, so its
    # checkpoint_iteration may correctly be the prior saved checkpoint. Require
    # full filename/target/checkpoint identity only for a claimed PASS.
    if ($overall -eq "PASS") {
        $reportedCheckpoint = Get-RearmGateStatusInteger $status "checkpoint_iteration"
        if ((-not $reportedCheckpoint.valid) -or ($reportedCheckpoint.value -ne $TargetIteration)) {
            return [pscustomobject]@{ target_iteration = $TargetIteration; state = "MISMATCHED_PASS_CHECKPOINT"; usable = $false; path = $statusPath }
        }
    } elseif ($overall -eq "PENDING") {
        $reportedCheckpoint = Get-RearmGateStatusInteger $status "checkpoint_iteration"
        if ($reportedCheckpoint.present -and (-not $reportedCheckpoint.valid)) {
            return [pscustomobject]@{ target_iteration = $TargetIteration; state = "INVALID_PENDING_CHECKPOINT"; usable = $false; path = $statusPath }
        }
        if ($reportedCheckpoint.valid -and ($reportedCheckpoint.value -gt $TargetIteration)) {
            return [pscustomobject]@{ target_iteration = $TargetIteration; state = "PENDING_CHECKPOINT_AHEAD"; usable = $false; path = $statusPath }
        }
    }
    $state = if ($overall -eq "PENDING") { "PENDING" } elseif ($overall -eq "PASS") { "PASS" } else { "TERMINAL_$overall" }
    return [pscustomobject]@{ target_iteration = $TargetIteration; state = $state; usable = ($state -eq "PENDING"); path = $statusPath }
}

function Get-RearmCheckpointCatchup {
    param(
        [string]$CurrentRunDir,
        [int]$CheckpointIteration
    )
    if (($CheckpointIteration % 100) -ne 0) {
        return [pscustomobject]@{ include = $false; start_iteration = $null; state = "CHECKPOINT_NOT_GATE_ALIGNED" }
    }

    # v5_gate_sequence_watch evaluates latest.pt. It can validate the latest saved
    # checkpoint, but it cannot reconstruct any target below it. Never scan or
    # replay older PENDING/MISSING files during re-arm.
    $checkpointEvidence = Get-RearmGateStatusEvidence $CurrentRunDir $CheckpointIteration
    if (($checkpointEvidence.state -eq "MISSING") -or ($checkpointEvidence.state -eq "PENDING")) {
        return [pscustomobject]@{ include = $true; start_iteration = $CheckpointIteration; state = "CURRENT_SAVED_CHECKPOINT_$($checkpointEvidence.state)" }
    }
    return [pscustomobject]@{ include = $false; start_iteration = $null; state = [string]$checkpointEvidence.state }
}

function Test-RearmGateCanStart {
    param(
        [string]$CurrentRunDir,
        [int]$TargetIteration
    )
    $evidence = Get-RearmGateStatusEvidence $CurrentRunDir $TargetIteration
    return [bool]$evidence.usable
}

function Get-RearmNextGateCandidates {
    param([string]$CurrentRunDir)

    $results = @()
    $dashboard = Read-JsonFile (Join-Path $CurrentRunDir "v5_dashboard_watch_status.json") -Quiet
    $dashboardTarget = Get-RearmJsonInteger $dashboard @("next_gate_target_iteration")
    if ($null -ne $dashboardTarget) {
        $results += [pscustomobject]@{ iteration = [int]$dashboardTarget; source = "dashboard.next_gate_target_iteration" }
    }

    $queue = Read-JsonFile (Join-Path $CurrentRunDir "v5_next_action_queue.json") -Quiet
    if (($null -ne $queue) -and ($null -ne $queue.queue)) {
        foreach ($entry in @($queue.queue)) {
            $key = [string]$entry.key
            if ($key -match '^gate_(\d+)$') {
                $results += [pscustomobject]@{ iteration = [int]$Matches[1]; source = "queue.$key" }
            }
        }
    }
    return $results
}

function Resolve-RearmWatcherRange {
    param(
        [string]$Kind,
        [int]$RequestedStart,
        [int]$RequestedMax,
        [int]$SafeStart,
        [int]$SpanIterations,
        [int]$HighWaterIteration
    )
    $startName = "${Kind}StartIteration"
    $maxName = "${Kind}MaxIteration"
    if ($RequestedStart -lt 0) { throw "$startName must be zero (auto) or a positive gate iteration" }
    if ($RequestedMax -lt 0) { throw "$maxName must be zero (auto) or a positive gate iteration" }
    if (($RequestedStart -gt 0) -and (($RequestedStart % 100) -ne 0)) {
        throw "$startName=$RequestedStart is not aligned to the 100-iteration gate cadence"
    }
    if (($RequestedMax -gt 0) -and (($RequestedMax % 100) -ne 0)) {
        throw "$maxName=$RequestedMax is not aligned to the 100-iteration gate cadence"
    }
    if (($RequestedStart -gt 0) -and ($RequestedStart -lt $SafeStart)) {
        throw "Refusing stale $Kind range: $startName=$RequestedStart is below safe start $SafeStart (current high-water iteration $HighWaterIteration). Remove the stale override and let rearm derive the range."
    }
    if (($RequestedMax -gt 0) -and ($RequestedMax -lt $SafeStart)) {
        throw "Refusing stale $Kind range: $maxName=$RequestedMax is below safe start $SafeStart (current high-water iteration $HighWaterIteration). Remove the stale override and let rearm derive the range."
    }

    $start = if ($RequestedStart -gt 0) { $RequestedStart } else { $SafeStart }
    $max = if ($RequestedMax -gt 0) { $RequestedMax } else { $start + $SpanIterations }
    if ($max -lt $start) {
        throw "Refusing invalid $Kind range: $maxName=$max is below $startName=$start"
    }
    return [pscustomobject]@{
        start_iteration = [int]$start
        max_iteration = [int]$max
        requested_start_iteration = [int]$RequestedStart
        requested_max_iteration = [int]$RequestedMax
    }
}

function Resolve-RearmWatcherRanges {
    param(
        [string]$CurrentRunDir,
        [int]$RequestedGateStart,
        [int]$RequestedGateMax,
        [int]$RequestedInternalStart,
        [int]$RequestedInternalMax,
        [int]$SpanIterations
    )
    if (($SpanIterations -lt 100) -or (($SpanIterations % 100) -ne 0)) {
        throw "WatcherRangeSpanIterations=$SpanIterations must be a positive multiple of 100"
    }

    $evidence = @(Get-RearmIterationEvidence $CurrentRunDir)
    if ($evidence.Count -eq 0) {
        throw "Refusing re-arm: unable to derive current live/checkpoint iteration from dashboard/progress/health/queue artifacts"
    }
    $liveEvidence = @($evidence | Where-Object { $_.kind -eq "live" })
    $checkpointEvidence = @($evidence | Where-Object { $_.kind -eq "checkpoint" })
    $liveIteration = if ($liveEvidence.Count -gt 0) { [int](($liveEvidence | Measure-Object -Property iteration -Maximum).Maximum) } else { $null }
    $checkpointIteration = if ($checkpointEvidence.Count -gt 0) { [int](($checkpointEvidence | Measure-Object -Property iteration -Maximum).Maximum) } else { $null }
    $highWaterIteration = [int](($evidence | Measure-Object -Property iteration -Maximum).Maximum)
    $liveBoundaryGate = [int]([Math]::Ceiling(([double]$highWaterIteration) / 100.0) * 100.0)
    $nextFutureGate = $liveBoundaryGate
    if (($null -ne $checkpointIteration) -and (($checkpointIteration % 100) -eq 0)) {
        # This is deliberately based on the saved model, not an older status file:
        # a target below latest.pt can never be reconstructed by the gate watcher.
        $nextFutureGate = $checkpointIteration + 100
    }

    $checkpointCatchup = [pscustomobject]@{ include = $false; start_iteration = $null; state = "NO_CURRENT_CHECKPOINT" }
    if ($null -ne $checkpointIteration) {
        $checkpointCatchup = Get-RearmCheckpointCatchup $CurrentRunDir $checkpointIteration
    }

    # Do not let queue/dashboard status pull re-arm behind latest.pt. Without a
    # current-saved-checkpoint candidate, only a future target may be launched.
    $nextGateCandidates = @(Get-RearmNextGateCandidates $CurrentRunDir | Where-Object {
        ($_.iteration -ge $nextFutureGate) -and
        ($_.iteration -le ($nextFutureGate + 100)) -and
        (Test-RearmGateCanStart $CurrentRunDir ([int]$_.iteration))
    })
    $safeStart = $nextFutureGate
    $safeStartSource = "next-future-gate-after-saved-checkpoint"
    if ($checkpointCatchup.include) {
        $safeStart = [int]$checkpointCatchup.start_iteration
        $safeStartSource = "checkpoint-catchup.$($checkpointCatchup.state)"
    } elseif ($nextGateCandidates.Count -gt 0) {
        $selected = @($nextGateCandidates | Sort-Object iteration, source | Select-Object -First 1)[0]
        $safeStart = [int]$selected.iteration
        $safeStartSource = [string]$selected.source
    }
    while (-not (Test-RearmGateCanStart $CurrentRunDir $safeStart)) {
        $safeStart += 100
        $safeStartSource = "advance-after-completed-or-invalid-gate"
    }

    $gate = Resolve-RearmWatcherRange "Gate" $RequestedGateStart $RequestedGateMax $safeStart $SpanIterations $highWaterIteration
    $internal = Resolve-RearmWatcherRange "Internal" $RequestedInternalStart $RequestedInternalMax $safeStart $SpanIterations $highWaterIteration
    return [pscustomobject]@{
        resolution_version = "saved_checkpoint_no_historical_replay_v3"
        cadence_iterations = 100
        span_iterations = [int]$SpanIterations
        live_iteration = $liveIteration
        checkpoint_iteration = $checkpointIteration
        high_water_iteration = $highWaterIteration
        safe_start_iteration = [int]$safeStart
        safe_start_source = $safeStartSource
        checkpoint_catchup = $checkpointCatchup
        evidence = $evidence
        gate = $gate
        internal = $internal
    }
}

$validationManifest = Read-JsonFile (Join-Path $RunDirAbs "run_manifest.json") -Quiet
$validationRunId = if ($null -ne $validationManifest) { [string]$validationManifest.run_id } else { "" }
$validationIsExpW1Arm = ($validationRunId -like "*expw1*")
$validationIsHybridH1Arm = ($validationRunId -like "*v5_hybrid_h1_*")
$validationIsHybridH2Arm = ($validationRunId -like "*v5_hybrid_h2_*")
$validationIsHybridH6Arm = ($validationRunId -like "*v5_hybrid_h6_*")
$validationIsHybridH7Arm = ($validationRunId -like "*v5_hybrid_h7_*")
$validationIsHybridH8Arm = ($validationRunId -like "*v5_hybrid_h8_*")
$validationIsHybridH9Arm = ($validationRunId -like "*v5_hybrid_h9_*")
$validationIsHybridH10Arm = ($validationRunId -like "*v5_hybrid_h10_*")
$validationIsHybridH11Arm = ($validationRunId -like "*v5_hybrid_h11_*")
$validationIsHybridH12Arm = ($validationRunId -like "*v5_hybrid_h12_*")
$validationIsHybridH13Arm = ($validationRunId -like "*v5_hybrid_h13_*")
$validationIsHybridH14Arm = ($validationRunId -like "*v5_hybrid_h14_*")
$validationIsHybridH15Arm = ($validationRunId -like "*v5_hybrid_h15_*")
$validationIsHybridH16Arm = ($validationRunId -like "*v5_hybrid_h16_*")
$validationIsHybridH17Arm = ($validationRunId -like "*v5_hybrid_h17_*")
$validationIsHybridH18Arm = ($validationRunId -like "*v5_hybrid_h18_*")

# H1 arms terminally skip every generic gate/eval/internal path. A completed H1
# arm can be re-armed from its exact run_manifest before watcher artifacts exist.
if ($validationIsHybridH1Arm -or $validationIsHybridH2Arm -or $validationIsHybridH6Arm -or $validationIsHybridH7Arm -or $validationIsHybridH8Arm -or $validationIsHybridH9Arm -or $validationIsHybridH10Arm -or $validationIsHybridH11Arm -or $validationIsHybridH12Arm -or $validationIsHybridH13Arm -or $validationIsHybridH14Arm -or $validationIsHybridH15Arm -or $validationIsHybridH16Arm -or $validationIsHybridH17Arm -or $validationIsHybridH18Arm) {
    $manifestIteration = 0
    try { $manifestIteration = [Convert]::ToInt32($validationManifest.iteration) } catch { $manifestIteration = 0 }
    if ($manifestIteration -le 0) { throw "Refusing H1 re-arm: run_manifest iteration is missing or invalid" }
    $rangeResolution = [pscustomobject]@{
        resolution_version = "hybrid_h1_manifest_identity_v1"
        cadence_iterations = 100
        span_iterations = [int]$WatcherRangeSpanIterations
        live_iteration = [int]$manifestIteration
        checkpoint_iteration = [int]$manifestIteration
        high_water_iteration = [int]$manifestIteration
        safe_start_iteration = [int]$manifestIteration
        safe_start_source = "hybrid-h1-exact-run-manifest"
        checkpoint_catchup = [pscustomobject]@{ include = $false; start_iteration = $null; state = "H1_GENERIC_GATES_TERMINAL_BLOCKED" }
        evidence = @([pscustomobject]@{ kind = "manifest"; source = "run_manifest.iteration"; iteration = [int]$manifestIteration })
        gate = [pscustomobject]@{ start_iteration = 0; max_iteration = 0; requested_start_iteration = [int]$GateStartIteration; requested_max_iteration = [int]$GateMaxIteration }
        internal = [pscustomobject]@{ start_iteration = 0; max_iteration = 0; requested_start_iteration = [int]$InternalStartIteration; requested_max_iteration = [int]$InternalMaxIteration }
    }
} else {
    $rangeResolution = Resolve-RearmWatcherRanges `
        -CurrentRunDir $RunDirAbs `
        -RequestedGateStart $GateStartIteration `
        -RequestedGateMax $GateMaxIteration `
        -RequestedInternalStart $InternalStartIteration `
        -RequestedInternalMax $InternalMaxIteration `
        -SpanIterations $WatcherRangeSpanIterations
}
$GateStartIteration = [int]$rangeResolution.gate.start_iteration
$GateMaxIteration = [int]$rangeResolution.gate.max_iteration
$InternalStartIteration = [int]$rangeResolution.internal.start_iteration
$InternalMaxIteration = [int]$rangeResolution.internal.max_iteration
$rangeResolution | Add-Member -NotePropertyName run_classification -NotePropertyValue ([pscustomobject]@{
    run_id = $validationRunId
    is_exp_w1_arm = $validationIsExpW1Arm
    is_hybrid_h1_arm = $validationIsHybridH1Arm
    is_hybrid_h2_arm = $validationIsHybridH2Arm
    is_hybrid_h6_arm = $validationIsHybridH6Arm
    is_hybrid_h7_arm = $validationIsHybridH7Arm
    is_hybrid_h8_arm = $validationIsHybridH8Arm
    is_hybrid_h9_arm = $validationIsHybridH9Arm
    is_hybrid_h10_arm = $validationIsHybridH10Arm
    is_hybrid_h11_arm = $validationIsHybridH11Arm
    is_hybrid_h12_arm = $validationIsHybridH12Arm
    is_hybrid_h13_arm = $validationIsHybridH13Arm
    is_hybrid_h14_arm = $validationIsHybridH14Arm
    is_hybrid_h15_arm = $validationIsHybridH15Arm
    is_hybrid_h16_arm = $validationIsHybridH16Arm
    is_hybrid_h17_arm = $validationIsHybridH17Arm
    is_hybrid_h18_arm = $validationIsHybridH18Arm
    block_generic_eval_and_slumbot = ($validationIsExpW1Arm -or $validationIsHybridH1Arm -or $validationIsHybridH2Arm -or $validationIsHybridH6Arm -or $validationIsHybridH7Arm -or $validationIsHybridH8Arm -or $validationIsHybridH9Arm -or $validationIsHybridH10Arm -or $validationIsHybridH11Arm -or $validationIsHybridH12Arm -or $validationIsHybridH13Arm -or $validationIsHybridH14Arm -or $validationIsHybridH15Arm -or $validationIsHybridH16Arm -or $validationIsHybridH17Arm -or $validationIsHybridH18Arm)
}) -Force

if ($ValidateOnly) {
    $rangeResolution | ConvertTo-Json -Depth 8
    return
}

Log "Re-arming watchers for $RunDirAbs (trainer untouched) - derived gate=$GateStartIteration..$GateMaxIteration internal=$InternalStartIteration..$InternalMaxIteration from $($rangeResolution.safe_start_source)"

$runManifest = Read-JsonFile (Join-Path $RunDirAbs "run_manifest.json")
if ($null -eq $runManifest) {
    throw "Refusing re-arm: run_manifest.json is missing or invalid"
}
$script:expectedOpponentAssignment = [string]$runManifest.config.opponent_assignment
if ([string]::IsNullOrWhiteSpace($script:expectedOpponentAssignment)) {
    throw "Refusing re-arm: run manifest has no opponent_assignment"
}
$script:isExp005CArm = ([string]$runManifest.run_id -like "*exp005c*")
$script:isExpW1Arm = ([string]$runManifest.run_id -like "*expw1*")
$script:isHybridH1Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h1_*")
$script:isHybridH2Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h2_*")
$script:isHybridH6Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h6_*")
$script:isHybridH7Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h7_*")
$script:isHybridH8Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h8_*")
$script:isHybridH9Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h9_*")
$script:isHybridH10Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h10_*")
$script:isHybridH11Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h11_*")
$script:isHybridH12Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h12_*")
$script:isHybridH13Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h13_*")
$script:isHybridH14Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h14_*")
$script:isHybridH15Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h15_*")
$script:isHybridH16Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h16_*")
$script:isHybridH17Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h17_*")
$script:isHybridH18Arm = ([string]$runManifest.run_id -like "*v5_hybrid_h18_*")
$script:isExp005PilotRun = (
    ($script:expectedOpponentAssignment -eq "per-group") -and
    ([int]$runManifest.config.opponent_groups -eq 5) -and
    ([string]$runManifest.run_id -like "*exp005*") -and
    (-not $script:isExp005CArm)
)
$script:isExp005EvidenceRun = ($script:isExp005PilotRun -or $script:isExp005CArm -or $script:isExpW1Arm -or $script:isHybridH1Arm -or $script:isHybridH2Arm -or $script:isHybridH6Arm -or $script:isHybridH7Arm -or $script:isHybridH8Arm -or $script:isHybridH9Arm -or $script:isHybridH10Arm -or $script:isHybridH11Arm -or $script:isHybridH12Arm -or $script:isHybridH13Arm -or $script:isHybridH14Arm -or $script:isHybridH15Arm -or $script:isHybridH16Arm -or $script:isHybridH17Arm -or $script:isHybridH18Arm)

function Get-ActiveSlumbotStatus($stage) {
    $path = Join-Path $RunDirAbs "slumbot_${stage}_launch_status.json"
    $status = Read-JsonFile $path
    if ($null -eq $status) { return $null }
    return [pscustomobject]@{
        path = $path
        state = [string]$status.state
    }
}

function Is-LaunchableSlumbotState($state) {
    if ([string]::IsNullOrWhiteSpace($state)) { return $true }
    return @("WAITING", "READY", "READY_WITH_WARNINGS", "FREEZE_RETRY") -contains ([string]$state)
}

function Add-SkippedSlumbotLaunch($stage, $outLog, $errLog, $reason) {
    Log "Skipping v5_slumbot_benchmark_watch.py ${stage}: $reason"
    $script:launched += [pscustomobject]@{
        script = "v5_slumbot_benchmark_watch.py:$stage"
        pid = -1
        out = $outLog
        err = $errLog
        skipped = $true
        skip_reason = $reason
    }
}

function Find-ExistingPromotion20kResult {
    $manifest = Read-JsonFile (Join-Path $RunDirAbs "run_manifest.json")
    $runId = $null
    if ($null -ne $manifest) { $runId = [string]$manifest.run_id }
    if ([string]::IsNullOrWhiteSpace($runId)) { return $null }
    $filter = "bench_v55_v5_${runId}_iter*_promotion20k_ci_summary.json"
    return @(Get-ChildItem -Path (Join-Path $Repo "models") -Filter $filter -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)[0]
}

function Find-ExistingFormal100kResult {
    $manifest = Read-JsonFile (Join-Path $RunDirAbs "run_manifest.json")
    $runId = $null
    if ($null -ne $manifest) { $runId = [string]$manifest.run_id }
    if ([string]::IsNullOrWhiteSpace($runId)) { return $null }
    $filter = "bench_v55_v5_${runId}_iter*_formal100k_ci_summary.json"
    return @(Get-ChildItem -Path (Join-Path $Repo "models") -Filter $filter -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)[0]
}

function Should-PreserveSlumbotWatcher($proc) {
    $cmd = $proc.CommandLine
    if (-not $cmd) { return $false }
    if ($cmd -notlike "*v5_slumbot_benchmark_watch.py*") { return $false }

    foreach ($stage in @("promotion20k", "formal100k")) {
        if ($cmd -notlike "*--stage $stage*") { continue }
        $status = Get-ActiveSlumbotStatus $stage
        if ($null -eq $status) { continue }
        if ($status.state -eq "RUNNING") {
            Log "Idempotency: preserving active Slumbot $stage watcher PID $($proc.ProcessId) (status RUNNING)"
            $script:preservedSlumbotWatchers += [pscustomobject]@{
                script = "v5_slumbot_benchmark_watch.py:$stage"
                stage = $stage
                pid = $proc.ProcessId
                status_json = $status.path
                preserved = $true
            }
            return $true
        }
    }
    return $false
}

function Get-PreservedSlumbotWatcher($stage) {
    return @($script:preservedSlumbotWatchers | Where-Object { $_.stage -eq $stage } | Select-Object -First 1)[0]
}

function Get-JsonProcessIdentity($proc) {
    if ($null -eq $proc) { return $null }
    return $proc | Select-Object ProcessId,Name,CreationDate,CommandLine |
        ConvertTo-Json -Compress | ConvertFrom-Json
}

function Test-ExactProcessIdentity($proc, $expected) {
    if (($null -eq $proc) -or ($null -eq $expected)) { return $false }
    $actual = Get-JsonProcessIdentity $proc
    return (
        ([int]$actual.ProcessId -eq [int]$expected.pid) -and
        ([string]$actual.CreationDate -eq [string]$expected.creation_date) -and
        ([string]$actual.CommandLine -eq [string]$expected.command_line)
    )
}

function Should-PreserveExp003BundleWatcher($proc) {
    if ($script:isExp005EvidenceRun) { return $false }
    $cmd = [string]$proc.CommandLine
    if ($cmd -notlike '*v5_exp003_bundle_watch.py*') { return $false }
    $statusPath = Join-Path $RunDirAbs 'v5_exp003_bundle_watch_status.json'
    $status = Read-JsonFile $statusPath
    if (($null -eq $status) -or ([string]$status.overall -ne 'RUNNING')) { return $false }
    if (-not (Test-ExactProcessIdentity $proc $status.watcher_identity)) {
        throw "Refusing re-arm: EXP-003 bundle status is RUNNING but watcher PID/CreationDate/cmd is not exact"
    }
    if ($null -ne $status.launcher_pid) {
        $child = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq [int]$status.launcher_pid } |
            Select-Object -First 1
        $expectedChild = [pscustomobject]@{
            pid = $status.launcher_pid
            creation_date = $status.launcher_creation_date
            command_line = $status.launcher_command_line
        }
        if (-not (Test-ExactProcessIdentity $child $expectedChild)) {
            throw "Refusing re-arm: exact RUNNING EXP-003 evaluator child could not be proven; watcher will not be killed"
        }
    }
    $script:preservedExp003BundleWatcher = [pscustomobject]@{
        script = 'v5_exp003_bundle_watch.py'
        pid = [int]$proc.ProcessId
        out = Join-Path $RunDirAbs 'exp003_bundle_watch_rearmed.out.log'
        err = Join-Path $RunDirAbs 'exp003_bundle_watch_rearmed.err.log'
        preserved = $true
    }
    Log "Idempotency: preserving exact RUNNING EXP-003 bundle watcher PID $($proc.ProcessId) and its declared child"
    return $true
}

# IDEMPOTENCY GUARD (Fable 2026-07-08): kill existing watcher instances BEFORE
# spawning, so repeated re-arms can never stack duplicates. Never touches the
# trainer (train_v5 / multiprocessing workers are explicitly excluded).
$watcherScripts = @('v5_health_watch.py','v5_dashboard_watch.py','v5_gate_sequence_watch.py',
                    'v5_eval_cadence_watch.py','v5_internal_strength_watch.py',
                    'v5_checkpoint_archive_watch.py','v5_exp003_freeze_watch.py',
                    'v5_exp003_bundle_watch.py',
                    'v5_pilot_endpoint_stop_watch.py',
                    'v5_exp_w1_arm_endpoint_freeze_watch.py',
                    'v5_hybrid_h1_endpoint_watch.py',
                    'v5_hybrid_h2_endpoint_watch.py',
                    'v5_hybrid_h2_protocol_watch.py',
                    'v5_hybrid_h2_treatment_launch_watch.py',
                    'v5_hybrid_h2_completion_watch.py',
                    'v5_hybrid_h6_endpoint_watch.py',
                    'v5_hybrid_h6_protocol_watch.py',
                    'v5_hybrid_h6_completion_watch.py',
                    'v5_hybrid_h7_endpoint_watch.py',
                    'v5_hybrid_h7_protocol_watch.py',
                    'v5_hybrid_h7_treatment_launch_watch.py',
                    'v5_hybrid_h7_completion_watch.py',
                    'v5_hybrid_h8_endpoint_watch.py',
                    'v5_hybrid_h8_protocol_watch.py',
                    'v5_hybrid_h8_treatment_launch_watch.py',
                    'v5_hybrid_h8_completion_watch.py',
                    'v5_hybrid_h12_ordered_rearm.py',
                    'v5_hybrid_h12_health_watch.py',
                    'v5_hybrid_h12_endpoint_watch.py',
                    'v5_hybrid_h12_protocol_watch.py',
                    'v5_hybrid_h12_treatment_launch_watch.py',
                    'v5_hybrid_h12_completion_watch.py',
                    'v5_hybrid_h13_ordered_rearm.py',
                    'v5_hybrid_h13_health_watch.py',
                    'v5_hybrid_h13_endpoint_watch.py',
                    'v5_hybrid_h13_protocol_watch.py',
                    'v5_hybrid_h13_treatment_launch_watch.py',
                    'v5_hybrid_h13_completion_watch.py',
                    'v5_hybrid_h14_ordered_rearm.py',
                    'v5_hybrid_h14_health_watch.py',
                    'v5_hybrid_h14_endpoint_watch.py',
                    'v5_hybrid_h14_protocol_watch.py',
                    'v5_hybrid_h14_treatment_launch_watch.py',
                    'v5_hybrid_h14_completion_watch.py',
                    'v5_hybrid_h15_ordered_rearm.py',
                    'v5_hybrid_h15_health_watch.py',
                    'v5_hybrid_h15_endpoint_watch.py',
                    'v5_hybrid_h15_protocol_watch.py',
                    'v5_hybrid_h15_treatment_launch_watch.py',
                    'v5_hybrid_h15_completion_watch.py',
                    'v5_ops_log_watch.py','v5_throughput_watch.py',
                    'v5_slumbot_benchmark_watch.py','v5_gate_watch.py')
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $c = $_.CommandLine
    if (-not $c) { return $false }
    if ($c -like '*multiprocessing*' -or $c -like '*train_v5*') { return $false }
    foreach ($s in $watcherScripts) { if ($c -like "*$s*") { return $true } }
    return $false
}
# A watcher can invoke a launcher which, in turn, invokes this canonical re-arm.
# Killing that ancestor watcher here leaves its launch status permanently stuck at
# RUNNING even though the child launch and re-arm succeeded.  Preserve only the
# exact current process ancestry; ordinary/manual re-arms have no watcher ancestor.
$protectedAncestorPids = @{}
$ancestorPid = [int]$PID
while ($ancestorPid -gt 0) {
    $ancestor = Get-CimInstance Win32_Process -Filter "ProcessId=$ancestorPid" -ErrorAction SilentlyContinue
    if (-not $ancestor) { break }
    $parentPid = [int]$ancestor.ParentProcessId
    if ($parentPid -le 0 -or $protectedAncestorPids.ContainsKey($parentPid)) { break }
    $protectedAncestorPids[$parentPid] = $true
    $ancestorPid = $parentPid
}
foreach ($e in $existing) {
    if ($protectedAncestorPids.ContainsKey([int]$e.ProcessId)) {
        Log "Idempotency: preserving invoking ancestor watcher PID $($e.ProcessId)"
        continue
    }
    if (Should-PreserveSlumbotWatcher $e) { continue }
    if (Should-PreserveExp003BundleWatcher $e) { continue }
    Log "Idempotency: stopping existing watcher PID $($e.ProcessId)"
    Stop-Process -Id $e.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

$script:launched = @()

# Verbatim from continue for health (simplified for rearm, full in continue)
function Launch-Health {
    $outLog = Join-Path $RunDirAbs "health_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "health_watch_rearmed.err.log"
    $healthLog = Join-Path $RunDirAbs "health_watch.log"
    $healthArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_health_watch.py",
        "--run-dir", $RunDirAbs,
        "--poll-seconds", "30",
        "--log", $healthLog
    )
    $p = Start-Process -FilePath $Python -ArgumentList $healthArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_health_watch.py PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_health_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# Verbatim-ish for dashboard
function Launch-Dashboard {
    $outLog = Join-Path $RunDirAbs "dashboard_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "dashboard_watch_rearmed.err.log"
    $dashLog = Join-Path $RunDirAbs "v5_dashboard_watch.log"
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_dashboard_watch.py",
        "--run-dir", $RunDirAbs
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_dashboard_watch.py PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_dashboard_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# Append-only Ops-log watcher. It is reporting-only and was added to the
# canonical rearm after the 2026-07-09 ledger gap was reconciled.
function Launch-OpsLog {
    $outLog = Join-Path $RunDirAbs "ops_log_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "ops_log_watch_rearmed.err.log"
    $statusJson = Join-Path $RunDirAbs "v5_ops_log_watch_status.json"
    $ledger = Join-Path $Repo "reports\v5_experiment_ledger.md"
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_ops_log_watch.py",
        "--run-dir", $RunDirAbs,
        "--ledger", $ledger,
        "--status-json", $statusJson,
        "--poll-seconds", "120"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_ops_log_watch.py PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_ops_log_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# Verbatim for gate_sequence, with caller-specified range for continuation runs.
function Launch-GateSequence {
    $outLog = Join-Path $RunDirAbs "gate_sequence_${GateStartIteration}_${GateMaxIteration}_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "gate_sequence_${GateStartIteration}_${GateMaxIteration}_rearmed.err.log"
    $seqLog = Join-Path $RunDirAbs "gate_sequence_watch.log"
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_gate_sequence_watch.py",
        "--run-dir", $RunDirAbs,
        "--start-iteration", "$GateStartIteration",
        "--max-iteration", "$GateMaxIteration",
        "--step", "100",
        "--snapshot-every", "200",
        "--k-best", "5",
        "--expected-pool-snapshots", "5",
        "--expected-opponent-assignment", $script:expectedOpponentAssignment,
        "--expected-pool-strategy", "loss-kbest",
        "--require-current-pool-snapshot-on-snapshot-gates",
        "--refresh-health",
        "--python", $Python,
        "--poll-seconds", "60",
        "--timeout-seconds", "14400",
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_gate_sequence_watch.py PID $($p.Id) start=$GateStartIteration max=$GateMaxIteration"
    $script:launched += [pscustomobject]@{ script = "v5_gate_sequence_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# For eval_cadence (from current)
function Launch-EvalCadence {
    $outLog = Join-Path $RunDirAbs "eval_cadence_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "eval_cadence_rearmed.err.log"
    $cadLog = Join-Path $RunDirAbs "v5_eval_cadence_watch.log"
    # FLOOR FLAGS (Fable 2026-07-08, mandated by 14:40 incident row): without
    # these a rebooted/re-armed cadence watcher re-exposes early milestones
    # (the 50M-mislabel misfire). 200M quick5k is done; next targets are 250M.
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_eval_cadence_watch.py",
        "--run-dir", $RunDirAbs,
        "--min-quick-target-hands", "250000000",
        "--min-promotion-target-hands", "250000000",
        "--min-formal-target-hands", "250000000"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_eval_cadence_watch.py PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_eval_cadence_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# Verbatim for internal, with caller-specified range for continuation runs.
function Launch-Internal {
    $internalStart = $InternalStartIteration
    $internalMax = $InternalMaxIteration
    $internalStep = 100
    $internalHands = 200
    $internalOut = Join-Path $RunDirAbs "internal_strength_watch_rearmed.out.log"
    $internalErr = Join-Path $RunDirAbs "internal_strength_watch_rearmed.err.log"
    $internalStatus = Join-Path $RunDirAbs "internal_strength_watch_status.json"
    $internalLog = Join-Path $RunDirAbs "internal_strength_watch.log"
    $internalArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_internal_strength_watch.py",
        "--run-dir", $RunDirAbs,
        "--start-iteration", "$internalStart",
        "--max-iteration", "$internalMax",
        "--step", "$internalStep",
        "--hands", "$internalHands",
        "--require-health-pass",
        "--python", $Python,
        "--status-json", $internalStatus,
        "--log", $internalLog,
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $internalArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $internalOut `
        -RedirectStandardError $internalErr `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_internal_strength_watch.py PID $($p.Id) targets=$internalStart..$internalMax"
    $script:launched += [pscustomobject]@{ script = "v5_internal_strength_watch.py"; pid = $p.Id; out = $internalOut; err = $internalErr }
    return $p
}

# Verbatim for checkpoint archive
function Launch-Archive {
    $archiveOut = Join-Path $RunDirAbs "checkpoint_archive_watch_rearmed.out.log"
    $archiveErr = Join-Path $RunDirAbs "checkpoint_archive_watch_rearmed.err.log"
    $archiveStatus = Join-Path $RunDirAbs "checkpoint_archive_status.json"
    $archiveLog = Join-Path $RunDirAbs "checkpoint_archive_watch.log"
    $archiveArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_checkpoint_archive_watch.py",
        "--run-dir", $RunDirAbs,
        "--status-json", $archiveStatus,
        "--log", $archiveLog,
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md",
        "--sleep-seconds", "300"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $archiveArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $archiveOut `
        -RedirectStandardError $archiveErr `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_checkpoint_archive_watch.py PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_checkpoint_archive_watch.py"; pid = $p.Id; out = $archiveOut; err = $archiveErr }
    return $p
}

function Launch-PilotEndpointStop {
    if (-not $script:isExp005PilotRun) { return $null }
    $outLog = Join-Path $RunDirAbs "pilot_endpoint_stop_watch.out.log"
    $errLog = Join-Path $RunDirAbs "pilot_endpoint_stop_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "pilot_endpoint_stop_status.json"
    $existingStatus = Read-JsonFile $statusJson
    if (($null -ne $existingStatus) -and ([string]$existingStatus.overall -eq "PASS") -and ([string]$existingStatus.state -eq "PILOT_STOPPED_AT_ENDPOINT")) {
        $reason = "pilot already stopped at exact endpoint"
        Log "Skipping v5_pilot_endpoint_stop_watch.py: $reason"
        $script:launched += [pscustomobject]@{ script = "v5_pilot_endpoint_stop_watch.py"; pid = -1; out = $outLog; err = $errLog; skipped = $true; skip_reason = $reason }
        return $null
    }
    $trainerPid = [int]$runManifest.process_id
    if ($trainerPid -le 0) {
        throw "Refusing pilot stop watcher launch: manifest has no positive process_id"
    }
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_pilot_endpoint_stop_watch.py",
        "--run-dir", $RunDirAbs,
        "--expected-pid", "$trainerPid",
        "--target-iteration", "32700",
        "--min-hands", "535989661",
        "--poll-seconds", "30",
        "--status-json", $statusJson
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_pilot_endpoint_stop_watch.py PID $($p.Id) trainer_pid=$trainerPid endpoint=32700/535989661"
    $script:launched += [pscustomobject]@{ script = "v5_pilot_endpoint_stop_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

function Launch-ExpW1EndpointFreeze {
    if ($script:isHybridH11Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H11 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h11_design_lock_20260715.json"; $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant(); $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h11_endpoint_watch.py"; $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h11_endpoint_watch.py'
        if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H11 endpoint watcher tool SHA mismatch" }
        $outLog=Join-Path $RunDirAbs "h11_${arm}_endpoint_watch.out.log";$errLog=Join-Path $RunDirAbs "h11_${arm}_endpoint_watch.err.log";$statusJson=Join-Path $RunDirAbs "h11_${arm}_endpoint_status.json"
        $args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","30","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h11_endpoint_watch.py PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h11_endpoint_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
    }
    if ($script:isHybridH10Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H10 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h10_design_lock_20260715.json"; $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant(); $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h10_endpoint_watch.py"; $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h10_endpoint_watch.py'
        if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H10 endpoint watcher tool SHA mismatch" }
        $outLog=Join-Path $RunDirAbs "h10_${arm}_endpoint_watch.out.log";$errLog=Join-Path $RunDirAbs "h10_${arm}_endpoint_watch.err.log";$statusJson=Join-Path $RunDirAbs "h10_${arm}_endpoint_status.json"
        $args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","30","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h10_endpoint_watch.py PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h10_endpoint_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
    }
    if ($script:isHybridH9Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H9 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h9_design_lock_20260714.json"; $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant(); $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h9_endpoint_watch.py"; $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h9_endpoint_watch.py'
        if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H9 endpoint watcher tool SHA mismatch" }
        $outLog=Join-Path $RunDirAbs "h9_${arm}_endpoint_watch.out.log";$errLog=Join-Path $RunDirAbs "h9_${arm}_endpoint_watch.err.log";$statusJson=Join-Path $RunDirAbs "h9_${arm}_endpoint_status.json"
        $args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","30","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h9_endpoint_watch.py PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h9_endpoint_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
    }
    if ($script:isHybridH8Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H8 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h8_design_lock_v5_20260714.json"; $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant(); $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h8_endpoint_watch.py"; $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h8_endpoint_watch.py'
        if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H8 endpoint watcher tool SHA mismatch" }
        $outLog=Join-Path $RunDirAbs "h8_${arm}_endpoint_watch.out.log";$errLog=Join-Path $RunDirAbs "h8_${arm}_endpoint_watch.err.log";$statusJson=Join-Path $RunDirAbs "h8_${arm}_endpoint_status.json"
        $args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","30","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h8_endpoint_watch.py PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h8_endpoint_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
    }
    if ($script:isHybridH7Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H7 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h7_design_lock_20260713.json"; $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant(); $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h7_endpoint_watch.py"; $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h7_endpoint_watch.py'
        if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H7 endpoint watcher tool SHA mismatch" }
        $outLog=Join-Path $RunDirAbs "h7_${arm}_endpoint_watch.out.log";$errLog=Join-Path $RunDirAbs "h7_${arm}_endpoint_watch.err.log";$statusJson=Join-Path $RunDirAbs "h7_${arm}_endpoint_status.json"
        $args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","30","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h7_endpoint_watch.py PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h7_endpoint_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
    }
    if ($script:isHybridH6Arm) {
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h6_design_lock_20260713.json"
        if (-not (Test-Path -LiteralPath $lockPath)) { throw "H6 immutable design lock missing" }
        $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $lockData = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
        $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h6_endpoint_watch.py"
        $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h6_endpoint_watch.py'
        if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H6 endpoint watcher tool SHA mismatch" }
        $outLog = Join-Path $RunDirAbs "h6_treatment_endpoint_watch.out.log"; $errLog = Join-Path $RunDirAbs "h6_treatment_endpoint_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h6_treatment_endpoint_status.json"
        $args = @("-u", $toolPath, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--poll-seconds", "30", "--status-json", $statusJson)
        $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h6_endpoint_watch.py PID $($proc.Id)"
        $script:launched += [pscustomobject]@{ script = "v5_hybrid_h6_endpoint_watch.py:treatment"; pid = $proc.Id; out = $outLog; err = $errLog }
        return $proc
    }
    if ($script:isHybridH2Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H2 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h2_design_lock_20260713.json"
        if (-not (Test-Path -LiteralPath $lockPath)) { throw "H2 immutable design lock missing" }
        $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $outLog = Join-Path $RunDirAbs "h2_${arm}_endpoint_watch.out.log"; $errLog = Join-Path $RunDirAbs "h2_${arm}_endpoint_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h2_${arm}_endpoint_status.json"
        $args = @("-u", "scripts/alpha_holdem/v5_hybrid_h2_endpoint_watch.py", "--arm", $arm, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--poll-seconds", "30", "--status-json", $statusJson)
        $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h2_endpoint_watch.py PID $($proc.Id) arm=$arm"
        $script:launched += [pscustomobject]@{ script = "v5_hybrid_h2_endpoint_watch.py:$arm"; pid = $proc.Id; out = $outLog; err = $errLog }
        return $proc
    }
    if ($script:isHybridH1Arm) {
        $runId = [string]$runManifest.run_id
        $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H1 run_id does not identify arm" }
        $lockPath = Resolve-RepoPath "reports/v5_hybrid_h1_design_lock_v3_20260712.json"
        if (-not (Test-Path -LiteralPath $lockPath)) { throw "H1 immutable design lock missing" }
        $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $outLog = Join-Path $RunDirAbs "h1_${arm}_endpoint_watch.out.log"; $errLog = Join-Path $RunDirAbs "h1_${arm}_endpoint_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h1_${arm}_endpoint_status.json"
        $args = @("-u", "scripts/alpha_holdem/v5_hybrid_h1_endpoint_watch.py", "--arm", $arm, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--poll-seconds", "30", "--status-json", $statusJson)
        $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
        Log "Started v5_hybrid_h1_endpoint_watch.py PID $($proc.Id) arm=$arm"
        $script:launched += [pscustomobject]@{ script = "v5_hybrid_h1_endpoint_watch.py:$arm"; pid = $proc.Id; out = $outLog; err = $errLog }
        return $proc
    }
    if (-not $script:isExpW1Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "EXP-W1 run_id does not identify control/treatment arm" }
    $lockPath = [string]$runManifest.config.exp_w1_design_lock
    $lockSha = [string]$runManifest.config.exp_w1_design_lock_sha256
    if ([string]::IsNullOrWhiteSpace($lockPath) -or [string]::IsNullOrWhiteSpace($lockSha)) {
        throw "EXP-W1 manifest missing immutable design-lock identity"
    }
    $lockPath = Resolve-RepoPath $lockPath
    if (-not (Test-Path -LiteralPath $lockPath)) {
        throw "EXP-W1 design lock missing: $lockPath"
    }
    $actualLockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualLockSha -ne $lockSha.ToLowerInvariant()) {
        throw "EXP-W1 design lock SHA mismatch during canonical rearm"
    }
    $outLog = Join-Path $RunDirAbs "exp_w1_$($arm)_endpoint_freeze_watch.out.log"
    $errLog = Join-Path $RunDirAbs "exp_w1_$($arm)_endpoint_freeze_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "exp_w1_$($arm)_endpoint_freeze_status.json"
    $args = @(
        "-u", "scripts/alpha_holdem/v5_exp_w1_arm_endpoint_freeze_watch.py",
        "--repo", $Repo,
        "--arm", $arm,
        "--design-lock", $lockPath,
        "--expected-lock-sha256", $lockSha,
        "--poll-seconds", "30",
        "--status-json", $statusJson
    )
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_exp_w1_arm_endpoint_freeze_watch.py PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{ script = "v5_exp_w1_arm_endpoint_freeze_watch.py:$arm"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

function Launch-H9ProtocolWatch {
    if (-not $script:isHybridH9Arm) { return $null };$runId=[string]$runManifest.run_id;$arm=if($runId-like"*control*"){"control"}elseif($runId-like"*treatment*"){"treatment"}else{throw"H9 arm identity"}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h9_design_lock_20260714.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h9_protocol_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h9_protocol_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H9 protocol tool SHA"}
    $outLog=Join-Path $RunDirAbs "h9_${arm}_protocol_watch.out.log";$errLog=Join-Path $RunDirAbs "h9_${arm}_protocol_watch.err.log";$statusJson=Join-Path $RunDirAbs "h9_${arm}_protocol_status.json";$args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","15","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H9 protocol PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h9_protocol_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H10ProtocolWatch {
    if (-not $script:isHybridH10Arm) { return $null };$runId=[string]$runManifest.run_id;$arm=if($runId-like"*control*"){"control"}elseif($runId-like"*treatment*"){"treatment"}else{throw"H10 arm identity"}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h10_design_lock_20260715.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h10_protocol_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h10_protocol_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H10 protocol tool SHA"}
    $outLog=Join-Path $RunDirAbs "h10_${arm}_protocol_watch.out.log";$errLog=Join-Path $RunDirAbs "h10_${arm}_protocol_watch.err.log";$statusJson=Join-Path $RunDirAbs "h10_${arm}_protocol_status.json";$args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","15","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H10 protocol PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h10_protocol_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H10TreatmentLaunchWatch {
    if (-not $script:isHybridH10Arm) { return $null };if(([string]$runManifest.run_id)-notlike"*control*"){$script:launched += [pscustomobject]@{script="v5_hybrid_h10_treatment_launch_watch.py";pid=-1;out="";err="";skipped=$true;skip_reason="H10 treatment cannot launch another treatment"};return $null}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h10_design_lock_20260715.json";$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h10_treatment_launch_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h10_treatment_launch_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H10 treatment launch watch SHA"}
    $controlDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h10_control_catchmse_same33834_20m_r1_20260715";$treatmentDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h10_treatment_catchsmoothl1b1_same33834_20m_r1_20260715";$launcher=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h10_launch_treatment.ps1";$outLog=Join-Path $controlDir 'h10_treatment_launch_watch.out.log';$errLog=Join-Path $controlDir 'h10_treatment_launch_watch.err.log';$statusJson=Join-Path $controlDir 'h10_treatment_launch_watch_status.json';$args=@("-u",$toolPath,"--control-dir",$controlDir,"--treatment-dir",$treatmentDir,"--launcher",$launcher,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H10 treatment launch watch PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h10_treatment_launch_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H10CompletionWatch {
    if (-not $script:isHybridH10Arm) { return $null };$lockPath=Resolve-RepoPath "reports/v5_hybrid_h10_design_lock_20260715.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h10_completion_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h10_completion_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H10 completion tool SHA"}
    $outLog=Join-Path $RunDirAbs 'h10_completion_watch.out.log';$errLog=Join-Path $RunDirAbs 'h10_completion_watch.err.log';$statusJson=Join-Path $RunDirAbs 'h10_completion_watch_status.json';$args=@("-u",$toolPath,"--repo",$Repo,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H10 completion PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h10_completion_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H12OrderedRearm {
    if (-not $script:isHybridH12Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H12 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h12_design_lock_v2_20260716.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H12 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h12_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h12_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h12_ordered_rearm_status.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H12 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h12_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H13OrderedRearm {
    if (-not $script:isHybridH13Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H13 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h13_design_lock_v2_20260716.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h13_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h13_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H13 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h13_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h13_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h13_ordered_rearm_status.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H13 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h13_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H14OrderedRearm {
    if (-not $script:isHybridH14Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H14 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h14_design_lock_v6_20260717.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h14_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h14_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H14 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h14_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h14_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h14_ordered_rearm_status.json"
    $registry = Join-Path $RunDirAbs "h14_lifecycle_allow_registry.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--allow-registry",$registry,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H14 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h14_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H15OrderedRearm {
    if (-not $script:isHybridH15Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H15 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h15_design_lock_v3_20260719.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h15_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h15_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H15 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h15_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h15_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h15_ordered_rearm_status.json"
    $registry = Join-Path $RunDirAbs "h15_lifecycle_allow_registry.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--allow-registry",$registry,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H15 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h15_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H16OrderedRearm {
    if (-not $script:isHybridH16Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H16 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h16_design_lock_v1_20260719.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h16_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h16_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H16 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h16_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h16_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h16_ordered_rearm_status.json"
    $registry = Join-Path $RunDirAbs "h16_lifecycle_allow_registry.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--allow-registry",$registry,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H16 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h16_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H17OrderedRearm {
    if (-not $script:isHybridH17Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H17 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h17_design_lock_v1_20260719.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h17_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h17_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H17 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h17_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h17_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h17_ordered_rearm_status.json"
    $registry = Join-Path $RunDirAbs "h17_lifecycle_allow_registry.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--allow-registry",$registry,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H17 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h17_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H18OrderedRearm {
    if (-not $script:isHybridH18Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H18 arm identity" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h18_design_lock_v1_20260719.json"
    $lockSha = (Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h18_ordered_rearm.py"
    $expected = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h18_ordered_rearm.py'
    if ((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw "H18 ordered rearm tool SHA" }
    $outLog = Join-Path $RunDirAbs "h18_ordered_rearm.out.log"
    $errLog = Join-Path $RunDirAbs "h18_ordered_rearm.err.log"
    $statusJson = Join-Path $RunDirAbs "h18_ordered_rearm_status.json"
    $registry = Join-Path $RunDirAbs "h18_lifecycle_allow_registry.json"
    $args = @("-u",$toolPath,"--repo",$Repo,"--run-dir",$RunDirAbs,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--allow-registry",$registry,"--readiness-timeout-seconds","180")
    $proc = Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started H18 dependency-ordered rearm supervisor PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{script="v5_hybrid_h18_ordered_rearm.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog}
    return $proc
}

function Launch-H11ProtocolWatch {
    if (-not $script:isHybridH11Arm) { return $null };$runId=[string]$runManifest.run_id;$arm=if($runId-like"*control*"){"control"}elseif($runId-like"*treatment*"){"treatment"}else{throw"H11 arm identity"}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h11_design_lock_20260715.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h11_protocol_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h11_protocol_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H11 protocol tool SHA"}
    $outLog=Join-Path $RunDirAbs "h11_${arm}_protocol_watch.out.log";$errLog=Join-Path $RunDirAbs "h11_${arm}_protocol_watch.err.log";$statusJson=Join-Path $RunDirAbs "h11_${arm}_protocol_status.json";$args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","15","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H11 protocol PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h11_protocol_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H11TreatmentLaunchWatch {
    if (-not $script:isHybridH11Arm) { return $null };if(([string]$runManifest.run_id)-notlike"*control*"){$script:launched += [pscustomobject]@{script="v5_hybrid_h11_treatment_launch_watch.py";pid=-1;out="";err="";skipped=$true;skip_reason="H11 treatment cannot launch another treatment"};return $null}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h11_design_lock_20260715.json";$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h11_treatment_launch_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h11_treatment_launch_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H11 treatment launch watch SHA"}
    $controlDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715";$treatmentDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_treatment_catchsmoothl1b1_same33834_20m_r1_20260715";$launcher=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h11_launch_treatment.ps1";$outLog=Join-Path $controlDir 'h11_treatment_launch_watch.out.log';$errLog=Join-Path $controlDir 'h11_treatment_launch_watch.err.log';$statusJson=Join-Path $controlDir 'h11_treatment_launch_watch_status.json';$args=@("-u",$toolPath,"--control-dir",$controlDir,"--treatment-dir",$treatmentDir,"--launcher",$launcher,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H11 treatment launch watch PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h11_treatment_launch_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H11CompletionWatch {
    if (-not $script:isHybridH11Arm) { return $null };$lockPath=Resolve-RepoPath "reports/v5_hybrid_h11_design_lock_20260715.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h11_completion_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h11_completion_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H11 completion tool SHA"}
    $outLog=Join-Path $RunDirAbs 'h11_completion_watch.out.log';$errLog=Join-Path $RunDirAbs 'h11_completion_watch.err.log';$statusJson=Join-Path $RunDirAbs 'h11_completion_watch_status.json';$args=@("-u",$toolPath,"--repo",$Repo,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H11 completion PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h11_completion_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H9TreatmentLaunchWatch {
    if (-not $script:isHybridH9Arm) { return $null };if(([string]$runManifest.run_id)-notlike"*control*"){$script:launched += [pscustomobject]@{script="v5_hybrid_h9_treatment_launch_watch.py";pid=-1;out="";err="";skipped=$true;skip_reason="H9 treatment cannot launch another treatment"};return $null}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h9_design_lock_20260714.json";$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h9_treatment_launch_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h9_treatment_launch_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H9 treatment launch watch SHA"}
    $controlDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h9_control_catchmse_same33834_20m_r1_20260714";$treatmentDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h9_treatment_catchsmoothl1b1_same33834_20m_r1_20260714";$launcher=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h9_launch_treatment.ps1";$outLog=Join-Path $controlDir 'h9_treatment_launch_watch.out.log';$errLog=Join-Path $controlDir 'h9_treatment_launch_watch.err.log';$statusJson=Join-Path $controlDir 'h9_treatment_launch_watch_status.json';$args=@("-u",$toolPath,"--control-dir",$controlDir,"--treatment-dir",$treatmentDir,"--launcher",$launcher,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H9 treatment launch watch PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h9_treatment_launch_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H9CompletionWatch {
    if (-not $script:isHybridH9Arm) { return $null };$lockPath=Resolve-RepoPath "reports/v5_hybrid_h9_design_lock_20260714.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h9_completion_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h9_completion_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H9 completion tool SHA"}
    $outLog=Join-Path $RunDirAbs 'h9_completion_watch.out.log';$errLog=Join-Path $RunDirAbs 'h9_completion_watch.err.log';$statusJson=Join-Path $RunDirAbs 'h9_completion_watch_status.json';$args=@("-u",$toolPath,"--repo",$Repo,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H9 completion PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h9_completion_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H8ProtocolWatch {
    if (-not $script:isHybridH8Arm) { return $null };$runId=[string]$runManifest.run_id;$arm=if($runId-like"*control*"){"control"}elseif($runId-like"*treatment*"){"treatment"}else{throw"H8 arm identity"}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h8_design_lock_v5_20260714.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h8_protocol_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h8_protocol_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H8 protocol tool SHA"}
    $outLog=Join-Path $RunDirAbs "h8_${arm}_protocol_watch.out.log";$errLog=Join-Path $RunDirAbs "h8_${arm}_protocol_watch.err.log";$statusJson=Join-Path $RunDirAbs "h8_${arm}_protocol_status.json";$args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","15","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H8 protocol PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h8_protocol_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H8TreatmentLaunchWatch {
    if (-not $script:isHybridH8Arm) { return $null };if(([string]$runManifest.run_id)-notlike"*control*"){$script:launched += [pscustomobject]@{script="v5_hybrid_h8_treatment_launch_watch.py";pid=-1;out="";err="";skipped=$true;skip_reason="H8 treatment cannot launch another treatment"};return $null}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h8_design_lock_v5_20260714.json";$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h8_treatment_launch_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h8_treatment_launch_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H8 treatment launch watch SHA"}
    $controlDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h8_control_kles003_nocatch_same32617_20m_r1_20260714";$treatmentDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714";$launcher=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h8_launch_treatment.ps1";$outLog=Join-Path $controlDir 'h8_treatment_launch_watch.out.log';$errLog=Join-Path $controlDir 'h8_treatment_launch_watch.err.log';$statusJson=Join-Path $controlDir 'h8_treatment_launch_watch_status.json';$args=@("-u",$toolPath,"--control-dir",$controlDir,"--treatment-dir",$treatmentDir,"--launcher",$launcher,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H8 treatment launch watch PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h8_treatment_launch_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H8CompletionWatch {
    if (-not $script:isHybridH8Arm) { return $null };$lockPath=Resolve-RepoPath "reports/v5_hybrid_h8_design_lock_v5_20260714.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h8_completion_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h8_completion_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H8 completion tool SHA"}
    $outLog=Join-Path $RunDirAbs 'h8_completion_watch.out.log';$errLog=Join-Path $RunDirAbs 'h8_completion_watch.err.log';$statusJson=Join-Path $RunDirAbs 'h8_completion_watch_status.json';$args=@("-u",$toolPath,"--repo",$Repo,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H8 completion PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h8_completion_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}
function Launch-H7ProtocolWatch {
    if (-not $script:isHybridH7Arm) { return $null };$runId=[string]$runManifest.run_id;$arm=if($runId-like"*control*"){"control"}elseif($runId-like"*treatment*"){"treatment"}else{throw"H7 arm identity"}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h7_design_lock_20260713.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h7_protocol_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h7_protocol_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H7 protocol tool SHA"}
    $outLog=Join-Path $RunDirAbs "h7_${arm}_protocol_watch.out.log";$errLog=Join-Path $RunDirAbs "h7_${arm}_protocol_watch.err.log";$statusJson=Join-Path $RunDirAbs "h7_${arm}_protocol_status.json";$args=@("-u",$toolPath,"--arm",$arm,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--poll-seconds","15","--status-json",$statusJson);$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H7 protocol PID $($proc.Id) arm=$arm";$script:launched += [pscustomobject]@{script="v5_hybrid_h7_protocol_watch.py:$arm";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H7TreatmentLaunchWatch {
    if (-not $script:isHybridH7Arm) { return $null };if(([string]$runManifest.run_id)-notlike"*control*"){$script:launched += [pscustomobject]@{script="v5_hybrid_h7_treatment_launch_watch.py";pid=-1;out="";err="";skipped=$true;skip_reason="H7 treatment cannot launch another treatment"};return $null}
    $lockPath=Resolve-RepoPath "reports/v5_hybrid_h7_design_lock_20260713.json";$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h7_treatment_launch_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h7_treatment_launch_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H7 treatment launch watch SHA"}
    $controlDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h7_control_kl0_same31400_20m_r1_20260713";$treatmentDir=Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h7_treatment_kles003_same31400_20m_r1_20260713";$launcher=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h7_launch_treatment.ps1";$outLog=Join-Path $controlDir 'h7_treatment_launch_watch.out.log';$errLog=Join-Path $controlDir 'h7_treatment_launch_watch.err.log';$statusJson=Join-Path $controlDir 'h7_treatment_launch_watch_status.json';$args=@("-u",$toolPath,"--control-dir",$controlDir,"--treatment-dir",$treatmentDir,"--launcher",$launcher,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H7 treatment launch watch PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h7_treatment_launch_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H7CompletionWatch {
    if (-not $script:isHybridH7Arm) { return $null };$lockPath=Resolve-RepoPath "reports/v5_hybrid_h7_design_lock_20260713.json";$lockSha=(Get-FileHash $lockPath -Algorithm SHA256).Hash.ToLowerInvariant();$lockData=Get-Content $lockPath -Raw|ConvertFrom-Json;$toolPath=Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h7_completion_watch.py";$expected=[string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h7_completion_watch.py';if((Get-FileHash $toolPath -Algorithm SHA256).Hash.ToLowerInvariant()-ne$expected){throw"H7 completion tool SHA"}
    $outLog=Join-Path $RunDirAbs 'h7_completion_watch.out.log';$errLog=Join-Path $RunDirAbs 'h7_completion_watch.err.log';$statusJson=Join-Path $RunDirAbs 'h7_completion_watch_status.json';$args=@("-u",$toolPath,"--repo",$Repo,"--design-lock",$lockPath,"--expected-lock-sha256",$lockSha,"--status-json",$statusJson,"--poll-seconds","30");$proc=Start-Process $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru;Log "Started H7 completion PID $($proc.Id)";$script:launched += [pscustomobject]@{script="v5_hybrid_h7_completion_watch.py";pid=$proc.Id;out=$outLog;err=$errLog};return $proc
}

function Launch-H6ProtocolWatch {
    if (-not $script:isHybridH6Arm) { return $null }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h6_design_lock_20260713.json"
    $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h6_protocol_watch.py"
    $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h6_protocol_watch.py'
    if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H6 protocol watcher tool SHA mismatch" }
    $outLog = Join-Path $RunDirAbs "h6_treatment_protocol_watch.out.log"; $errLog = Join-Path $RunDirAbs "h6_treatment_protocol_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h6_treatment_protocol_status.json"
    $args = @("-u", $toolPath, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--poll-seconds", "15", "--status-json", $statusJson)
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_hybrid_h6_protocol_watch.py PID $($proc.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_hybrid_h6_protocol_watch.py:treatment"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

function Launch-H6CompletionWatch {
    if (-not $script:isHybridH6Arm) { return $null }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h6_design_lock_20260713.json"
    $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $lockData = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h6_completion_watch.py"
    $expectedToolSha = [string]$lockData.tools.'scripts/alpha_holdem/v5_hybrid_h6_completion_watch.py'
    if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H6 completion watcher tool SHA mismatch" }
    $outLog = Join-Path $RunDirAbs "h6_completion_watch.out.log"; $errLog = Join-Path $RunDirAbs "h6_completion_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h6_completion_watch_status.json"
    $args = @("-u", $toolPath, "--repo", $Repo, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--status-json", $statusJson, "--poll-seconds", "30", "--stable-polls", "10")
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_hybrid_h6_completion_watch.py PID $($proc.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_hybrid_h6_completion_watch.py"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

function Launch-H2ProtocolWatch {
    if (-not $script:isHybridH2Arm) { return $null }
    $runId = [string]$runManifest.run_id
    $arm = if ($runId -like "*control*") { "control" } elseif ($runId -like "*treatment*") { "treatment" } else { throw "H2 run_id does not identify arm" }
    $toolPath = Resolve-RepoPath "scripts/v5_hybrid_h2_protocol_watch.py"
    if (-not (Test-Path -LiteralPath $toolPath)) { $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h2_protocol_watch.py" }
    $expectedToolSha = "de91a7d1d73adc0aa63b0d23091ea3b78503b1533040963abfda0a1f0363e970"
    if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H2 protocol watcher tool SHA mismatch" }
    $lockPath = Resolve-RepoPath "reports/v5_hybrid_h2_design_lock_20260713.json"
    $lockSha = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $outLog = Join-Path $RunDirAbs "h2_${arm}_protocol_watch.out.log"; $errLog = Join-Path $RunDirAbs "h2_${arm}_protocol_watch.err.log"; $statusJson = Join-Path $RunDirAbs "h2_${arm}_protocol_status.json"
    $args = @("-u", $toolPath, "--arm", $arm, "--design-lock", $lockPath, "--expected-lock-sha256", $lockSha, "--poll-seconds", "15", "--status-json", $statusJson)
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_hybrid_h2_protocol_watch.py PID $($proc.Id) arm=$arm"
    $script:launched += [pscustomobject]@{ script = "v5_hybrid_h2_protocol_watch.py:$arm"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

function Launch-H2TreatmentLaunchWatch {
    if (-not $script:isHybridH2Arm) { return $null }
    $runId = [string]$runManifest.run_id
    if ($runId -notlike "*control*") {
        $reason = "H2 treatment arm does not launch another treatment"
        Log "Skipping v5_hybrid_h2_treatment_launch_watch.py: $reason"
        $script:launched += [pscustomobject]@{ script = "v5_hybrid_h2_treatment_launch_watch.py"; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
        return $null
    }
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h2_treatment_launch_watch.py"
    $expectedToolSha = "6fe8883b25b3508485103ccb360639c42df4932a36d877f458b789b01545dcd2"
    if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H2 treatment launch watcher tool SHA mismatch" }
    $launcher = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h2_launch_treatment.ps1"
    $treatmentDir = Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h2_treatment_showdownk200_same31400_20m_r1_20260713"
    $outLog = Join-Path $RunDirAbs "h2_treatment_launch_watch.out.log"
    $errLog = Join-Path $RunDirAbs "h2_treatment_launch_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "h2_treatment_launch_watch_status.json"
    $args = @("-u", $toolPath, "--control-dir", $RunDirAbs, "--treatment-dir", $treatmentDir, "--launcher", $launcher, "--status-json", $statusJson, "--poll-seconds", "30")
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_hybrid_h2_treatment_launch_watch.py PID $($proc.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_hybrid_h2_treatment_launch_watch.py"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

function Launch-H2CompletionWatch {
    if (-not $script:isHybridH2Arm) { return $null }
    $toolPath = Resolve-RepoPath "scripts/alpha_holdem/v5_hybrid_h2_completion_watch.py"
    $expectedToolSha = "e1f27a0bd8dfd4234ec6ee1c9b70fe764f21d7c6a1ec603f93a785e3b47a1962"
    if ((Get-FileHash -LiteralPath $toolPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedToolSha) { throw "H2 completion watcher tool SHA mismatch" }
    $controlDir = Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h2_control_allinonly_same31400_20m_r1_20260713"
    $treatmentDir = Resolve-RepoPath "models/alpha_holdem_v5_hybrid/v5_hybrid_h2_treatment_showdownk200_same31400_20m_r1_20260713"
    $outLog = Join-Path $controlDir "h2_completion_watch.out.log"
    $errLog = Join-Path $controlDir "h2_completion_watch.err.log"
    $statusJson = Join-Path $controlDir "h2_completion_watch_status.json"
    $args = @("-u", $toolPath, "--repo", $Repo, "--control-dir", $controlDir, "--treatment-dir", $treatmentDir, "--status-json", $statusJson, "--poll-seconds", "30", "--stable-polls", "10")
    $proc = Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    Log "Started v5_hybrid_h2_completion_watch.py PID $($proc.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_hybrid_h2_completion_watch.py"; pid = $proc.Id; out = $outLog; err = $errLog }
    return $proc
}

# EXP-003 first-eligible-PASS freeze. This reporting-only watcher preserves the
# registered candidate before latest.pt can advance to the next checkpoint.
# Terminal PASS/FAIL is deliberately not relaunched: FAIL is sticky so a later
# checkpoint can never replace a missed first eligible PASS.
function Launch-Exp003Freeze {
    $outLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.err.log"
    $statusJson = Join-Path $RunDirAbs "exp003_judgment_freeze_status.json"
    if ($script:isExp005EvidenceRun) {
        $reason = if ($script:isExpW1Arm) { "EXP-003 is terminally INCONCLUSIVE; EXP-W1 arm must not reopen it" } else { "EXP-003 is terminally INCONCLUSIVE; EXP-005 evidence run must not reopen it" }
        Log "Skipping v5_exp003_freeze_watch.py: $reason"
        $script:launched += [pscustomobject]@{ script = "v5_exp003_freeze_watch.py"; pid = -1; out = $outLog; err = $errLog; skipped = $true; skip_reason = $reason }
        return $null
    }
    $status = Read-JsonFile $statusJson
    if (($null -ne $status) -and (@("PASS", "FAIL") -contains ([string]$status.overall).ToUpperInvariant())) {
        $reason = "terminal status $($status.overall); refusing to reselect a later checkpoint"
        Log "Skipping v5_exp003_freeze_watch.py: $reason"
        $script:launched += [pscustomobject]@{
            script = "v5_exp003_freeze_watch.py"
            pid = -1
            out = $outLog
            err = $errLog
            skipped = $true
            skip_reason = $reason
        }
        return $null
    }
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_exp003_freeze_watch.py",
        "--run-dir", $RunDirAbs,
        "--target-hands", "408064575",
        "--status-json", $statusJson,
        "--poll-seconds", "10"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_exp003_freeze_watch.py PID $($p.Id) target_hands=408064575"
    $script:launched += [pscustomobject]@{ script = "v5_exp003_freeze_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# EXP-003 fixed-bundle launcher. It is evaluation/reporting-only and waits for
# the terminal first-eligible freeze. A RUNNING instance is preserved above by
# exact PID+CreationDate+command identity so its evaluator child is never
# orphaned by an idempotent re-arm.
function Launch-Exp003Bundle {
    $outLog = Join-Path $RunDirAbs "exp003_bundle_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "exp003_bundle_watch_rearmed.err.log"
    $statusJson = Join-Path $RunDirAbs "v5_exp003_bundle_watch_status.json"
    if ($script:isExp005EvidenceRun) {
        $reason = if ($script:isExpW1Arm) { "EXP-003 is terminally INCONCLUSIVE; EXP-W1 arm must not reopen or reinterpret it" } else { "EXP-003 is terminally INCONCLUSIVE; EXP-005 evidence run must not reopen or reinterpret it" }
        Log "Skipping v5_exp003_bundle_watch.py: $reason"
        $script:launched += [pscustomobject]@{ script = "v5_exp003_bundle_watch.py"; pid = -1; out = $outLog; err = $errLog; skipped = $true; skip_reason = $reason }
        return $null
    }
    if ($null -ne $script:preservedExp003BundleWatcher) {
        $script:exp003BundleLaunchAttempted = $true
        $script:launched += $script:preservedExp003BundleWatcher
        return $null
    }
    $status = Read-JsonFile $statusJson
    # The only recoverable terminal failure is the independently pinned
    # gate24900 false-positive process-inspection incident.  The Python watcher
    # re-verifies the original status/staged hashes and refuses recovery unless
    # its forensic certificate can be built; every other FAIL remains sticky.
    $forensicRecoveryCandidate = $false
    if (($null -ne $status) -and ([string]$status.overall).ToUpperInvariant() -eq "FAIL") {
        $freeze = $status.freeze
        $forensicRecoveryCandidate = (
            ([bool]$status.terminal) -and
            ([string]$status.state -eq "MEASUREMENT_CONTENTION_QUARANTINED") -and
            ($null -ne $freeze) -and
            ([int]$freeze.gate_iteration -eq 24900) -and
            ([int64]$freeze.gate_hands -eq 409058520) -and
            ([string]$freeze.archive_sha256 -eq "060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020") -and
            (Test-Path (Join-Path $RunDirAbs "exp003_bundle_staging\post_vs_native_attempt1\payload.launcher.json")) -and
            (Test-Path (Join-Path $RunDirAbs "exp003_bundle_staging\post_vs_native_attempt1\quarantine.json"))
        )
    }
    if (($null -ne $status) -and (@("REVIEW_READY", "INCONCLUSIVE_JUDGMENT_REQUIRED", "FAIL") -contains ([string]$status.overall).ToUpperInvariant()) -and -not $forensicRecoveryCandidate) {
        $reason = "terminal bundle status $($status.overall); no measurement retry or overwrite is allowed"
        Log "Skipping v5_exp003_bundle_watch.py: $reason"
        $script:launched += [pscustomobject]@{
            script = "v5_exp003_bundle_watch.py"
            pid = -1
            out = $outLog
            err = $errLog
            skipped = $true
            skip_reason = $reason
        }
        return $null
    }
    if ($forensicRecoveryCandidate) {
        Log "Allowing the one named gate24900 forensic re-audit path; watcher must independently reject any mismatch before publication"
    }
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_exp003_bundle_watch.py",
        "--run-dir", $RunDirAbs,
        "--python", $Python,
        "--status-json", $statusJson,
        "--poll-seconds", "30"
    )
    $script:exp003BundleLaunchAttempted = $true
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_exp003_bundle_watch.py PID $($p.Id); fixed roles remain staged until complete validation"
    $script:launched += [pscustomobject]@{ script = "v5_exp003_bundle_watch.py"; pid = $p.Id; out = $outLog; err = $errLog }
    $bundleLock = Join-Path $RunDirAbs 'v5_exp003_bundle_watch.lock'
    for ($i = 0; $i -lt 20 -and -not (Test-Path $bundleLock); $i++) {
        Start-Sleep -Milliseconds 100
    }
    return $p
}

# Verbatim for throughput (from continue, baseline = parent call36_r1 for EXP-004 lineage, candidate = current)
function Launch-Throughput {
    $baseline = "models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1"
    $throughputOut = Join-Path $RunDirAbs "throughput_watch_rearmed.out.log"
    $throughputErr = Join-Path $RunDirAbs "throughput_watch_rearmed.err.log"
    $throughputJson = Join-Path $RunDirAbs "throughput_compare.json"
    $throughputMd = Join-Path $RunDirAbs "throughput_compare.md"
    $throughputLog = Join-Path $RunDirAbs "throughput_watch.log"
    $throughputArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_throughput_watch.py",
        "--baseline-run-dir", $baseline,
        "--candidate-run-dir", $RunDirAbs,
        "--tail", "20",
        "--min-baseline-rows", "20",
        "--min-candidate-rows", "20",
        "--min-hps-ratio", "1.0",
        "--min-inf-bs-ratio", "1.0",
        "--min-candidate-inf-bs", "10",
        "--poll-seconds", "60",
        "--timeout-seconds", "3600",
        "--out-json", $throughputJson,
        "--out-md", $throughputMd,
        "--log-path", $throughputLog,
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $throughputArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $throughputOut `
        -RedirectStandardError $throughputErr `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_throughput_watch.py PID $($p.Id) baseline=$baseline candidate=$RunDirAbs"
    $script:launched += [pscustomobject]@{ script = "v5_throughput_watch.py"; pid = $p.Id; out = $throughputOut; err = $throughputErr }
    return $p
}

# For staged Slumbot launches. These are floored watchers: they only launch once
# checkpoint and quality gates make the stage eligible.
function Test-Exp003BundleEvalActive {
    if ($null -ne $script:preservedExp003BundleWatcher) { return $true }
    if ($script:exp003BundleLaunchAttempted) { return $true }
    if (Test-Path (Join-Path $RunDirAbs 'v5_exp003_bundle_watch.lock')) { return $true }
    $status = Read-JsonFile (Join-Path $RunDirAbs 'v5_exp003_bundle_watch_status.json')
    if ($null -eq $status) { return $false }
    return ([string]$status.overall).ToUpperInvariant() -eq 'RUNNING'
}

function Launch-SlumbotPromotion20k {
    $outLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.out.log"
    $errLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "slumbot_promotion20k_launch_status.json"
    $planJson = Join-Path $RunDirAbs "slumbot_promotion20k_plan.json"
    $planMd = Join-Path $RunDirAbs "slumbot_promotion20k_plan.md"
    $watchLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.log"
    if ($script:isExp005EvidenceRun) {
        $reason = if ($script:isExpW1Arm) {
            "EXP-W1 arm cannot launch promotion before both endpoints and terminal primary100k PASS"
        } elseif ($script:isExp005CArm) {
            "EXP005-C arm cannot launch promotion before both clean arms and terminal 100k paired judgment"
        } else {
            "EXP-005 is an EXPLORATORY_PILOT_NO_METHOD_JUDGMENT; promotion is forbidden for this run"
        }
        Add-SkippedSlumbotLaunch "promotion20k" $outLog $errLog $reason
        return $null
    }
    if (Test-Exp003BundleEvalActive) {
        Add-SkippedSlumbotLaunch "promotion20k" $outLog $errLog "EXP-003 bundle evaluation owns the shared eval slot"
        return $null
    }
    $preserved = Get-PreservedSlumbotWatcher "promotion20k"
    if ($null -ne $preserved) {
        Log "Preserving active v5_slumbot_benchmark_watch.py promotion20k PID $($preserved.pid); not launching duplicate"
        $script:launched += [pscustomobject]@{ script = "v5_slumbot_benchmark_watch.py:promotion20k"; pid = $preserved.pid; out = $outLog; err = $errLog; preserved = $true }
        return $null
    }
    $status = Read-JsonFile $statusJson
    if (($null -ne $status) -and ([string]$status.state -eq "RUNNING")) {
        Add-SkippedSlumbotLaunch "promotion20k" $outLog $errLog "status RUNNING but no live parent was preserved"
        return $null
    }
    if (($null -ne $status) -and (-not (Is-LaunchableSlumbotState $status.state))) {
        Add-SkippedSlumbotLaunch "promotion20k" $outLog $errLog "status $($status.state) is not a launchable waiting state"
        return $null
    }
    $existingResult = Find-ExistingPromotion20kResult
    if ($null -ne $existingResult) {
        Add-SkippedSlumbotLaunch "promotion20k" $outLog $errLog "existing promotion20k primary result present at $($existingResult.FullName)"
        return $null
    }
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_slumbot_benchmark_watch.py",
        "--run-dir", $RunDirAbs,
        "--stage", "promotion20k",
        "--output-dir", "models",
        "--min-training-hands", "250000000",
        "--status-json", $statusJson,
        "--plan-json", $planJson,
        "--plan-md", $planMd,
        "--log", $watchLog,
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md",
        "--sleep-seconds", "60",
        "--max-health-age-seconds", "1200",
        "--no-require-quality-gate",
        "--launch-path", "direct"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_slumbot_benchmark_watch.py promotion20k PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_slumbot_benchmark_watch.py:promotion20k"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

function Launch-SlumbotFormal100k {
    $outLog = Join-Path $RunDirAbs "slumbot_formal100k_launch_watch.out.log"
    $errLog = Join-Path $RunDirAbs "slumbot_formal100k_launch_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "slumbot_formal100k_launch_status.json"
    $planJson = Join-Path $RunDirAbs "slumbot_formal100k_plan.json"
    $planMd = Join-Path $RunDirAbs "slumbot_formal100k_plan.md"
    $watchLog = Join-Path $RunDirAbs "slumbot_formal100k_launch_watch.log"
    if ($script:isExp005EvidenceRun) {
        $reason = if ($script:isExpW1Arm) {
            "EXP-W1 arm cannot launch formal100k before primary PASS and exact-endpoint strong promotion"
        } elseif ($script:isExp005CArm) {
            "EXP005-C arm cannot launch formal100k before PASS, exact-endpoint strong promotion, and program stop gates"
        } else {
            "EXP-005 is an EXPLORATORY_PILOT_NO_METHOD_JUDGMENT; formal100k is forbidden for this run"
        }
        Add-SkippedSlumbotLaunch "formal100k" $outLog $errLog $reason
        return $null
    }
    if (Test-Exp003BundleEvalActive) {
        Add-SkippedSlumbotLaunch "formal100k" $outLog $errLog "EXP-003 bundle evaluation owns the shared eval slot"
        return $null
    }
    $preserved = Get-PreservedSlumbotWatcher "formal100k"
    if ($null -ne $preserved) {
        Log "Preserving active v5_slumbot_benchmark_watch.py formal100k PID $($preserved.pid); not launching duplicate"
        $script:launched += [pscustomobject]@{ script = "v5_slumbot_benchmark_watch.py:formal100k"; pid = $preserved.pid; out = $outLog; err = $errLog; preserved = $true }
        return $null
    }
    $status = Read-JsonFile $statusJson
    if (($null -ne $status) -and ([string]$status.state -eq "RUNNING")) {
        Add-SkippedSlumbotLaunch "formal100k" $outLog $errLog "status RUNNING but no live parent was preserved"
        return $null
    }
    if (($null -ne $status) -and (-not (Is-LaunchableSlumbotState $status.state))) {
        Add-SkippedSlumbotLaunch "formal100k" $outLog $errLog "status $($status.state) is not a launchable waiting state"
        return $null
    }
    $existingResult = Find-ExistingFormal100kResult
    if ($null -ne $existingResult) {
        Add-SkippedSlumbotLaunch "formal100k" $outLog $errLog "existing formal100k primary result present at $($existingResult.FullName)"
        return $null
    }
    $args = @(
        "-u",
        "scripts\alpha_holdem\v5_slumbot_benchmark_watch.py",
        "--run-dir", $RunDirAbs,
        "--stage", "formal100k",
        "--output-dir", "models",
        "--min-training-hands", "250000000",
        "--status-json", $statusJson,
        "--plan-json", $planJson,
        "--plan-md", $planMd,
        "--log", $watchLog,
        "--append-report", "reports\v5_zero_l6_fixedenv_launch.md",
        "--sleep-seconds", "60",
        "--max-health-age-seconds", "1200",
        "--no-require-quality-gate",
        "--launch-path", "direct"
    )
    $p = Start-Process -FilePath $Python -ArgumentList $args `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Log "Started v5_slumbot_benchmark_watch.py formal100k PID $($p.Id)"
    $script:launched += [pscustomobject]@{ script = "v5_slumbot_benchmark_watch.py:formal100k"; pid = $p.Id; out = $outLog; err = $errLog }
    return $p
}

# Launch all (Fable 2026-07-08: Throughput/Slumbot-rearm DISABLED — throughput
# watcher's survival-fail loop caused duplicate stacking; the 200M rearm tag is
# complete and relaunching it against FAIL-audit artifacts risks a re-fire.
# 250M promotion/formal watchers are re-armed explicitly by the operator when
# ~250M nears, per ledger.)
# Promotion/formal Slumbot launch watchers are intentionally armed below.
if ($script:isHybridH18Arm) {
    Launch-H18OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H18 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH17Arm) {
    Launch-H17OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H17 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH16Arm) {
    Launch-H16OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H16 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH15Arm) {
    Launch-H15OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H15 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH14Arm) {
    Launch-H14OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H14 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH13Arm) {
    Launch-H13OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H13 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH12Arm) {
    # H12 launches one lock-bound supervisor which dependency-orders
    # health+protocol -> endpoint -> downstream.  Every generic path remains blocked.
    Launch-H12OrderedRearm
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H12 exact ordered lifecycle terminally blocks every generic project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH11Arm) {
    # H11 strict no-observer active-window contract: only exact locked lifecycle tools.
    Launch-ExpW1EndpointFreeze
    Launch-H11ProtocolWatch
    Launch-H11TreatmentLaunchWatch
    Launch-H11CompletionWatch
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H11 strict active-window contract terminally blocks every non-H11 project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH10Arm) {
    # H10 strict active-window contract: only exact locked H10 lifecycle tools.
    Launch-ExpW1EndpointFreeze
    Launch-H10ProtocolWatch
    Launch-H10TreatmentLaunchWatch
    Launch-H10CompletionWatch
    foreach ($blocked in @("v5_health_watch.py", "v5_dashboard_watch.py", "v5_ops_log_watch.py", "v5_checkpoint_archive_watch.py", "v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py")) {
        $reason = "H10 strict active-window contract terminally blocks every non-H10 project path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} elseif ($script:isHybridH1Arm -or $script:isHybridH2Arm -or $script:isHybridH6Arm -or $script:isHybridH7Arm -or $script:isHybridH8Arm -or $script:isHybridH9Arm) {
    # H1 watcher-only contract: no generic gate/eval/internal/EXP/Slumbot paths.
    Launch-Health
    Launch-Dashboard
    Launch-OpsLog
    Launch-Archive
    Launch-ExpW1EndpointFreeze
    Launch-H2ProtocolWatch
    Launch-H2TreatmentLaunchWatch
    Launch-H2CompletionWatch
    Launch-H6ProtocolWatch
    Launch-H6CompletionWatch
    Launch-H7ProtocolWatch
    Launch-H7TreatmentLaunchWatch
    Launch-H7CompletionWatch
    Launch-H8ProtocolWatch
    Launch-H8TreatmentLaunchWatch
    Launch-H8CompletionWatch
    Launch-H9ProtocolWatch
    Launch-H9TreatmentLaunchWatch
    Launch-H9CompletionWatch
    foreach ($blocked in @("v5_gate_sequence_watch.py", "v5_eval_cadence_watch.py", "v5_internal_strength_watch.py", "v5_pilot_endpoint_stop_watch.py", "v5_exp003_freeze_watch.py", "v5_exp003_bundle_watch.py", "v5_slumbot_benchmark_watch.py:promotion20k", "v5_slumbot_benchmark_watch.py:formal100k")) {
        $reason = "HYBRID H-window watcher-only contract terminally blocks this path"
        Log "Skipping ${blocked}: $reason"
        $script:launched += [pscustomobject]@{ script = $blocked; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    }
} else {
    Launch-Health
    Launch-Dashboard
    Launch-OpsLog
    Launch-GateSequence
    if ($script:isExpW1Arm) {
        $reason = "EXP-W1 arm blocks generic eval cadence until terminal primary100k PASS"
        Log "Skipping v5_eval_cadence_watch.py: $reason"
        $script:launched += [pscustomobject]@{ script = "v5_eval_cadence_watch.py"; pid = -1; out = ""; err = ""; skipped = $true; skip_reason = $reason }
    } else { Launch-EvalCadence }
    Launch-Internal
    Launch-Archive
    Launch-PilotEndpointStop
    Launch-ExpW1EndpointFreeze
    Launch-Exp003Freeze
    Launch-Exp003Bundle
    Launch-SlumbotPromotion20k
    Launch-SlumbotFormal100k
}
Log "All launches attempted. $( $script:launched.Count ) entries in launched list."

# Post-launch survival gate (per strategist rec)
Start-Sleep -Seconds 8
$survivalPass = $true
$failed = @()
foreach ($w in $script:launched) {
    if (($w.PSObject.Properties.Name -contains "skipped") -and $w.skipped) {
        Log "SURVIVAL SKIP for $($w.script): $($w.skip_reason)"
        continue
    }
    $proc = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq $w.pid }
    if (-not $proc) {
        $survivalPass = $false
        $failed += $w.script
        $errTail = ""
        if (Test-Path $w.err) { $errTail = (Get-Content $w.err -Tail 10 | Out-String) }
        Log "SURVIVAL FAIL for $($w.script) PID $($w.pid). Err tail: $errTail"
    } else {
        Log "SURVIVAL OK for $($w.script) PID $($w.pid)"
    }
}

$status = @{
    rearmed_at = $timestamp
    run_dir = $RunDirAbs
    watchers = $script:launched
    range_resolution = $rangeResolution
    survival_pass = $survivalPass
    failed_watchers = $failed
    note = "Re-armed without touching trainer. survival_pass must be true for verifier step 6. Run this whenever ledger indicates watchers are down."
}
$status | ConvertTo-Json -Depth 5 | Out-File -FilePath $statusJson -Encoding UTF8
Log "Wrote $statusJson with survival_pass=$survivalPass"
if (-not $survivalPass) {
    Log "WARNING: Some watchers failed to survive launch. Check err logs and fix args before claiming step 6."
}

# Output for caller
$script:launched | Select-Object script, pid | ConvertTo-Json -Compress | Out-String
if (-not $survivalPass) {
    exit 3
}
