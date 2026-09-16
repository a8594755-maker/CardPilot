$ErrorActionPreference = 'Stop'
$actorRunBase = $PSScriptRoot
$actorWorkspace = 'C:\Users\a8594\CardPilot'
$actorPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$actorScript = Join-Path $actorRunBase 'run_actor_control.py'
$actorOut = Join-Path $actorRunBase 'controller_stdout.log'
$actorErr = Join-Path $actorRunBase 'controller_stderr.log'
foreach ($actorExisting in @($actorOut, $actorErr, (Join-Path $actorRunBase 'ownership.json'))) {
    if (Test-Path -LiteralPath $actorExisting) { throw "Preserve previous attempt: $actorExisting" }
}
if (!(Test-Path -LiteralPath (Join-Path $actorRunBase 'controller_tests_final.xml'))) { throw 'Controller tests missing' }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$actorProcess = Start-Process -FilePath $actorPython -ArgumentList @('-B', '-u', $actorScript) -WorkingDirectory $actorWorkspace -WindowStyle Hidden -RedirectStandardOutput $actorOut -RedirectStandardError $actorErr -PassThru
$actorProcess | Select-Object Id, StartTime, Path
