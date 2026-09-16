$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-262k-scale-20260903'
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
    & $python scripts/alpha_holdem/audit_v6_static_current_kl_262k_training.py `
        --experiment-dir $experiment `
        --base models/baseline/standard10/latest.pt `
        --out $auditOut
    if ($LASTEXITCODE -ne 0) {
        throw "Training audit failed with exit code $LASTEXITCODE"
    }
}

foreach ($seed in 1..3) {
    $control = "research/experiments/v6-nashpg-moving-reference-geometric-20260903/static_seed$seed/latest.pt"
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
        '--seed', [string](20263040 + $seed),
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
        '--seed', [string](20263050 + $seed),
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
