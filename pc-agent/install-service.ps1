# Requires elevation: installs the BioUnlock agent as a boot-start Windows
# service so the paired phone can unlock the PC at the sign-in screen, before
# anyone logs in. Also switches the agent to the machine-wide, machine-scope
# store under %ProgramData%\BioUnlock.
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SERVICE_NAME = "BioUnlockAgent"

$sharedDir = Join-Path $env:ProgramData "BioUnlock"
New-Item -ItemType Directory -Force -Path $sharedDir | Out-Null

# SYSTEM + Administrators full, Users modify: the service (SYSTEM) and the
# in-session tray must both read/write the config, device key and ticket here.
icacls $sharedDir /inheritance:r `
    /grant "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)M" |
    Out-Null

# Marker read by config.service_mode(): the installed agent uses this shared
# home and DPAPI machine-scope secrets.
$marker = Join-Path $sharedDir "service.json"
@{ installedAt = (Get-Date).ToString("o"); user = $env:USERNAME } |
    ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
Write-Host "Wrote service marker -> $marker"

Push-Location $root
try {
    # pywin32's pythonservice.exe runs with the interpreter's own path, so make
    # the project importable there via a .pth file in site-packages.
    $siteDir = & $Python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    if (-not $siteDir) { throw "Could not locate the site-packages directory for '$Python'." }
    $pth = Join-Path $siteDir "biounlock-agent.pth"
    Set-Content -LiteralPath $pth -Value $root -Encoding ASCII
    Write-Host "Registered import path -> $pth"

    Write-Host "Registering the '$SERVICE_NAME' service (running as LocalSystem)..."
    & $Python -m biounlock_agent.service install
    if ($LASTEXITCODE -ne 0) { throw "Service install failed (exit $LASTEXITCODE)." }

    # Start automatically at boot, before any user logs in.
    & sc.exe config $SERVICE_NAME start= auto | Out-Null
    & sc.exe failure $SERVICE_NAME reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    Start-Service $SERVICE_NAME
    Write-Host "Service '$SERVICE_NAME' installed and started."
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Next steps (as your normal user, not elevated):"
Write-Host "  1. Open the BioUnlock tray and 'Link this PC' again, then scan with your phone."
Write-Host "     (Install switches to the shared home, so it needs a fresh link.)"
Write-Host "  2. Re-run: python -m biounlock_agent set-credential   to store your Windows password."
Write-Host "  3. Reboot and try unlocking from the phone at the sign-in screen."
