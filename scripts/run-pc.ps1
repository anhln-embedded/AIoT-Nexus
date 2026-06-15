$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$main = Join-Path $projectDir "main.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing virtual environment: $python"
}

$env:AIOT_IS_PI = "false"
$env:AIOT_USE_UART = "false"
$env:AIOT_DISPLAY_WIDTH = "1280"
$env:AIOT_DISPLAY_HEIGHT = "800"

Set-Location -LiteralPath $projectDir
& $python $main
