$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$trainLog = 'reports\sourcev4_postflop_head_rl_1m_20260726.stdout.log'
$checkpointDir = 'models\sourcev4_postflop_head_rl_1m_20260726\checkpoints'
$curveDir = 'models\sourcev4_postflop_head_rl_1m_20260726\archive_curve'
$deadline = (Get-Date).AddHours(7)
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null

while ((Get-Date) -lt $deadline) {
    $evaluatedOne = $false
    foreach ($checkpoint in @(
        Get-ChildItem -LiteralPath $checkpointDir -Filter 'checkpoint_iter*.pt' -File |
            Sort-Object Name
    )) {
        $outJson = Join-Path $curveDir ($checkpoint.BaseName + '.json')
        if (Test-Path -LiteralPath $outJson) {
            continue
        }
        $outMd = Join-Path $curveDir ($checkpoint.BaseName + '.md')
        $outLog = Join-Path $curveDir ($checkpoint.BaseName + '.log')
        $probeArgs = @(
            '-X', 'utf8', '-u',
            'scripts/alpha_holdem/v5_internal_strength_probe.py',
            '--checkpoint', $checkpoint.FullName,
            '--hands', '1000',
            '--opponents', 'aggressive', 'call-station', 'random',
            '--max-pool-snapshots', '0',
            '--device', 'cuda',
            '--starting-stack', '200',
            '--seed', '20260726',
            '--policy-mode', 'greedy',
            '--out-json', $outJson,
            '--out-md', $outMd
        )
        & python @probeArgs 2>&1 | Tee-Object -FilePath $outLog
        if ($LASTEXITCODE -ne 0) {
            throw "Archive probe failed: $($checkpoint.FullName)"
        }
        $evaluatedOne = $true
    }

    $trainingComplete = (
        (Test-Path -LiteralPath $trainLog) -and
        (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
    )
    if ($trainingComplete -and -not $evaluatedOne) {
        break
    }

    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match 'sourcev4_postflop_head_rl_1m_20260726'
            }
    )
    if ($trainer.Count -eq 0 -and -not $trainingComplete) {
        throw '1M trainer exited before the archive curve completed'
    }
    Start-Sleep -Seconds 20
}

if ((Get-Date) -ge $deadline) {
    throw 'Timed out building the 1M archive learning curve'
}
