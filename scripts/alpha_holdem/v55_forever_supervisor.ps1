# Keep the V5.5 supervisor alive until it promotes a model that beats Slumbot.
#
# This is a process watchdog, not the experiment logic itself. The Python
# supervisor owns training, benchmark, promotion gates, and state. This wrapper
# only restarts it if it exits before promoted=true.

param(
    [double]$TargetBb100 = 30.0,
    [int64]$SegmentHands = 1000000,
    [int]$PollSeconds = 300
)

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\a8594\CardPilot'

$lab = 'C:\Users\a8594\CardPilot\models\v55_lab'
$statePath = Join-Path $lab 'supervisor_state.json'
$foreverLog = Join-Path $lab 'forever_supervisor.log'

New-Item -ItemType Directory -Force -Path $lab | Out-Null

function Write-ForeverLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $foreverLog -Value $line
    Write-Host $line
}

function Is-Promoted {
    if (-not (Test-Path $statePath)) { return $false }
    try {
        $state = Get-Content $statePath -Raw | ConvertFrom-Json
        return [bool]$state.promoted
    } catch {
        return $false
    }
}

function Get-SupervisorProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*scripts/alpha_holdem/v55_supervisor.py*' }
}

function Get-TrainerProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*scripts/alpha_holdem/train_v55.py*' }
}

function Start-Supervisor {
    $argsList = @(
        '-X', 'utf8', '-u',
        'scripts/alpha_holdem/v55_supervisor.py',
        '--target-bb100', "$TargetBb100",
        '--segment-hands', "$SegmentHands",
        '--max-rounds', '10000'
    )
    $p = Start-Process -FilePath 'python' -ArgumentList $argsList `
        -WorkingDirectory 'C:\Users\a8594\CardPilot' `
        -RedirectStandardOutput 'models\v55_lab\supervisor_stdout.log' `
        -RedirectStandardError 'models\v55_lab\supervisor_stderr.log' `
        -WindowStyle Hidden -PassThru
    Write-ForeverLog "started supervisor pid=$($p.Id) target_bb100=$TargetBb100 segment_hands=$SegmentHands"
}

Write-ForeverLog "forever watchdog started target_bb100=$TargetBb100 segment_hands=$SegmentHands"

while ($true) {
    if (Is-Promoted) {
        Write-ForeverLog "promoted=true detected; watchdog stopping"
        break
    }

    $sup = @(Get-SupervisorProcess)
    if ($sup.Count -eq 0) {
        $trainer = @(Get-TrainerProcess)
        if ($trainer.Count -gt 0) {
            Write-ForeverLog "supervisor missing but trainer alive pid=$($trainer[0].ProcessId); waiting to avoid duplicate GPU run"
        } else {
            Write-ForeverLog "supervisor not running; starting"
            Start-Supervisor
        }
    } elseif ($sup.Count -gt 1) {
        Write-ForeverLog "warning: multiple supervisors detected: $($sup.ProcessId -join ',')"
    } else {
        Write-ForeverLog "supervisor alive pid=$($sup[0].ProcessId)"
    }

    Start-Sleep -Seconds $PollSeconds
}
