$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$run = 'models\sourcev4_formal100k_postflop_awr_e1_rl1m_20260726'
$curve = Join-Path $run 'proxy_curve'
New-Item -ItemType Directory -Path $curve -Force | Out-Null

$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$candidates = @(
    [PSCustomObject]@{
        label = 'awr_source_e1'
        path = 'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt'
    },
    [PSCustomObject]@{
        label = 'rl_iter10_295k'
        path = (Join-Path $run 'checkpoints\checkpoint_iter000010_hands000000295289.pt')
    },
    [PSCustomObject]@{
        label = 'rl_iter30_624k'
        path = (Join-Path $run 'checkpoints\checkpoint_iter000030_hands000000624009.pt')
    },
    [PSCustomObject]@{
        label = 'rl_iter50_952k'
        path = (Join-Path $run 'checkpoints\checkpoint_iter000050_hands000000952581.pt')
    },
    [PSCustomObject]@{
        label = 'rl_final_1265k'
        path = (Join-Path $run 'latest.pt')
    }
)

$summary = foreach ($candidate in $candidates) {
    $json = Join-Path $curve ($candidate.label + '.json')
    if (-not (Test-Path -LiteralPath $json)) {
        & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
            --checkpoint $candidate.path `
            --hands 1000 `
            --opponents aggressive `
            --checkpoint-opponent $proxy `
            --checkpoint-opponent-only `
            --checkpoint-opponent-policy-mode greedy `
            --max-pool-snapshots 0 `
            --device cuda `
            --starting-stack 200 `
            --seed 20260758 `
            --policy-mode greedy `
            --out-json $json `
            --out-md (Join-Path $curve ($candidate.label + '.md')) |
            Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Proxy curve failed for $($candidate.label)"
        }
    }
    $result = Get-Content -Raw -LiteralPath $json | ConvertFrom-Json
    [PSCustomObject]@{
        label = $candidate.label
        checkpoint = (Resolve-Path -LiteralPath $candidate.path).Path
        checkpoint_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate.path).Hash.ToLowerInvariant()
        total_hands = [int64]$result.checkpoint.total_hands
        bb100 = [double]$result.results[0].bb100
        ci95 = [double]$result.results[0].ci95_bb100
    }
}

$best = $summary | Sort-Object bb100 -Descending | Select-Object -First 1
[PSCustomObject]@{
    hypothesis = 'AWR-seeded self-play may peak before the final 1M-hand endpoint.'
    proxy = (Resolve-Path -LiteralPath $proxy).Path
    seed = 20260758
    hands_per_candidate = 1000
    rows = @($summary)
    best_label = $best.label
    best_checkpoint = $best.checkpoint
    best_checkpoint_sha256 = $best.checkpoint_sha256
    best_bb100 = $best.bb100
    best_ci95 = $best.ci95
    interpretation = 'Internal proxy learning curve only; Slumbot remains the external authority.'
} |
    ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $curve 'summary.json') -Encoding UTF8
