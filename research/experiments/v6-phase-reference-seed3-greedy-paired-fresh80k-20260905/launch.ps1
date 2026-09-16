$ErrorActionPreference = 'Stop'
$externalBase = $PSScriptRoot
$researchWorkspace = 'C:\Users\a8594\CardPilot'
$researchPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$pairController = Join-Path $externalBase 'run_pair.py'
$pairOut = Join-Path $externalBase 'controller.stdout.log'
$pairErr = Join-Path $externalBase 'controller.stderr.log'
foreach ($priorOutput in @($pairOut, $pairErr, (Join-Path $externalBase 'execution.json'))) {
    if (Test-Path -LiteralPath $priorOutput) { throw "Prior attempt exists; do not restart: $priorOutput" }
}
if (!(Test-Path -LiteralPath (Join-Path $externalBase 'preparation_report.json'))) { throw 'Offline preparation missing' }
& $researchPython -B $pairController --experiment-dir $externalBase --preflight-only
if ($LASTEXITCODE -ne 0) { throw 'Final admission check failed before launch' }
$pairProcess = Start-Process -FilePath $researchPython -ArgumentList @('-u', $pairController, '--experiment-dir', $externalBase) -WorkingDirectory $researchWorkspace -WindowStyle Hidden -RedirectStandardOutput $pairOut -RedirectStandardError $pairErr -PassThru
$pairProcess | Select-Object Id, StartTime, Path
