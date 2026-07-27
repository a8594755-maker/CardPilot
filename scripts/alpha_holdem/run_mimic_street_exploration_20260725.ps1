param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 3)]
    [int]$Street,
    [ValidateRange(1, 64)]
    [int]$Parts = 28,
    [ValidateRange(1, 2000)]
    [int]$HandsPerPart = 250,
    [ValidateRange(0.01, 1.0)]
    [double]$Epsilon = 0.30
)

$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$checkpoint = "models/slumbot_imitation_stage4_onpolicy_v2_20260725/best.pt"
$epsilonLabel = [int][math]::Round(100.0 * $Epsilon)
$runId = "slumbot_mimic_street${Street}_epsilon${epsilonLabel}_explore_20260725"
$runDir = Join-Path "models" $runId
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$processes = @()
for ($part = 1; $part -le $Parts; $part++) {
    $stem = "${runId}_part$part"
    $arguments = @(
        "-X", "utf8", "-u",
        "scripts/alpha_holdem/play_slumbot.py",
        "--strategy", "model",
        "--hands", "$HandsPerPart",
        "--device", "cpu",
        "--policy-mode", "street-epsilon",
        "--epsilon-streets", "$Street",
        "--preflop-epsilon", "$Epsilon",
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
    "$runDir/*_hands.jsonl" `
    --out-json "$runDir/exploration_ci.json"
exit $LASTEXITCODE
