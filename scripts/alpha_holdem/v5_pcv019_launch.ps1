# PCV019 registered launcher: Windows-safe CPU child contract plus invocation-robust
# launcher-owned independent audit. ContractProbe, Smoke, and Audit modes share this
# exact file. Every path is hardcoded absolute; no mode accepts a path override.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Smoke', 'Audit')]
    [string]$Mode,

    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Launcher = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv019_launch.ps1'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv019_exact_v55_teacher_smoke.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_pcv019_result_audit.py'
$Prereg = 'C:\Users\a8594\CardPilot\reports\v5_pcv019_preregistration_20260722.json'
$PreregAudit = 'C:\Users\a8594\CardPilot\reports\v5_pcv019_preregistration_audit_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_pcv019_implementation_audit_20260722.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\pcv019_exact_v55_teacher_smoke_20260722'

# Registered parent operations, in order. All environment values are present-nonempty
# for Windows PowerShell 5.1 child propagation.
Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:PCV019_AUDIT_INVOCATION -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:PCV019_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'
$env:PCV019_CONTRACT_NONCE = '2027972093'

if ($Mode -eq 'ContractProbe') {
    & $Python $Runner --contract-probe
    exit $LASTEXITCODE
}

if (-not [regex]::IsMatch($ImplementationAuditSha256, '^[0-9a-f]{64}$')) {
    Write-Error "$Mode mode requires -ImplementationAuditSha256 as exactly 64 lowercase hex characters"
    exit 1
}

if ($Mode -eq 'Smoke') {
    & $Python $Runner `
        --preregistration $Prereg `
        --preregistration-audit $PreregAudit `
        --implementation-audit $ImplementationAudit `
        --implementation-audit-sha256 $ImplementationAuditSha256 `
        --output $OutputRoot
    exit $LASTEXITCODE
}

# Audit mode is the sole registered independent-auditor boundary. It owns every path
# argument, supplies only absolute hardcoded identities, and exposes no path override.
$env:PCV019_AUDIT_INVOCATION = 'LAUNCHER_OWNED_ABSOLUTE_PATHS'
& $Python $Auditor `
    --root $OutputRoot `
    --preregistration $Prereg `
    --preregistration-audit $PreregAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256 `
    --runner $Runner `
    --launcher $Launcher
exit $LASTEXITCODE
