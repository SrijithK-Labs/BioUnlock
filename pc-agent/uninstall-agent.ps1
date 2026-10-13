# Uninstalls the BioUnlock tray agent for the current user (no admin required).
#
#   powershell -ExecutionPolicy Bypass -File uninstall-agent.ps1
#   powershell -ExecutionPolicy Bypass -File uninstall-agent.ps1 -KeepData
#   powershell -ExecutionPolicy Bypass -File uninstall-agent.ps1 -RemoveCredentialProvider
#
# Removes the running tray, the start-at-login entry, the Start Menu shortcut, and
# (unless -KeepData) the local data under %LOCALAPPDATA%\BioUnlock. It does NOT
# remove the Windows Credential Provider or a boot-start service by default, since
# both need elevation; pass -RemoveCredentialProvider or run uninstall-service.ps1.
[CmdletBinding()]
param(
    [switch]$KeepData,
    [switch]$RemoveCredentialProvider,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$installDir = Join-Path $env:LOCALAPPDATA "BioUnlock"

# 1. Stop the running tray (the packaged .exe and the source pythonw launcher).
Get-Process -Name "BioUnlock" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "biounlock_agent" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 300
Write-Host "Stopped the running tray."

# 2. Remove the start-at-login entry.
$runKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
try {
    if (Get-ItemProperty -Path $runKey -Name "BioUnlock" -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $runKey -Name "BioUnlock" -Force
        Write-Host "Removed the start-at-login entry."
    }
}
catch {
    Write-Warning "Could not update the Run key: $_"
}

# 3. Remove the Start Menu shortcut.
if (-not $NoShortcut) {
    $shortcutPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BioUnlock.lnk"
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "Removed the Start Menu shortcut -> $shortcutPath"
    }
}

# 4. Remove local data (exe, config, device key, credential, replay DB, logs).
if ($KeepData) {
    Write-Host "Kept local data -> $installDir"
}
elseif (Test-Path -LiteralPath $installDir) {
    Remove-Item -LiteralPath $installDir -Recurse -Force
    Write-Host "Removed local data -> $installDir"
}

# 5. Optionally remove the Credential Provider (needs elevation).
if ($RemoveCredentialProvider) {
    $cpUninstall = Join-Path $root "windows-credential-provider\uninstall.ps1"
    if (Test-Path -LiteralPath $cpUninstall) {
        Write-Host "Removing the Windows Credential Provider (needs elevation)..."
        try {
            $proc = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$cpUninstall`""
            )
            if ($proc.ExitCode -ne 0) {
                Write-Warning "Credential Provider uninstaller exited with code $($proc.ExitCode)."
            }
        }
        catch {
            Write-Warning "Did not remove the Credential Provider ($_)."
        }
    }
    else {
        Write-Warning "Could not find windows-credential-provider\uninstall.ps1."
    }
}

Write-Host ""
Write-Host "BioUnlock tray agent removed."
if (-not $RemoveCredentialProvider) {
    Write-Host "Note: to also remove the Windows Credential Provider (logon-screen unlock),"
    Write-Host "run this again with -RemoveCredentialProvider (needs admin)."
}
Write-Host "Note: if you installed the boot-start service, remove it separately (needs admin):"
Write-Host "  powershell -ExecutionPolicy Bypass -File uninstall-service.ps1"
Write-Host "Note: machine-wide data under $env:ProgramData\BioUnlock (if any) is left in place."
