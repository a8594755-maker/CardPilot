$ErrorActionPreference = 'Stop'
$seed3Base = $PSScriptRoot
$researchWorkspace = 'C:\Users\a8594\CardPilot'
$researchPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$seed3Controller = Join-Path $seed3Base 'run_control.py'
$seed3Out = Join-Path $seed3Base 'controller.stdout.log'
$seed3Err = Join-Path $seed3Base 'controller.stderr.log'
foreach ($seed3Previous in @($seed3Out, $seed3Err, (Join-Path $seed3Base 'ownership.json'))) {
    if (Test-Path -LiteralPath $seed3Previous) { throw "Previous controller attempt exists; preserve: $seed3Previous" }
}
if (!(Test-Path -LiteralPath (Join-Path $seed3Base 'qualification_result.json'))) { throw 'Qualification missing' }
$seed3Process = Start-Process -FilePath $researchPython -ArgumentList @('-u', $seed3Controller) -WorkingDirectory $researchWorkspace -WindowStyle Hidden -RedirectStandardOutput $seed3Out -RedirectStandardError $seed3Err -PassThru
$seed3Process | Select-Object Id, StartTime, Path
