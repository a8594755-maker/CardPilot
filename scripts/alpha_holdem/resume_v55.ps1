# resume_v55.ps1 - Resume V5.5 burn-in from latest ckpt (or fall back to V4 final).
#
# Default: resume from models\alpha_holdem_v55.pt (the last save_interval boundary).
# -FromV4: explicitly restart from models\alpha_holdem_v4_final.pt (loses V5.5 progress!)

param(
    [int]$Workers = 28,
    [int64]$TotalHands = 1500000000,
    [double]$Lr = 5e-5,                  # halved from V4-end 1e-4 (Phase 2d v3 hybrid)
    [double]$EmaAlpha = 0.999,
    [double]$EmaOnlyFraction = 1.0,
    [double]$EntropyCoef = 0.02,         # doubled (Phase 2d v3 entropy floor protection)
    [double]$EntropyFloor = 0.5,         # boost activates earlier
    [int]$SaveInterval = 50,
    [switch]$FromV4
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Decide resume path
if ($FromV4) {
    $resumePath = "models\alpha_holdem_v4_final.pt"
    Write-Host "Resuming from V4 final (V5.5 progress will be discarded)"
} else {
    if (Test-Path "models\alpha_holdem_v55.pt") {
        $resumePath = "models\alpha_holdem_v55.pt"
        Write-Host "Resuming from latest V5.5 ckpt"
    } else {
        $resumePath = "models\alpha_holdem_v4_final.pt"
        Write-Host "No V5.5 ckpt found, falling back to V4 final"
    }
}

# Check no trainer is already running (avoid double-launch)
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*train_v55.py*' }
if ($existing) {
    Write-Host "ERROR: V5.5 trainer already running (PID $($existing.ProcessId))."
    Write-Host "Run .\pause_v55.ps1 first."
    exit 1
}

$env:PYTHONUNBUFFERED = '1'
$pyArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v55.py',
    '--resume', $resumePath,
    '--out', 'models/alpha_holdem_v55.pt',
    '--device', 'cuda',
    '--workers', "$Workers",
    '--hands-per-iter', '16384',
    '--total-hands', "$TotalHands",
    '--starting-stack', '200.0',
    '--lr', "$Lr",
    '--epsilon', '0',
    '--gamma', '0.999',
    '--ema-alpha', "$EmaAlpha",
    '--ema-only-fraction', "$EmaOnlyFraction",
    '--entropy-coef', "$EntropyCoef",
    '--entropy-floor', "$EntropyFloor",
    '--save-interval', "$SaveInterval"
)

$logOut = 'models\v55_phase2d_stdout.log'
$logErr = 'models\v55_phase2d_stderr.log'

$p = Start-Process -FilePath 'python' -ArgumentList $pyArgs `
    -WorkingDirectory 'C:\Users\a8594\CardPilot' `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -NoNewWindow -PassThru

Write-Host ""
Write-Host "=== V5.5 RESUMED ==="
Write-Host "PID:    $($p.Id)"
Write-Host "Resume: $resumePath"
Write-Host "Target: $($TotalHands.ToString('N0')) real hands"
Write-Host "EMA:    alpha=$EmaAlpha, fraction=$EmaOnlyFraction"
Write-Host "Save:   every $SaveInterval iter"
Write-Host "stdout: $logOut"
Write-Host "stderr: $logErr"
Write-Host "log:    models\alpha_holdem_v55_train.log"
