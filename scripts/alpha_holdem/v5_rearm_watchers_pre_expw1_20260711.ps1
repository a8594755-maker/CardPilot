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

$rangeResolution = Resolve-RearmWatcherRanges `
    -CurrentRunDir $RunDirAbs `
    -RequestedGateStart $GateStartIteration `
    -RequestedGateMax $GateMaxIteration `
    -RequestedInternalStart $InternalStartIteration `
    -RequestedInternalMax $InternalMaxIteration `
    -SpanIterations $WatcherRangeSpanIterations
$GateStartIteration = [int]$rangeResolution.gate.start_iteration
$GateMaxIteration = [int]$rangeResolution.gate.max_iteration
$InternalStartIteration = [int]$rangeResolution.internal.start_iteration
$InternalMaxIteration = [int]$rangeResolution.internal.max_iteration

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
$script:isExp005PilotRun = (
    ($script:expectedOpponentAssignment -eq "per-group") -and
    ([int]$runManifest.config.opponent_groups -eq 5) -and
    ([string]$runManifest.run_id -like "*exp005*") -and
    (-not $script:isExp005CArm)
)
$script:isExp005EvidenceRun = ($script:isExp005PilotRun -or $script:isExp005CArm)

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
                    'v5_ops_log_watch.py','v5_throughput_watch.py',
                    'v5_slumbot_benchmark_watch.py','v5_gate_watch.py')
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $c = $_.CommandLine
    if (-not $c) { return $false }
    if ($c -like '*multiprocessing*' -or $c -like '*train_v5*') { return $false }
    foreach ($s in $watcherScripts) { if ($c -like "*$s*") { return $true } }
    return $false
}
foreach ($e in $existing) {
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

# EXP-003 first-eligible-PASS freeze. This reporting-only watcher preserves the
# registered candidate before latest.pt can advance to the next checkpoint.
# Terminal PASS/FAIL is deliberately not relaunched: FAIL is sticky so a later
# checkpoint can never replace a missed first eligible PASS.
function Launch-Exp003Freeze {
    $outLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.err.log"
    $statusJson = Join-Path $RunDirAbs "exp003_judgment_freeze_status.json"
    if ($script:isExp005EvidenceRun) {
        $reason = "EXP-003 is terminally INCONCLUSIVE; EXP-005 evidence run must not reopen it"
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
        $reason = "EXP-003 is terminally INCONCLUSIVE; EXP-005 evidence run must not reopen or reinterpret it"
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
        $reason = if ($script:isExp005CArm) {
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
        $reason = if ($script:isExp005CArm) {
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
Launch-Health
Launch-Dashboard
Launch-OpsLog
Launch-GateSequence
Launch-EvalCadence
Launch-Internal
Launch-Archive
Launch-PilotEndpointStop
Launch-Exp003Freeze
Launch-Exp003Bundle
Launch-SlumbotPromotion20k
Launch-SlumbotFormal100k

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
