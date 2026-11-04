$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python not found: $python"
}

Push-Location $root
try {
    & $python "desktop\main.py"
}
finally {
    Pop-Location
}

