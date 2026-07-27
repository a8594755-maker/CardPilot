$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runDir = 'models\sourcev4_heroawr_league_criticv2_scale10m_20260726'
$checkpoint = Join-Path $runDir 'checkpoints\checkpoint_iter000200_*.pt'
$deadline = (Get-Date).AddHours(3)
while ((Get-Date) -lt $deadline) {
    $matches = @(Get-ChildItem -Path $checkpoint -File -ErrorAction SilentlyContinue)
    if ($matches.Count -eq 1) { break }
    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq 'python.exe' -and
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5\.py' -and
                $_.CommandLine -match
                    'sourcev4_heroawr_league_criticv2_scale10m_20260726'
            }
    )
    if ($trainer.Count -eq 0) {
        throw 'Critic-v2 scale trainer exited before iteration 200'
    }
    Start-Sleep -Seconds 20
}
$matches = @(Get-ChildItem -Path $checkpoint -File -ErrorAction SilentlyContinue)
if ($matches.Count -ne 1) {
    throw "Expected one critic-v2 iteration-200 checkpoint, found $($matches.Count)"
}

$outputDir = Join-Path $runDir 'internal_curve_iter200'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$candidateJson = Join-Path $outputDir 'candidate.json'
$probeOutput = & python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $matches[0].FullName `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260777 `
    --policy-mode greedy `
    --out-json $candidateJson `
    --out-md (Join-Path $outputDir 'candidate.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 iteration-200 internal probe failed'
}

$source = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_1p64m\source_hero_awr.json'
) -Raw | ConvertFrom-Json
$mainV1 = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_6p56m\summary.json'
) -Raw | ConvertFrom-Json
$initialV2 = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_league_iter50_criticv2_1p64m_20260726\' +
    'internal_curve\candidate.json'
) -Raw | ConvertFrom-Json
$candidate = Get-Content -LiteralPath $candidateJson -Raw | ConvertFrom-Json
$sourceMean = [double](
    ($source.results | Measure-Object -Property bb100 -Average).Average
)
$initialV2Mean = [double](
    ($initialV2.results | Measure-Object -Property bb100 -Average).Average
)
$candidateMean = [double](
    ($candidate.results | Measure-Object -Property bb100 -Average).Average
)
[ordered]@{
    schema = 'cardpilot.internal_learning_curve.v1'
    seed = 20260777
    hands_per_scripted_opponent = 1000
    opponents = @('aggressive', 'call-station', 'random')
    source_mean_bb_per_100 = $sourceMean
    critic_v1_iter200_mean_bb_per_100 = (
        [double]$mainV1.candidate_mean_bb_per_100
    )
    critic_v2_initial_mean_bb_per_100 = $initialV2Mean
    candidate_checkpoint = $matches[0].FullName
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $matches[0].FullName -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = [int64]$candidate.checkpoint.total_hands
    candidate_mean_bb_per_100 = $candidateMean
    delta_vs_source_bb_per_100 = $candidateMean - $sourceMean
    delta_vs_initial_critic_v2_bb_per_100 = $candidateMean - $initialV2Mean
    candidate_results = $candidate.results
    interpretation = 'Internal generalization proxy only; not Slumbot strength evidence.'
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $outputDir 'summary.json') -Encoding UTF8
