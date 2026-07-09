# bench_v55_slumbot.ps1 - Run 12 parallel Slumbot sessions on V5.5 ckpt and aggregate.
#
# Each session plays 1700 hands; 12 in parallel = 20,400 hands total (~50 min wall).
# CI ~ +/-21 bb/100, same setup as V4's reference benchmark.
#
# Usage:
#   .\scripts\alpha_holdem\bench_v55_slumbot.ps1 -ModelPath models\alpha_holdem_v55_iter600.pt -Tag v55_iter600
# Output:
#   models\bench_v55_<tag>_part{1..12}.log + bench_v55_<tag>_summary.txt

param(
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$Tag,
    [int]$HandsPerSession = 1700,
    [int]$Sessions = 12,
    [string]$OutputDir = 'C:\Users\a8594\CardPilot\models',
    [string]$RunDir = '',
    [string]$PythonExe = '',
    [switch]$Sample,
    [ValidateSet('greedy','greedy-guarded','preflop-callguard','sample','guarded','preflop-mixed')][string]$PolicyMode = 'greedy',
    [double]$Temperature = 1.0,
    [double]$GuardedAllinMaxSpr = 2.0,
    [double]$GuardedAllinMinProb = 0.65,
    [double]$CallguardMinProb = 0.20,
    [double]$CallguardRatio = 0.65,
    [switch]$CallguardIncludeOpen
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

if (-not (Test-Path $ModelPath)) {
    Write-Host "ERROR: $ModelPath not found"; exit 1
}

function Resolve-BenchPython {
    param([string]$RequestedPython)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        $candidates += $RequestedPython
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $candidates += $cmd.Source
    }
    if ($env:LocalAppData) {
        $candidates += (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe')
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        $resolved = $candidate
        if (Test-Path $candidate) {
            $resolved = (Resolve-Path $candidate).Path
        }
        if ($seen.ContainsKey($resolved)) { continue }
        $seen[$resolved] = $true

        $probe = & $resolved -c "import sys, torch; print(sys.executable); print(torch.__version__)" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Python executable: $($probe[0])"
            Write-Host "Torch version: $($probe[1])"
            return $resolved
        }
        Write-Host "Skipping Python candidate without torch: $resolved"
        Write-Host ($probe -join "`n")
    }

    throw "No usable Python interpreter with torch was found. Pass -PythonExe explicitly."
}

$ResolvedPython = Resolve-BenchPython -RequestedPython $PythonExe

Write-Host "Launching $Sessions parallel Slumbot sessions on $ModelPath"
Write-Host "Per session: $HandsPerSession hands. Total: $($Sessions * $HandsPerSession)."
if ($Sample) { $PolicyMode = 'sample' }
Write-Host "Policy mode: $PolicyMode temperature=$Temperature guarded_allin_max_spr=$GuardedAllinMaxSpr guarded_allin_min_prob=$GuardedAllinMinProb callguard_min_prob=$CallguardMinProb callguard_ratio=$CallguardRatio callguard_include_open=$CallguardIncludeOpen"
Write-Host ""

$jobs = @()
for ($i = 1; $i -le $Sessions; $i++) {
    $logFile = Join-Path $OutputDir "bench_v55_${Tag}_part${i}.log"
    $resultJson = Join-Path $OutputDir "bench_v55_${Tag}_part${i}.json"
    $handsJsonl = Join-Path $OutputDir "bench_v55_${Tag}_part${i}_hands.jsonl"
    $dumpJsonl = Join-Path $OutputDir "bench_v55_${Tag}_part${i}_dump.jsonl"
    $sessionArgs = @('-X','utf8','-u','scripts/alpha_holdem/play_slumbot.py',
                     '--model', $ModelPath,
                     '--hands', "$HandsPerSession",
                     '--device', 'cpu',
                     '--policy-mode', $PolicyMode,
                     '--temperature', "$Temperature",
                     '--guarded-allin-max-spr', "$GuardedAllinMaxSpr",
                     '--guarded-allin-min-prob', "$GuardedAllinMinProb",
                     '--callguard-min-prob', "$CallguardMinProb",
                     '--callguard-ratio', "$CallguardRatio",
                     '--result-json', $resultJson,
                     '--hand-results-jsonl', $handsJsonl,
                     '--dump-slumbot', $dumpJsonl)
    if ($CallguardIncludeOpen) {
        $sessionArgs += '--callguard-include-open'
    }
    $p = Start-Process -FilePath $ResolvedPython -ArgumentList $sessionArgs `
        -WorkingDirectory 'C:\Users\a8594\CardPilot' `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError ($logFile -replace '\.log$', '_err.log') `
        -NoNewWindow -PassThru
    $jobs += @{ PID = $p.Id; Process = $p; Log = $logFile; ResultJson = $resultJson; HandsJsonl = $handsJsonl; DumpJsonl = $dumpJsonl; Idx = $i }
    Write-Host "  session $i started: PID $($p.Id) -> $logFile"
}

Write-Host ""
Write-Host "All $Sessions sessions launched. Waiting for completion..."
Write-Host "(check progress: Get-Content $OutputDir\bench_v55_${Tag}_part1.log -Tail 5)"

# Wait for all
$startTime = Get-Date
while ($true) {
    $alive = 0
    foreach ($j in $jobs) {
        if (Get-Process -Id $j.PID -ErrorAction SilentlyContinue) { $alive++ }
    }
    $elapsed = ((Get-Date) - $startTime).TotalMinutes
    Write-Host "[$([math]::Round($elapsed,1)) min] $alive/$Sessions sessions still running"
if ($alive -eq 0) { break }
    Start-Sleep -Seconds 60
}

$failedJobs = @()
foreach ($j in $jobs) {
    try {
        $j.Process.WaitForExit()
        $j.Process.Refresh()
        $exitCode = $j.Process.ExitCode
    } catch {
        $exitCode = $null
    }
    if ($null -ne $exitCode -and $exitCode -ne 0) {
        $failedJobs += "session $($j.Idx) pid=$($j.PID) exit=$exitCode log=$($j.Log)"
    } elseif ($null -eq $exitCode) {
        Write-Host "WARNING: session $($j.Idx) exit code unavailable; validating required artifacts instead."
    }
    if (-not (Test-Path $j.ResultJson)) {
        $failedJobs += "session $($j.Idx) missing result json: $($j.ResultJson)"
    }
    if (-not (Test-Path $j.HandsJsonl)) {
        $failedJobs += "session $($j.Idx) missing hand jsonl: $($j.HandsJsonl)"
    }
    if (-not (Test-Path $j.DumpJsonl)) {
        $failedJobs += "session $($j.Idx) missing decision dump jsonl: $($j.DumpJsonl)"
    }
}
if ($failedJobs.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: one or more Slumbot sessions failed or missed required artifacts:"
    $failedJobs | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host ""
Write-Host "All sessions done. Aggregating results..."

# Run aggregator (script takes positional log paths)
$summary = Join-Path $OutputDir "bench_v55_${Tag}_summary.txt"
$logFiles = Get-ChildItem -Path (Join-Path $OutputDir "bench_v55_${Tag}_part*.log") | Where-Object { $_.Name -notmatch '_err\.log$' } | ForEach-Object { $_.FullName }
$pyArgs = @('-X','utf8','scripts/alpha_holdem/combine_slumbot_logs.py') + $logFiles
$result = & $ResolvedPython @pyArgs 2>&1
$result | Out-File -FilePath $summary -Encoding utf8
Write-Host ($result -join "`n")

$ciSummary = Join-Path $OutputDir "bench_v55_${Tag}_ci_summary.json"
$handFiles = Get-ChildItem -Path (Join-Path $OutputDir "bench_v55_${Tag}_part*_hands.jsonl") | ForEach-Object { $_.FullName }
if ($handFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "Computing exact CI from per-hand JSONL..."
    $ciArgs = @('scripts/alpha_holdem/slumbot_ci_from_hands.py') + $handFiles + @('--out-json', $ciSummary)
    $ciResult = & $ResolvedPython @ciArgs 2>&1
    $ciText = $ciResult -join "`n"
    Write-Host $ciText
    $ciText | Out-File -FilePath ($ciSummary -replace '\.json$', '.txt') -Encoding utf8
} else {
    Write-Host "ERROR: no per-hand JSONL files found; cannot compute CI."
    exit 1
}

if (Test-Path $ciSummary) {
    $ci = Get-Content $ciSummary -Raw | ConvertFrom-Json
    $minExpectedHands = [int][math]::Floor(($Sessions * $HandsPerSession) * 0.9)
    if ([int]$ci.hands -lt $minExpectedHands) {
        Write-Host "ERROR: CI contains only $($ci.hands) hands; expected at least $minExpectedHands."
        exit 1
    }
    Write-Host ""
    Write-Host "Evaluating V5 promotion gate..."
    $promotionJson = Join-Path $OutputDir "bench_v55_${Tag}_promotion_gate.json"
    $promotionMd = Join-Path $OutputDir "bench_v55_${Tag}_promotion_gate.md"
    $promotionArgs = @(
        'scripts/alpha_holdem/v5_slumbot_promotion_gate.py',
        '--checkpoint', $ModelPath,
        '--ci-json', $ciSummary,
        '--out-json', $promotionJson,
        '--out-md', $promotionMd
    )

    $effectiveRunDir = $RunDir
    if ([string]::IsNullOrWhiteSpace($effectiveRunDir)) {
        $modelParent = Split-Path -Parent (Resolve-Path $ModelPath)
        if (Test-Path (Join-Path $modelParent 'health_status.json')) {
            $effectiveRunDir = $modelParent
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($effectiveRunDir)) {
        $promotionArgs += @('--run-dir', $effectiveRunDir)
    }

    $promotionResult = & $ResolvedPython @promotionArgs 2>&1
    $promotionText = $promotionResult -join "`n"
    Write-Host $promotionText
    $promotionText | Out-File -FilePath ($promotionJson -replace '\.json$', '.txt') -Encoding utf8
    if (-not (Test-Path $promotionJson)) {
        Write-Host "ERROR: promotion gate JSON was not produced."
        exit 1
    }
} else {
    Write-Host "ERROR: CI summary was not produced."
    exit 1
}

$dumpFiles = Get-ChildItem -Path (Join-Path $OutputDir "bench_v55_${Tag}_part*_dump.jsonl") | ForEach-Object { $_.FullName }
if ($dumpFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "Analyzing Slumbot decision dumps..."
    $dumpAnalysis = Join-Path $OutputDir "bench_v55_${Tag}_dump_analysis.txt"
    $dumpArgs = @('scripts/alpha_holdem/analyze_dump.py', '--label', $Tag, '--dumps') + $dumpFiles
    $dumpResult = & $ResolvedPython @dumpArgs 2>&1
    $dumpText = $dumpResult -join "`n"
    Write-Host $dumpText
    $dumpText | Out-File -FilePath $dumpAnalysis -Encoding utf8

    Write-Host ""
    Write-Host "Building Slumbot loss report..."
    $lossReportJson = Join-Path $OutputDir "bench_v55_${Tag}_loss_report.json"
    $lossReportMd = Join-Path $OutputDir "bench_v55_${Tag}_loss_report.md"
    $lossReportTxt = $lossReportJson -replace '\.json$', '.txt'
    foreach ($staleLossArtifact in @($lossReportJson, $lossReportMd, $lossReportTxt)) {
        if (Test-Path -LiteralPath $staleLossArtifact) {
            Remove-Item -LiteralPath $staleLossArtifact -Force
        }
    }
    $lossArgs = @(
        'scripts/alpha_holdem/v5_slumbot_loss_report.py',
        '--label', $Tag,
        '--dumps'
    ) + $dumpFiles + @(
        '--out-json', $lossReportJson,
        '--out-md', $lossReportMd
    )
    $lossResult = & $ResolvedPython @lossArgs 2>&1
    $lossExitCode = $LASTEXITCODE
    $lossText = $lossResult -join "`n"
    $lossText | Out-File -FilePath $lossReportTxt -Encoding utf8
    if ($lossExitCode -ne 0) {
        Write-Host "ERROR: loss report failed with exit code $lossExitCode."
        Write-Host $lossText
        exit 1
    }
    if (-not (Test-Path $lossReportJson)) {
        Write-Host "ERROR: loss report JSON was not produced."
        exit 1
    }
    if (-not (Test-Path $lossReportMd)) {
        Write-Host "ERROR: loss report markdown was not produced."
        exit 1
    }
    $lossReport = Get-Content $lossReportJson -Raw | ConvertFrom-Json
    if ($null -eq $lossReport.rates.sb_open_call_rate -or $null -eq $lossReport.rates.sb_open_raise_rate) {
        Write-Host "ERROR: loss report is missing SB open call/raise rates."
        exit 1
    }
}

Write-Host ""
Write-Host "=== Bench complete ==="
Write-Host "Summary: $summary"
if (Test-Path $ciSummary) { Write-Host "CI summary: $ciSummary" }
if (Test-Path (Join-Path $OutputDir "bench_v55_${Tag}_promotion_gate.json")) {
    Write-Host "Promotion gate: $(Join-Path $OutputDir "bench_v55_${Tag}_promotion_gate.json")"
}
if (Test-Path (Join-Path $OutputDir "bench_v55_${Tag}_dump_analysis.txt")) {
    Write-Host "Dump analysis: $(Join-Path $OutputDir "bench_v55_${Tag}_dump_analysis.txt")"
}
if (Test-Path (Join-Path $OutputDir "bench_v55_${Tag}_loss_report.md")) {
    Write-Host "Loss report: $(Join-Path $OutputDir "bench_v55_${Tag}_loss_report.md")"
}
if (Test-Path $summary) { Get-Content $summary }
