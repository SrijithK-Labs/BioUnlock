# Requires elevation: stops and removes the BioUnlock boot-start service and
# removes the machine-wide marker (the shared data under %ProgramData%\BioUnlock
# is left in place; delete it manually if you want a clean slate).
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SERVICE_NAME = "BioUnlockAgent"

$service = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne "Stopped") {
        Stop-Service $SERVICE_NAME -Force
    }
    Push-Location $root
    try {
        & $Python -m biounlock_agent.service remove
    }
    finally {
        Pop-Location
    }
    Write-Host "Service '$SERVICE_NAME' removed."
}
else {
    Write-Host "Service '$SERVICE_NAME' is not installed."
}

$marker = Join-Path $env:ProgramData "BioUnlock\service.json"
if (Test-Path -LiteralPath $marker) {
    Remove-Item -LiteralPath $marker -Force
    Write-Host "Removed service marker -> $marker"
}

try {
    $siteDir = & $Python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    if ($siteDir) {
        $pth = Join-Path $siteDir "biounlock-agent.pth"
        if (Test-Path -LiteralPath $pth) {
            Remove-Item -LiteralPath $pth -Force
            Write-Host "Removed import path -> $pth"
        }
    }
}
catch {
    Write-Warning "Could not remove the import .pth file: $_"
}

Write-Host ""
Write-Host "The agent now runs only in your user session again. Re-link the tray if needed:"
Write-Host "  (open BioUnlock tray -> Link this PC)"
