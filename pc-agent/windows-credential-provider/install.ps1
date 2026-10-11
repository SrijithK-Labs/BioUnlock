# Requires elevation: registers a COM in-proc server and a credential provider.
#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$sourceDll = Join-Path $root "build\BioUnlockProvider.dll"
if (-not (Test-Path -LiteralPath $sourceDll)) {
    throw "Build the provider first: powershell -ExecutionPolicy Bypass -File build.ps1"
}

$clsid = "{B10F7A5E-3C41-4E9A-9F2B-7D6C1A2E3F40}"

$installDir = Join-Path $env:ProgramFiles "BioUnlock"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$targetDll = Join-Path $installDir "BioUnlockProvider.dll"
Copy-Item -LiteralPath $sourceDll -Destination $targetDll -Force
Write-Host "Installed DLL -> $targetDll"

# Shared ticket directory: SYSTEM/Administrators full, Users modify so the
# per-user agent can drop and clear its short-lived ticket.
$sharedDir = Join-Path $env:ProgramData "BioUnlock"
New-Item -ItemType Directory -Force -Path $sharedDir | Out-Null
icacls $sharedDir /inheritance:r /grant "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-32-545:(OI)(CI)M" | Out-Null
Write-Host "Prepared shared directory -> $sharedDir"

# COM in-proc server (64-bit view; LogonUI is 64-bit on 64-bit Windows).
$clsidKey = "HKLM:\SOFTWARE\Classes\CLSID\$clsid"
New-Item -Path $clsidKey -Force | Out-Null
Set-ItemProperty -Path $clsidKey -Name "(default)" -Value "BioUnlock Credential Provider"
New-Item -Path "$clsidKey\InprocServer32" -Force | Out-Null
Set-ItemProperty -Path "$clsidKey\InprocServer32" -Name "(default)" -Value $targetDll
Set-ItemProperty -Path "$clsidKey\InprocServer32" -Name "ThreadingModel" -Value "Apartment"

# Register the credential provider with the logon UI.
$cpKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$clsid"
New-Item -Path $cpKey -Force | Out-Null
Set-ItemProperty -Path $cpKey -Name "(default)" -Value "BioUnlock"

Write-Host ""
Write-Host "BioUnlock Credential Provider installed (added, not replacing the password tile)."
Write-Host "Enroll your Windows credential as your own user:"
Write-Host "  python -m biounlock_agent set-credential"
