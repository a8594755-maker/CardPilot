$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$outputDir =
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\internal_curve_1p64m'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

$candidates = [ordered]@{
    source_hero_awr =
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\selected.pt'
    league_1p64m =
        'models\sourcev4_heroawr_mimic_league_rl10m_20260726\checkpoints\checkpoint_iter000050_hands000001641693.pt'
}
$rows = @(
    foreach ($name in $candidates.Keys) {
        $json = Join-Path $outputDir "$name.json"
        if (-not (Test-Path -LiteralPath $json)) {
            $probeOutput = & python -X utf8 -u `
                scripts/alpha_holdem/v5_internal_strength_probe.py `
                --checkpoint $candidates[$name] `
                --hands 1000 `
                --opponents aggressive call-station random `
                --max-pool-snapshots 0 `
                --device cuda `
                --starting-stack 200 `
                --seed 20260777 `
                --policy-mode greedy `
                --out-json $json `
                --out-md (Join-Path $outputDir "$name.md")
            $probeOutput | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "League 1.64M internal probe failed for $name"
            }
        }
        $probe = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
        [PSCustomObject]@{
            name = $name
            checkpoint = (Resolve-Path -LiteralPath $candidates[$name]).Path
            checkpoint_sha256 = (
                Get-FileHash -LiteralPath $candidates[$name] -Algorithm SHA256
            ).Hash.ToLowerInvariant()
            total_hands = [int64]$probe.checkpoint.total_hands
            mean_bb_per_100 = [double](
                ($probe.results | Measure-Object -Property bb100 -Average).Average
            )
            results = $probe.results
        }
    }
)
[PSCustomObject]@{
    schema = 'cardpilot.internal_learning_curve.v1'
    seed = 20260777
    hands_per_scripted_opponent = 1000
    opponents = @('aggressive', 'call-station', 'random')
    rows = $rows
    delta_mean_bb_per_100 = (
        [double]$rows[1].mean_bb_per_100 -
        [double]$rows[0].mean_bb_per_100
    )
    interpretation = 'Internal generalization proxy only; not Slumbot strength evidence.'
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $outputDir 'summary.json') -Encoding UTF8
