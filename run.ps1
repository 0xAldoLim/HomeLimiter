$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$launchArgs = @($args)

function Test-HomeLimiterPython([string]$Executable, [string[]]$Prefix) {
    try {
        & $Executable @Prefix -c 'import sys; sys.exit(not (sys.version_info.major == 3 and sys.version_info.minor >= 12))' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if ($env:OS -ne 'Windows_NT') {
    Write-Host 'This launcher is for Windows. On Linux, run ./run.sh.'
    exit 1
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        if (Test-Path -LiteralPath '.venv') {
            throw 'This .venv is incomplete or belongs to another OS. Rename it and run .\run.ps1 again.'
        }
        $installer = $null
        $installerArgs = @()
        if ($env:HOMELIMITER_PYTHON) {
            if (Test-HomeLimiterPython $env:HOMELIMITER_PYTHON @()) {
                $installer = $env:HOMELIMITER_PYTHON
            }
        } else {
            foreach ($name in @('py', 'python', 'python3')) {
                $candidate = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($candidate) {
                    $prefix = if ($name -eq 'py') { @('-3') } else { @() }
                    if (Test-HomeLimiterPython $candidate.Source $prefix) {
                        $installer = $candidate.Source
                        $installerArgs = @($prefix | Where-Object { $_ })
                        break
                    }
                }
            }
        }
        if (-not $installer) {
            throw 'Install Python 3.12 or newer from python.org, then reopen PowerShell. You can set HOMELIMITER_PYTHON to the full path of python.exe.'
        }
        & $installer @installerArgs -m venv '.venv'
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not create .venv. Check the Python installation, write access and free space.'
        }
    }

    if (-not (Test-HomeLimiterPython $pythonExe @())) {
        throw 'The local .venv needs a working Python 3.12 or newer. Rename .venv, then rerun .\run.ps1.'
    }
    & $pythonExe 'scripts\prepare.py'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $pythonExe -m homelimiter.cli @launchArgs
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine("HomeLimiter: $($_.Exception.Message)")
    exit 1
} finally {
    Pop-Location
}