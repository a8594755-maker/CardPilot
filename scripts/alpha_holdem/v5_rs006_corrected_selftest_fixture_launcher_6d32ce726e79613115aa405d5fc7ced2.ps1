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
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs006_corrected_selftest_fixture_6d32ce726e79613115aa405d5fc7ced2.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs006_corrected_selftest_fixture_audit_6d32ce726e79613115aa405d5fc7ced2.py'
$Root = 'C:\Users\a8594\CardPilot\reports\v5_rs006_corrected_selftest_fixture_qualification_6d32ce726e79613115aa405d5fc7ced2_20260723'
$env:CUDA_VISIBLE_DEVICES = '0'
$env:RS006_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

if ($Mode -eq 'Audit') {
    if ($ImplementationAuditSha256 -notmatch '^[0-9a-f]{64}$') { throw 'implementation_audit_sha256_invalid' }
    & $Python $Auditor --root $Root --implementation-audit-sha256 $ImplementationAuditSha256
    exit $LASTEXITCODE
}
if ([string]::IsNullOrWhiteSpace($Nonce)) { throw 'nonce_required' }
$env:RS006_NONCE = $Nonce
$env:RS005_NONCE = $Nonce
$env:RS005_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'

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
