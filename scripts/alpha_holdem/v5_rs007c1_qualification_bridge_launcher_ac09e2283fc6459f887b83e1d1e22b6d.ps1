param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Qualification','Audit')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Bridge = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_rs007c1_qualification_bridge_ac09e2283fc6459f887b83e1d1e22b6d.py'
$Nonce = 'RS007_QUALIFICATION_2036972299'
$env:CUDA_VISIBLE_DEVICES = '0'
$env:RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'
$env:RS007_NONCE = $Nonce
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'

if ($Mode -eq 'Qualification') {
    & $Python $Bridge --mode Qualification --nonce $Nonce
    exit $LASTEXITCODE
}
& $Python $Bridge --mode Audit
exit $LASTEXITCODE
