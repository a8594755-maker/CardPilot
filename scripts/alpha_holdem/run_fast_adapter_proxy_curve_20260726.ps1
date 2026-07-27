$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidate = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\latest.pt'
$finalProbe = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\internal_curve\candidate.json'
$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$curveDir = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\proxy_curve'
$deadline = (Get-Date).AddHours(7)

while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $finalProbe) {
        break
    }
    $pipeline = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_fast1m_20260726'
            }
    )
    if ($pipeline.Count -eq 0) {
        throw 'Fast PPO pipeline exited before its final internal probe'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $finalProbe)) {
    throw 'Timed out waiting for fast PPO final internal probe'
}

New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 250 `
    --opponents aggressive `
    --checkpoint-opponent $proxy `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode greedy `
    --max-pool-snapshots 5 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260748 `
    --policy-mode greedy `
    --out-json (Join-Path $curveDir 'slumbot_imitation_proxy.json') `
    --out-md (Join-Path $curveDir 'slumbot_imitation_proxy.md')
exit $LASTEXITCODE
