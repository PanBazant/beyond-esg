param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8000,
  [switch]$Restart,
  [switch]$AutoPort
)

$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $rootDir "backend"
$pidPath = Join-Path $backendDir ".uvicorn.pid"
$portInfoPath = Join-Path $backendDir ".app-port"

function Get-BackendProcessOnPort {
  param([int]$TargetPort)

  $netstatLine = netstat -ano -p TCP | Select-String -Pattern "127.0.0.1:$TargetPort\s+.*LISTENING\s+(\d+)" | Select-Object -First 1
  if (-not $netstatLine) {
    return $null
  }

  $matches = [regex]::Match($netstatLine.Line, "LISTENING\s+(\d+)\s*$")
  if (-not $matches.Success) {
    return $null
  }

  $processId = [int]$matches.Groups[1].Value

  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if (-not $process) {
    return $null
  }

  if ($process.ProcessName -eq "python") {
    return [pscustomobject]@{
      ProcessId = $processId
      ProcessName = $process.ProcessName
    }
  }

  return [pscustomobject]@{
    ProcessId = $processId
    ProcessName = $process.ProcessName
    Foreign = $true
  }
}

function Test-PortOccupied {
  param([int]$TargetPort)
  return [bool](netstat -ano -p TCP | Select-String -Pattern "127.0.0.1:$TargetPort\s+.*LISTENING")
}

function Resolve-TargetPort {
  param(
    [int]$PreferredPort,
    [bool]$AllowAutoPort
  )

  if (-not (Test-PortOccupied -TargetPort $PreferredPort)) {
    return $PreferredPort
  }

  if (-not $AllowAutoPort) {
    return $PreferredPort
  }

  foreach ($candidate in @($PreferredPort, 8010, 8020, 8080, 8090)) {
    if (-not (Test-PortOccupied -TargetPort $candidate)) {
      return $candidate
    }
  }

  throw "Nie znaleziono wolnego portu w puli 8000/8010/8020/8080/8090."
}

function Wait-ForHealth {
  param(
    [string]$Url,
    [int]$TimeoutSeconds = 20
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -eq 200) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  return $false
}

$existing = Get-BackendProcessOnPort -TargetPort $Port
$healthUrl = "http://$HostName`:$Port/api/v1/health"
if ($existing -and -not $Restart) {
  if ($existing.Foreign) {
    throw "Port $Port jest zajety przez inny proces (PID $($existing.ProcessId)). Uruchom .\stop_app.ps1 albo zmien port."
  }

  if (Wait-ForHealth -Url $healthUrl -TimeoutSeconds 3) {
    Write-Host "Aplikacja juz dziala pod http://$HostName`:$Port" -ForegroundColor Green
    Write-Host "API health: $healthUrl"
    exit 0
  }
}

if ($existing -and $existing.Foreign) {
  if (-not $AutoPort) {
    throw "Port $Port jest zajety przez inny proces (PID $($existing.ProcessId)). Uzyj .\\start_app.ps1 -AutoPort albo zmien port."
  }
}

if ($existing -and -not $existing.Foreign) {
  Stop-Process -Id $existing.ProcessId -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
}

if (Test-Path $pidPath) {
  Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

$targetPort = Resolve-TargetPort -PreferredPort $Port -AllowAutoPort ([bool]$AutoPort)
$healthUrl = "http://$HostName`:$targetPort/api/v1/health"
$process = Start-Process python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", $HostName, "--port", "$targetPort" -WorkingDirectory $backendDir -PassThru
Set-Content -LiteralPath $pidPath -Value $process.Id
Set-Content -LiteralPath $portInfoPath -Value $targetPort

if (-not (Wait-ForHealth -Url $healthUrl -TimeoutSeconds 20)) {
  throw "Backend nie odpowiedzial poprawnie pod $healthUrl po starcie."
}

Write-Host "Backend uruchomiony pod http://$HostName`:$targetPort" -ForegroundColor Green
Write-Host "Frontend jest serwowany z tego samego adresu."
Write-Host "PID: $($process.Id)"
