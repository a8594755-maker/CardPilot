# PCV018 registered launcher — Windows-safe parent-to-child CPU device admission.
# Windows PowerShell 5.1 (Desktop). Two modes share this exact file and the exact
# runner file: ContractProbe (stdout JSON, zero files) and Smoke (the one registered
# bounded CPU smoke). Parent operations follow the preregistration order exactly.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Smoke')]
    [string]$Mode,

    [string]$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_pcv018_implementation_audit_20260720.json',
    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv018_exact_v55_teacher_smoke.py'
$Prereg = 'C:\Users\a8594\CardPilot\reports\v5_pcv018_preregistration_20260720.json'
$PreregAudit = 'C:\Users\a8594\CardPilot\reports\v5_pcv018_preregistration_audit_20260720.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\pcv018_exact_v55_teacher_smoke_20260720'

# Registered parent operations, in order. '-1' is present-nonempty, so Windows
# PowerShell 5.1 keeps the variable in the child environment (the PCV017 failure
# mode was present-empty, which 5.1 removes).
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:PCV018_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'
$env:PCV018_CONTRACT_NONCE = '2027972092'

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --contract-probe
    exit $LASTEXITCODE
}

if ([string]::IsNullOrEmpty($ImplementationAuditSha256)) {
    Write-Error 'Smoke mode requires -ImplementationAuditSha256'
    exit 1
}

& $Python $Runner `
    --preregistration $Prereg `
    --preregistration-audit $PreregAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256 `
    --output $OutputRoot
exit $LASTEXITCODE
