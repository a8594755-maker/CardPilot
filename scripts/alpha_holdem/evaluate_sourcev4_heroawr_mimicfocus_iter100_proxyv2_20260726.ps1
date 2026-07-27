$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runDir = 'models\sourcev4_heroawr_slumbot_mimicfocus_10m_20260726'
$mimic = (
    'models\sourcev4_slumbot_history500k_postflop_imitation_' +
    'fullnet_20260726\best.pt'
)
$source = (
    'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
    'selected.pt'
)
$deadline = (Get-Date).AddHours(1)
$candidate = $null
while ((Get-Date) -lt $deadline) {
    $matches = @(
        Get-ChildItem -Path (
            Join-Path $runDir (
                'checkpoints\checkpoint_iter000100_*.pt'
            )
        ) -File -ErrorAction SilentlyContinue
    )
    if ($matches.Count -eq 1) {
        $candidate = $matches[0].FullName
        break
    }
    Start-Sleep -Seconds 20
}
if ($null -eq $candidate) {
    throw 'Mimic-focus iteration-100 checkpoint did not appear'
}

$outDir = Join-Path $runDir 'proxyv2_curve_iter100'
New-Item -ItemType Directory -Path $outDir | Out-Null
$rows = foreach ($entry in ([ordered]@{
    source = $source
    iter100 = $candidate
}).GetEnumerator()) {
    $json = Join-Path $outDir "$($entry.Key).json"
    $probeOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 3000 `
        --checkpoint-opponent $mimic `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode sample `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260812 `
        --policy-mode greedy `
        --out-json $json `
        --out-md (Join-Path $outDir "$($entry.Key).md")
    $probeOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Mimic-focus proxy-v2 probe failed: $($entry.Key)"
    }
    $probe = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
    [pscustomobject]@{
        name = $entry.Key
        checkpoint = (Resolve-Path -LiteralPath $entry.Value).Path
        checkpoint_sha256 = (
            Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        total_hands = [int64]$probe.checkpoint.total_hands
        proxy_v2_bb_per_100 = [double](
            ($probe.results | Measure-Object -Property bb100 -Average).Average
        )
        results = $probe.results
    }
}
$sourceRow = $rows | Where-Object name -eq 'source'
$candidateRow = $rows | Where-Object name -eq 'iter100'
[ordered]@{
    schema = 'cardpilot.internal_learning_curve.v1'
    opponent = (Resolve-Path -LiteralPath $mimic).Path
    opponent_sha256 = (
        Get-FileHash -LiteralPath $mimic -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    hands_per_match = 3000
    seed = 20260812
    rows = $rows
    delta_vs_source_bb_per_100 = (
        [double]$candidateRow.proxy_v2_bb_per_100 -
        [double]$sourceRow.proxy_v2_bb_per_100
    )
    interpretation = (
        'High-fidelity local opponent learning-curve evidence only; not ' +
        'Slumbot strength evidence.'
    )
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $outDir 'summary.json') `
        -Encoding UTF8
exit 0
