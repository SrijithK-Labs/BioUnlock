# Requires elevation: removes the COM registration and credential provider key.
#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$clsid = "{B10F7A5E-3C41-4E9A-9F2B-7D6C1A2E3F40}"

Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "HKLM:\SOFTWARE\Classes\CLSID\$clsid" -Recurse -Force -ErrorAction SilentlyContinue

$installDir = Join-Path $env:ProgramFiles "BioUnlock"
if (Test-Path -LiteralPath $installDir) {
    Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "BioUnlock Credential Provider uninstalled."
Write-Host "The stored Windows credential (if any) remains under %LOCALAPPDATA%\BioUnlock and can be removed with:"
Write-Host "  python -m biounlock_agent clear-credential"
Write-Host ""
Write-Host "Emergency recovery (if the logon UI ever misbehaves): boot to Safe Mode and run this script;"
Write-Host "the normal password tile is never removed, so you can always sign in with your password."
