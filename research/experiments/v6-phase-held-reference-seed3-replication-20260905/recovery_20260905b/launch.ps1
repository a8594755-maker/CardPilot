$ErrorActionPreference = 'Stop'
$recoveryDirectory = $PSScriptRoot
$researchWorkspace = 'C:\Users\a8594\CardPilot'
$researchPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$recoveryController = Join-Path $recoveryDirectory 'resume_control_second.py'
$recoveryStdout = Join-Path $recoveryDirectory 'controller.stdout.log'
$recoveryStderr = Join-Path $recoveryDirectory 'controller.stderr.log'
foreach ($recoveryPrevious in @($recoveryStdout, $recoveryStderr, (Join-Path $recoveryDirectory 'ownership.json'))) {
    if (Test-Path -LiteralPath $recoveryPrevious) { throw "Preserve previous recovery attempt: $recoveryPrevious" }
}
if (!(Test-Path -LiteralPath (Join-Path $recoveryDirectory 'recovery_preflight.json'))) { throw 'Recovery qualification missing' }
$recoveryProcess = Start-Process -FilePath $researchPython -ArgumentList @('-u', $recoveryController) -WorkingDirectory $researchWorkspace -WindowStyle Hidden -RedirectStandardOutput $recoveryStdout -RedirectStandardError $recoveryStderr -PassThru
$recoveryProcess | Select-Object Id, StartTime, Path
