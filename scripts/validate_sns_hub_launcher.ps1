$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$shortcutPath = Join-Path $repoRoot 'SNS허브_바로가기.lnk'
$vbsPath = Join-Path $repoRoot 'sns_hub.vbs'
$packageJsonPath = Join-Path $repoRoot 'package.json'
$readmePath = Join-Path $repoRoot 'README.md'

if (-not (Test-Path -LiteralPath $shortcutPath)) {
    throw "Missing shortcut: $shortcutPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
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
if ($vbsText -notmatch '/api/status') {
    throw "sns_hub.vbs does not reference /api/status"
}

if ($vbsText -notmatch 'taskkill') {
    throw "sns_hub.vbs does not contain port kill logic"
}

if ($vbsText -notmatch 'cmd\s+/c.*start' -and $vbsText -notmatch 'explorer\.exe') {
    throw "sns_hub.vbs does not contain a browser launch command"
}

$packageJson = Get-Content -LiteralPath $packageJsonPath -Raw | ConvertFrom-Json
if ($packageJson.scripts.view -ne 'wscript sns_hub.vbs') {
    throw "Unexpected package.json scripts.view: $($packageJson.scripts.view)"
}

$readmeText = Get-Content -LiteralPath $readmePath -Raw
foreach ($required in @('SNS허브_바로가기.lnk', 'sns_hub.vbs')) {
    if ($readmeText -notmatch [regex]::Escape($required)) {
        throw "README.md is missing: $required"
    }
}

Write-Host 'SNS hub launcher validation passed.'
