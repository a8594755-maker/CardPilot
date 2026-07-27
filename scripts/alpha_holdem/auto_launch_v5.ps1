# auto_launch_v5.ps1 - Watcher: detect V4 reaches 1B + Slumbot benchmark out, then start V5.
#
# Phases:
#   1. Wait until V4 training log reports hands >= TargetHands (default 1B).
#   2. Wait for green-light signal:
#        - file: models\v5_ready.flag                  (manual: user touches after benchmark)
#        - OR: a benchmark log matching $env:V5_BENCH_GLOB whose tail says "Total bb/100"
#   3. Run freeze_v4.ps1 -> models\alpha_holdem_v4_final.pt
#   4. (Optional) stop V4 trainer to free GPU.        controlled by -KillV4 switch
#   5. Launch V5: python train_v5.py --resume v4_final.pt --out v5.pt
#
# Usage:
#   .\scripts\alpha_holdem\auto_launch_v5.ps1                 # waits for flag, KEEPS V4 running
#   .\scripts\alpha_holdem\auto_launch_v5.ps1 -KillV4         # stops V4 before launching V5
#   .\scripts\alpha_holdem\auto_launch_v5.ps1 -DryRun         # show plan only
#
# Manual trigger when benchmark complete:
#   New-Item models\v5_ready.flag -ItemType File -Force

param(
    [string]$Repo = "C:\Users\a8594\CardPilot",
    [int64]$TargetHands = 1000000000,
    [int]$PollSeconds = 60,
    [switch]$KillV4,
    [switch]$DryRun,
    [string]$V5OutPath = "models\alpha_holdem_v5.pt",
    [int64]$V5TotalHands = 1500000000,
    [int]$V5Workers = 28,
    [double]$V5Lr = 1e-4
)

$ErrorActionPreference = 'Stop'
Set-Location $Repo

$trainLog = "models\alpha_holdem_v4_train.log"
$flagPath = "models\v5_ready.flag"
$watcherLog = "models\auto_launch_v5.log"

function Log-Watcher([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $watcherLog -Value $line
}

function Get-LatestHands {
    if (-not (Test-Path $trainLog)) { return 0 }
    $tail = Get-Content $trainLog -Tail 50 -ErrorAction SilentlyContinue
    if (-not $tail) { return 0 }
    # Walk lines from newest to oldest looking for hands=N
    for ($i = $tail.Count - 1; $i -ge 0; $i--) {
        if ($tail[$i] -match 'hands=([\d,]+)') {
            $n = $matches[1] -replace ',', ''
            return [int64]$n
        }
    }
    return 0
}

# ---------- Phase 1: wait for 1B ----------
Log-Watcher "Phase 1: waiting for V4 to reach $($TargetHands.ToString('N0')) hands"
while ($true) {
    $h = Get-LatestHands
    if ($h -ge $TargetHands) {
        Log-Watcher "V4 reached $($h.ToString('N0')) hands (>= target)"
        break
    }
    Log-Watcher "  current: $($h.ToString('N0')) hands; sleep ${PollSeconds}s"
    Start-Sleep -Seconds $PollSeconds
}

# ---------- Phase 2: wait for green-light flag ----------
Log-Watcher "Phase 2: waiting for benchmark green-light: $flagPath"
Log-Watcher "  When 20K-hand Slumbot benchmark out, run:"
Log-Watcher "      New-Item $flagPath -ItemType File -Force"
while (-not (Test-Path $flagPath)) {
    Start-Sleep -Seconds $PollSeconds
}
Log-Watcher "Green light: $flagPath present"

# ---------- Phase 3: stop V4 trainer (must precede freeze for stable .pt) ----------
if ($KillV4) {
    Log-Watcher "Phase 3: stopping V4 trainer process(es) before freeze"
    $v4Procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*train_mp3.py*' }
    if ($v4Procs) {
        foreach ($p in $v4Procs) {
            Log-Watcher "  stopping PID $($p.ProcessId): $($p.CommandLine)"
            if (-not $DryRun) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        }
        # Wait for shm cleanup + final ckpt write
        Start-Sleep -Seconds 10
    } else {
        Log-Watcher "  no V4 trainer process found"
    }
} else {
    Log-Watcher "Phase 3: -KillV4 not set; freeze will use latest rolling/eval (live .pt unsafe while training)"
    Log-Watcher "  WARNING: dual training on RTX 4070 may OOM. Pass -KillV4 to stop V4."
}

# ---------- Phase 4: freeze V4 ----------
Log-Watcher "Phase 4: freezing V4 (>=1000M rolling/eval/live -> alpha_holdem_v4_final.pt)"
$freezeArgs = @('-MinHandsM', '1000')
if ($DryRun) { $freezeArgs += '-DryRun' }
& "$PSScriptRoot\freeze_v4.ps1" @freezeArgs
if ($LASTEXITCODE -ne 0) {
    Log-Watcher "ERROR: freeze_v4.ps1 returned $LASTEXITCODE; aborting"
    exit 1
}

# ---------- Phase 5: launch V5 ----------
$resumePath = "models\alpha_holdem_v4_final.pt"
if (-not (Test-Path $resumePath)) {
    Log-Watcher "ERROR: $resumePath missing; freeze must have failed"
    exit 1
}

$pyArgs = @(
    'scripts\alpha_holdem\train_v5.py',
    '--resume', $resumePath,
    '--out', $V5OutPath,
    '--device', 'cuda',
    '--workers', "$V5Workers",
    '--total-hands', "$V5TotalHands",
    '--starting-stack', '200.0',
    '--lr', "$V5Lr",
    '--epsilon', '0',
    '--gamma', '0.999',
    '--k-best', '5'
)

Log-Watcher "Phase 5: launching V5 trainer"
Log-Watcher "  python $($pyArgs -join ' ')"

if ($DryRun) {
    Log-Watcher "(DryRun) skipping actual launch"
    exit 0
}

# Launch as detached process so this watcher can exit cleanly.
$v5LogPath = $V5OutPath -replace '\.pt$', '_train.log'
Log-Watcher "  V5 stdout/stderr -> $v5LogPath"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'python'
foreach ($a in $pyArgs) { $psi.ArgumentList.Add($a) | Out-Null }
$psi.WorkingDirectory = $Repo
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $false

# Simpler: spawn via Start-Process with redirect, return immediately
Start-Process -FilePath 'python' -ArgumentList $pyArgs `
    -WorkingDirectory $Repo `
    -RedirectStandardOutput $v5LogPath `
    -RedirectStandardError ($v5LogPath -replace '\.log$', '_err.log') `
    -NoNewWindow -PassThru | ForEach-Object {
        Log-Watcher "V5 PID: $($_.Id)"
    }

Log-Watcher "V5 launched. Watcher exits."
