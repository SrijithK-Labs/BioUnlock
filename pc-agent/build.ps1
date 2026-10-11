# Builds the BioUnlock tray agent into a single dist\BioUnlock.exe.
# Requires: Python 3.11+ with the agent requirements + pyinstaller installed.
[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition

Push-Location $root
try {
    if ($Clean) {
        foreach ($dir in @("build", "dist")) {
            $path = Join-Path $root $dir
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Recurse -Force
            }
        }
    }

    python -m pip install --disable-pip-version-check -q pyinstaller
    python -m PyInstaller --clean --noconfirm "BioUnlock.spec"

    $exe = Join-Path $root "dist\BioUnlock.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Build completed but $exe was not produced."
    }

    Write-Host ""
    Write-Host "Built $exe"
    Write-Host "Install it for the current user with:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File install-agent.ps1"
}
finally {
    Pop-Location
}
