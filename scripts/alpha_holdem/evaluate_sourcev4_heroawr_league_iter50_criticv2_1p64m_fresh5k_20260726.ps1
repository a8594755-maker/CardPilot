$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runDir = 'models\sourcev4_heroawr_league_iter50_criticv2_1p64m_20260726'
$source = @(
    Get-ChildItem -Path (
        'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
        'checkpoints\checkpoint_iter000050_*.pt'
    ) -File
)
if ($source.Count -ne 1) {
    throw "Expected one iteration-50 source checkpoint, found $($source.Count)"
}
$candidate = Join-Path $runDir 'latest.pt'
$probeJson = Join-Path $runDir 'internal_curve\candidate.json'
foreach ($path in @($candidate, $probeJson)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing critic-v2 result: $path"
    }
}

$sourceProbe = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_1p64m\source_hero_awr.json'
) -Raw | ConvertFrom-Json
$criticV1Probe = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_3p28m\summary.json'
) -Raw | ConvertFrom-Json
$candidateProbe = Get-Content -LiteralPath $probeJson -Raw | ConvertFrom-Json
$sourceMean = [double](
    ($sourceProbe.results | Measure-Object -Property bb100 -Average).Average
)
$criticV1Mean = [double]$criticV1Probe.candidate_mean_bb_per_100
$candidateMean = [double](
    ($candidateProbe.results | Measure-Object -Property bb100 -Average).Average
)
$candidateHands = [int64]$candidateProbe.checkpoint.total_hands
$sourceHandsText = & python -X utf8 -c (
    "import torch; c=torch.load(r'$($source[0].FullName)'," +
    "map_location='cpu',weights_only=False); print(int(c['total_hands']))"
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not read iteration-50 source hand count'
}
$sourceHands = [int64]$sourceHandsText
$newHands = $candidateHands - $sourceHands
$runExternal = (
    $candidateMean -ge ($sourceMean - 10.0) -and
    $candidateMean -ge ($criticV1Mean + 20.0)
)
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A deeper critic with 200bb-normalized targets reduces the late-policy ' +
        'drift seen with the single-layer raw-BB critic.'
    )
    material_change = (
        'From the exact iteration-50 actor: critic_v1 to freshly initialized ' +
        'critic_v2, normalized returns, fresh Adam; all actor/league settings fixed.'
    )
    source_checkpoint = $source[0].FullName
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source[0].FullName -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = $newHands
    inherited_lineage_training_hands = 2825663
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    stable_internal_seed = 20260777
    stable_internal_hands_per_opponent = 1000
    source_mean_bb_per_100 = $sourceMean
    critic_v1_same_endpoint_mean_bb_per_100 = $criticV1Mean
    critic_v2_candidate_mean_bb_per_100 = $candidateMean
    external_gate = (
        'candidate >= source-10 and candidate >= critic_v1 same endpoint+20'
    )
    run_fresh5k = $runExternal
    decision = if ($runExternal) { 'RETAIN_AND_SCREEN' } else { 'REJECT' }
    evaluator_compatibility_repair = (
        'Canonical inference loader now reads critic_contract; actor logits unchanged.'
    )
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
if (-not $runExternal) { exit 0 }

$externalDir = (
    'models\bench_sourcev4_heroawr_league_iter50_criticv2_1p64m_' +
    'pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag (
        'sourcev4_heroawr_league_iter50_criticv2_1p64m_' +
        'pure_fresh5k_20260726'
    ) `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_league_iter50_criticv2_1p64m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_league_iter50_criticv2_1p64m' `
    -TrainingMethod (
        'normalized deeper critic-v2 fixed pure-policy league PPO from ' +
        'iteration-50 hero-AWR league actor'
    ) `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 2825663 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
