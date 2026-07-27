$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$deadline = [datetime]'2026-08-01T23:30:00'
$standard32 = (
    'models\frozen_candidates\' +
    'b5a4cc970e206303280278425bd99684ebdab80c2dba07575b9bb7deb602f78c\' +
    'policy.pt'
)
$standard32 = (Resolve-Path -LiteralPath $standard32).Path
$standard32Sha = (
    Get-FileHash -LiteralPath $standard32 -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $standard32Sha -ne
    'b5a4cc970e206303280278425bd99684ebdab80c2dba07575b9bb7deb602f78c'
) {
    throw 'Standard32 frozen source hash mismatch'
}

function Wait-CandidateRecord {
    param(
        [Parameter(Mandatory = $true)][string]$RecordPath,
        [Parameter(Mandatory = $true)][string]$Label
    )
    do {
        if (Test-Path -LiteralPath $RecordPath -PathType Leaf) {
            $record = Get-Content -LiteralPath $RecordPath -Raw |
                ConvertFrom-Json
            if (
                -not [string]::IsNullOrWhiteSpace(
                    [string]$record.candidate_checkpoint
                ) -and
                -not [string]::IsNullOrWhiteSpace(
                    [string]$record.candidate_checkpoint_sha256
                ) -and
                (Test-Path -LiteralPath (
                    [string]$record.candidate_checkpoint
                ) -PathType Leaf)
            ) {
                $candidate = (
                    Resolve-Path -LiteralPath (
                        [string]$record.candidate_checkpoint
                    )
                ).Path
                $candidateSha = (
                    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
                ).Hash.ToLowerInvariant()
                if (
                    $candidateSha -ne
                    [string]$record.candidate_checkpoint_sha256
                ) {
                    throw "$Label candidate hash mismatch"
                }
                return [pscustomobject]@{
                    Record = $record
                    Path = $candidate
                    Sha256 = $candidateSha
                }
            }
            if ([string]$record.status -eq 'FAILED') {
                throw "$Label training failed"
            }
        }
        Start-Sleep -Seconds 20
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Label candidate"
}

function New-DualCandidate {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$SbPath,
        [Parameter(Mandatory = $true)][string]$SbSha,
        [Parameter(Mandatory = $true)][string]$SbLineage,
        [Parameter(Mandatory = $true)][string]$BbPath,
        [Parameter(Mandatory = $true)][string]$BbSha,
        [Parameter(Mandatory = $true)][string]$BbLineage
    )
    $outDir = Join-Path 'models' $Name
    $policy = Join-Path $outDir 'policy.pt'
    if (Test-Path -LiteralPath $outDir) {
        $existingPolicy = Join-Path $outDir 'policy.pt'
        $existingVerification = Join-Path $outDir 'verification.json'
        if (
            (Test-Path -LiteralPath $existingPolicy -PathType Leaf) -and
            (Test-Path -LiteralPath $existingVerification -PathType Leaf)
        ) {
            $verification = (
                Get-Content -LiteralPath $existingVerification -Raw |
                    ConvertFrom-Json
            )
            if ([bool]$verification.passed) {
                Write-Output "$Name already packaged and verified"
                return
            }
        }
        throw "$Name has an incomplete existing output"
    }

    & python -X utf8 `
        'scripts/alpha_holdem/build_dual_seat_v2_checkpoint.py' `
        --sb-checkpoint $SbPath `
        --bb-checkpoint $BbPath `
        --out $policy
    if ($LASTEXITCODE -ne 0) {
        throw "$Name packaging failed"
    }
    $policy = (Resolve-Path -LiteralPath $policy).Path
    $verificationPath = Join-Path $outDir 'verification.json'
    & python -X utf8 `
        'scripts/alpha_holdem/verify_dual_seat_v2_checkpoint.py' `
        --dual-checkpoint $policy `
        --sb-checkpoint $SbPath `
        --bb-checkpoint $BbPath `
        --rows 512 `
        --batch-size 64 `
        --seed 20260727 `
        --out-json $verificationPath
    if ($LASTEXITCODE -ne 0) {
        throw "$Name verification failed"
    }
    $verification = Get-Content -LiteralPath $verificationPath -Raw |
        ConvertFrom-Json
    if (-not [bool]$verification.passed) {
        throw "$Name verification did not pass"
    }
    $policySha = (
        Get-FileHash -LiteralPath $policy -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    $record = [ordered]@{
        schema = 'cardpilot.discovery_experiment.v1'
        run_id = $Name
        status = 'PACKAGED_AWAITING_LOADER_AND_FRESH_SCREEN'
        hypothesis = (
            'Combining independently trained seat specialists inside one ' +
            'pure network can preserve the strongest learned actor for each ' +
            'public seat without evaluator-side action overrides.'
        )
        material_change = (
            'Package the frozen SB and BB actor weights in dual_seat_v2; ' +
            'the public seat observation selects the actor inside forward.'
        )
        candidate_checkpoint = $policy
        candidate_checkpoint_sha256 = $policySha
        architecture = 'dual_seat_v2'
        sb_component = [ordered]@{
            checkpoint = $SbPath
            sha256 = $SbSha
            lineage = $SbLineage
        }
        bb_component = [ordered]@{
            checkpoint = $BbPath
            sha256 = $BbSha
            lineage = $BbLineage
        }
        component_training_hands_are_separate = $true
        policy_inference_classification = 'PURE_TRAINED'
        training_data_classification = 'SLUMBOT_ASSISTED'
        evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
        pure_weight_policy = $true
        evaluator_side_overrides = $false
        verification = (
            (Resolve-Path -LiteralPath $verificationPath).Path
        )
        random_forward_rows_verified = 512
        loader_integration_deferred_until_dual_v1_exact20k_finishes = $true
        decision = 'AWAIT_FRESH5K'
        recorded_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $record | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath (
            Join-Path $outDir 'experiment_record.json'
        ) -Encoding UTF8
}

$bbRecordPath = (
    'models\sourcev4_standard10_bb_only_position_adapter10m_20260727\' +
    'experiment_record.json'
)
$bb = Wait-CandidateRecord `
    -RecordPath $bbRecordPath `
    -Label 'BB-only position adapter'

New-DualCandidate `
    -Name 'dual_seat_v2_standard32sb_bbpos10m_20260727' `
    -SbPath $standard32 `
    -SbSha $standard32Sha `
    -SbLineage 'sourcev4_standard32_20260727' `
    -BbPath $bb.Path `
    -BbSha $bb.Sha256 `
    -BbLineage 'sourcev4_standard10_bb_only_position_adapter10m_20260727'

$sbRecordPath = (
    'models\sourcev4_standard10_sb_only_scaled_position_adapter10m_20260727\' +
    'experiment_record.json'
)
$sb = Wait-CandidateRecord `
    -RecordPath $sbRecordPath `
    -Label 'SB-only scaled position adapter'

New-DualCandidate `
    -Name 'dual_seat_v2_sbpos10m_bbpos10m_20260727' `
    -SbPath $sb.Path `
    -SbSha $sb.Sha256 `
    -SbLineage 'sourcev4_standard10_sb_only_scaled_position_adapter10m_20260727' `
    -BbPath $bb.Path `
    -BbSha $bb.Sha256 `
    -BbLineage 'sourcev4_standard10_bb_only_position_adapter10m_20260727'
