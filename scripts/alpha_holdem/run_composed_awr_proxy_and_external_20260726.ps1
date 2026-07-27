$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidateDir = 'models\sourcev4_composed_preflopformal100k_e5_postflopawrformal100k_e1_20260726'
$candidate = Join-Path $candidateDir 'latest.pt'
$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$proxyResult = Join-Path $candidateDir 'proxy5000.json'
$proxyMarkdown = Join-Path $candidateDir 'proxy5000.md'

& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 5000 `
    --opponents aggressive `
    --checkpoint-opponent $proxy `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode greedy `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260751 `
    --policy-mode greedy `
    --out-json $proxyResult `
    --out-md $proxyMarkdown
if ($LASTEXITCODE -ne 0) {
    throw 'Composed AWR proxy evaluation failed'
}

$result = Get-Content -LiteralPath $proxyResult -Raw | ConvertFrom-Json
$bb100 = [double]$result.results[0].bb100
if ($bb100 -le 0) {
    [PSCustomObject]@{
        status = 'PROXY_NONPOSITIVE_NO_EXTERNAL'
        bb100 = $bb100
        ci95 = [double]$result.results[0].ci95_bb100
    } |
        ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $candidateDir 'external_decision.json') -Encoding UTF8
    exit 0
}

$externalDir = 'models\bench_sourcev4_composed_preflopformal100k_e5_postflopawrformal100k_e1_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
[PSCustomObject]@{
    status = 'PROXY_POSITIVE_EXTERNAL_LAUNCHED'
    bb100 = $bb100
    ci95 = [double]$result.results[0].ci95_bb100
} |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $candidateDir 'external_decision.json') -Encoding UTF8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_composed_preflopformal100k_e5_postflopawrformal100k_e1_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
