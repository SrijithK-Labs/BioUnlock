# Installs the BioUnlock tray agent for the current user (no admin required).
#
#   powershell -ExecutionPolicy Bypass -File install-agent.ps1               # packaged .exe
#   powershell -ExecutionPolicy Bypass -File install-agent.ps1 -FromSource   # run from Python
#
# -FromSource installs a launcher that runs the agent with pythonw.exe instead
# of the packaged .exe. Use it when the machine's Windows Smart App Control
# blocks the unsigned .exe, or when you want to run straight from the repo.
#
# Adds the app to Start-up, creates a Start Menu shortcut, and (optionally)
# installs the Windows Credential Provider, which *does* need an elevation
# prompt.
[CmdletBinding()]
param(
    [string]$ExePath,
    [switch]$FromSource,
    [switch]$NoAutostart,
    [switch]$NoShortcut,
    [switch]$NoLaunch,
    [switch]$SkipCredentialProvider
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition

$installDir = Join-Path $env:LOCALAPPDATA "BioUnlock"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

if ($FromSource) {
    $projectDir = $root
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
        if ($python) { $pythonw = Join-Path (Split-Path $python) "pythonw.exe" }
    }
    if (-not $pythonw -or -not (Test-Path -LiteralPath $pythonw)) {
        throw "pythonw.exe was not found. Install Python 3.11+ and its dependencies first."
    }
    $target = Join-Path $installDir "biounlock-tray.cmd"
    $content = @"
@echo off
cd /d "$projectDir"
start "" "$pythonw" -m biounlock_agent tray
"@
    Set-Content -LiteralPath $target -Value $content -Encoding ASCII
    Write-Host "Installed source launcher -> $target"
    $runValue = "`"$target`""
    $launchExe = $target
    $launchArgs = @()
    $shortcutArgs = ""
    $shortcutWorkDir = $projectDir
}
else {
    if (-not $ExePath) {
        $candidates = @(
            (Join-Path $root "dist\BioUnlock.exe"),
            (Join-Path $root "BioUnlock.exe")
        )
        $ExePath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $ExePath -or -not (Test-Path -LiteralPath $ExePath)) {
        throw "Could not find BioUnlock.exe. Build it with build.ps1, pass -ExePath, or use -FromSource."
    }
    $target = Join-Path $installDir "BioUnlock.exe"
    Get-Process -Name "BioUnlock" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
    Copy-Item -LiteralPath $ExePath -Destination $target -Force
    Write-Host "Installed agent -> $target"
    $runValue = "`"$target`" tray"
    $launchExe = $target
    $launchArgs = @("tray")
    $shortcutArgs = "tray"
    $shortcutWorkDir = $installDir
}

# A source install and an .exe install write the same value name; make sure the
# tray process (pythonw for source mode) is stopped before switching.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "biounlock_agent" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (-not $NoAutostart) {
    $runKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    New-Item -Path $runKey -Force | Out-Null
    Set-ItemProperty -Path $runKey -Name "BioUnlock" -Value $runValue
    Write-Host "Enabled start-at-login for the current user."
}

if (-not $NoShortcut) {
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $shortcutPath = Join-Path $startMenu "BioUnlock.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launchExe
    $shortcut.Arguments = $shortcutArgs
    $shortcut.WorkingDirectory = $shortcutWorkDir
    $shortcut.Description = "BioUnlock phone unlock agent"
    $shortcut.Save()
    Write-Host "Created Start Menu shortcut -> $shortcutPath"
}

if (-not $SkipCredentialProvider) {
    $cpScript = Join-Path $root "windows-credential-provider\install.ps1"
    $cpDll = Join-Path $root "windows-credential-provider\build\BioUnlockProvider.dll"
    if ((Test-Path -LiteralPath $cpScript) -and (Test-Path -LiteralPath $cpDll)) {
        Write-Host "Installing the Windows Credential Provider (needs elevation)..."
        try {
            $proc = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @(
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$cpScript`""
            )
            if ($proc.ExitCode -ne 0) {
                Write-Warning "Credential Provider installer exited with code $($proc.ExitCode)."
            }
        }
        catch {
            Write-Warning "Skipped the Credential Provider install ($_)."
        }
    }
    else {
        Write-Host ""
        Write-Host "Credential Provider not installed (provider DLL not built)."
        Write-Host "To enable phone unlock at the Windows logon screen, build and install it:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File windows-credential-provider\build.ps1"
        Write-Host "  powershell -ExecutionPolicy Bypass -File windows-credential-provider\install.ps1"
    }
}

if (-not $NoLaunch) {
    if ($launchArgs.Count -gt 0) {
        Start-Process -FilePath $launchExe -ArgumentList $launchArgs
    }
    else {
        Start-Process -FilePath $launchExe
    }
    Write-Host "Started BioUnlock. Look for it in the system tray."
}

Write-Host ""
Write-Host "Done. Open the tray icon to enter your backend URL and link this PC."
