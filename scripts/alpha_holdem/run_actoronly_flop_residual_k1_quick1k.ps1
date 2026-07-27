$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$checkpoint = "models/actoronly_flop_residual_awr_k1_v1_20260725/best.pt"
$runDir = "models/actoronly_flop_residual_awr_k1_quick1k_20260725"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le 8; $part++) {
    $stem = "bench_v55_actoronly_flop_residual_k1_part$part"
    $arguments = @(
        "-X", "utf8", "-u",
        "scripts/alpha_holdem/play_slumbot.py",
        "--strategy", "model",
        "--hands", "125",
        "--device", "cpu",
        "--policy-mode", "greedy",
        "--result-json", "$runDir/${stem}.json",
        "--hand-results-jsonl", "$runDir/${stem}_hands.jsonl",
        "--dump-slumbot", "$runDir/${stem}_dump.jsonl",
        "--model", $checkpoint
    )
    $processes += Start-Process -FilePath python `
        -ArgumentList $arguments `
        -WorkingDirectory $repo `
        -RedirectStandardOutput "$repo/$runDir/${stem}.stdout.log" `
        -RedirectStandardError "$repo/$runDir/${stem}.stderr.log" `
        -WindowStyle Hidden `
        -PassThru
}

foreach ($process in $processes) {
    $process.WaitForExit()
}

$resultFiles = @(Get-ChildItem -LiteralPath $runDir -Filter "*.json" |
    Where-Object { $_.Name -ne "final_ci.json" })
$successfulHands = 0
foreach ($resultFile in $resultFiles) {
    $result = Get-Content -LiteralPath $resultFile.FullName -Raw |
        ConvertFrom-Json
    $successfulHands += [int]$result.successful_hands
}
if ($successfulHands -lt 950) {
    throw "actor-only flop residual quick1k produced only $successfulHands hands"
}

& python scripts/alpha_holdem/slumbot_ci_from_hands.py `
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/final_ci.json"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
