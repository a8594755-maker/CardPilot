param(
    [Parameter(Mandatory=$true)]
    [string]$ImplementationAuditSha256
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Root = 'C:\Users\a8594\CardPilot'
$Token = '3923624abb5ec15db4dca9ba20e36895c'
$Identity = '3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70'
$Prereg = Join-Path $Root "reports\v5_rs009_quick5k_preregistration_${Token}_20260723.json"
$Runner = Join-Path $Root "scripts\alpha_holdem\v5_rs009_quick5k_session_${Token}.py"
$Audit = Join-Path $Root "reports\v5_rs009_quick5k_implementation_audit_${Token}_20260723.json"
$QuickRoot = Join-Path $Root 'models\bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723'

if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'implementation_audit_sha256_invalid'
}
if (-not (Test-Path -LiteralPath $Audit -PathType Leaf)) {
    throw 'implementation_audit_missing'
}
$ObservedAuditSha = (Get-FileHash -LiteralPath $Audit -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ObservedAuditSha -ne $ImplementationAuditSha256) {
    throw 'implementation_audit_sha256_mismatch'
}
$AuditJson = Get-Content -LiteralPath $Audit -Raw | ConvertFrom-Json
if ($AuditJson.classification -ne 'PASS / RS009_QUICK5K_IMPLEMENTATION_AUDIT_PASS_NETWORK_READY') {
    throw 'implementation_audit_nonpass'
}
if (Test-Path -LiteralPath $QuickRoot) {
    throw 'quick5k_root_collision'
}

$null = New-Item -ItemType Directory -Path $QuickRoot
$InvocationPath = Join-Path $QuickRoot 'invocation.json'
$Invocation = [ordered]@{
    schema_version = 'v5.rs009.quick5k.invocation.v1'
    identity_sha256 = $Identity
    implementation_audit_sha256 = $ImplementationAuditSha256
    preregistration_sha256 = (Get-FileHash -LiteralPath $Prereg -Algorithm SHA256).Hash.ToLowerInvariant()
    session_runner_sha256 = (Get-FileHash -LiteralPath $Runner -Algorithm SHA256).Hash.ToLowerInvariant()
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    started_epoch = [DateTimeOffset]::Now.ToUnixTimeMilliseconds() / 1000.0
    parts = 4
    hands_per_part = 1250
    maximum_attempts_per_part = 1500
    policy_mode = 'greedy-direct'
    cuda_visible_devices = '0'
    nonces = @(
        'RS009_QUICK5K_PART1_2036972301',
        'RS009_QUICK5K_PART2_2036972301',
        'RS009_QUICK5K_PART3_2036972301',
        'RS009_QUICK5K_PART4_2036972301'
    )
}
$Invocation | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $InvocationPath -Encoding utf8NoBOM -NoNewline

$Jobs = @()
for ($Part = 1; $Part -le 4; $Part++) {
    $Nonce = "RS009_QUICK5K_PART${Part}_2036972301"
    $Stdout = Join-Path $QuickRoot "part${Part}_stdout.log"
    $Stderr = Join-Path $QuickRoot "part${Part}_stderr.log"
    $Args = @(
        '-X', 'utf8', '-u', $Runner,
        '--mode', 'Session',
        '--part', "$Part",
        '--hands', '1250',
        '--max-attempts', '1500',
        '--nonce', $Nonce,
        '--implementation-audit-sha256', $ImplementationAuditSha256
    )
    $Environment = @{
        CUDA_VISIBLE_DEVICES = '0'
        RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'
        RS007_NONCE = $Nonce
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONHASHSEED = '0'
        CUBLAS_WORKSPACE_CONFIG = ':4096:8'
    }
    foreach ($Key in $Environment.Keys) {
        [Environment]::SetEnvironmentVariable($Key, $Environment[$Key], 'Process')
    }
    $Process = Start-Process -FilePath $Python -ArgumentList $Args `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr `
        -WindowStyle Hidden `
        -PassThru
    $Jobs += [pscustomobject]@{
        Part = $Part
        Process = $Process
        Stdout = $Stdout
        Stderr = $Stderr
    }
}

while (($Jobs | Where-Object { -not $_.Process.HasExited }).Count -gt 0) {
    $Alive = ($Jobs | Where-Object { -not $_.Process.HasExited }).Count
    Write-Host "RS009 quick5k: $Alive/4 parts running"
    Start-Sleep -Seconds 5
    foreach ($Job in $Jobs) {
        $Job.Process.Refresh()
    }
}

$PartResults = @()
$Failed = $false
foreach ($Job in $Jobs) {
    $Job.Process.WaitForExit()
    $Job.Process.Refresh()
    $ResultPath = Join-Path $QuickRoot "part$($Job.Part)_result.json"
    $ResultExists = Test-Path -LiteralPath $ResultPath -PathType Leaf
    if ($Job.Process.ExitCode -ne 0 -or -not $ResultExists) {
        $Failed = $true
    }
    $PartResults += [ordered]@{
        part = $Job.Part
        pid = $Job.Process.Id
        exit_code = $Job.Process.ExitCode
        result_exists = $ResultExists
        stdout = $Job.Stdout
        stderr = $Job.Stderr
    }
}

$LaunchResult = [ordered]@{
    schema_version = 'v5.rs009.quick5k.launch_result.v1'
    identity_sha256 = $Identity
    completed_epoch = [DateTimeOffset]::Now.ToUnixTimeMilliseconds() / 1000.0
    classification = if ($Failed) { 'FAIL_CLOSED / RS009_QUICK5K_PART_FAILURE' } else { 'PASS / RS009_QUICK5K_ALL_PARTS_COMPLETE' }
    parts = $PartResults
}
$LaunchResultPath = Join-Path $QuickRoot 'launch_result.json'
$LaunchResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $LaunchResultPath -Encoding utf8NoBOM -NoNewline
if ($Failed) {
    exit 1
}
exit 0
