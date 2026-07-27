[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Qualification', 'Audit')]
    [string]$Mode,
    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Launcher = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_tn001_trajectory_native_launch.ps1'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_tn001_trajectory_native_qualification.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_tn001_trajectory_native_qualification_audit.py'
$Design = 'C:\Users\a8594\CardPilot\reports\v5_tn001_trajectory_native_design_preregistration_20260722.json'
$DesignAudit = 'C:\Users\a8594\CardPilot\reports\v5_tn001_trajectory_native_design_preregistration_audit_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_tn001_trajectory_native_implementation_audit_20260722.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\tn001_trajectory_native_qualification_20260722'

Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:TN001_AUDIT_INVOCATION -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TN001_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'
$env:TN001_CONTRACT_NONCE = '2026472291'

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --contract-probe
    exit $LASTEXITCODE
}
if (-not [regex]::IsMatch($ImplementationAuditSha256, '^[0-9a-f]{64}$')) {
    Write-Error "$Mode requires a lowercase 64-hex implementation audit SHA"
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
$env:TN001_AUDIT_INVOCATION = 'LAUNCHER_OWNED_ABSOLUTE_PATHS'
& $Python $Auditor `
    --root $OutputRoot `
    --design $Design `
    --design-audit $DesignAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256 `
    --runner $Runner `
    --launcher $Launcher
exit $LASTEXITCODE
