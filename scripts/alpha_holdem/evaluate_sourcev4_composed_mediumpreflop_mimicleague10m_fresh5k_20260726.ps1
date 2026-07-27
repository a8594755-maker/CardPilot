$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidate = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_composed_heroawr_bbpreflop_medium_' +
        'mimicleague10m_20260726\selected.pt'
    )
).Path
$runDir = Split-Path -Parent $candidate
$composition = Get-Content -LiteralPath (
    Join-Path $runDir 'selected.json'
) -Raw | ConvertFrom-Json

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The independently learned medium BB-preflop head and 10M postflop ' +
        'adapter are complementary because each changes disjoint policy weights.'
    )
    material_change = (
        'Pure checkpoint composition: two learned preflop-head tensors plus ' +
        'four learned postflop-adapter tensors; no evaluator override.'
    )
    source_checkpoint = $composition.source_checkpoint
    source_checkpoint_sha256 = $composition.source_checkpoint_sha256
    preflop_checkpoint = $composition.preflop_checkpoint
    preflop_checkpoint_sha256 = $composition.preflop_checkpoint_sha256
    postflop_checkpoint = $composition.postflop_checkpoint
    postflop_checkpoint_sha256 = $composition.postflop_checkpoint_sha256
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $composition.output_checkpoint_sha256
    new_training_hands = 10020915
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = 600000
    pure_weight_policy = $true
    evaluator_overrides = $false
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_composed_heroawr_bbpreflop_medium_' +
    'mimicleague10m_pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag `
    'sourcev4_composed_heroawr_bbpreflop_medium_mimicleague10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Composed medium-preflop plus mimic-league-10M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate `
    'sourcev4_composed_heroawr_bbpreflop_medium_mimicleague10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem `
    'sourcev4_composed_heroawr_bbpreflop_medium_mimicleague10m' `
    -TrainingMethod `
    'pure disjoint learned-weight composition: medium preflop AWR plus 10M postflop PPO' `
    -NewTrainingHands 10020915 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 600000
exit $LASTEXITCODE
