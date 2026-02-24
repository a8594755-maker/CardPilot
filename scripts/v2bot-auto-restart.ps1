param(
  [int]$IntervalHours = 4
)

$ErrorActionPreference = "Stop"

$Root = "C:\Users\a8594\CardPilot"
$Artifacts = Join-Path $Root "artifacts"
$SelfPlayLog = Join-Path $Artifacts "selfplay-v2-auto-8srv.log"
$ManagerLog = Join-Path $Artifacts "v2bot-auto-restart.log"
$Ports = 4000..4009
$PortList = ($Ports -join ",")
$Shards = 6

function Write-Log {
  param([string]$Message)
  if (!(Test-Path $Artifacts)) {
    New-Item -ItemType Directory -Path $Artifacts -Force | Out-Null
  }
  if (!(Test-Path $ManagerLog)) {
    New-Item -ItemType File -Path $ManagerLog -Force | Out-Null
  }
  $line = "[{0}] [auto-restart] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $ManagerLog -Value $line
  Write-Output $line
}

function Stop-Processes {
  Write-Log "Stopping existing v2 self-play and game-server processes..."

  $selfPlayPids = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -match "self-play\.ts" -and $_.CommandLine -match "--mode train" -and $_.CommandLine -match "--version v2" } |
    Select-Object -ExpandProperty ProcessId -Unique

  $gameServerPids = Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -match "apps[\\/]+game-server[\\/]+src[\\/]+server\.ts" -or $_.CommandLine -match "@cardpilot/game-server" } |
    Select-Object -ExpandProperty ProcessId -Unique

  $all = @($selfPlayPids + $gameServerPids | Select-Object -Unique)
  if ($all.Count -gt 0) {
    $all | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Write-Log ("Stopped PIDs: " + ($all -join ", "))
  } else {
    Write-Log "No existing matching processes found."
  }
}

function Start-GameServers {
  Write-Log ("Starting game servers on ports: " + $PortList)
  foreach ($p in $Ports) {
    $serverLog = Join-Path $Artifacts ("game-server-{0}.log" -f $p)
    $cmd = "set PORT=$p&&npm run dev -w @cardpilot/game-server >> `"$serverLog`" 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory $Root
  }

  $deadline = (Get-Date).AddSeconds(45)
  do {
    Start-Sleep -Seconds 2
    $listening = 0
    foreach ($p in $Ports) {
      $hit = netstat -ano | Select-String -SimpleMatch (":$p")
      if ($hit) { $listening++ }
    }
    if ($listening -ge $Ports.Count) {
      Write-Log "All game server ports are listening."
      return
    }
  } while ((Get-Date) -lt $deadline)

  Write-Log "Warning: some ports are not listening yet, continuing startup."
}

function Start-SelfPlay {
  Write-Log "Starting self-play v2 training (8 servers / 8 shards)..."
  $cmd = @(
    "set PREFLOP_KEEP_EVERY=4&&",
    "set EV_TRAIN_MC_ITERS=4&&",
    "set EV_TRAIN_MC_MS=0&&",
    "npx tsx apps/bot-client/src/self-play.ts",
    "--mode train",
    "--version v2",
    "--servers $PortList",
    "--shards $Shards",
    "--max-rooms-per-server 36",
    "--train-every 50000",
    "--target 5000000",
    "--min-rate 60000",
    "--min-rate-grace-min 4",
    "--recover-rooms 1",
    "--recover-cooldown-min 5",
    "--quality-cooldown-min 2",
    ">> `"$SelfPlayLog`" 2>&1"
  ) -join " "

  Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory $Root
  Write-Log "Self-play launch command submitted."
}

function Restart-Training {
  Write-Log "=== Restart cycle begin ==="
  Stop-Processes
  Start-Sleep -Seconds 2
  Start-GameServers
  Start-Sleep -Seconds 3
  Start-SelfPlay
  Write-Log "=== Restart cycle end ==="
}

Write-Log ("Auto-restart manager started (interval: {0}h)." -f $IntervalHours)
while ($true) {
  Restart-Training
  Write-Log ("Sleeping for {0} hours..." -f $IntervalHours)
  Start-Sleep -Seconds ($IntervalHours * 3600)
}
