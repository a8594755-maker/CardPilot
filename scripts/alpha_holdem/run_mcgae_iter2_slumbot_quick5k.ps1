$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$checkpoint = "models/slumbot_br_mcgae_v12_524k_20260725/checkpoints/checkpoint_iter000002_hands000000065561.pt"
$runDir = "models/slumbot_br_mcgae_v12_iter2_quick5k_20260725"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le 20; $part++) {
    $stem = "bench_v55_mcgae_v12_iter2_q5k_part$part"
    $arguments = @(
        "-X", "utf8", "-u",
        "scripts/alpha_holdem/play_slumbot.py",
        "--strategy", "model",
        "--hands", "250",
        "--device", "cpu",
        "--policy-mode", "greedy",
        "--temperature", "1",
        "--preflop-epsilon", "0.3",
        "--epsilon-streets", "0",
        "--guarded-allin-max-spr", "2",
        "--guarded-allin-min-prob", "0.65",
        "--callguard-min-prob", "0.2",
        "--callguard-ratio", "0.65",
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

$failures = @()
foreach ($process in $processes) {
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        $failures += @{ pid = $process.Id; exit_code = $process.ExitCode }
    }
}
if ($failures.Count -gt 0) {
    $failures | ConvertTo-Json | Write-Error
    exit 1
}

& python scripts/alpha_holdem/slumbot_ci_from_hands.py `
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/final_ci.json"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
