param(
  [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$AuthHome = "$HOME\.config\auth",
  [string]$LegacyAuthDir = ""
)

$ErrorActionPreference = "Stop"

function Test-PathAny {
  param([Parameter(Mandatory = $true)][string]$Path)
  try {
    Get-Item -LiteralPath $Path -Force | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Remove-WithTrash {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (Test-PathAny $Path) {
    & trash $Path | Out-Null
  }
}

function Ensure-Dir {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Set-CompatLink {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Target
  )
  Ensure-Dir (Split-Path -Parent $Path)
  @'
import os
import pathlib
import sys
import uuid

link_path = pathlib.Path(sys.argv[1])
target_path = pathlib.Path(sys.argv[2]).resolve()
temp_link = link_path.with_name(f".{link_path.name}.{uuid.uuid4().hex}.tmp")
try:
    temp_link.symlink_to(target_path)
    os.replace(temp_link, link_path)
finally:
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
'@ | python - $Path $Target
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to refresh compat link: $Path"
  }
}

function Move-IfMissing {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Destination
  )
  if ((Test-PathAny $Source) -and -not (Test-PathAny $Destination)) {
    Ensure-Dir (Split-Path -Parent $Destination)
    Move-Item -LiteralPath $Source -Destination $Destination
  }
}

$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)
$AuthHome = [System.IO.Path]::GetFullPath($AuthHome)
if ($LegacyAuthDir) {
  $LegacyAuthDir = [System.IO.Path]::GetFullPath($LegacyAuthDir)
}

Ensure-Dir $AuthHome
Ensure-Dir (Join-Path $AuthHome "linkedin")
Ensure-Dir (Join-Path $AuthHome "threads")
Ensure-Dir (Join-Path $AuthHome "skool")
Ensure-Dir (Join-Path $AuthHome "x")

Copy-Item (Join-Path $SourceRoot "utils\auth_paths.py") (Join-Path $AuthHome "auth_paths.py") -Force
Copy-Item (Join-Path $SourceRoot "scripts\auth_runtime\renew.py") (Join-Path $AuthHome "renew.py") -Force
Copy-Item (Join-Path $SourceRoot "scripts\auth_runtime\export_x_artifacts.py") (Join-Path $AuthHome "export_x_artifacts.py") -Force

if ($LegacyAuthDir -and (Test-PathAny $LegacyAuthDir)) {
  Move-IfMissing (Join-Path $LegacyAuthDir "auth_linkedin.json") (Join-Path $AuthHome "linkedin\storage_state.json")
  Move-IfMissing (Join-Path $LegacyAuthDir "auth_threads.json") (Join-Path $AuthHome "threads\storage_state.json")
  Move-IfMissing (Join-Path $LegacyAuthDir "auth_skool.json") (Join-Path $AuthHome "skool\storage_state.json")

  if ((Test-PathAny (Join-Path $LegacyAuthDir "x_user_data")) -and -not (Test-PathAny (Join-Path $AuthHome "x\user_data"))) {
    Copy-Item -LiteralPath (Join-Path $LegacyAuthDir "x_user_data") -Destination (Join-Path $AuthHome "x\user_data") -Recurse -Force
  }

  Get-ChildItem -LiteralPath $LegacyAuthDir -Filter "x_cookies_*.json" -File -ErrorAction SilentlyContinue |
    ForEach-Object {
      Move-IfMissing $_.FullName (Join-Path $AuthHome ("x\" + $_.Name.Replace("x_", "")))
    }

  $legacyStorage = Get-ChildItem -LiteralPath $LegacyAuthDir -Filter "x_storage_state_*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    Select-Object -First 1
  if ($legacyStorage) {
    Move-IfMissing $legacyStorage.FullName (Join-Path $AuthHome "x\storage_state.json")
  }
}

Ensure-Dir (Join-Path $AuthHome "x\user_data")

$latestCookie = Get-ChildItem -LiteralPath (Join-Path $AuthHome "x") -Filter "cookies_*.json" -File -ErrorAction SilentlyContinue |
  Sort-Object Name -Descending |
  Select-Object -First 1

if ($latestCookie) {
  Set-CompatLink -Path (Join-Path $AuthHome "x\cookies.json") -Target $latestCookie.FullName
}

if (Test-PathAny (Join-Path $AuthHome "linkedin\storage_state.json")) {
  Set-CompatLink -Path (Join-Path $AuthHome "auth_linkedin.json") -Target (Join-Path $AuthHome "linkedin\storage_state.json")
}
if (Test-PathAny (Join-Path $AuthHome "threads\storage_state.json")) {
  Set-CompatLink -Path (Join-Path $AuthHome "auth_threads.json") -Target (Join-Path $AuthHome "threads\storage_state.json")
}
if (Test-PathAny (Join-Path $AuthHome "skool\storage_state.json")) {
  Set-CompatLink -Path (Join-Path $AuthHome "auth_skool.json") -Target (Join-Path $AuthHome "skool\storage_state.json")
}
if (Test-PathAny (Join-Path $AuthHome "x\cookies.json")) {
  Set-CompatLink -Path (Join-Path $AuthHome "x_cookies_current.json") -Target (Join-Path $AuthHome "x\cookies.json")
}
if (Test-PathAny (Join-Path $AuthHome "x\storage_state.json")) {
  Set-CompatLink -Path (Join-Path $AuthHome "x_storage_state_current.json") -Target (Join-Path $AuthHome "x\storage_state.json")
}

if ($LegacyAuthDir) {
  Remove-WithTrash $LegacyAuthDir
  New-Item -ItemType Junction -Path $LegacyAuthDir -Target $AuthHome | Out-Null
}

Write-Output "SYNC_OK"
