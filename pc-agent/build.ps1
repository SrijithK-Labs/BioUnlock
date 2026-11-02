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

    # Build the native Credential Provider first so it can be bundled into the
    # .exe (the installer registers it). Requires VS Build Tools; if it is
    # missing, the .exe still builds without logon-screen unlock.
    $cpBuild = Join-Path $root "windows-credential-provider\build.ps1"
    $cpDll = Join-Path $root "windows-credential-provider\build\BioUnlockProvider.dll"
    if ((Test-Path -LiteralPath $cpBuild) -and -not (Test-Path -LiteralPath $cpDll)) {
        Write-Host "Building the Windows Credential Provider..."
        try {
            & powershell -ExecutionPolicy Bypass -File $cpBuild
        }
        catch {
            Write-Warning "Credential Provider build failed; shipping without logon-screen unlock."
        }
    }
    if (Test-Path -LiteralPath $cpDll) {
        Write-Host "Bundling the Credential Provider into the .exe."
    }
    else {
        Write-Warning "Credential Provider DLL not found; the .exe will not include logon-screen unlock."
    }

    python -m PyInstaller --clean --noconfirm "BioUnlock.spec"

    $exe = Join-Path $root "dist\BioUnlock.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Build completed but $exe was not produced."
    }

    Write-Host ""
    Write-Host "Built $exe"
    Write-Host "Install it by running the .exe (it self-installs), or:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File install-agent.ps1"
}
finally {
    Pop-Location
}
