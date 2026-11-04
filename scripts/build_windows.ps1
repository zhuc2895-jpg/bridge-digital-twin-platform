[CmdletBinding()]
param(
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"
$backend = Join-Path $root "backend"
$desktopEntry = Join-Path $root "desktop\main.py"
$distRoot = Join-Path $root "dist-windows"
$workRoot = Join-Path $root ".build\pyinstaller"
$appDir = Join-Path $distRoot "BridgeDigitalTwin"

function Assert-WithinRoot([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $rootPrefix = $root.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the repository: $resolved"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment Python not found: $python"
}
if (-not (Test-Path -LiteralPath $desktopEntry)) {
    throw "Desktop entry point not found: $desktopEntry"
}

if (-not $SkipFrontendBuild) {
    Push-Location $frontend
    try {
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend "dist\index.html"))) {
    throw "frontend/dist/index.html is missing"
}

& $python -m pip install -r (Join-Path $backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed" }
& $python -m pip install -r (Join-Path $root "desktop\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed" }

foreach ($target in @($distRoot, $workRoot)) {
    Assert-WithinRoot $target
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

$addData = "$frontend\dist;frontend\dist"
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name BridgeDigitalTwin `
    --distpath $distRoot `
    --workpath $workRoot `
    --specpath $workRoot `
    --paths $backend `
    --add-data $addData `
    --collect-all webview `
    --collect-submodules uvicorn `
    --hidden-import app.main `
    --hidden-import sklearn.utils._typedefs `
    --hidden-import sklearn.neighbors._partition_nodes `
    $desktopEntry

if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exe = Join-Path $appDir "BridgeDigitalTwin.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Expected executable was not produced: $exe"
}

$smoke = Start-Process `
    -FilePath $exe `
    -ArgumentList "--headless-smoke" `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
if ($smoke.ExitCode -ne 0) {
    throw "Packaged desktop smoke test failed with exit code $($smoke.ExitCode)"
}

$zipPath = Join-Path $distRoot "BridgeDigitalTwin-windows-x64.zip"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
$archived = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Compress-Archive -Path $appDir -DestinationPath $zipPath -CompressionLevel Optimal
        $archived = $true
        break
    }
    catch {
        if ($attempt -eq 5) { throw }
        Start-Sleep -Seconds 2
    }
}
if (-not $archived) { throw "Could not archive the Windows application" }

Write-Host ""
Write-Host "Windows application built successfully:"
Write-Host "  Executable: $exe"
Write-Host "  Archive:    $zipPath"
