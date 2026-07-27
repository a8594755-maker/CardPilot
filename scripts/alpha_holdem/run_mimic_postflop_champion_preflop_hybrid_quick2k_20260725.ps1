$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$postflop = "models/slumbot_br_preflopv2_mimic_postflop_riverpairfold_v2_20260725/latest.pt"
$preflop = "models/slumbot_br_stage4_pokerskill_sb_v1_20260725/latest.pt"
$runDir = "models/slumbot_br_mimic_postflop_champion_preflop_hybrid_quick2k_20260725"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le 8; $part++) {
    $stem = "mimic_postflop_champion_preflop_part$part"
    $arguments = @(
        "-X", "utf8", "-u",
        "scripts/alpha_holdem/play_slumbot.py",
        "--strategy", "postflop_hybrid",
        "--hands", "250",
        "--device", "cpu",
        "--policy-mode", "greedy",
        "--result-json", "$runDir/${stem}.json",
        "--hand-results-jsonl", "$runDir/${stem}_hands.jsonl",
        "--dump-slumbot", "$runDir/${stem}_dump.jsonl",
        "--model", $postflop,
        "--fallback-model", $preflop
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
if ($successfulHands -lt 1900) {
    throw "Postflop hybrid quick2k produced only $successfulHands hands"
}

& python scripts/alpha_holdem/slumbot_ci_from_hands.py `
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/final_ci.json"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
