$ErrorActionPreference = 'Stop'
$recoveryRoot = $PSScriptRoot
$workspaceRoot = 'C:\Users\a8594\CardPilot'
$researchPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$controllerPath = Join-Path $recoveryRoot 'resume_control.py'
$controllerOut = Join-Path $recoveryRoot 'controller.stdout.log'
$controllerErr = Join-Path $recoveryRoot 'controller.stderr.log'
foreach ($unusedPath in @($controllerOut, $controllerErr, (Join-Path $recoveryRoot 'ownership.json'))) {
    if (Test-Path -LiteralPath $unusedPath) { throw "Recovery already attempted; preserve existing output: $unusedPath" }
}
$controllerProcess = Start-Process -FilePath $researchPython -ArgumentList @('-u', $controllerPath, '--run') -WorkingDirectory $workspaceRoot -WindowStyle Hidden -RedirectStandardOutput $controllerOut -RedirectStandardError $controllerErr -PassThru
$controllerProcess | Select-Object Id, StartTime, Path
