# Phase FA Q001 registered launcher. ContractProbe, Qualification, and Audit all
# cross this exact Windows PowerShell 5.1 boundary. Every path is hardcoded and
# absolute; the only caller-supplied identity is the immutable implementation audit SHA.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Qualification', 'Audit')]
    [string]$Mode,

    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Launcher = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_teacher_launch.ps1'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_teacher_qualification.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_phase_fa_teacher_qualification_audit.py'
$Design = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_20260722.json'
$DesignAudit = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_full_teacher_asset_design_preregistration_audit_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_phase_fa_teacher_qualification_implementation_audit_20260722.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\phase_fa_teacher_qualification_20260722'

# Windows-safe parent-to-child contract. Values must remain present and nonempty.
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:PHASE_FA_AUDIT_INVOCATION -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:PHASE_FA_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'
$env:PHASE_FA_CONTRACT_NONCE = '2029972201'

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

$env:PHASE_FA_AUDIT_INVOCATION = 'LAUNCHER_OWNED_ABSOLUTE_PATHS'
& $Python $Auditor `
    --root $OutputRoot `
    --design $Design `
    --design-audit $DesignAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256 `
    --runner $Runner `
    --launcher $Launcher
exit $LASTEXITCODE
