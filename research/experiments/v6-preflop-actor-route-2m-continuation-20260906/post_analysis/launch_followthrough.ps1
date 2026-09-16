$ErrorActionPreference = 'Stop'
$followPython = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
foreach ($followName in @('followthrough_execution.json','followthrough.stdout.log','followthrough.stderr.log')) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot $followName)) { throw "Preserve previous helper: $followName" }
}
$followProcess = Start-Process -FilePath $followPython -ArgumentList @('-B','-u',(Join-Path $PSScriptRoot 'terminal_followthrough.py')) -WorkingDirectory 'C:\Users\a8594\CardPilot' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'followthrough.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'followthrough.stderr.log') -PassThru
$followProcess | Select-Object Id,StartTime,Path

