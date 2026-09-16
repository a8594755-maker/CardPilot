$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-4m-scale-20260904'
$parentExperiment = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
$python = (Get-Command python).Source
$anchors = @(
    'standard10=models/baseline/standard10/latest.pt',
    'cfr4=research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt',
    'legacy_iter16=research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt',
    'legacy_mixed65k=research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt'
)

$auditOut = "$experiment/training_audit.json"
if (Test-Path -LiteralPath $auditOut) {
    $existingAudit = Get-Content -Raw -LiteralPath $auditOut | ConvertFrom-Json
    if (-not $existingAudit.passed) {
        throw "Existing training audit is not passing: $auditOut"
    }
    Write-Output "Using existing passing training audit: $auditOut"
} else {
    $auditArguments = @(
        'scripts/alpha_holdem/audit_v6_static_current_kl_1m_training.py',
        '--experiment-dir', $experiment,
        '--base', 'models/baseline/standard10/latest.pt',
        '--min-environment-hands', '4194304'
    )
    foreach ($iteration in @(448, 512, 576, 640, 704, 768, 832)) {
        $auditArguments += @('--expected-archive-iteration', [string]$iteration)
    }
    $auditArguments += @(
        '--schema', 'cardpilot.static_current_kl_4m_training_audit.v1',
        '--out', $auditOut
    )
    & $python @auditArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Training audit failed with exit code $LASTEXITCODE"
    }
}

foreach ($seed in 1..3) {
    $control = "$parentExperiment/seed$seed/latest.pt"
    $treatment = "$experiment/seed$seed/latest.pt"
    $outDir = "$experiment/eval_seed$seed"
    if (Test-Path -LiteralPath $outDir) {
        throw "Refusing to overwrite evaluation directory: $outDir"
    }
    $arguments = @(
        'scripts/alpha_holdem/v6_public_opponent_matched_eval.py',
        '--control', $control,
        '--treatment', $treatment
    )
    foreach ($anchor in $anchors) {
        $arguments += @('--anchor', $anchor)
    }
    $arguments += @(
        '--pairs-per-anchor', '2048',
        '--seed', [string](20263280 + $seed),
        '--device', 'cuda',
        '--out-dir', $outDir
    )
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Seed $seed evaluation failed with exit code $LASTEXITCODE"
    }
}

$jobs = @()
foreach ($seed in 1..3) {
    $treatment = (Resolve-Path -LiteralPath "$experiment/seed$seed/latest.pt").Path
    $outDir = "$experiment/drift_seed$seed"
    if (Test-Path -LiteralPath $outDir) {
        throw "Refusing to overwrite drift directory: $outDir"
    }
    $arguments = @(
        'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py',
        '--parent', 'models/baseline/standard10/latest.pt',
        '--parent-sha256', '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
        '--treatment', $treatment,
        '--out-dir', $outDir,
        '--states', '20000',
        '--seed', [string](20263290 + $seed),
        '--device', 'cuda',
        '--batch-size', '1024',
        '--source-tv-max', '1',
        '--greedy-disagreement-max', '1'
    )
    $jobs += Start-Job -ScriptBlock {
        param($Repo, $Python, $Arguments)
        Set-Location -LiteralPath $Repo
        & $Python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Drift audit failed with exit code $LASTEXITCODE"
        }
    } -ArgumentList (Get-Location).Path, $python, (,$arguments)
}

$jobs | Wait-Job | Out-Null
$failed = @($jobs | Where-Object State -ne 'Completed')
$jobs | Receive-Job
if ($failed.Count -gt 0) {
    $failed | Format-List Id, State, ChildJobs
    throw "$($failed.Count) drift audit job(s) failed"
}

& $python scripts/alpha_holdem/aggregate_v6_static_current_kl_1m.py `
    --experiment-dir $experiment `
    --prior-dir research/experiments/v6-static-current-kl-262k-scale-20260903 `
    --prior-dir research/experiments/v6-static-current-kl-262k-fresh-confirmation-20260903 `
    --prior-dir research/experiments/v6-static-current-kl-1m-scale-20260903 `
    --prior-dir research/experiments/v6-static-current-kl-2m-scale-20260904 `
    --expected-prior-raw-rows 122880 `
    --eval-seed-base 20263280 `
    --drift-seed-base 20263290 `
    --scale-label 4M `
    --schema cardpilot.static_current_kl_4m_aggregate.v1 `
    --breadth-informational-only `
    --require-positive-combined `
    --require-improved-breadth `
    --out "$experiment/aggregate.json"
if ($LASTEXITCODE -ne 0) {
    throw "Aggregation failed with exit code $LASTEXITCODE"
}
