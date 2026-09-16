$ErrorActionPreference = 'Stop'
$actorRecoveryBase = $PSScriptRoot
$actorWorkspace = 'C:\Users\a8594\CardPilot'
$actorPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$actorScript = Join-Path $actorRecoveryBase 'resume_actor.py'
$actorOut = Join-Path $actorRecoveryBase 'controller_stdout.log'
$actorErr = Join-Path $actorRecoveryBase 'controller_stderr.log'
foreach ($actorExisting in @($actorOut, $actorErr, (Join-Path $actorRecoveryBase 'ownership.json'))) {
    if (Test-Path -LiteralPath $actorExisting) { throw "Preserve previous recovery attempt: $actorExisting" }
}
if (!(Test-Path -LiteralPath (Join-Path $actorRecoveryBase 'recovery_preflight.json'))) { throw 'Recovery qualification missing' }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$actorProcess = Start-Process -FilePath $actorPython -ArgumentList @('-B', '-u', $actorScript) -WorkingDirectory $actorWorkspace -WindowStyle Hidden -RedirectStandardOutput $actorOut -RedirectStandardError $actorErr -PassThru
$actorProcess | Select-Object Id, StartTime, Path
