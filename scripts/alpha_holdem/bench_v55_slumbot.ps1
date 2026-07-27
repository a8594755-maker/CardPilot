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
    [string]$ModelPath = '',
    [Parameter(Mandatory=$true)][string]$Tag,
    [int]$HandsPerSession = 1700,
    [int]$Sessions = 12,
    [string]$OutputDir = 'C:\Users\a8594\CardPilot\models',
    [string]$RunDir = '',
    [string]$PythonExe = '',
    [switch]$Sample,
    [ValidateSet('greedy','greedy-guarded','preflop-callguard','sample','guarded','preflop-mixed','preflop-epsilon','street-epsilon')][string]$PolicyMode = 'greedy',
    [double]$Temperature = 1.0,
    [double]$PreflopEpsilon = 0.30,
    [string]$EpsilonStreets = '0',
    [double]$GuardedAllinMaxSpr = 2.0,
    [double]$GuardedAllinMinProb = 0.65,
    [double]$CallguardMinProb = 0.20,
    [double]$CallguardRatio = 0.65,
    [switch]$CallguardIncludeOpen,
    [ValidateSet('model','ensemble','seat_hybrid','postflop_hybrid','postflop_heuristic_v3','preflop_heuristic_v4','preflop_heuristic_v4_nolimp','fold','call','random','heuristic','heuristic_v2','heuristic_v3','heuristic_v3_1','heuristic_v4')][string]$Strategy = 'model',
    [string]$EnsembleModels = '',
    [string]$SbModel = '',
    [string]$BbModel = '',
    [string]$FallbackModel = ''
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Serialize complete Slumbot evaluations.  Discovery watchers can become ready
# at the same time, but overlapping sessions only contend for local CPU/network
# and make both evidence bundles slower.  A named OS mutex survives independent
# PowerShell launchers and is released automatically if a launcher exits.
$BenchMutex = [System.Threading.Mutex]::new(
    $false,
    'Local\CardPilotSlumbotBenchV1'
)
try {
    $null = $BenchMutex.WaitOne()
} catch [System.Threading.AbandonedMutexException] {
    # The previous owner exited unexpectedly; ownership transfers to this
    # process and its incomplete output remains preserved in its own directory.
}

# A bench launched before the mutex was introduced cannot own it.  Wait for
# any such already-running play workers before starting this evaluation.
while (
    @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^python(?:\.exe)?$' -and
                $_.CommandLine -and
                $_.CommandLine -match (
                    'scripts[\\/]alpha_holdem[\\/]play_slumbot\.py'
                )
            }
    ).Count -gt 0
) {
    Start-Sleep -Seconds 15
}

if ($Strategy -in @('model','preflop_heuristic_v4','preflop_heuristic_v4_nolimp') -and (-not (Test-Path $ModelPath))) {
    Write-Host "ERROR: $ModelPath not found"; exit 1
}
if ($Strategy -eq 'ensemble') {
    $ensembleModelPaths = @(
        $EnsembleModels.Split(',') |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($ensembleModelPaths.Count -lt 2) {
        Write-Host "ERROR: ensemble requires at least two comma-separated -EnsembleModels"; exit 1
    }
    foreach ($ensembleModelPath in $ensembleModelPaths) {
        if (-not (Test-Path $ensembleModelPath)) {
            Write-Host "ERROR: ensemble model not found: $ensembleModelPath"; exit 1
        }
    }
}
if ($Strategy -eq 'seat_hybrid' -and (
    [string]::IsNullOrWhiteSpace($SbModel) -or -not (Test-Path $SbModel) -or
    [string]::IsNullOrWhiteSpace($BbModel) -or -not (Test-Path $BbModel)
)) {
    Write-Host "ERROR: seat_hybrid requires existing -SbModel and -BbModel paths"; exit 1
}
if ($Strategy -eq 'postflop_hybrid' -and (
    [string]::IsNullOrWhiteSpace($ModelPath) -or -not (Test-Path $ModelPath) -or
    [string]::IsNullOrWhiteSpace($FallbackModel) -or -not (Test-Path $FallbackModel)
)) {
    Write-Host "ERROR: postflop_hybrid requires existing -ModelPath and -FallbackModel paths"; exit 1
}
if ($Strategy -eq 'postflop_heuristic_v3' -and (
    [string]::IsNullOrWhiteSpace($FallbackModel) -or -not (Test-Path $FallbackModel)
)) {
    Write-Host "ERROR: postflop_heuristic_v3 requires an existing -FallbackModel path"; exit 1
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

Write-Host "Launching $Sessions parallel Slumbot sessions: strategy=$Strategy model=$ModelPath"
Write-Host "Per session: $HandsPerSession hands. Total: $($Sessions * $HandsPerSession)."
if ($Sample) { $PolicyMode = 'sample' }
Write-Host "Policy mode: $PolicyMode temperature=$Temperature preflop_epsilon=$PreflopEpsilon epsilon_streets=$EpsilonStreets guarded_allin_max_spr=$GuardedAllinMaxSpr guarded_allin_min_prob=$GuardedAllinMinProb callguard_min_prob=$CallguardMinProb callguard_ratio=$CallguardRatio callguard_include_open=$CallguardIncludeOpen"
Write-Host ""

$jobs = @()
for ($i = 1; $i -le $Sessions; $i++) {
    $logFile = Join-Path $OutputDir "bench_v55_${Tag}_part${i}.log"
    $resultJson = Join-Path $OutputDir "bench_v55_${Tag}_part${i}.json"
    $handsJsonl = Join-Path $OutputDir "bench_v55_${Tag}_part${i}_hands.jsonl"
    $dumpJsonl = Join-Path $OutputDir "bench_v55_${Tag}_part${i}_dump.jsonl"
    $sessionArgs = @('-X','utf8','-u','scripts/alpha_holdem/play_slumbot.py',
                     '--strategy', $Strategy,
                     '--hands', "$HandsPerSession",
                     '--device', 'cpu',
                     '--policy-mode', $PolicyMode,
                     '--temperature', "$Temperature",
                     '--preflop-epsilon', "$PreflopEpsilon",
                     '--epsilon-streets', $EpsilonStreets,
                     '--guarded-allin-max-spr', "$GuardedAllinMaxSpr",
                     '--guarded-allin-min-prob', "$GuardedAllinMinProb",
                     '--callguard-min-prob', "$CallguardMinProb",
                     '--callguard-ratio', "$CallguardRatio",
                     '--result-json', $resultJson,
                     '--hand-results-jsonl', $handsJsonl,
                     '--dump-slumbot', $dumpJsonl)
    if (-not [string]::IsNullOrWhiteSpace($ModelPath)) {
        $sessionArgs += @('--model', $ModelPath)
    }
    if ($Strategy -eq 'ensemble') {
        $sessionArgs += @('--ensemble-models', $EnsembleModels)
    }
    if ($Strategy -eq 'seat_hybrid') {
        $sessionArgs += @('--sb-model', $SbModel, '--bb-model', $BbModel)
    }
    if ($Strategy -in @('postflop_hybrid', 'postflop_heuristic_v3')) {
        $sessionArgs += @('--fallback-model', $FallbackModel)
    }
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

# A transient Slumbot/network failure can make play_slumbot return fewer
# successful hands than requested while still preserving every completed raw
# hand.  Promotion requires an exact sample size, so append small, separately
# named supplement sessions instead of accepting the old 90%-complete bundle.
$targetHands = $Sessions * $HandsPerSession
$supplementAttempt = 0
while ($true) {
    $observedHands = 0
    $observedHandFiles = @(
        Get-ChildItem -Path (
            Join-Path $OutputDir "bench_v55_${Tag}_part*_hands.jsonl"
        ) -File -ErrorAction SilentlyContinue
    )
    foreach ($observedHandFile in $observedHandFiles) {
        $observedHands += (
            Get-Content -LiteralPath $observedHandFile.FullName |
                Measure-Object -Line
        ).Lines
    }
    if ($observedHands -eq $targetHands) { break }
    if ($observedHands -gt $targetHands) {
        Write-Host (
            "ERROR: raw hand count $observedHands exceeds exact target " +
            "$targetHands; refusing to truncate evidence."
        )
        exit 1
    }
    if ($supplementAttempt -ge 5) {
        Write-Host (
            "ERROR: raw hand count remains $observedHands/$targetHands " +
            "after $supplementAttempt supplement attempts."
        )
        exit 1
    }

    $supplementAttempt++
    $missingHands = $targetHands - $observedHands
    $supplementStem = "bench_v55_${Tag}_part_supplement${supplementAttempt}"
    $supplementLog = Join-Path $OutputDir "${supplementStem}.log"
    $supplementErr = Join-Path $OutputDir "${supplementStem}_err.log"
    $supplementResult = Join-Path $OutputDir "${supplementStem}.json"
    $supplementHands = Join-Path $OutputDir "${supplementStem}_hands.jsonl"
    $supplementDump = Join-Path $OutputDir "${supplementStem}_dump.jsonl"
    $supplementArgs = @(
        '-X', 'utf8', '-u',
        'scripts/alpha_holdem/play_slumbot.py',
        '--strategy', $Strategy,
        '--hands', "$missingHands",
        '--device', 'cpu',
        '--policy-mode', $PolicyMode,
        '--temperature', "$Temperature",
        '--preflop-epsilon', "$PreflopEpsilon",
        '--epsilon-streets', $EpsilonStreets,
        '--guarded-allin-max-spr', "$GuardedAllinMaxSpr",
        '--guarded-allin-min-prob', "$GuardedAllinMinProb",
        '--callguard-min-prob', "$CallguardMinProb",
        '--callguard-ratio', "$CallguardRatio",
        '--result-json', $supplementResult,
        '--hand-results-jsonl', $supplementHands,
        '--dump-slumbot', $supplementDump
    )
    if (-not [string]::IsNullOrWhiteSpace($ModelPath)) {
        $supplementArgs += @('--model', $ModelPath)
    }
    if ($Strategy -eq 'ensemble') {
        $supplementArgs += @('--ensemble-models', $EnsembleModels)
    }
    if ($Strategy -eq 'seat_hybrid') {
        $supplementArgs += @(
            '--sb-model', $SbModel,
            '--bb-model', $BbModel
        )
    }
    if ($Strategy -in @('postflop_hybrid', 'postflop_heuristic_v3')) {
        $supplementArgs += @('--fallback-model', $FallbackModel)
    }
    if ($CallguardIncludeOpen) {
        $supplementArgs += '--callguard-include-open'
    }

    Write-Host (
        "Appending supplement attempt $supplementAttempt for " +
        "$missingHands missing successful hands."
    )
    $supplementProcess = Start-Process -FilePath $ResolvedPython `
        -ArgumentList $supplementArgs `
        -WorkingDirectory 'C:\Users\a8594\CardPilot' `
        -RedirectStandardOutput $supplementLog `
        -RedirectStandardError $supplementErr `
        -NoNewWindow -PassThru -Wait
    if ($supplementProcess.ExitCode -ne 0) {
        Write-Host (
            "ERROR: supplement attempt $supplementAttempt exited " +
            "$($supplementProcess.ExitCode); see $supplementErr"
        )
        exit 1
    }
    foreach ($requiredSupplement in @(
        $supplementResult,
        $supplementHands,
        $supplementDump
    )) {
        if (-not (Test-Path -LiteralPath $requiredSupplement -PathType Leaf)) {
            Write-Host "ERROR: supplement artifact missing: $requiredSupplement"
            exit 1
        }
    }
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
    $expectedHands = $Sessions * $HandsPerSession
    if ([int]$ci.hands -ne $expectedHands) {
        Write-Host "ERROR: CI contains $($ci.hands) hands; expected exactly $expectedHands."
        exit 1
    }
    if ($Strategy -eq 'model') {
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
        Write-Host "Skipping neural-checkpoint promotion gate for strategy=$Strategy."
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

try {
    $BenchMutex.ReleaseMutex()
} finally {
    $BenchMutex.Dispose()
}
