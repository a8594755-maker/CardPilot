param(
    [ValidateRange(1, 4096)]
    [int]$PositionAdapterHidden = 64,
    [ValidateRange(1, 1000)]
    [int]$Epochs = 8,
    [ValidateRange(0.00000001, 1.0)]
    [double]$LearningRate = 0.0001,
    [ValidateRange(1, 2147483647)]
    [int]$Seed = 20260843,
    [switch]$TrainPolicyTrunk,
    [ValidateNotNullOrEmpty()]
    [string]$OutputName = (
        'sourcev4_position_teacher_' +
        'standardSB_bbweight3BB_20260727'
    )
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay10m_20260726\experiment_record.json'
)
$bbRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726\experiment_record.json'
)
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
$bbRecord = Get-Content -LiteralPath $bbRecordPath -Raw |
    ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$bbTeacher = (Resolve-Path -LiteralPath $bbRecord.selected_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
$bbTeacherSha = (
    Get-FileHash -LiteralPath $bbTeacher -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Position-distillation source hash mismatch'
}
if ($bbTeacherSha -ne [string]$bbRecord.selected_checkpoint_sha256) {
    throw 'Position-distillation BB-teacher hash mismatch'
}

$standardEvalDir = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay10m_pure_fresh20k_20260726'
)
$bbEvalDir = (
    'models\bench_sourcev4_slumbot_allstreet_' +
    'imitation_bbweight3_pure_fresh20k_20260726'
)
$standardLossPath = Join-Path $standardEvalDir (
    'bench_v55_sourcev4_imitation_anchor_' +
    'mixedselfplay10m_pure_fresh20k_20260726_loss_report.json'
)
$bbLossPath = Join-Path $bbEvalDir (
    'bench_v55_sourcev4_slumbot_allstreet_' +
    'imitation_bbweight3_pure_fresh20k_20260726_loss_report.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $bbLossPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $standardLossPath -PathType Leaf)) {
    throw "Missing standard20k loss report: $standardLossPath"
}
if (-not (Test-Path -LiteralPath $bbLossPath -PathType Leaf)) {
    throw "Timed out waiting for BB-weighted20k loss report: $bbLossPath"
}
$standardLoss = Get-Content -LiteralPath $standardLossPath -Raw |
    ConvertFrom-Json
$bbLoss = Get-Content -LiteralPath $bbLossPath -Raw | ConvertFrom-Json
if ([int]$standardLoss.hands -ne 20000 -or [int]$bbLoss.hands -ne 20000) {
    throw 'Position distillation requires two complete 20k evidence sets'
}
$standardBb = @($standardLoss.position | Where-Object key -eq 'BB')[0]
$bbTeacherBb = @($bbLoss.position | Where-Object key -eq 'BB')[0]

$outputDir = Join-Path 'models' $OutputName
if (Test-Path -LiteralPath $outputDir) {
    throw "Position-distillation output already exists: $outputDir"
}

# Require the larger, completed sample to confirm that the proposed BB teacher
# actually improves the seat it is meant to teach.  A failed gate creates one
# compact discovery record and returns the GPU slot immediately.
$bbSeatGain = (
    [double]$bbTeacherBb.bb_per_100 - [double]$standardBb.bb_per_100
)
if ($bbSeatGain -lt 5.0) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
    [ordered]@{
        schema = 'cardpilot.discovery_experiment.v1'
        hypothesis = (
            'Distill the standard 10M SB policy and BB-weighted imitation BB ' +
            'policy into one position-conditioned pure network.'
        )
        source_checkpoint = $source
        source_checkpoint_sha256 = $sourceSha
        sb_teacher = $source
        bb_teacher = $bbTeacher
        bb_teacher_sha256 = $bbTeacherSha
        standard20k_bb_bb_per_100 = [double]$standardBb.bb_per_100
        bb_teacher20k_bb_bb_per_100 = [double]$bbTeacherBb.bb_per_100
        bb_seat_gain_bb_per_100 = $bbSeatGain
        new_training_hands = 0
        offline_decision_samples = 0
        decision = 'REJECT_BB_TEACHER_COMPLETED20K_SEAT_GATE'
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (
            Join-Path $outputDir 'experiment_record.json'
        ) -Encoding UTF8
    exit 0
}

$distillArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/distill_position_teachers.py',
    '--source-checkpoint', $source,
    '--sb-teacher', $source,
    '--bb-teacher', $bbTeacher,
    '--dump-dir', $standardEvalDir,
    '--dump-dir', $bbEvalDir,
    '--out-dir', $outputDir,
    '--obs-version', 'v4',
    '--raise-action-mapping', 'preflop_pot_fraction_v2',
    '--max-rows-per-actor', '300000',
    '--epochs', "$Epochs",
    '--batch-size', '2048',
    '--lr', "$LearningRate",
    '--weight-decay', '0.00001',
    '--teacher-temperature', '1',
    '--position-adapter-hidden', "$PositionAdapterHidden",
    '--val-fraction', '0.08',
    '--seed', "$Seed",
    '--device', 'cuda'
)
if ($TrainPolicyTrunk) {
    $distillArgs += '--train-policy-trunk'
}
& python @distillArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Position-teacher distillation failed'
}

$report = Get-Content -LiteralPath (
    Join-Path $outputDir 'report.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath $report.best_checkpoint).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$best = @(
    $report.history |
        Where-Object {
            [math]::Abs(
                [double]$_.selection_score -
                [double]$report.best_selection_score
            ) -lt 1e-12
        }
)[-1]
$baselineP0 = [double]$report.baseline.position.p0.argmax_agreement
$bestP0 = [double]$best.position.p0.argmax_agreement
$bestP1 = [double]$best.position.p1.argmax_agreement
$ready = (
    $candidateSha -ne $sourceSha -and
    $bestP0 -ge ($baselineP0 + 0.02) -and
    $bestP1 -ge 0.999 -and
    [double]$report.best_selection_score -gt
        [double]$report.baseline.selection_score
)
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The standard 10M policy retained the stronger completed-sample SB ' +
        'behavior while BB-weighted imitation produced a stronger BB seat. ' +
        'Distilling those position-specific neural teachers into one policy ' +
        'should retain both without an evaluator-side seat switch.'
    )
    material_change = if ($TrainPolicyTrunk) {
        (
            'Starting from the standard 10M policy, keep the critic frozen ' +
            'while optimizing the shared actor representation, policy heads ' +
            "and $PositionAdapterHidden-hidden position adapters against " +
            'both neural teachers: standard for position1 and BB-weighted ' +
            'for position0.'
        )
    } else {
        (
            'Starting from the standard 10M policy, freeze the shared trunk, ' +
            'critic and existing policy heads. Add and optimize ' +
            "$PositionAdapterHidden-hidden neural logit adapters inside the " +
            'network, conditioned on the observed HUNL seat feature: ' +
            'standard teacher for position1 and BB-weighted teacher for ' +
            'position0.'
        )
    }
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    sb_teacher = $source
    sb_teacher_sha256 = $sourceSha
    bb_teacher = $bbTeacher
    bb_teacher_sha256 = $bbTeacherSha
    standard20k_bb_bb_per_100 = [double]$standardBb.bb_per_100
    bb_teacher20k_bb_bb_per_100 = [double]$bbTeacherBb.bb_per_100
    bb_seat_gain_bb_per_100 = $bbSeatGain
    new_training_hands = 0
    inherited_lineage_training_hands = (
        [int64]$sourceRecord.candidate_total_hands
    )
    offline_decision_samples = (
        [int64]$report.ingest.combined_rows
    )
    baseline_bb_teacher_agreement = $baselineP0
    selected_bb_teacher_agreement = $bestP0
    selected_sb_teacher_agreement = $bestP1
    selected_epoch = [int]$best.epoch
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    position_adapter_hidden = $PositionAdapterHidden
    train_policy_trunk = [bool]$TrainPolicyTrunk
    decision = if ($ready) {
        'READY_FOR_PURE_FRESH5K'
    } else {
        'REJECT_HELDOUT_TEACHER_AGREEMENT_GATE'
    }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (
        Join-Path $outputDir 'experiment_record.json'
    ) -Encoding UTF8
exit 0
