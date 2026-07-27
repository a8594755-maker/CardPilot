# Revision006 Q006 registered Windows child boundary.  Every scientific path is
# hardcoded and absolute.  No caller can override an input or output identity.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Qualification', 'Audit')]
    [string]$Mode,

    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Launcher = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\launch_v5_phase_fa_revision006_q006.ps1'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_revision006_q006.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\audit_v5_phase_fa_revision006_q006.py'
$Design = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_20260722.json'
$DesignAudit = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_design_revision006_preregistration_audit_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_implementation_audit_20260722.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_revision006_q006_20260722'

# Present, nonempty values are required for Windows PowerShell 5.1 propagation.
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:REV006_DEVICE_MODE -ErrorAction SilentlyContinue
Remove-Item Env:REV006_CONTRACT_NONCE -ErrorAction SilentlyContinue
Remove-Item Env:REV006_AUDIT_INVOCATION -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:REV006_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'
$env:REV006_CONTRACT_NONCE = '2031972206'

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --contract-probe
    exit $LASTEXITCODE
}

if (-not [regex]::IsMatch($ImplementationAuditSha256, '^[0-9a-f]{64}$')) {
    Write-Error "$Mode mode requires -ImplementationAuditSha256 as exactly 64 lowercase hex characters"
    exit 1
}

if ($Mode -eq 'Qualification') {
    & $Python $Runner `
        --design $Design `
        --design-audit $DesignAudit `
        --implementation-audit $ImplementationAudit `
        --implementation-audit-sha256 $ImplementationAuditSha256 `
        --output $OutputRoot
    exit $LASTEXITCODE
}

$env:REV006_AUDIT_INVOCATION = 'LAUNCHER_OWNED_ABSOLUTE_PATHS'
& $Python $Auditor `
    --root $OutputRoot `
    --design $Design `
    --design-audit $DesignAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256 `
    --runner $Runner `
    --launcher $Launcher
exit $LASTEXITCODE
