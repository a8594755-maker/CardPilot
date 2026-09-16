$ErrorActionPreference = 'Stop'
$followthroughBase = $PSScriptRoot
$researchWorkspace = 'C:\Users\a8594\CardPilot'
$researchPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$followthroughScript = Join-Path $followthroughBase 'terminal_followthrough.py'
$followthroughOut = Join-Path $followthroughBase 'followthrough.stdout.log'
$followthroughErr = Join-Path $followthroughBase 'followthrough.stderr.log'
foreach ($existingAttempt in @($followthroughOut, $followthroughErr, (Join-Path $followthroughBase 'followthrough_execution.json'))) {
    if (Test-Path -LiteralPath $existingAttempt) { throw "Prior attempt exists; preserve: $existingAttempt" }
}
if (!(Test-Path -LiteralPath (Join-Path $followthroughBase 'followthrough_qualification.json'))) { throw 'Qualification missing' }
$followthroughProcess = Start-Process -FilePath $researchPython -ArgumentList @('-B', '-u', $followthroughScript) -WorkingDirectory $researchWorkspace -WindowStyle Hidden -RedirectStandardOutput $followthroughOut -RedirectStandardError $followthroughErr -PassThru
$followthroughProcess | Select-Object Id, StartTime, Path
