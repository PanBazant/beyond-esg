param(
  [int]$Port = 8000
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

  return $null
}

$stopped = $false
$portsToCheck = @($Port)

if (Test-Path $portInfoPath) {
  $recordedPort = Get-Content -LiteralPath $portInfoPath -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($recordedPort -and ($recordedPort -as [int])) {
    $portsToCheck += [int]$recordedPort
  }
}

if (Test-Path $pidPath) {
  $pidValue = Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pidValue -and ($pidValue -as [int])) {
    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    if ($process) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
      $stopped = $true
    }
  }
  Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

foreach ($candidatePort in ($portsToCheck | Select-Object -Unique)) {
  $listener = Get-BackendProcessOnPort -TargetPort $candidatePort
  if ($listener) {
    Stop-Process -Id $listener.ProcessId -Force -ErrorAction SilentlyContinue
    $stopped = $true
  }
}

if (Test-Path $portInfoPath) {
  Remove-Item -LiteralPath $portInfoPath -Force -ErrorAction SilentlyContinue
}

if ($stopped) {
  Write-Host "Backend zatrzymany." -ForegroundColor Green
} else {
  Write-Host "Nie znaleziono uruchomionego backendu na porcie $Port."
}
