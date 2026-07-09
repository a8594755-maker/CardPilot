<#
v5_rearm_watchers.ps1
Trainer-preserving re-arm of V5 watchers after reboot or down state.
Uses VERBATIM arg blocks from v5_continue_after_gate.ps1 (per strategist rec).
Does NOT touch or restart the trainer.
Adds post-launch survival gate + err log check.
Logs to {RunDir}/watcher_rearm_status.json with survival_pass.

Usage:
  powershell -File scripts\alpha_holdem\v5_rearm_watchers.ps1 -RunDir "models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_r1_20260707"

For this run, derives internal start/max from next gate 11800 (from queue/gate_sequence).
For throughput, uses parent call36_r1 as baseline (EXP-004 lineage), current as candidate.
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$RunDir,
    [int]$GateStartIteration = 12900,
    [int]$GateMaxIteration = 14000,
    [int]$InternalStartIteration = 12900,
    [int]$InternalMaxIteration = 14000
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

Log "Re-arming watchers for $RunDirAbs (trainer untouched) - using canonical args"

$script:preservedSlumbotWatchers = @()

function Read-JsonFile($path) {
    if (-not (Test-Path $path)) { return $null }
    try {
        return Get-Content $path -Raw | ConvertFrom-Json
    } catch {
        Log "WARN: failed to parse ${path}: $($_.Exception.Message)"
        return $null
    }
}

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

# IDEMPOTENCY GUARD (Fable 2026-07-08): kill existing watcher instances BEFORE
# spawning, so repeated re-arms can never stack duplicates. Never touches the
# trainer (train_v5 / multiprocessing workers are explicitly excluded).
$watcherScripts = @('v5_health_watch.py','v5_dashboard_watch.py','v5_gate_sequence_watch.py',
                    'v5_eval_cadence_watch.py','v5_internal_strength_watch.py',
                    'v5_checkpoint_archive_watch.py','v5_exp003_freeze_watch.py',
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
        "--expected-opponent-assignment", "per-iteration",
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

# EXP-003 first-eligible-PASS freeze. This reporting-only watcher preserves the
# registered candidate before latest.pt can advance to the next checkpoint.
# Terminal PASS/FAIL is deliberately not relaunched: FAIL is sticky so a later
# checkpoint can never replace a missed first eligible PASS.
function Launch-Exp003Freeze {
    $outLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.out.log"
    $errLog = Join-Path $RunDirAbs "exp003_judgment_freeze_watch_rearmed.err.log"
    $statusJson = Join-Path $RunDirAbs "exp003_judgment_freeze_status.json"
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
function Launch-SlumbotPromotion20k {
    $outLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.out.log"
    $errLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.err.log"
    $statusJson = Join-Path $RunDirAbs "slumbot_promotion20k_launch_status.json"
    $planJson = Join-Path $RunDirAbs "slumbot_promotion20k_plan.json"
    $planMd = Join-Path $RunDirAbs "slumbot_promotion20k_plan.md"
    $watchLog = Join-Path $RunDirAbs "slumbot_promotion20k_launch_watch.log"
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
Launch-Exp003Freeze
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
