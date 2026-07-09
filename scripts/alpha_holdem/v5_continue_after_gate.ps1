# Continue a V5-from-zero run after a verified gate.
#
# Default mode is a dry run: validate the source run and print the continuation
# command. It does not stop the active trainer or launch a new one unless
# -Execute is passed. If a source trainer is still alive, -Execute also requires
# -StopOldTraining to avoid accidentally running two GPU trainers.

param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [string]$SourceRunDir = "models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445",
    [int]$TargetIteration = 1600,
    [int]$ExpectedPoolSnapshots = 5,
    [object]$RequireCurrentPoolSnapshot = $true,
    [string]$NewRunId = "",
    [string]$NewRunDir = "",
    [string]$Python = "python",
    [string]$Device = "cuda",
    [int]$Workers = 28,
    [int]$HandsPerIter = 16384,
    [int64]$TotalHands = 2700000000,
    [double]$StartingStack = 200.0,
    [string]$EnvVersion = "v55",
    [double]$Lr = 3e-4,
    [double]$Gamma = 0.999,
    [double]$Delta1 = 3.0,
    [double]$EntropyCoef = 0.05,
    [double]$EntropyFloor = 0.3,
    [double]$PostflopActionPriorCoef = 0.0,
    [string]$PostflopActionPriorTarget = "0.15,0.30,0.52,0.03",
    [double]$PreflopActionPriorCoef = 0.0,
    [string]$PreflopActionPriorTarget = "0.30,0.25,0.43,0.02",
    [double]$PreflopSbOpenActionPriorCoef = 0.0,
    [string]$PreflopSbOpenActionPriorTarget = "0.15,0.20,0.63,0.02",
    [double]$PreflopBbVsOpenActionPriorCoef = 0.0,
    [string]$PreflopBbVsOpenActionPriorTarget = "0.25,0.55,0.18,0.02",
    [int]$KBest = 5,
    [string]$PoolStrategy = "loss-kbest",
    [int]$PoolHistoryLimit = 200,
    [double]$SelfPlayFraction = 0.2,
    [string]$OpponentAssignment = "per-iteration",
    [int]$SnapshotEvery = 200,
    [int]$SaveInterval = 100,
    [string]$RolloutMode = "",
    [int]$RolloutEnvsPerWorker = 0,
    [int]$InferenceMinBatchSlots = -1,
    [int]$InferenceBatchDeadlineUs = -1,
    [switch]$ValidateStream,
    [switch]$MirrorSelfPlayDeals,
    [switch]$AllinRunoutEv,
    [int]$AllinRunoutEvMaxRunouts = -1,
    [string]$TrainerCopySource = "",
    [string]$ArchiveCurrentTrainerAs = "",
    [switch]$SkipGateCheck,
    [switch]$Execute,
    [switch]$StopOldTraining,
    [int]$OldTrainingPid = 0,
    [switch]$StartNextGateWatcher,
    [int]$NextGateIteration = 1700,
    [int]$NextGateExpectedPoolSnapshots = 5,
    [string]$NextGateExpectedPoolStrategy = "",
    [switch]$NextGateRequireCurrentPoolSnapshot,
    [switch]$StartGateSequenceWatcher,
    [int]$GateSequenceStartIteration = 0,
    [int]$GateSequenceMaxIteration = 5000,
    [int]$GateSequenceStep = 100,
    [int]$GateSequencePollSeconds = 60,
    [int]$GateSequenceTimeoutSeconds = 86400,
    [switch]$StartThroughputWatcher,
    [int]$ThroughputTail = 20,
    [int]$ThroughputMinBaselineRows = 10,
    [int]$ThroughputMinCandidateRows = 10,
    [double]$ThroughputMinHpsRatio = 0.75,
    [double]$ThroughputMinInfBsRatio = 0.8,
    [double]$ThroughputMinCandidateInfBs = 8.0,
    [int]$ThroughputPollSeconds = 60,
    [int]$ThroughputTimeoutSeconds = 7200,
    [switch]$StartHealthWatcher,
    [int]$HealthPollSeconds = 60,
    [int]$HealthTimeoutSeconds = 0,
    [switch]$HealthExitOnWarn,
    [int]$PreflopCallWarnAfterIter = 200,
    [double]$PreflopCallWarn = 0.03,
    [double]$PreflopCallFail = 0.005,
    [double]$PreflopDominanceWarn = 0.90,
    [double]$PreflopDominanceFail = 0.97,
    [double]$PreflopAllinWarn = 0.12,
    [double]$PreflopAllinFail = 0.25,
    [double]$StderrRecentMinutes = 5.0,
    [switch]$StartDashboardWatcher,
    [int]$DashboardPollSeconds = 120,
    [switch]$StartEvalCadenceWatcher,
    [int]$EvalCadencePollSeconds = 600,
    [switch]$StartSlumbotQuick5kWatcher,
    [int]$SlumbotQuick5kPollSeconds = 120,
    [int]$SlumbotQuick5kMaxHealthAgeSeconds = 900,
    [switch]$StartSlumbotPromotion20kWatcher,
    [int64]$SlumbotPromotion20kMinTrainingHands = 250000000,
    [int]$SlumbotPromotion20kPollSeconds = 600,
    [int]$SlumbotPromotion20kMaxHealthAgeSeconds = 1200,
    [switch]$StartSlumbotFormal100kWatcher,
    [int64]$SlumbotFormal100kMinTrainingHands = 250000000,
    [int]$SlumbotFormal100kPollSeconds = 600,
    [int]$SlumbotFormal100kMaxHealthAgeSeconds = 1200,
    [switch]$StartInternalStrengthWatcher,
    [int]$InternalStrengthStartIteration = 0,
    [int]$InternalStrengthMaxIteration = 5000,
    [int]$InternalStrengthStep = 200,
    [int]$InternalStrengthHands = 200,
    [switch]$StartCheckpointArchiveWatcher,
    [int]$ArchivePollSeconds = 300,
    [int]$PostLaunchWatcherDelaySeconds = 45,
    [string]$OutputDir = "models",
    [string]$ReportPath = "reports\v5_zero_l6_fixedenv_launch.md"
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

function Write-Step([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $Message"
}

function Resolve-RepoPath([string]$PathText) {
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return $PathText
    }
    return Join-Path $Repo $PathText
}

function Quote-CommandArg([string]$Value) {
    if ($null -eq $Value) {
        return "''"
    }
    if ($Value -match '^[A-Za-z0-9_\-./:\\]+$') {
        return $Value
    }
    return "'" + $Value.Replace("'", "''") + "'"
}

function Format-Command([string[]]$Parts) {
    return (($Parts | ForEach-Object { Quote-CommandArg $_ }) -join " ")
}

function Get-SourceTrainerProcess([string]$RunDirText) {
    $variants = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($RunDirText, (Resolve-RepoPath $RunDirText))) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $variants.Add($candidate.Replace("/", "\"))
            $variants.Add($candidate.Replace("\", "/"))
        }
    }
    $uniqueVariants = @($variants | Select-Object -Unique)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $cmd = [string]$_.CommandLine
            if ($cmd -notlike "*scripts\alpha_holdem\train_v5.py*") {
                return $false
            }
            foreach ($variant in $uniqueVariants) {
                $escaped = [regex]::Escape($variant)
                if ($cmd -match "(^|\s)--run-dir\s+[`"']?$escaped[`"']?(\s|$)") {
                    return $true
                }
            }
            return $false
        }
}

function Stop-SpawnChildrenForParent([int]$ParentPid) {
    $children = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            [int]$_.ParentProcessId -eq $ParentPid -and
            ([string]$_.CommandLine) -match "spawn_main\(parent_pid=$ParentPid,"
        })
    if ($children.Count -eq 0) {
        Write-Step "old trainer PID $ParentPid has no remaining spawn children"
        return
    }
    $childPids = ($children | ForEach-Object { $_.ProcessId }) -join ","
    Write-Step "stopping old trainer spawn children for PID ${ParentPid}: $childPids"
    Stop-Process -Id @($children | ForEach-Object { $_.ProcessId }) -Force -ErrorAction SilentlyContinue
}

function Stop-SourceRunWatcherProcesses([string]$RunDirText) {
    $variants = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($RunDirText, (Resolve-RepoPath $RunDirText))) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $variants.Add($candidate.Replace("/", "\"))
            $variants.Add($candidate.Replace("\", "/"))
        }
    }
    $uniqueVariants = @($variants | Select-Object -Unique)
    $watchers = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $cmd = [string]$_.CommandLine
            if ($cmd -match "spawn_main" -or $cmd -match "train_v5.py") {
                return $false
            }
            if ($cmd -notmatch "scripts[\\/]+alpha_holdem[\\/]+.*watch\.py") {
                return $false
            }
            foreach ($variant in $uniqueVariants) {
                if ($cmd.Contains($variant)) {
                    return $true
                }
            }
            return $false
        })
    if ($watchers.Count -eq 0) {
        Write-Step "source run watcher cleanup: no stale watcher processes found"
        return
    }
    $watcherPids = ($watchers | ForEach-Object { $_.ProcessId }) -join ","
    Write-Step "stopping source run watcher processes: $watcherPids"
    Stop-Process -Id @($watchers | ForEach-Object { $_.ProcessId }) -Force -ErrorAction SilentlyContinue
}

$sourceRunDirAbs = Resolve-RepoPath $SourceRunDir
if (-not (Test-Path -LiteralPath $sourceRunDirAbs)) {
    throw "Source run dir not found: $sourceRunDirAbs"
}

$sourceCheckpoint = Join-Path $sourceRunDirAbs "latest.pt"
if (-not (Test-Path -LiteralPath $sourceCheckpoint)) {
    throw "Source checkpoint not found: $sourceCheckpoint"
}

if ([string]::IsNullOrWhiteSpace($NewRunId)) {
    $sourceLeaf = Split-Path -Leaf $sourceRunDirAbs
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $NewRunId = "${sourceLeaf}_cont_${stamp}"
}
if ([string]::IsNullOrWhiteSpace($NewRunDir)) {
    $NewRunDir = Join-Path "models\alpha_holdem_v5_from_zero" $NewRunId
}
$newRunDirAbs = Resolve-RepoPath $NewRunDir

Write-Step "source run: $sourceRunDirAbs"
Write-Step "source checkpoint: $sourceCheckpoint"
Write-Step "new run id: $NewRunId"
Write-Step "new run dir: $newRunDirAbs"

if (-not $SkipGateCheck) {
    Write-Step "running health monitor"
    & $Python "scripts\alpha_holdem\v5_monitor.py" "--run-dir" $SourceRunDir
    if ($LASTEXITCODE -ne 0) {
        throw "v5_monitor.py failed with exit code $LASTEXITCODE"
    }

    Write-Step "verifying gate $TargetIteration"
    $gateArgs = @(
        "scripts\alpha_holdem\v5_gate_watch.py",
        "--run-dir", $SourceRunDir,
        "--target-iteration", "$TargetIteration",
        "--expected-pool-snapshots", "$ExpectedPoolSnapshots",
        "--poll-seconds", "1",
        "--timeout-seconds", "0"
    )
    if ($RequireCurrentPoolSnapshot) {
        $gateArgs += "--require-current-pool-snapshot"
    }
    & $Python @gateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "gate $TargetIteration is not PASS; refusing continuation"
    }
} else {
    Write-Step "skipping gate check by request"
}

Write-Step "checking checkpoint metadata"
$metadataScript = @'
import json
import sys
import torch
from pathlib import Path

path = Path(sys.argv[1])
ckpt = torch.load(path, map_location="cpu", weights_only=False)
lineage = bool(ckpt.get(
    "fresh_from_zero_lineage",
    ckpt.get("version") == "v5.zero" and ckpt.get("resume") is None,
))
summary = {
    "path": str(path),
    "version": ckpt.get("version"),
    "iteration": ckpt.get("iteration"),
    "total_hands": ckpt.get("total_hands"),
    "env_version": ckpt.get("env_version"),
    "obs_version": ckpt.get("obs_version"),
    "action_space_version": ckpt.get("action_space_version"),
    "starting_stack_bb": ckpt.get("starting_stack_bb"),
    "actual_hand_accounting": ckpt.get("actual_hand_accounting"),
    "resume": ckpt.get("resume"),
    "fresh_from_zero_lineage": lineage,
    "pool_snapshots": len(ckpt.get("pool_snapshots", [])),
    "pool_strategy": ckpt.get("pool_strategy") or (ckpt.get("config") or {}).get("pool_strategy"),
}
print(json.dumps(summary, indent=2, sort_keys=True))
ok = (
    ckpt.get("version") == "v5.zero"
    and ckpt.get("env_version") == "v55"
    and ckpt.get("obs_version") == "v55"
    and ckpt.get("action_space_version") == "9slot_v5"
    and ckpt.get("actual_hand_accounting") is True
    and lineage
)
sys.exit(0 if ok else 1)
'@
$metadataScript | & $Python - $sourceCheckpoint
if ($LASTEXITCODE -ne 0) {
    throw "checkpoint metadata check failed; refusing continuation"
}

$trainArgs = @(
    "-X", "utf8", "-u",
    "scripts\alpha_holdem\train_v5.py",
    "--device", $Device,
    "--workers", "$Workers",
    "--hands-per-iter", "$HandsPerIter",
    "--total-hands", "$TotalHands",
    "--starting-stack", "$StartingStack",
    "--env-version", $EnvVersion,
    "--lr", "$Lr",
    "--gamma", "$Gamma",
    "--delta1", "$Delta1",
    "--entropy-coef", "$EntropyCoef",
    "--entropy-floor", "$EntropyFloor",
    "--postflop-action-prior-coef", "$PostflopActionPriorCoef",
    "--postflop-action-prior-target", $PostflopActionPriorTarget,
    "--preflop-action-prior-coef", "$PreflopActionPriorCoef",
    "--preflop-action-prior-target", $PreflopActionPriorTarget,
    "--preflop-sb-open-action-prior-coef", "$PreflopSbOpenActionPriorCoef",
    "--preflop-sb-open-action-prior-target", $PreflopSbOpenActionPriorTarget,
    "--preflop-bb-vs-open-action-prior-coef", "$PreflopBbVsOpenActionPriorCoef",
    "--preflop-bb-vs-open-action-prior-target", $PreflopBbVsOpenActionPriorTarget,
    "--k-best", "$KBest",
    "--pool-strategy", $PoolStrategy,
    "--pool-history-limit", "$PoolHistoryLimit",
    "--self-play-fraction", "$SelfPlayFraction",
    "--opponent-assignment", $OpponentAssignment,
    "--snapshot-every", "$SnapshotEvery",
    "--save-interval", "$SaveInterval",
    "--resume", $sourceCheckpoint,
    "--allow-resume",
    "--no-reset-optimizer",
    "--run-id", $NewRunId,
    "--run-dir", $newRunDirAbs
)
if (-not [string]::IsNullOrWhiteSpace($RolloutMode)) {
    $trainArgs += @("--rollout-mode", $RolloutMode)
}
if ($RolloutEnvsPerWorker -gt 0) {
    $trainArgs += @("--rollout-envs-per-worker", "$RolloutEnvsPerWorker")
}
if ($InferenceMinBatchSlots -ge 0) {
    $trainArgs += @("--inference-min-batch-slots", "$InferenceMinBatchSlots")
}
if ($InferenceBatchDeadlineUs -ge 0) {
    $trainArgs += @("--inference-batch-deadline-us", "$InferenceBatchDeadlineUs")
}
if ($ValidateStream) {
    $trainArgs += "--validate-stream"
}
if ($MirrorSelfPlayDeals) {
    $trainArgs += "--mirror-self-play-deals"
}
if ($AllinRunoutEv) {
    $trainArgs += "--allin-runout-ev"
}
if ($AllinRunoutEvMaxRunouts -ge 0) {
    $trainArgs += @("--allin-runout-ev-max-runouts", "$AllinRunoutEvMaxRunouts")
}

Write-Step "continuation command:"
Write-Host "$Python $($trainArgs -join ' ')"

$sourceTrainers = @(Get-SourceTrainerProcess $sourceRunDirAbs)
if ($sourceTrainers.Count -gt 0) {
    $pids = ($sourceTrainers | ForEach-Object { $_.ProcessId }) -join ","
    Write-Step "source trainer currently running: PID $pids"
} else {
    Write-Step "source trainer currently running: none detected"
}

if (-not $Execute) {
    $recommendedOldPid = $OldTrainingPid
    if ($recommendedOldPid -le 0 -and $sourceTrainers.Count -eq 1) {
        $recommendedOldPid = [int]$sourceTrainers[0].ProcessId
    }
    $cutoverArgs = @(
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "scripts\alpha_holdem\v5_continue_after_gate.ps1",
        "-Repo", $Repo,
        "-SourceRunDir", $sourceRunDirAbs,
        "-TargetIteration", "$TargetIteration",
        "-ExpectedPoolSnapshots", "$ExpectedPoolSnapshots",
        "-NewRunId", $NewRunId,
        "-NewRunDir", $newRunDirAbs,
        "-Python", $Python,
        "-Device", $Device,
        "-Workers", "$Workers",
        "-HandsPerIter", "$HandsPerIter",
        "-TotalHands", "$TotalHands",
        "-StartingStack", "$StartingStack",
        "-EnvVersion", $EnvVersion,
        "-Lr", "$Lr",
        "-Gamma", "$Gamma",
        "-Delta1", "$Delta1",
        "-EntropyCoef", "$EntropyCoef",
        "-EntropyFloor", "$EntropyFloor",
        "-PostflopActionPriorCoef", "$PostflopActionPriorCoef",
        "-PostflopActionPriorTarget", $PostflopActionPriorTarget,
        "-PreflopActionPriorCoef", "$PreflopActionPriorCoef",
        "-PreflopActionPriorTarget", $PreflopActionPriorTarget,
        "-PreflopSbOpenActionPriorCoef", "$PreflopSbOpenActionPriorCoef",
        "-PreflopSbOpenActionPriorTarget", $PreflopSbOpenActionPriorTarget,
        "-PreflopBbVsOpenActionPriorCoef", "$PreflopBbVsOpenActionPriorCoef",
        "-PreflopBbVsOpenActionPriorTarget", $PreflopBbVsOpenActionPriorTarget,
        "-KBest", "$KBest",
        "-PoolStrategy", $PoolStrategy,
        "-PoolHistoryLimit", "$PoolHistoryLimit",
        "-SelfPlayFraction", "$SelfPlayFraction",
        "-OpponentAssignment", $OpponentAssignment,
        "-SnapshotEvery", "$SnapshotEvery",
        "-SaveInterval", "$SaveInterval",
        "-Execute",
        "-StopOldTraining",
        "-StartNextGateWatcher",
        "-StartGateSequenceWatcher",
        "-StartHealthWatcher",
        "-PreflopCallWarnAfterIter", "$PreflopCallWarnAfterIter",
        "-PreflopCallWarn", "$PreflopCallWarn",
        "-PreflopCallFail", "$PreflopCallFail",
        "-PreflopDominanceWarn", "$PreflopDominanceWarn",
        "-PreflopDominanceFail", "$PreflopDominanceFail",
        "-PreflopAllinWarn", "$PreflopAllinWarn",
        "-PreflopAllinFail", "$PreflopAllinFail",
        "-StderrRecentMinutes", "$StderrRecentMinutes",
        "-StartThroughputWatcher",
        "-StartDashboardWatcher",
        "-StartEvalCadenceWatcher",
        "-StartSlumbotQuick5kWatcher",
        "-StartSlumbotPromotion20kWatcher",
        "-StartSlumbotFormal100kWatcher",
        "-StartInternalStrengthWatcher",
        "-StartCheckpointArchiveWatcher",
        "-OutputDir", $OutputDir,
        "-ReportPath", $ReportPath
    )
    if (-not [string]::IsNullOrWhiteSpace($RolloutMode)) {
        $cutoverArgs += @("-RolloutMode", $RolloutMode)
    }
    if ($RolloutEnvsPerWorker -gt 0) {
        $cutoverArgs += @("-RolloutEnvsPerWorker", "$RolloutEnvsPerWorker")
    }
    if ($InferenceMinBatchSlots -ge 0) {
        $cutoverArgs += @("-InferenceMinBatchSlots", "$InferenceMinBatchSlots")
    }
    if ($InferenceBatchDeadlineUs -ge 0) {
        $cutoverArgs += @("-InferenceBatchDeadlineUs", "$InferenceBatchDeadlineUs")
    }
    if ($ValidateStream) {
        $cutoverArgs += "-ValidateStream"
    }
    if ($MirrorSelfPlayDeals) {
        $cutoverArgs += "-MirrorSelfPlayDeals"
    }
    if ($AllinRunoutEv) {
        $cutoverArgs += "-AllinRunoutEv"
    }
    if ($AllinRunoutEvMaxRunouts -ge 0) {
        $cutoverArgs += @("-AllinRunoutEvMaxRunouts", "$AllinRunoutEvMaxRunouts")
    }
    if (-not [string]::IsNullOrWhiteSpace($TrainerCopySource)) {
        $cutoverArgs += @("-TrainerCopySource", $TrainerCopySource)
    }
    if (-not [string]::IsNullOrWhiteSpace($ArchiveCurrentTrainerAs)) {
        $cutoverArgs += @("-ArchiveCurrentTrainerAs", $ArchiveCurrentTrainerAs)
    }
    if (-not $RequireCurrentPoolSnapshot) {
        $cutoverArgs += "-RequireCurrentPoolSnapshot:`$false"
    }
    if ($recommendedOldPid -gt 0) {
        $cutoverArgs += @("-OldTrainingPid", "$recommendedOldPid")
    }
    if ($NextGateIteration -ne 1700) {
        $cutoverArgs += @("-NextGateIteration", "$NextGateIteration")
    }
    if ($NextGateExpectedPoolSnapshots -ne 5) {
        $cutoverArgs += @("-NextGateExpectedPoolSnapshots", "$NextGateExpectedPoolSnapshots")
    }
    if (-not [string]::IsNullOrWhiteSpace($NextGateExpectedPoolStrategy)) {
        $cutoverArgs += @("-NextGateExpectedPoolStrategy", $NextGateExpectedPoolStrategy)
    }
    if ($NextGateRequireCurrentPoolSnapshot) {
        $cutoverArgs += "-NextGateRequireCurrentPoolSnapshot"
    }
    Write-Step "recommended guarded cutover command after gate PASS:"
    Write-Host (Format-Command $cutoverArgs)
    Write-Step "dry run only; pass -Execute to launch"
    exit 0
}

if (Test-Path -LiteralPath (Join-Path $newRunDirAbs "latest.pt")) {
    throw "New run already has latest.pt: $newRunDirAbs"
}
New-Item -ItemType Directory -Force -Path $newRunDirAbs | Out-Null

if ($sourceTrainers.Count -gt 0) {
    if (-not $StopOldTraining) {
        $pids = ($sourceTrainers | ForEach-Object { $_.ProcessId }) -join ","
        throw "Source trainer still running (PID $pids). Pass -StopOldTraining to cut over."
    }
    $stoppedAny = $false
    $stoppedTrainerPids = @()
    foreach ($proc in $sourceTrainers) {
        if ($OldTrainingPid -gt 0 -and $proc.ProcessId -ne $OldTrainingPid) {
            continue
        }
        Write-Step "stopping old trainer PID $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force
        $stoppedAny = $true
        $stoppedTrainerPids += [int]$proc.ProcessId
    }
    if ($OldTrainingPid -gt 0 -and -not $stoppedAny) {
        $pids = ($sourceTrainers | ForEach-Object { $_.ProcessId }) -join ","
        throw "OldTrainingPid $OldTrainingPid was not found among source trainers ($pids); refusing launch"
    }
    Start-Sleep -Seconds 5
    foreach ($pidValue in $stoppedTrainerPids) {
        Stop-SpawnChildrenForParent $pidValue
    }
    Stop-SourceRunWatcherProcesses $sourceRunDirAbs
    $remainingSourceTrainers = @(Get-SourceTrainerProcess $sourceRunDirAbs)
    if ($remainingSourceTrainers.Count -gt 0) {
        $pids = ($remainingSourceTrainers | ForEach-Object { $_.ProcessId }) -join ","
        throw "Source trainer still running after stop attempt (PID $pids); refusing launch"
    }
}

if (-not [string]::IsNullOrWhiteSpace($TrainerCopySource)) {
    $trainerCopySourceAbs = Resolve-RepoPath $TrainerCopySource
    if (-not (Test-Path -LiteralPath $trainerCopySourceAbs)) {
        throw "TrainerCopySource not found: $trainerCopySourceAbs"
    }
    $liveTrainerPath = Join-Path $Repo "scripts\alpha_holdem\train_v5.py"
    if (-not (Test-Path -LiteralPath $liveTrainerPath)) {
        throw "Live trainer script not found: $liveTrainerPath"
    }
    if ([string]::IsNullOrWhiteSpace($ArchiveCurrentTrainerAs)) {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $ArchiveCurrentTrainerAs = "scripts\alpha_holdem\train_v5_pre_cutover_${stamp}.py"
    }
    $archiveTrainerAbs = Resolve-RepoPath $ArchiveCurrentTrainerAs
    if (Test-Path -LiteralPath $archiveTrainerAbs) {
        throw "Trainer archive path already exists: $archiveTrainerAbs"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archiveTrainerAbs) | Out-Null
    $oldTrainerHash = (Get-FileHash -LiteralPath $liveTrainerPath -Algorithm SHA256).Hash
    $copySourceHash = (Get-FileHash -LiteralPath $trainerCopySourceAbs -Algorithm SHA256).Hash
    Copy-Item -LiteralPath $liveTrainerPath -Destination $archiveTrainerAbs
    Copy-Item -LiteralPath $trainerCopySourceAbs -Destination $liveTrainerPath -Force
    $newTrainerHash = (Get-FileHash -LiteralPath $liveTrainerPath -Algorithm SHA256).Hash
    Write-Step "archived live trainer to $archiveTrainerAbs sha256=$oldTrainerHash"
    Write-Step "copied trainer source $trainerCopySourceAbs sha256=$copySourceHash to live train_v5.py sha256=$newTrainerHash"
}

$stdoutPath = Join-Path $newRunDirAbs "console.out.log"
$stderrPath = Join-Path $newRunDirAbs "console.err.log"
Write-Step "launching continuation trainer"
$trainer = Start-Process -FilePath $Python -ArgumentList $trainArgs `
    -WorkingDirectory $Repo `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru
Write-Step "new trainer PID: $($trainer.Id)"

$shouldStartWatchers = (
    $StartNextGateWatcher -or
    $StartGateSequenceWatcher -or
    $StartThroughputWatcher -or
    $StartHealthWatcher -or
    $StartDashboardWatcher -or
    $StartEvalCadenceWatcher -or
    $StartSlumbotQuick5kWatcher -or
    $StartSlumbotPromotion20kWatcher -or
    $StartSlumbotFormal100kWatcher -or
    $StartInternalStrengthWatcher -or
    $StartCheckpointArchiveWatcher
)
if ($shouldStartWatchers -and $PostLaunchWatcherDelaySeconds -gt 0) {
    Write-Step "waiting ${PostLaunchWatcherDelaySeconds}s before starting watchers"
    Start-Sleep -Seconds $PostLaunchWatcherDelaySeconds
}

if ($StartNextGateWatcher) {
    $watchOut = Join-Path $newRunDirAbs "gate_${NextGateIteration}_watch.out.log"
    $watchErr = Join-Path $newRunDirAbs "gate_${NextGateIteration}_watch.err.log"
    $watchArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_gate_watch.py",
        "--run-dir", $newRunDirAbs,
        "--target-iteration", "$NextGateIteration",
        "--expected-pool-snapshots", "$NextGateExpectedPoolSnapshots",
        "--poll-seconds", "60",
        "--timeout-seconds", "14400",
        "--refresh-health",
        "--python", $Python,
        "--expected-opponent-assignment", $OpponentAssignment,
        "--expected-pool-strategy", $(if ([string]::IsNullOrWhiteSpace($NextGateExpectedPoolStrategy)) { $PoolStrategy } else { $NextGateExpectedPoolStrategy }),
        "--append-report", $ReportPath
    )
    if ($NextGateRequireCurrentPoolSnapshot) {
        $watchArgs += "--require-current-pool-snapshot"
    }
    $watcher = Start-Process -FilePath $Python -ArgumentList $watchArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $watchOut `
        -RedirectStandardError $watchErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "next-gate watcher PID: $($watcher.Id)"
}

if ($StartGateSequenceWatcher) {
    $sequenceStart = $GateSequenceStartIteration
    if ($sequenceStart -le 0) {
        if ($StartNextGateWatcher) {
            $sequenceStart = $NextGateIteration + $GateSequenceStep
        } else {
            $sequenceStart = $NextGateIteration
        }
    }
    if ($GateSequenceMaxIteration -lt $sequenceStart) {
        $GateSequenceMaxIteration = $sequenceStart
    }
    $sequenceOut = Join-Path $newRunDirAbs "gate_sequence_${sequenceStart}_${GateSequenceMaxIteration}.out.log"
    $sequenceErr = Join-Path $newRunDirAbs "gate_sequence_${sequenceStart}_${GateSequenceMaxIteration}.err.log"
    $sequenceArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_gate_sequence_watch.py",
        "--run-dir", $newRunDirAbs,
        "--start-iteration", "$sequenceStart",
        "--max-iteration", "$GateSequenceMaxIteration",
        "--step", "$GateSequenceStep",
        "--snapshot-every", "$SnapshotEvery",
        "--k-best", "$KBest",
        "--expected-pool-snapshots", "$NextGateExpectedPoolSnapshots",
        "--expected-opponent-assignment", $OpponentAssignment,
        "--expected-pool-strategy", $(if ([string]::IsNullOrWhiteSpace($NextGateExpectedPoolStrategy)) { $PoolStrategy } else { $NextGateExpectedPoolStrategy }),
        "--require-current-pool-snapshot-on-snapshot-gates",
        "--refresh-health",
        "--python", $Python,
        "--poll-seconds", "$GateSequencePollSeconds",
        "--timeout-seconds", "$GateSequenceTimeoutSeconds",
        "--append-report", $ReportPath
    )
    $sequenceWatcher = Start-Process -FilePath $Python -ArgumentList $sequenceArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $sequenceOut `
        -RedirectStandardError $sequenceErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "gate sequence watcher PID: $($sequenceWatcher.Id) start=$sequenceStart max=$GateSequenceMaxIteration"
}

if ($StartThroughputWatcher) {
    $throughputOut = Join-Path $newRunDirAbs "throughput_watch.out.log"
    $throughputErr = Join-Path $newRunDirAbs "throughput_watch.err.log"
    $throughputJson = Join-Path $newRunDirAbs "throughput_compare.json"
    $throughputMd = Join-Path $newRunDirAbs "throughput_compare.md"
    $throughputLog = Join-Path $newRunDirAbs "throughput_watch.log"
    $throughputArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_throughput_watch.py",
        "--baseline-run-dir", $sourceRunDirAbs,
        "--candidate-run-dir", $newRunDirAbs,
        "--tail", "$ThroughputTail",
        "--min-baseline-rows", "$ThroughputMinBaselineRows",
        "--min-candidate-rows", "$ThroughputMinCandidateRows",
        "--min-hps-ratio", "$ThroughputMinHpsRatio",
        "--min-inf-bs-ratio", "$ThroughputMinInfBsRatio",
        "--min-candidate-inf-bs", "$ThroughputMinCandidateInfBs",
        "--poll-seconds", "$ThroughputPollSeconds",
        "--timeout-seconds", "$ThroughputTimeoutSeconds",
        "--out-json", $throughputJson,
        "--out-md", $throughputMd,
        "--log-path", $throughputLog,
        "--append-report", $ReportPath
    )
    $throughputWatcher = Start-Process -FilePath $Python -ArgumentList $throughputArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $throughputOut `
        -RedirectStandardError $throughputErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "throughput watcher PID: $($throughputWatcher.Id)"
}

if ($StartHealthWatcher) {
    $healthOut = Join-Path $newRunDirAbs "health_watch.out.log"
    $healthErr = Join-Path $newRunDirAbs "health_watch.err.log"
    $healthLog = Join-Path $newRunDirAbs "health_watch.log"
    $healthArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_health_watch.py",
        "--run-dir", $newRunDirAbs,
        "--python", $Python,
        "--poll-seconds", "$HealthPollSeconds",
        "--timeout-seconds", "$HealthTimeoutSeconds",
        "--log-path", $healthLog,
        "--preflop-call-warn-after-iter", "$PreflopCallWarnAfterIter",
        "--preflop-call-warn", "$PreflopCallWarn",
        "--preflop-call-fail", "$PreflopCallFail",
        "--preflop-dominance-warn", "$PreflopDominanceWarn",
        "--preflop-dominance-fail", "$PreflopDominanceFail",
        "--preflop-allin-warn", "$PreflopAllinWarn",
        "--preflop-allin-fail", "$PreflopAllinFail",
        "--stderr-recent-minutes", "$StderrRecentMinutes"
    )
    if ($HealthExitOnWarn) {
        $healthArgs += "--exit-on-warn"
    }
    $healthWatcher = Start-Process -FilePath $Python -ArgumentList $healthArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $healthOut `
        -RedirectStandardError $healthErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "health watcher PID: $($healthWatcher.Id)"
}

if ($StartDashboardWatcher) {
    $dashboardOut = Join-Path $newRunDirAbs "dashboard_watch.out.log"
    $dashboardErr = Join-Path $newRunDirAbs "dashboard_watch.err.log"
    $dashboardStatus = Join-Path $newRunDirAbs "v5_dashboard_watch_status.json"
    $dashboardLog = Join-Path $newRunDirAbs "v5_dashboard_watch.log"
    $dashboardArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_dashboard_watch.py",
        "--run-dir", $newRunDirAbs,
        "--status-json", $dashboardStatus,
        "--log", $dashboardLog,
        "--sleep-seconds", "$DashboardPollSeconds",
        "--python", $Python,
        "--output-dir", $OutputDir
    )
    $dashboardWatcher = Start-Process -FilePath $Python -ArgumentList $dashboardArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $dashboardOut `
        -RedirectStandardError $dashboardErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "dashboard watcher PID: $($dashboardWatcher.Id)"
}

if ($StartEvalCadenceWatcher) {
    $evalOut = Join-Path $newRunDirAbs "eval_cadence_watch.out.log"
    $evalErr = Join-Path $newRunDirAbs "eval_cadence_watch.err.log"
    $evalStatus = Join-Path $newRunDirAbs "v5_eval_cadence_watch_status.json"
    $evalLog = Join-Path $newRunDirAbs "v5_eval_cadence_watch.log"
    $evalArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_eval_cadence_watch.py",
        "--run-dir", $newRunDirAbs,
        "--output-dir", $OutputDir,
        "--status-json", $evalStatus,
        "--log", $evalLog,
        "--append-report", $ReportPath,
        "--poll-seconds", "$EvalCadencePollSeconds",
        "--python", $Python
    )
    $evalWatcher = Start-Process -FilePath $Python -ArgumentList $evalArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $evalOut `
        -RedirectStandardError $evalErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "eval cadence watcher PID: $($evalWatcher.Id)"
}

if ($StartSlumbotQuick5kWatcher) {
    $quick5kOut = Join-Path $newRunDirAbs "slumbot_quick5k_launch_watch.out.log"
    $quick5kErr = Join-Path $newRunDirAbs "slumbot_quick5k_launch_watch.err.log"
    $quick5kStatus = Join-Path $newRunDirAbs "slumbot_quick5k_launch_status.json"
    $quick5kPlanJson = Join-Path $newRunDirAbs "slumbot_quick5k_plan.json"
    $quick5kPlanMd = Join-Path $newRunDirAbs "slumbot_quick5k_plan.md"
    $quick5kLog = Join-Path $newRunDirAbs "slumbot_quick5k_launch_watch.log"
    $quick5kArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_slumbot_benchmark_watch.py",
        "--run-dir", $newRunDirAbs,
        "--stage", "quick5k",
        "--output-dir", $OutputDir,
        "--status-json", $quick5kStatus,
        "--plan-json", $quick5kPlanJson,
        "--plan-md", $quick5kPlanMd,
        "--log", $quick5kLog,
        "--append-report", $ReportPath,
        "--sleep-seconds", "$SlumbotQuick5kPollSeconds",
        "--max-health-age-seconds", "$SlumbotQuick5kMaxHealthAgeSeconds"
    )
    $quick5kWatcher = Start-Process -FilePath $Python -ArgumentList $quick5kArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $quick5kOut `
        -RedirectStandardError $quick5kErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "Slumbot quick5k watcher PID: $($quick5kWatcher.Id)"
}

if ($StartSlumbotPromotion20kWatcher) {
    $promotionOut = Join-Path $newRunDirAbs "slumbot_promotion20k_launch_watch.out.log"
    $promotionErr = Join-Path $newRunDirAbs "slumbot_promotion20k_launch_watch.err.log"
    $promotionStatus = Join-Path $newRunDirAbs "slumbot_promotion20k_launch_status.json"
    $promotionPlanJson = Join-Path $newRunDirAbs "slumbot_promotion20k_plan.json"
    $promotionPlanMd = Join-Path $newRunDirAbs "slumbot_promotion20k_plan.md"
    $promotionLog = Join-Path $newRunDirAbs "slumbot_promotion20k_launch_watch.log"
    $promotionArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_slumbot_benchmark_watch.py",
        "--run-dir", $newRunDirAbs,
        "--stage", "promotion20k",
        "--output-dir", $OutputDir,
        "--min-training-hands", "$SlumbotPromotion20kMinTrainingHands",
        "--status-json", $promotionStatus,
        "--plan-json", $promotionPlanJson,
        "--plan-md", $promotionPlanMd,
        "--log", $promotionLog,
        "--append-report", $ReportPath,
        "--sleep-seconds", "$SlumbotPromotion20kPollSeconds",
        "--max-health-age-seconds", "$SlumbotPromotion20kMaxHealthAgeSeconds"
    )
    $promotionWatcher = Start-Process -FilePath $Python -ArgumentList $promotionArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $promotionOut `
        -RedirectStandardError $promotionErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "Slumbot promotion20k watcher PID: $($promotionWatcher.Id)"
}

if ($StartSlumbotFormal100kWatcher) {
    $formalOut = Join-Path $newRunDirAbs "slumbot_formal100k_launch_watch.out.log"
    $formalErr = Join-Path $newRunDirAbs "slumbot_formal100k_launch_watch.err.log"
    $formalStatus = Join-Path $newRunDirAbs "slumbot_formal100k_launch_status.json"
    $formalPlanJson = Join-Path $newRunDirAbs "slumbot_formal100k_plan.json"
    $formalPlanMd = Join-Path $newRunDirAbs "slumbot_formal100k_plan.md"
    $formalLog = Join-Path $newRunDirAbs "slumbot_formal100k_launch_watch.log"
    $formalArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_slumbot_benchmark_watch.py",
        "--run-dir", $newRunDirAbs,
        "--stage", "formal100k",
        "--output-dir", $OutputDir,
        "--min-training-hands", "$SlumbotFormal100kMinTrainingHands",
        "--status-json", $formalStatus,
        "--plan-json", $formalPlanJson,
        "--plan-md", $formalPlanMd,
        "--log", $formalLog,
        "--append-report", $ReportPath,
        "--sleep-seconds", "$SlumbotFormal100kPollSeconds",
        "--max-health-age-seconds", "$SlumbotFormal100kMaxHealthAgeSeconds"
    )
    $formalWatcher = Start-Process -FilePath $Python -ArgumentList $formalArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $formalOut `
        -RedirectStandardError $formalErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "Slumbot formal100k watcher PID: $($formalWatcher.Id)"
}

if ($StartInternalStrengthWatcher) {
    $internalStart = $InternalStrengthStartIteration
    if ($internalStart -le 0) {
        if ($SnapshotEvery -gt 0) {
            $internalStart = [int]([math]::Ceiling($NextGateIteration / [double]$SnapshotEvery) * $SnapshotEvery)
        } else {
            $internalStart = $NextGateIteration
        }
    }
    $internalMax = $InternalStrengthMaxIteration
    if ($internalMax -lt $internalStart) {
        $internalMax = $internalStart
    }
    $internalOut = Join-Path $newRunDirAbs "internal_strength_watch.out.log"
    $internalErr = Join-Path $newRunDirAbs "internal_strength_watch.err.log"
    $internalStatus = Join-Path $newRunDirAbs "internal_strength_watch_status.json"
    $internalLog = Join-Path $newRunDirAbs "internal_strength_watch.log"
    $internalArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_internal_strength_watch.py",
        "--run-dir", $newRunDirAbs,
        "--start-iteration", "$internalStart",
        "--max-iteration", "$internalMax",
        "--step", "$InternalStrengthStep",
        "--hands", "$InternalStrengthHands",
        "--require-health-pass",
        "--python", $Python,
        "--status-json", $internalStatus,
        "--log", $internalLog,
        "--append-report", $ReportPath
    )
    $internalWatcher = Start-Process -FilePath $Python -ArgumentList $internalArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $internalOut `
        -RedirectStandardError $internalErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "internal strength watcher PID: $($internalWatcher.Id) targets=$internalStart..$internalMax"
}

if ($StartCheckpointArchiveWatcher) {
    $archiveOut = Join-Path $newRunDirAbs "checkpoint_archive_watch.out.log"
    $archiveErr = Join-Path $newRunDirAbs "checkpoint_archive_watch.err.log"
    $archiveStatus = Join-Path $newRunDirAbs "checkpoint_archive_status.json"
    $archiveLog = Join-Path $newRunDirAbs "checkpoint_archive_watch.log"
    $archiveArgs = @(
        "-u",
        "scripts\alpha_holdem\v5_checkpoint_archive_watch.py",
        "--run-dir", $newRunDirAbs,
        "--status-json", $archiveStatus,
        "--log", $archiveLog,
        "--append-report", $ReportPath,
        "--sleep-seconds", "$ArchivePollSeconds"
    )
    $archiveWatcher = Start-Process -FilePath $Python -ArgumentList $archiveArgs `
        -WorkingDirectory $Repo `
        -RedirectStandardOutput $archiveOut `
        -RedirectStandardError $archiveErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Step "checkpoint archive watcher PID: $($archiveWatcher.Id)"
}

Write-Step "continuation launch complete"
