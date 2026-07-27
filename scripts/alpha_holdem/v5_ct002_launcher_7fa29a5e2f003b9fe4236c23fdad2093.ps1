[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Probe', 'BuildData', 'Calibrate', 'Mechanism', 'PPO')]
    [string]$Operation,

    [Parameter(Mandatory = $false)]
    [ValidateSet('control_selfplay_calibration', 'treatment_opponent_mix_calibration')]
    [string]$Arm
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = 'C:\Users\a8594\CardPilot'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = Join-Path $Root 'scripts\alpha_holdem\v5_ct002_runner_7fa29a5e2f003b9fe4236c23fdad2093.py'
$Preregistration = Join-Path $Root 'reports\v5_ct002_corrected_preregistration_7fa29a5e2f003b9fe4236c23fdad2093_20260722.json'
$PreregistrationAudit = Join-Path $Root 'reports\v5_ct002_corrected_preregistration_audit_7fa29a5e2f003b9fe4236c23fdad2093_20260722.json'
$OutputRoot = Join-Path $Root 'models\alpha_holdem_v5_hybrid\v5_ct002_7fa29a5e2f003b9fe4236c23fdad2093_20260722'
$Token = '7fa29a5e2f003b9fe4236c23fdad2093'

$ExpectedHashes = @{
    $Python = '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a'
    $Runner = '1a2ade05051eb4fd1ac3a5bec0e5e151dc1ccdf19a8fe8bdd6977ce6d5f81fd5'
    $Preregistration = '4c21f92dc37b668a57e850a07ab279ebe90f3115b22b7aff48f66b8f674ac1b2'
    $PreregistrationAudit = '7dc738ce349008fee8f08b79ffc3c094b314ed1f2280f70a62a6f93755b4233a'
}

foreach ($Path in $ExpectedHashes.Keys) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Registered launcher input is absent: $Path"
    }
    $Observed = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($Observed -ne $ExpectedHashes[$Path]) {
        throw "Registered launcher input hash mismatch: $Path"
    }
}

if ($Operation -in @('Probe', 'Calibrate', 'PPO') -and [string]::IsNullOrWhiteSpace($Arm)) {
    throw "$Operation requires -Arm"
}
if ($Operation -in @('BuildData', 'Mechanism') -and -not [string]::IsNullOrWhiteSpace($Arm)) {
    throw "$Operation forbids -Arm"
}

$env:CT002_IDENTITY_TOKEN = $Token
$env:PYTHONHASHSEED = '0'

switch ($Operation) {
    'Probe' {
        if (Test-Path -LiteralPath $OutputRoot) {
            throw 'Probe requires the registered output root to remain absent'
        }
        $Nonce = switch ($Arm) {
            'control_selfplay_calibration' { '2026972214' }
            'treatment_opponent_mix_calibration' { '2027972214' }
            default { throw 'Unknown registered probe arm' }
        }
        $env:CUDA_VISIBLE_DEVICES = '-1'
        $env:CT002_DEVICE_MODE = 'CPU_ONLY_NO_GPU_NO_OUTPUT'
        $env:CT002_PROBE_NONCE = $Nonce
        $CommandArguments = @('-B', $Runner, 'contract-probe', '--arm', $Arm, '--nonce', $Nonce)
    }
    'BuildData' {
        if (Test-Path -LiteralPath $OutputRoot) {
            throw 'BuildData requires the registered output root to be absent'
        }
        $env:CUDA_VISIBLE_DEVICES = '0'
        $env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'
        Remove-Item Env:CT002_PROBE_NONCE -ErrorAction SilentlyContinue
        $CommandArguments = @('-B', $Runner, 'build-data')
    }
    'Calibrate' {
        $env:CUDA_VISIBLE_DEVICES = '0'
        $env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'
        Remove-Item Env:CT002_PROBE_NONCE -ErrorAction SilentlyContinue
        $CommandArguments = @('-B', $Runner, 'calibrate', '--arm', $Arm)
    }
    'Mechanism' {
        $env:CUDA_VISIBLE_DEVICES = '0'
        $env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'
        Remove-Item Env:CT002_PROBE_NONCE -ErrorAction SilentlyContinue
        $CommandArguments = @('-B', $Runner, 'mechanism')
    }
    'PPO' {
        $env:CUDA_VISIBLE_DEVICES = '0'
        $env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'
        Remove-Item Env:CT002_PROBE_NONCE -ErrorAction SilentlyContinue
        $CommandArguments = @('-B', $Runner, 'ppo', '--arm', $Arm)
    }
    default { throw 'Unreachable operation' }
}

Push-Location -LiteralPath $Root
try {
    & $Python @CommandArguments
    $ChildExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($ChildExitCode -ne 0) {
    throw "Registered CT002 child exited $ChildExitCode"
}
exit 0
