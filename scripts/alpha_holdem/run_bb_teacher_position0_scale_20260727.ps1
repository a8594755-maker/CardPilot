$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726\experiment_record.json'
)
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.selected_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.selected_checkpoint_sha256) {
    throw 'Position0 teacher source hash mismatch'
}

$runDir = (
    'models\sourcev4_slumbot_position0_teacher_' +
    'scale20260726_historical_20260727'
)
if (Test-Path -LiteralPath $runDir) {
    throw "Position0 teacher output already exists: $runDir"
}

# Train only on completed 2026-07-26 opponent observations. The later
# specialist32M fresh5k remains a fully unseen common fidelity set.
& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $runDir `
    --roots models `
    --exclude-substring '__NO_DUMP_PATH_MATCH_20260727__' `
    --include-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping preflop_pot_fraction_v2 `
    --actor opp `
    --position 0 `
    --street-min 0 `
    --street-max 3 `
    --max-rows 1250000 `
    --min-rows 200000 `
    --seed 20260893 `
    --device cuda `
    --epochs 8 `
    --batch-size 4096 `
    --lr 0.00001 `
    --kl-coef 0.1 `
    --return-clip-bb 0 `
    --val-fraction 0.05
if ($LASTEXITCODE -ne 0) {
    throw 'Position0 teacher training failed'
}

$report = Get-Content -LiteralPath (Join-Path $runDir 'report.json') -Raw |
    ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath $report.best_checkpoint).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()

$heldoutDir = (
    'models\bench_sourcev4_imitation_anchor_' +
    'specialist_mixed32m_pure_fresh5k_20260727'
)
$heldoutDumps = @(
    Get-ChildItem -LiteralPath $heldoutDir -Filter '*_dump.jsonl' -File |
        Sort-Object Name |
        ForEach-Object { $_.FullName }
)
if ($heldoutDumps.Count -ne 4) {
    throw "Expected four held-out dump files, got $($heldoutDumps.Count)"
}
$comparisonPath = Join-Path $runDir 'unseen_specialist32m_comparison.json'
$compareArgs = @(
    '-X', 'utf8',
    'scripts/alpha_holdem/compare_policy_on_slumbot_dumps.py',
    '--source-checkpoint', $source,
    '--candidate-checkpoint', $candidate,
    '--dumps'
) + $heldoutDumps + @(
    '--actor', 'opp',
    '--obs-version', 'v4',
    '--raise-action-mapping', 'preflop_pot_fraction_v2',
    '--max-rows', '100000',
    '--batch-size', '4096',
    '--seed', '20260894',
    '--device', 'cuda',
    '--out-json', $comparisonPath
)
& python @compareArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Position0 teacher unseen comparison failed'
}
$comparison = Get-Content -LiteralPath $comparisonPath -Raw |
    ConvertFrom-Json
$sourceP0 = [double](
    $comparison.groups.position_0.source_matches_logged_rate
)
$candidateP0 = [double](
    $comparison.groups.position_0.candidate_matches_logged_rate
)
$retain = (
    $candidateSha -ne $sourceSha -and
    $candidateP0 -ge ($sourceP0 + 0.005)
)

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The BB-weight3 teacher improved the deployed BB seat, but it had ' +
        'seen only the older 750k mixed-position corpus. Continuing it only ' +
        'on the larger completed position0 Slumbot-opponent corpus should ' +
        'produce a more faithful BB neural teacher.'
    )
    material_change = (
        'Fine-tune all learned weights of the BB-weight3 source for eight ' +
        'epochs at lr=1e-5 and KL=0.1 on up to 1.25M position0 opponent ' +
        'decisions from completed 2026-07-26 dumps only.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = 0
    inherited_lineage_training_hands = (
        [int64]$sourceRecord.inherited_lineage_training_hands
    )
    offline_decision_samples = (
        [int64]$report.train_rows + [int64]$report.val_rows
    )
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    unseen_dump_family = 'specialist32M fresh5k 20260727'
    unseen_rows = [int64]$comparison.overall.rows
    unseen_source_position0_match = $sourceP0
    unseen_candidate_position0_match = $candidateP0
    unseen_position0_delta = $candidateP0 - $sourceP0
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    intended_use = 'BB_NEURAL_TEACHER'
    decision = if ($retain) {
        'RETAIN_AS_BB_NEURAL_TEACHER'
    } else {
        'REJECT_UNSEEN_POSITION0_FIDELITY'
    }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
exit 0
