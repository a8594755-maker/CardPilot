$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-nashpg-moving-reference-geometric-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$anchors = @(
    '--anchor', 'standard10=models/baseline/standard10/latest.pt',
    '--anchor', 'cfr4=research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt',
    '--anchor', 'legacy_iter16=research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt',
    '--anchor', 'legacy_mixed65k=research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt'
)

foreach ($seed in 1..3) {
    $staticRun = "$experiment/static_seed$seed"
    $movingRun = "$experiment/moving_seed$seed"
    $staticEarlyFiles = @(Get-ChildItem -LiteralPath "$staticRun/checkpoints" -Filter 'checkpoint_iter000004_hands*.pt')
    $movingEarlyFiles = @(Get-ChildItem -LiteralPath "$movingRun/checkpoints" -Filter 'checkpoint_iter000004_hands*.pt')
    if ($staticEarlyFiles.Count -ne 1 -or $movingEarlyFiles.Count -ne 1) {
        throw "Seed $seed does not have exactly one iteration-4 archive per arm"
    }
    $staticEarly = $staticEarlyFiles[0].FullName
    $movingEarly = $movingEarlyFiles[0].FullName
    $staticFinal = (Resolve-Path -LiteralPath "$staticRun/latest.pt").Path
    $movingFinal = (Resolve-Path -LiteralPath "$movingRun/latest.pt").Path
    $evalSeed = 20263010 + $seed
    $comparisons = @(
        @{ Name = 'static_slope'; Control = $staticEarly; Treatment = $staticFinal },
        @{ Name = 'moving_slope'; Control = $movingEarly; Treatment = $movingFinal },
        @{ Name = 'early_delta'; Control = $staticEarly; Treatment = $movingEarly },
        @{ Name = 'final_delta'; Control = $staticFinal; Treatment = $movingFinal }
    )
    foreach ($comparison in $comparisons) {
        $outDir = "$experiment/eval_seed$seed`_$($comparison.Name)"
        if (Test-Path -LiteralPath $outDir) {
            throw "Refusing to overwrite evaluation directory: $outDir"
        }
        $arguments = @(
            'scripts/alpha_holdem/v6_public_opponent_matched_eval.py',
            '--control', $comparison.Control,
            '--treatment', $comparison.Treatment
        ) + $anchors + @(
            '--pairs-per-anchor', '2048',
            '--seed', [string]$evalSeed,
            '--device', 'cuda',
            '--out-dir', $outDir
        )
        Write-Host "Evaluating seed$seed $($comparison.Name)"
        & python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Evaluation seed$seed $($comparison.Name) failed"
        }
    }

    foreach ($arm in @('static', 'moving')) {
        $checkpoint = (Resolve-Path -LiteralPath "$experiment/$arm`_seed$seed/latest.pt").Path
        $outDir = "$experiment/drift_$arm`_seed$seed"
        if (Test-Path -LiteralPath $outDir) {
            throw "Refusing to overwrite drift directory: $outDir"
        }
        $driftSeed = 20263030 + (($seed - 1) * 2) + $(if ($arm -eq 'moving') { 2 } else { 1 })
        & python scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py `
            --parent $standard10 `
            --parent-sha256 91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428 `
            --treatment $checkpoint `
            --out-dir $outDir `
            --states 20000 `
            --seed $driftSeed `
            --device cuda `
            --batch-size 1024 `
            --source-tv-max 1 `
            --greedy-disagreement-max 1
        if ($LASTEXITCODE -ne 0) {
            throw "Drift audit $arm seed$seed failed"
        }
    }
}
