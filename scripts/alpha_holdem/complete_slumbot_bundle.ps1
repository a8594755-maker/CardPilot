[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Candidate,
    [Parameter(Mandatory = $true)][string]$BundleDir,
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][int]$TargetHands,
    [Parameter(Mandatory = $true)][string]$RepairDir
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidateResolved = (Resolve-Path -LiteralPath $Candidate).Path
$bundleResolved = (Resolve-Path -LiteralPath $BundleDir).Path
$originalHandFiles = @(
    Get-ChildItem -LiteralPath $bundleResolved `
        -Filter "bench_v55_${Tag}_part*_hands.jsonl" -File |
        Sort-Object Name
)
if ($originalHandFiles.Count -eq 0) {
    throw "No original hand evidence found in $bundleResolved"
}
$originalHands = 0
foreach ($file in $originalHandFiles) {
    $originalHands += (
        Get-Content -LiteralPath $file.FullName | Measure-Object -Line
    ).Lines
}
if ($originalHands -gt $TargetHands) {
    throw "Original bundle has $originalHands hands, above target $TargetHands"
}
if ($originalHands -eq $TargetHands) {
    Write-Output "Bundle already exact: $originalHands/$TargetHands hands"
    exit 0
}

$missingHands = $TargetHands - $originalHands
if (Test-Path -LiteralPath $RepairDir) {
    $repairResolved = (Resolve-Path -LiteralPath $RepairDir).Path
    $repairArtifacts = @(Get-ChildItem -LiteralPath $repairResolved -Force)
} else {
    New-Item -ItemType Directory -Path $RepairDir | Out-Null
    $repairResolved = (Resolve-Path -LiteralPath $RepairDir).Path
    $repairArtifacts = @()
}

$repairTag = "${Tag}_repair${missingHands}"
if ($repairArtifacts.Count -eq 0) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
        -ModelPath $candidateResolved `
        -Tag $repairTag `
        -HandsPerSession $missingHands `
        -Sessions 1 `
        -OutputDir $repairResolved `
        -PolicyMode greedy `
        -Strategy model
    if ($LASTEXITCODE -ne 0) {
        throw "Slumbot supplement for $missingHands hands failed"
    }
}

$repairHandFiles = @(
    Get-ChildItem -LiteralPath $repairResolved -Filter '*_hands.jsonl' -File
)
$repairDumpFiles = @(
    Get-ChildItem -LiteralPath $repairResolved -Filter '*_dump.jsonl' -File
)
$repairLogFiles = @(
    Get-ChildItem -LiteralPath $repairResolved -Filter '*.log' -File |
        Where-Object { $_.Name -notmatch '_err\.log$' }
)
$repairHands = 0
foreach ($file in $repairHandFiles) {
    $repairHands += (
        Get-Content -LiteralPath $file.FullName | Measure-Object -Line
    ).Lines
}
if ($repairHands -ne $missingHands) {
    throw "Repair has $repairHands hands; expected exactly $missingHands"
}
if ($repairDumpFiles.Count -eq 0 -or $repairLogFiles.Count -eq 0) {
    throw 'Repair is missing decision-dump or log evidence'
}

$derivedArtifacts = @(
    "bench_v55_${Tag}_summary.txt",
    "bench_v55_${Tag}_ci_summary.json",
    "bench_v55_${Tag}_ci_summary.txt",
    "bench_v55_${Tag}_promotion_gate.json",
    "bench_v55_${Tag}_promotion_gate.md",
    "bench_v55_${Tag}_promotion_gate.txt",
    "bench_v55_${Tag}_dump_analysis.txt",
    "bench_v55_${Tag}_loss_report.json",
    "bench_v55_${Tag}_loss_report.md",
    "bench_v55_${Tag}_loss_report.txt"
)
foreach ($name in $derivedArtifacts) {
    $sourcePath = Join-Path $bundleResolved $name
    if (Test-Path -LiteralPath $sourcePath) {
        $preservedPath = "$sourcePath.incomplete${originalHands}"
        if (-not (Test-Path -LiteralPath $preservedPath)) {
            Copy-Item -LiteralPath $sourcePath -Destination $preservedPath
        }
    }
}

$allHandFiles = @($originalHandFiles.FullName) + @($repairHandFiles.FullName)
$ciSummary = Join-Path $bundleResolved "bench_v55_${Tag}_ci_summary.json"
$ciArgs = @('scripts/alpha_holdem/slumbot_ci_from_hands.py') +
    $allHandFiles + @('--out-json', $ciSummary)
$ciResult = & python -X utf8 @ciArgs 2>&1
$ciExitCode = $LASTEXITCODE
$ciText = $ciResult -join "`n"
$ciText | Out-File -FilePath (
    Join-Path $bundleResolved "bench_v55_${Tag}_ci_summary.txt"
) -Encoding utf8
if ($ciExitCode -ne 0 -or -not (Test-Path -LiteralPath $ciSummary)) {
    throw "Exact CI rebuild failed: $ciText"
}
$ci = Get-Content -LiteralPath $ciSummary -Raw | ConvertFrom-Json
if ([int]$ci.hands -ne $TargetHands) {
    throw "Rebuilt CI has $($ci.hands) hands; expected $TargetHands"
}

$promotionJson = Join-Path $bundleResolved `
    "bench_v55_${Tag}_promotion_gate.json"
$promotionMd = Join-Path $bundleResolved `
    "bench_v55_${Tag}_promotion_gate.md"
$promotionResult = & python -X utf8 `
    scripts/alpha_holdem/v5_slumbot_promotion_gate.py `
    --checkpoint $candidateResolved `
    --ci-json $ciSummary `
    --out-json $promotionJson `
    --out-md $promotionMd 2>&1
$promotionExitCode = $LASTEXITCODE
$promotionText = $promotionResult -join "`n"
$promotionText | Out-File -FilePath (
    Join-Path $bundleResolved "bench_v55_${Tag}_promotion_gate.txt"
) -Encoding utf8
if ($promotionExitCode -ne 0 -or -not (Test-Path -LiteralPath $promotionJson)) {
    throw "Promotion-gate rebuild failed: $promotionText"
}

$originalDumpFiles = @(
    Get-ChildItem -LiteralPath $bundleResolved `
        -Filter "bench_v55_${Tag}_part*_dump.jsonl" -File |
        Sort-Object Name
)
$allDumpFiles = @($originalDumpFiles.FullName) + @($repairDumpFiles.FullName)
$dumpResult = & python -X utf8 scripts/alpha_holdem/analyze_dump.py `
    --label $Tag `
    --dumps @allDumpFiles 2>&1
$dumpExitCode = $LASTEXITCODE
$dumpText = $dumpResult -join "`n"
$dumpText | Out-File -FilePath (
    Join-Path $bundleResolved "bench_v55_${Tag}_dump_analysis.txt"
) -Encoding utf8
if ($dumpExitCode -ne 0) {
    throw "Decision-dump analysis failed: $dumpText"
}

$lossJson = Join-Path $bundleResolved "bench_v55_${Tag}_loss_report.json"
$lossMd = Join-Path $bundleResolved "bench_v55_${Tag}_loss_report.md"
$lossArgs = @(
    'scripts/alpha_holdem/v5_slumbot_loss_report.py',
    '--label', $Tag,
    '--dumps'
) + $allDumpFiles + @(
    '--out-json', $lossJson,
    '--out-md', $lossMd
)
$lossResult = & python -X utf8 @lossArgs 2>&1
$lossExitCode = $LASTEXITCODE
$lossText = $lossResult -join "`n"
$lossText | Out-File -FilePath (
    Join-Path $bundleResolved "bench_v55_${Tag}_loss_report.txt"
) -Encoding utf8
if (
    $lossExitCode -ne 0 -or
    -not (Test-Path -LiteralPath $lossJson) -or
    -not (Test-Path -LiteralPath $lossMd)
) {
    throw "Loss-report rebuild failed: $lossText"
}

$originalLogFiles = @(
    Get-ChildItem -LiteralPath $bundleResolved `
        -Filter "bench_v55_${Tag}_part*.log" -File |
        Where-Object { $_.Name -notmatch '_err\.log$' } |
        Sort-Object Name
)
$allLogFiles = @($originalLogFiles.FullName) + @($repairLogFiles.FullName)
$logResult = & python -X utf8 `
    scripts/alpha_holdem/combine_slumbot_logs.py @allLogFiles 2>&1
$logExitCode = $LASTEXITCODE
$logText = $logResult -join "`n"
$logText | Out-File -FilePath (
    Join-Path $bundleResolved "bench_v55_${Tag}_summary.txt"
) -Encoding utf8
if ($logExitCode -ne 0) {
    throw "Log summary rebuild failed: $logText"
}

Write-Output (
    "Completed exact bundle: hands=$($ci.hands) " +
    "bb/100=$($ci.bb_per_100) " +
    "CI95=[$($ci.lower_bound_bb_per_100)," +
    "$($ci.upper_bound_bb_per_100)]"
)
