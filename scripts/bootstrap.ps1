param([switch]$Dev, [switch]$Demo, [switch]$Launch)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12+ and ensure python is on PATH.' }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    $pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $cliExe = Join-Path $projectRoot '.venv\Scripts\homelimiter.exe'
    $package = if ($Dev) { '.[dev]' } else { '.' }
    & $pythonExe -m pip install -e $package
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    $modeArgs = if ($Demo) { @('--demo') } else { @() }
    & $cliExe @modeArgs init
    if ($LASTEXITCODE -ne 0) { throw 'Private state initialization failed.' }
    Write-Host "Ready. Read your local admin credential with: $cliExe $modeArgs token"
    if ($Launch) { & $cliExe @modeArgs dashboard }
} finally {
    Pop-Location
}
