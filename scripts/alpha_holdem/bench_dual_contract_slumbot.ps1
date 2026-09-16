param(
    [Parameter(Mandatory=$true)][string]$ModelPath,
    [Parameter(Mandatory=$true)][string]$BaseModel,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [Parameter(Mandatory=$true)][string]$SessionPrefix,
    [int]$HandsPerSession = 625,
    [int]$Sessions = 8,
    [int]$SeedBase = 2026091000,
    [int]$LaunchStaggerSeconds = 1,
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ModelPath = (Resolve-Path -LiteralPath $ModelPath).Path
$BaseModel = (Resolve-Path -LiteralPath $BaseModel).Path
$OutDir = [System.IO.Path]::GetFullPath((Join-Path $Repo $OutDir))
if (Test-Path -LiteralPath $OutDir) {
    throw "Output directory already exists: $OutDir"
}
if ($HandsPerSession -le 0 -or $Sessions -lt 2) {
    throw 'Positive hands and at least two sessions are required'
}

$BenchMutex = [System.Threading.Mutex]::new($false, 'Local\CardPilotSlumbotBenchV1')
try {
    try {
        $null = $BenchMutex.WaitOne()
    } catch [System.Threading.AbandonedMutexException] {
    }
    $active = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match '^python(?:\.exe)?$' -and $_.CommandLine -and
            $_.CommandLine -match 'play_slumbot(?:_v6_journaled)?\.py'
        }
    )
    if ($active.Count -gt 0) {
        throw 'Another Slumbot evaluation process is already active'
    }
    New-Item -ItemType Directory -Path $OutDir | Out-Null
    $jobs = @()
    for ($index = 1; $index -le $Sessions; $index++) {
        $label = '{0}_s{1:d2}' -f $SessionPrefix, $index
        $sessionDir = Join-Path $OutDir ('s{0:d2}' -f $index)
        $stdout = Join-Path $OutDir ('s{0:d2}.stdout.log' -f $index)
        $stderr = Join-Path $OutDir ('s{0:d2}.stderr.log' -f $index)
        $arguments = @(
            '-X', 'utf8', '-u', 'scripts/alpha_holdem/play_slumbot_v6_journaled.py',
            '--model', $ModelPath,
            '--base-model', $BaseModel,
            '--observation-bridge', 'dual-contract',
            '--hands', "$HandsPerSession",
            '--seed', "$($SeedBase + $index)",
            '--session-id', $label,
            '--out-dir', $sessionDir,
            '--device', 'cpu',
            '--policy-mode', 'greedy'
        )
        $process = Start-Process -FilePath $PythonExe -ArgumentList $arguments `
            -WorkingDirectory $Repo -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -NoNewWindow -PassThru
        $jobs += [pscustomobject]@{
            Index = $index; Process = $process; SessionDir = $sessionDir
            Stdout = $stdout; Stderr = $stderr
        }
        Write-Host "Started $label PID=$($process.Id)"
        if ($index -lt $Sessions -and $LaunchStaggerSeconds -gt 0) {
            Start-Sleep -Seconds $LaunchStaggerSeconds
        }
    }
    while ($true) {
        $alive = @($jobs | Where-Object { -not $_.Process.HasExited }).Count
        Write-Host "$(Get-Date -Format o) active_sessions=$alive/$Sessions"
        if ($alive -eq 0) { break }
        Start-Sleep -Seconds 30
        foreach ($job in $jobs) { $job.Process.Refresh() }
    }
    $failures = @()
    foreach ($job in $jobs) {
        $job.Process.WaitForExit()
        if ($job.Process.ExitCode -ne 0) {
            $failures += "s$($job.Index) exit=$($job.Process.ExitCode) stderr=$($job.Stderr)"
        }
    }
    if ($failures.Count -gt 0) {
        throw "One or more fixed sessions failed; no retry/replacement is permitted: $($failures -join '; ')"
    }

    $sessionDirs = @($jobs | Sort-Object Index | ForEach-Object { $_.SessionDir })
    $auditArgs = @('scripts/alpha_holdem/audit_slumbot_v6_session.py')
    foreach ($directory in $sessionDirs) { $auditArgs += @('--session-dir', $directory) }
    $auditArgs += @(
        '--model', $ModelPath, '--base-model', $BaseModel,
        '--observation-bridge', 'dual-contract'
    )
    $auditText = & $PythonExe @auditArgs
    if ($LASTEXITCODE -ne 0) { throw 'Journal/session replay audit failed' }
    $auditText | Set-Content -LiteralPath (Join-Path $OutDir 'session_audit.json') -Encoding utf8

    $independenceArgs = @('scripts/alpha_holdem/audit_journaled_slumbot_independence.py')
    foreach ($directory in $sessionDirs) { $independenceArgs += @('--session-dir', $directory) }
    $independenceArgs += @('--out-json', (Join-Path $OutDir 'session_independence.json'))
    & $PythonExe @independenceArgs
    if ($LASTEXITCODE -ne 0) { throw 'Empirical session-independence audit failed' }

    $handFiles = @($sessionDirs | ForEach-Object { Join-Path $_ 'hands.jsonl' })
    $ciArgs = @('scripts/alpha_holdem/slumbot_ci_from_hands.py') + $handFiles + @(
        '--baseline-bb100', '-11.4275', '--out-json', (Join-Path $OutDir 'ci_summary.json')
    )
    & $PythonExe @ciArgs
    if ($LASTEXITCODE -ne 0) { throw 'Raw-hand CI computation failed' }
    $ci = Get-Content (Join-Path $OutDir 'ci_summary.json') -Raw | ConvertFrom-Json
    if ([int]$ci.hands -ne ($HandsPerSession * $Sessions)) {
        throw "Raw CI hand count mismatch: $($ci.hands)"
    }
    Write-Host "Completed exact fresh gate: hands=$($ci.hands) bb/100=$($ci.bb_per_100) CI=[$($ci.lower_bound_bb_per_100),$($ci.upper_bound_bb_per_100)]"
} finally {
    try { $BenchMutex.ReleaseMutex() } catch {}
    $BenchMutex.Dispose()
}
