$ErrorActionPreference = 'Stop'
$scaleWorkspace = 'C:\Users\a8594\CardPilot'
$scalePython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
foreach ($scaleName in @('ownership.json','controller.stdout.log','controller.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot $scaleName)) { throw "Preserve prior attempt: $scaleName" }
}
$scaleQualification = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'qualification.json') | ConvertFrom-Json
if (!$scaleQualification.passed) { throw 'Qualification not passed' }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$scaleProcess = Start-Process -FilePath $scalePython -ArgumentList @('-B','-u',(Join-Path $PSScriptRoot 'run_scale.py')) -WorkingDirectory $scaleWorkspace -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'controller.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'controller.stderr.log') -PassThru
$scaleProcess | Select-Object Id,StartTime,Path

