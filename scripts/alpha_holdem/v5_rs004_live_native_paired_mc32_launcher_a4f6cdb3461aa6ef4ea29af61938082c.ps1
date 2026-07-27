param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('ContractProbe','SelfTest','Qualification','Audit')]
    [string]$Mode,
    [string]$Nonce = '',
    [ValidateSet('quick','deep')]
    [string]$Level = 'quick',
    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs004_live_native_paired_mc32_a4f6cdb3461aa6ef4ea29af61938082c.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs004_live_native_paired_mc32_audit_a4f6cdb3461aa6ef4ea29af61938082c.py'
$Root = 'C:\Users\a8594\CardPilot\reports\v5_rs004_live_native_paired_mc32_qualification_a4f6cdb3461aa6ef4ea29af61938082c_20260722'
$env:CUDA_VISIBLE_DEVICES = '0'
$env:RS004_DEVICE_MODE = 'CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

if ($Mode -eq 'Audit') {
    if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') { throw 'implementation_audit_sha256_invalid' }
    & $Python $Auditor --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($Nonce)) { throw 'nonce_required' }
$env:RS004_NONCE = $Nonce

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --mode ContractProbe --nonce $Nonce
    exit $LASTEXITCODE
}
if ($Mode -eq 'SelfTest') {
    & $Python $Runner --mode SelfTest --nonce $Nonce --level $Level
    exit $LASTEXITCODE
}
if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') { throw 'implementation_audit_sha256_invalid' }
& $Python $Runner --mode Qualification --nonce $Nonce --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
exit $LASTEXITCODE
