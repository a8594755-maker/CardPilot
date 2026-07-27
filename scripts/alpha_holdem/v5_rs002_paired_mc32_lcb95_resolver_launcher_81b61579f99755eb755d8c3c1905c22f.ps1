param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'SelfTest', 'Qualification', 'Audit')]
    [string]$Mode,
    [string]$Nonce = '',
    [ValidateSet('shallow', 'deep')]
    [string]$Level = 'shallow'
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs002_paired_mc32_lcb95_resolver_81b61579f99755eb755d8c3c1905c22f.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs002_paired_mc32_lcb95_resolver_audit_81b61579f99755eb755d8c3c1905c22f.py'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_rs002_paired_mc32_lcb95_resolver_implementation_audit_81b61579f99755eb755d8c3c1905c22f_20260722.json'
$QualificationRoot = 'C:\Users\a8594\CardPilot\reports\v5_rs002_paired_mc32_lcb95_resolver_qualification_81b61579f99755eb755d8c3c1905c22f_20260722'
$QualificationNonce = 'RS002_QUALIFICATION_2036972294'
$DeviceMode = 'CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK'
$AllowedProbeNonces = @('RS002_PROBE_A_2034972294', 'RS002_PROBE_B_2035972294')

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'python_missing' }
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) { throw 'runner_missing' }

$env:CUDA_VISIBLE_DEVICES = '0'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'
$env:PYTHONHASHSEED = '0'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:RS002_DEVICE_MODE = $DeviceMode

if ($Mode -eq 'ContractProbe') {
    if ($AllowedProbeNonces -notcontains $Nonce) { throw 'unregistered_probe_nonce' }
    $env:RS002_EXECUTION_NONCE = $Nonce
    & $Python $Runner --mode ContractProbe --nonce $Nonce
    exit $LASTEXITCODE
}

if ($Nonce -ne '') { throw 'nonce_override_forbidden' }
$env:RS002_EXECUTION_NONCE = $QualificationNonce

if ($Mode -eq 'SelfTest') {
    & $Python $Runner --mode SelfTest --nonce $QualificationNonce --level $Level
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $ImplementationAudit -PathType Leaf)) { throw 'implementation_audit_missing' }
$ImplementationAuditSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ImplementationAudit).Hash.ToLowerInvariant()

if ($Mode -eq 'Qualification') {
    if (Test-Path -LiteralPath $QualificationRoot) { throw 'qualification_root_not_fresh' }
    & $Python $Runner --mode Qualification --nonce $QualificationNonce --root $QualificationRoot --implementation-audit-sha256 $ImplementationAuditSha
    exit $LASTEXITCODE
}

if ($Mode -eq 'Audit') {
    if (-not (Test-Path -LiteralPath $Auditor -PathType Leaf)) { throw 'auditor_missing' }
    & $Python $Auditor --root $QualificationRoot --implementation-audit-sha256 $ImplementationAuditSha
    exit $LASTEXITCODE
}

throw 'unsupported_mode'
