# freeze_v4.ps1 - Freeze V4 at the 1B-hand milestone (or nearest rolling >= MinHandsM)
#
# Selects the smallest rolling ckpt whose embedded hand count >= MinHandsM (in millions),
# then writes:
#   models/alpha_holdem_v4_final.pt              - the canonical V5 starting point
#   models/alpha_holdem_v4_final_<NNN>M.pt       - tagged copy (audit trail)
#
# Usage:
#   .\scripts\alpha_holdem\freeze_v4.ps1                      # default >=1000M
#   .\scripts\alpha_holdem\freeze_v4.ps1 -MinHandsM 1000      # explicit
#   .\scripts\alpha_holdem\freeze_v4.ps1 -DryRun              # show selection only

param(
    [int]$MinHandsM = 1000,
    [switch]$DryRun,
    [string]$ModelsDir = "C:\Users\a8594\CardPilot\models"
)

$ErrorActionPreference = 'Stop'

function Get-CkptCandidates([string]$pattern, [string]$nameRegex, [int]$min) {
    Get-ChildItem -Path (Join-Path $ModelsDir $pattern) -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match $nameRegex) {
            [PSCustomObject]@{
                Path = $_.FullName; HandsM = [int]$matches[1]; Modified = $_.LastWriteTime
            }
        }
    } | Where-Object { $_.HandsM -ge $min } | Sort-Object HandsM
}

# Pref order: rolling >= MinHandsM, then eval >= MinHandsM, then live .pt (only if log shows >= MinHandsM)
$rolling = Get-CkptCandidates 'alpha_holdem_v4_rolling_*M.pt' 'alpha_holdem_v4_rolling_(\d+)M\.pt' $MinHandsM
$eval    = Get-CkptCandidates 'alpha_holdem_v4_eval*M*.pt' 'alpha_holdem_v4_eval(\d+)M' $MinHandsM

$pick = $null
$source = ''
if ($rolling) { $pick = $rolling | Select-Object -First 1; $source = 'rolling' }
elseif ($eval) { $pick = $eval | Select-Object -First 1; $source = 'eval' }
else {
    # Fallback to live alpha_holdem_v4.pt if training log shows hands >= MinHandsM
    $logPath = Join-Path $ModelsDir 'alpha_holdem_v4_train.log'
    $livePath = Join-Path $ModelsDir 'alpha_holdem_v4.pt'
    if ((Test-Path $logPath) -and (Test-Path $livePath)) {
        $tail = Get-Content $logPath -Tail 50
        $liveHandsM = 0
        for ($i = $tail.Count - 1; $i -ge 0; $i--) {
            if ($tail[$i] -match 'hands=([\d,]+)') {
                $liveHandsM = [int]([int64]($matches[1] -replace ',','') / 1000000); break
            }
        }
        if ($liveHandsM -ge $MinHandsM) {
            $pick = [PSCustomObject]@{
                Path = $livePath; HandsM = $liveHandsM; Modified = (Get-Item $livePath).LastWriteTime
            }
            $source = 'live'
            Write-Host "NOTE: no rolling/eval >= ${MinHandsM}M, using live .pt at ${liveHandsM}M (log)"
            Write-Host "      ensure V4 trainer is stopped before this script runs"
        }
    }
}

if (-not $pick) {
    Write-Host "ERROR: no V4 ckpt available with hands >= ${MinHandsM}M"
    Write-Host "       rolling ckpts found:"
    Get-ChildItem -Path (Join-Path $ModelsDir 'alpha_holdem_v4_rolling_*M.pt') | Sort-Object Name | ForEach-Object { Write-Host "         $($_.Name)" }
    exit 1
}

Write-Host "Source : $source"
Write-Host "Selected: $($pick.Path)"
Write-Host "  Hands  : $($pick.HandsM)M"
Write-Host "  Mtime  : $($pick.Modified)"

$finalPath = Join-Path $ModelsDir 'alpha_holdem_v4_final.pt'
$taggedPath = Join-Path $ModelsDir "alpha_holdem_v4_final_$($pick.HandsM)M.pt"

if ($DryRun) {
    Write-Host "(DryRun) Would copy to:"
    Write-Host "  $finalPath"
    Write-Host "  $taggedPath"
    exit 0
}

if (Test-Path $finalPath) {
    $backup = "$finalPath.replaced_$(Get-Date -Format yyyyMMdd_HHmmss).bak"
    Write-Host "WARN: $finalPath already exists; preserving as $backup"
    Move-Item -Path $finalPath -Destination $backup -Force
}

Copy-Item -Path $pick.Path -Destination $finalPath -Force
Copy-Item -Path $pick.Path -Destination $taggedPath -Force

Write-Host "Frozen V4:"
Write-Host "  $finalPath"
Write-Host "  $taggedPath"

# Sanity: log freeze event
$logPath = Join-Path $ModelsDir 'v4_freeze.log'
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -Path $logPath -Value "[$ts] froze $($pick.Path) -> $finalPath ($($pick.HandsM)M hands, source=$source)"
Write-Host "  Logged to $logPath"
