# pause_v55.ps1 - Cleanly pause V5.5 burn-in via file-flag mechanism.
#
# How it works:
# 1. Touch models/v55_pause.flag
# 2. Trainer detects flag at top of next iter loop, saves + exits gracefully
# 3. Wait up to GraceSeconds for trainer to exit (default 60s — generous)
# 4. If still alive (older trainer code without flag check, or stuck), fall back
#    to taskkill + Stop-Process (loses up to save_interval iters)
#
# Resume with:  .\scripts\alpha_holdem\resume_v55.ps1

param(
    [int]$GraceSeconds = 60,
    [switch]$Force   # skip flag, immediately taskkill
)

$ErrorActionPreference = 'Continue'

$flag = 'C:\Users\a8594\CardPilot\models\v55_pause.flag'
$ckpt = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v55.pt'
$log  = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v55_train.log'

$main = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*train_v55.py*' }

if (-not $main) {
    Write-Host "No V5.5 trainer found running."
    if (Test-Path $flag) { Remove-Item $flag -Force; Write-Host "Cleaned stale flag." }
    exit 0
}

foreach ($p in $main) {
    Write-Host "Found V5.5 trainer: PID $($p.ProcessId)"
}

if ($Force) {
    Write-Host "Force mode: skipping graceful pause."
    foreach ($p in $main) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
} else {
    # Ckpt mtime BEFORE flag — used to detect successful save
    $ckptMtimeBefore = if (Test-Path $ckpt) { (Get-Item $ckpt).LastWriteTime } else { [datetime]::MinValue }

    Write-Host "Touching pause flag: $flag"
    New-Item -ItemType File -Path $flag -Force | Out-Null

    # Wait for trainer to detect flag, save, exit
    Write-Host "Waiting up to $GraceSeconds s for graceful save+exit..."
    $deadline = (Get-Date).AddSeconds($GraceSeconds)
    $exited = $false
    while ((Get-Date) -lt $deadline) {
        $still = Get-Process -Id $main[0].ProcessId -ErrorAction SilentlyContinue
        if (-not $still) { $exited = $true; break }
        Start-Sleep -Seconds 2
    }

    if ($exited) {
        # Verify ckpt was saved (mtime advanced)
        if (Test-Path $ckpt) {
            $ckptMtimeAfter = (Get-Item $ckpt).LastWriteTime
            if ($ckptMtimeAfter -gt $ckptMtimeBefore) {
                Write-Host "Trainer exited gracefully — ckpt updated to $ckptMtimeAfter"
            } else {
                Write-Host "Trainer exited but ckpt mtime unchanged (was $ckptMtimeBefore). Possible: paused before first save_interval — check log."
            }
        } else {
            Write-Host "Trainer exited but $ckpt missing. First save did not happen yet."
        }
    } else {
        Write-Host "Graceful pause timed out, force-killing (older trainer code without flag support, or hung)..."
        foreach ($p in $main) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        # Clean flag since the dying trainer can't
        if (Test-Path $flag) { Remove-Item $flag -Force }
    }
}

# Cleanup orphan worker processes (preserve safe_watcher PID 19820 + safe_watcher_v55)
Start-Sleep -Seconds 4
$preserve = @(19820)
$watcher_v55 = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*safe_watcher_v55*' }
foreach ($w in $watcher_v55) { $preserve += $w.ProcessId }

$orphans = Get-Process python -ErrorAction SilentlyContinue |
    Where-Object { $_.WorkingSet64 -gt 100MB -and $_.Id -notin $preserve }
if ($orphans) {
    Write-Host "Cleaning $($orphans.Count) orphan worker(s)..."
    foreach ($p in $orphans) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
}

Write-Host ""
Write-Host "=== V5.5 PAUSED ==="
if (Test-Path $ckpt) {
    $f = Get-Item $ckpt
    Write-Host "Latest ckpt: $($f.FullName)"
    Write-Host "  size:  $([math]::Round($f.Length/1MB,1)) MB"
    Write-Host "  mtime: $($f.LastWriteTime)"
} else {
    Write-Host "WARNING: $ckpt missing. Resume from V4: .\resume_v55.ps1 -FromV4"
}

if (Test-Path $log) {
    Write-Host ""
    Write-Host "Last 3 iter lines:"
    Get-Content $log -Tail 3
}
