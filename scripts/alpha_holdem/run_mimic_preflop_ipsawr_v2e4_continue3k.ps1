$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$checkpoint = "models/slumbot_mimic_preflop_ipsawr_v2_20260725/epoch_4.pt"
$screenDir = "models/slumbot_mimic_preflop_ipsawr_v2e4_quick2k_20260725"
$runDir = "models/slumbot_mimic_preflop_ipsawr_v2e4_continue3k_20260725"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le 12; $part++) {
    $stem = "bench_v55_mimic_preflop_ipsawr_v2e4_cont_part$part"
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

& python scripts/alpha_holdem/slumbot_ci_from_hands.py `
    "$screenDir/*_hands.jsonl" `
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/combined5k_ci.json"
exit $LASTEXITCODE
