$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$checkpoint = "models/slumbot_br_stage4_pokerskill_sb_bb_riverpairfold_v2_20260725/latest.pt"
$quickDir = "models/slumbot_br_stage4_pokerskill_sb_bb_riverpairfold_v2_quick2k_20260725"
$runDir = "models/slumbot_br_stage4_pokerskill_sb_bb_riverpairfold_v2_continue3k_20260725"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le 12; $part++) {
    $stem = "pokerskill_sb_bb_riverpairfold_v2_cont_part$part"
    $arguments = @(
        "-X", "utf8", "-u",
        "scripts/alpha_holdem/play_slumbot.py",
        "--strategy", "model",
        "--hands", "250",
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
    Where-Object { $_.Name -ne "combined5k_ci.json" })
$successfulHands = 0
foreach ($resultFile in $resultFiles) {
    $result = Get-Content -LiteralPath $resultFile.FullName -Raw |
        ConvertFrom-Json
    $successfulHands += [int]$result.successful_hands
}
if ($successfulHands -lt 2850) {
    throw "River pair-fold continuation produced only $successfulHands hands"
}

& python scripts/alpha_holdem/slumbot_ci_from_hands.py `
    "$quickDir/*_hands.jsonl" `
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/combined5k_ci.json"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
