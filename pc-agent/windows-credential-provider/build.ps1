# Builds BioUnlockProvider.dll with the Visual Studio 2022 Build Tools.
param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$buildDir = Join-Path $root "build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "vcvars64.bat not found at $vcvars. Install Visual Studio 2022 Build Tools (Desktop C++)."
}

$src = Join-Path $root "src"
$def = Join-Path $root "BioUnlockProvider.def"
$opt = if ($Configuration -eq "Debug") { "/Od /Zi" } else { "/O2" }

$sources = @(
    "`"$src\dllmain.cpp`"",
    "`"$src\Provider.cpp`"",
    "`"$src\Ticket.cpp`""
) -join " "

$cl = "cl /nologo /LD /EHsc /std:c++17 /W4 /utf-8 /DUNICODE /D_UNICODE $opt " +
      "/I`"$src`" $sources /Fe:BioUnlockProvider.dll " +
      "/link /DEF:`"$def`" secur32.lib crypt32.lib shell32.lib shlwapi.lib ole32.lib advapi32.lib"

$command = "call `"$vcvars`" >nul && cd /d `"$buildDir`" && $cl"
cmd /c $command
if ($LASTEXITCODE -ne 0) {
    throw "Build failed with exit code $LASTEXITCODE"
}

Write-Host "Built $(Join-Path $buildDir 'BioUnlockProvider.dll')"
