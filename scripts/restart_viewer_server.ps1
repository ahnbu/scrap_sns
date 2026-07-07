param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$Port = 5000,
    [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

function Test-JsonEndpoint {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
        if ($response.StatusCode -ne 200) {
            return $false
        }
        $contentType = [string]$response.Headers["Content-Type"]
        if ($contentType -notmatch "application/json") {
            return $false
        }
        $null = $response.Content | ConvertFrom-Json
        return $true
    } catch {
        return $false
    }
}

function Test-ViewerServerReady {
    $baseUrl = "http://$HostName`:$Port"
    return (
        (Test-JsonEndpoint "$baseUrl/api/status") -and
        (Test-JsonEndpoint "$baseUrl/api/get-tag-catalog")
    )
}

function Get-ListeningProcessIds {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
}

function Stop-ViewerServerOnPort {
    $processIds = @(Get-ListeningProcessIds)
    foreach ($processId in $processIds) {
        if (-not $processId) {
            continue
        }

        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $commandLine = [string]$processInfo.CommandLine
        if ($commandLine -notmatch "scrap_sns_server\.py") {
            throw "Port $Port is used by PID $processId, but it does not look like scrap_sns_server.py. CommandLine: $commandLine"
        }

        Stop-Process -Id $processId -Force
    }
}

function Start-ViewerServer {
    Start-Process `
        -FilePath "python" `
        -ArgumentList "scrap_sns_server.py" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden | Out-Null
}

Stop-ViewerServerOnPort
Start-ViewerServer

for ($attempt = 1; $attempt -le 12; $attempt += 1) {
    Start-Sleep -Seconds 1
    if (Test-ViewerServerReady) {
        Write-Output "Viewer server restarted on port $Port."
        exit 0
    }
}

throw "Viewer server did not become ready on port $Port."
