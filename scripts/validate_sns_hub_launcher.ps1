$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$shortcutFile = Get-ChildItem -LiteralPath $repoRoot -Filter 'SNS*.lnk' | Select-Object -First 1
$vbsPath = Join-Path $repoRoot 'sns_hub.vbs'
$packageJsonPath = Join-Path $repoRoot 'package.json'
$readmePath = Join-Path $repoRoot 'README.md'

if (-not $shortcutFile) {
    throw "Missing SNS shortcut in: $repoRoot"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutFile.FullName)
$expectedTarget = [Environment]::ExpandEnvironmentVariables('%WINDIR%\System32\wscript.exe')
$expectedArguments = '"' + (Resolve-Path -LiteralPath $vbsPath).Path + '"'
$expectedWorkingDirectory = (Resolve-Path -LiteralPath $repoRoot).Path

if ($shortcut.TargetPath -ne $expectedTarget) {
    throw "Unexpected shortcut target: $($shortcut.TargetPath)"
}

if ($shortcut.Arguments -ne $expectedArguments) {
    throw "Unexpected shortcut arguments: $($shortcut.Arguments)"
}

if ($shortcut.WorkingDirectory -ne $expectedWorkingDirectory) {
    throw "Unexpected shortcut working directory: $($shortcut.WorkingDirectory)"
}

$vbsText = Get-Content -LiteralPath $vbsPath -Raw
if ($vbsText -notmatch 'restart_viewer_server\.ps1') {
    throw "sns_hub.vbs does not reference restart_viewer_server.ps1"
}

if ($vbsText -notmatch 'cmd\s+/c.*start' -and $vbsText -notmatch 'explorer\.exe') {
    throw "sns_hub.vbs does not contain a browser launch command"
}

$packageJson = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
if ($packageJson.scripts.view -ne 'wscript sns_hub.vbs') {
    throw "Unexpected package.json scripts.view: $($packageJson.scripts.view)"
}

$restartScriptPath = Join-Path $repoRoot 'scripts\restart_viewer_server.ps1'
$restartScriptText = Get-Content -LiteralPath $restartScriptPath -Raw
if ($restartScriptText -notmatch 'scrap_sns_server\.py') {
    throw "restart_viewer_server.ps1 does not reference scrap_sns_server.py"
}

$readmeText = Get-Content -LiteralPath $readmePath -Raw
foreach ($required in @('npm run view', 'sns_hub.vbs')) {
    if ($readmeText -notmatch [regex]::Escape($required)) {
        throw "README.md is missing: $required"
    }
}

Write-Host 'SNS hub launcher validation passed.'
