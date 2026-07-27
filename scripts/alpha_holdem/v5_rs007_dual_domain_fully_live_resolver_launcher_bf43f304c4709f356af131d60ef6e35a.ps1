param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('ContractProbe','SelfTest','Qualification','Audit')]
    [string]$Mode,
    [string]$Nonce = '',
    [ValidateSet('quick','deep')]
    [string]$Level = 'deep',
    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs007_dual_domain_fully_live_resolver_bf43f304c4709f356af131d60ef6e35a.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs007_dual_domain_fully_live_resolver_audit_bf43f304c4709f356af131d60ef6e35a.py'
$Root = 'C:\Users\a8594\CardPilot\reports\v5_rs007_dual_domain_fully_live_resolver_qualification_bf43f304c4709f356af131d60ef6e35a_20260723'
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
if ($Mode -eq 'SelfTest') {
    & $Python $Runner --mode SelfTest --nonce $Nonce --level $Level
    exit $LASTEXITCODE
}
if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'implementation_audit_sha256_invalid'
}
& $Python $Runner --mode Qualification --nonce $Nonce --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
exit $LASTEXITCODE
