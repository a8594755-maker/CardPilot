param(
  [int]$Port = 3460
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$url = "http://127.0.0.1:$Port"

function Test-PanelRunning {
  param([string]$TargetUrl)
  try {
    $res = Invoke-WebRequest -UseBasicParsing -Uri "$TargetUrl/api/status" -TimeoutSec 2
    return $res.StatusCode -eq 200
  } catch {
    return $false
  }
}

if (-not (Test-PanelRunning -TargetUrl $url)) {
  $launch = "Set-Location -LiteralPath '$root'; npm run self-play:panel"
  Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $launch) | Out-Null

  $deadline = (Get-Date).AddSeconds(12)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    if (Test-PanelRunning -TargetUrl $url) { break }
  }
}

Start-Process $url | Out-Null
