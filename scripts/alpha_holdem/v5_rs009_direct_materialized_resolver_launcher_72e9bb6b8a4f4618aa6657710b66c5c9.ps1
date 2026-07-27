param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('ContractProbe','Qualification','Audit')]
    [string]$Mode,
    [string]$Nonce = '',
    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs009_direct_materialized_resolver_72e9bb6b8a4f4618aa6657710b66c5c9.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs009_direct_materialized_resolver_audit_72e9bb6b8a4f4618aa6657710b66c5c9.py'
$Root = 'C:\Users\a8594\CardPilot\reports\v5_rs009_direct_materialized_resolver_qualification_72e9bb6b8a4f4618aa6657710b66c5c9_20260723'
$env:CUDA_VISIBLE_DEVICES = '0'
$env:RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

if ($Mode -eq 'Audit') {
    if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'implementation_audit_sha256_invalid'
    }
    & $Python $Auditor --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($Nonce)) {
    throw 'nonce_required'
}
$env:RS007_NONCE = $Nonce

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --mode ContractProbe --nonce $Nonce
    exit $LASTEXITCODE
}
if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'implementation_audit_sha256_invalid'
}
& $Python $Runner --mode Qualification --nonce $Nonce --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
exit $LASTEXITCODE
