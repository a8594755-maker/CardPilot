$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-nashpg-moving-reference-geometric-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$jobs = @()
foreach ($seed in 1..3) {
    foreach ($arm in @('static', 'moving')) {
        $checkpoint = (Resolve-Path -LiteralPath "$experiment/$arm`_seed$seed/latest.pt").Path
        $outDir = "$experiment/drift_$arm`_seed$seed"
        if (Test-Path -LiteralPath $outDir) {
            throw "Refusing to overwrite drift directory: $outDir"
        }
        $driftSeed = 20263030 + (($seed - 1) * 2) + $(if ($arm -eq 'moving') { 2 } else { 1 })
        $arguments = @(
            'scripts/alpha_holdem/v6_legacy_bridge_drift_audit.py',
            '--parent', $standard10,
            '--parent-sha256', '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428',
            '--treatment', $checkpoint,
            '--out-dir', $outDir,
            '--states', '20000',
            '--seed', [string]$driftSeed,
            '--device', 'cuda',
            '--batch-size', '1024',
            '--source-tv-max', '1',
            '--greedy-disagreement-max', '1'
        )
        $jobs += Start-Job -ScriptBlock {
            param($Repo, $Arguments)
            Set-Location -LiteralPath $Repo
            & python @Arguments
            if ($LASTEXITCODE -ne 0) {
                throw "Drift audit failed with exit code $LASTEXITCODE"
            }
        } -ArgumentList (Get-Location).Path, (,$arguments)
    }
}

$jobs | Wait-Job | Out-Null
$failed = @($jobs | Where-Object State -ne 'Completed')
$jobs | Receive-Job
if ($failed.Count -gt 0) {
    $failed | Format-List Id, State, ChildJobs
    throw "$($failed.Count) drift audit job(s) failed"
}
