$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-262k-fresh-confirmation-20260903'
$python = (Get-Command python).Source
$anchors = @(
    'standard10=models/baseline/standard10/latest.pt',
    'cfr4=research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt',
    'legacy_iter16=research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt',
    'legacy_mixed65k=research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt'
)

foreach ($seed in 1..3) {
    $control = "research/experiments/v6-nashpg-moving-reference-geometric-20260903/static_seed$seed/latest.pt"
    $treatment = "research/experiments/v6-static-current-kl-262k-scale-20260903/seed$seed/latest.pt"
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
        '--pairs-per-anchor', '4096',
        '--seed', [string](20263060 + $seed),
        '--device', 'cuda',
        '--out-dir', $outDir
    )
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Seed $seed evaluation failed with exit code $LASTEXITCODE"
    }
}
