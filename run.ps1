#Requires -Version 5.1
<#
.SYNOPSIS
    The one script for RusNet: auto-installs any missing prerequisites via winget, then
    builds and deploys both halves to C:\Apps\RusNet, and optionally launches the app.

.DESCRIPTION
    C:\Apps\RusNet\
      rusnet\      a vendored copy of this repo's rusnet\ Python package. RusNet.Viewer
                   .exe's Scan button walks up from its own folder looking for
                   rusnet\__main__.py (see FindRepoRoot in MainWindow.xaml.cs); this is
                   what lets Scan work from the deployed app with no RUSNET_HOME needed.
      Windows\     RusNet.Viewer.exe, published from dotnet\RusNet.Viewer\RusNet.Viewer.csproj.
      Python\      a standalone venv (.venv) with the rusnet package installed (desktop +
                   interfaces extras), plus rusnet.bat / rusnet-desktop.bat launchers that
                   activate it and forward arguments. Independent of this repo once deployed.
      run.bat      regenerated on every run; a desktop shortcut can point at it. Double-clicked it
                   opens a menu: 1) Deploy & Run reruns this script with -Force, then opens the
                   viewer; 2) Run opens the deployed viewer without calling this script. This
                   script itself never prompts, so agents and /deploy can run it unattended.

    Missing prerequisites (the .NET SDK, Python 3.9+, the Edge WebView2 runtime) are
    installed with winget, using the same silent posture and mid-process PATH refresh as
    MindAttic.Launcher's setup.ps1. If winget isn't available, this script says what to
    install by hand and stops.

    Without -Force each half republishes only when its output is missing or a source
    file is newer than it, so a plain `run.ps1` is a fast no-op. Whenever a half DOES
    republish, its old install location is wiped first (Windows\ contents; the Python
    venv) so a deploy never leaves stale files from a previous version behind.

.PARAMETER Force
    Rebuild the Windows app and reinstall the Python venv even if nothing looks changed.

.PARAMETER Launch
    After deploying, launch RusNet.Viewer.exe.

.PARAMETER LauncherOnly
    Only write C:\Apps\RusNet\run.bat, then exit: nothing is synced, built, stopped or installed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File run.ps1
    powershell -ExecutionPolicy Bypass -File run.ps1 -Force -Launch
#>
param(
    [switch]$Force,
    [switch]$Launch,
    [switch]$LauncherOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo        = $PSScriptRoot
$deployRoot  = 'C:\Apps\RusNet'
$sharedPy    = Join-Path $deployRoot 'rusnet'
$winDir      = Join-Path $deployRoot 'Windows'
$pyDir       = Join-Path $deployRoot 'Python'
$pyVenv      = Join-Path $pyDir '.venv'
$launcherBat = Join-Path $deployRoot 'run.bat'
$staleBat    = Join-Path $deployRoot 'deploy.bat'   # the launcher's name before the deploy -> run rename (MAT-T68)

$repoRusnet  = Join-Path $repo 'rusnet'
$winProj     = Join-Path $repo 'dotnet\RusNet.Viewer\RusNet.Viewer.csproj'
$winProjDir  = Join-Path $repo 'dotnet\RusNet.Viewer'
$winExe      = Join-Path $winDir 'RusNet.Viewer.exe'
$winExts     = @('.cs', '.csproj', '.xaml', '.manifest', '.htm', '.html', '.css', '.js')
$pyStamp     = Join-Path $pyDir '.installed'
$pySourceExts = @('.py', '.csv', '.css', '.js', '.htm', '.html')

function Test-OnPath([string]$cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# The MindAttic house pattern (see MindAttic.Launcher\setup.ps1): install a missing tool with
# winget, then re-read PATH from the registry so it's usable without opening a new shell.
function Install-ViaWingetIfMissing([string]$cmd, [string]$wingetId, [string]$label) {
    if (Test-OnPath $cmd) { return $true }
    if (-not (Test-OnPath 'winget')) {
        Write-Host "$label not found and winget is unavailable - install $label manually." -ForegroundColor Red
        return $false
    }
    Write-Host "$label not found - installing via winget ($wingetId)..." -ForegroundColor Yellow
    winget install --id $wingetId -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
    if (Test-OnPath $cmd) { Write-Host "$label installed" -ForegroundColor Green; return $true }
    Write-Host "Could not auto-install $label (winget failed)." -ForegroundColor Red
    return $false
}

# WebView2 runtime isn't a PATH command, so detect it by its EdgeUpdate client registry key.
function Test-WebView2 {
    $guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach ($p in @(
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid",
            "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid",
            "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid")) {
        $pv = (Get-ItemProperty -Path $p -Name pv -ErrorAction SilentlyContinue).pv
        if ($pv -and $pv -ne '0.0.0.0') { return $true }
    }
    return $false
}

function Resolve-Python {
    if (Test-OnPath 'py')     { return @{ Exe = 'py'; Pre = @('-3') } }
    if (Test-OnPath 'python') { return @{ Exe = 'python'; Pre = @() } }
    return $null
}

function Get-NewestWriteUtc([string]$dir, [string[]]$exts) {
    $newest = Get-ChildItem -Path $dir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notmatch '\\(bin|obj|__pycache__)\\' -and
            ($exts -contains $_.Extension.ToLowerInvariant())
        } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($newest) { return $newest.LastWriteTimeUtc }
    return [datetime]::MinValue
}

# ── Shared rusnet source (what RusNet.Viewer.exe's Scan button finds) ──────────
function Sync-SharedSource {
    New-Item -ItemType Directory -Force -Path $sharedPy | Out-Null
    robocopy $repoRusnet $sharedPy /MIR /NFL /NDL /NJH /NJS /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed syncing rusnet -> $sharedPy (exit $LASTEXITCODE)" }
}

# ── Windows (.NET WebView2) half ────────────────────────────────────────────
function Test-WindowsNeedsPublish {
    if (-not (Test-Path $winExe)) { return $true }
    $exeTime = (Get-Item $winExe).LastWriteTimeUtc
    return (Get-NewestWriteUtc $winProjDir $winExts) -gt $exeTime
}

function Stop-RusNetViewer {
    $procs = @(Get-Process -Name 'RusNet.Viewer' -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) { return }
    Write-Host "Closing running RusNet.Viewer ($($procs.Count))..." -ForegroundColor Yellow
    foreach ($p in $procs) {
        try { if ($p.MainWindowHandle -ne [IntPtr]::Zero) { [void]$p.CloseMainWindow() } } catch { }
    }
    foreach ($p in $procs) { try { [void]$p.WaitForExit(5000) } catch { } }
    foreach ($p in @(Get-Process -Name 'RusNet.Viewer' -ErrorAction SilentlyContinue)) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; [void]$p.WaitForExit(3000) } catch { }
    }
}

function Publish-Windows {
    if (-not (Install-ViaWingetIfMissing 'dotnet' 'Microsoft.DotNet.SDK.10' '.NET SDK')) {
        throw "The .NET 10 SDK is required to build the Windows app."
    }
    if (Test-WebView2) {
        Write-Host "Edge WebView2 runtime found" -ForegroundColor Green
    } elseif (Test-OnPath 'winget') {
        Write-Host "Edge WebView2 runtime not found - installing via winget..." -ForegroundColor Yellow
        winget install --id Microsoft.EdgeWebView2Runtime -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
        if (Test-WebView2) { Write-Host "WebView2 runtime installed" -ForegroundColor Green }
        else { Write-Host "Could not confirm the WebView2 runtime; the app may prompt to install it on first run." -ForegroundColor Yellow }
    } else {
        Write-Host "WebView2 runtime not found and winget is unavailable; the app may prompt on first run." -ForegroundColor Yellow
    }

    if ($Force) {
        foreach ($d in @((Join-Path $winProjDir 'bin'), (Join-Path $winProjDir 'obj'))) {
            if (Test-Path $d) {
                try { Remove-Item -Recurse -Force $d -ErrorAction Stop }
                catch { Write-Host "  (could not fully remove $d : $($_.Exception.Message))" -ForegroundColor DarkYellow }
            }
        }
    }

    Stop-RusNetViewer
    if (Test-Path $winDir) {
        Write-Host "Cleaning old install -> $winDir" -ForegroundColor DarkGray
        try { Remove-Item -Recurse -Force $winDir -ErrorAction Stop }
        catch { Write-Host "  (could not fully clean $winDir : $($_.Exception.Message))" -ForegroundColor DarkYellow }
    }

    Write-Host "Publishing RusNet.Viewer -> $winExe" -ForegroundColor Cyan
    dotnet publish $winProj --configuration Release --output $winDir | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    return (Test-Path $winExe)
}

# ── Python half ──────────────────────────────────────────────────────────────
function Test-PythonNeedsInstall {
    if (-not (Test-Path (Join-Path $pyVenv 'Scripts\rusnet.exe'))) { return $true }
    if (-not (Test-Path $pyStamp)) { return $true }
    $stampTime = (Get-Item $pyStamp).LastWriteTimeUtc
    if ((Get-NewestWriteUtc $repoRusnet $pySourceExts) -gt $stampTime) { return $true }
    foreach ($f in @((Join-Path $repo 'pyproject.toml'), (Join-Path $repo 'requirements.txt'))) {
        if ((Test-Path $f) -and (Get-Item $f).LastWriteTimeUtc -gt $stampTime) { return $true }
    }
    return $false
}

function Write-RunnerBats {
    $venvPyExe = Join-Path $pyVenv 'Scripts\python.exe'
    $cliBat = @"
@echo off
rem Generated by $repo\run.ps1 - edits here are overwritten.
"$venvPyExe" -m rusnet %*
"@
    Set-Content -LiteralPath (Join-Path $pyDir 'rusnet.bat') -Value $cliBat -Encoding ASCII

    $desktopBat = @"
@echo off
rem Generated by $repo\run.ps1 - edits here are overwritten.
"$venvPyExe" -m rusnet.desktop %*
"@
    Set-Content -LiteralPath (Join-Path $pyDir 'rusnet-desktop.bat') -Value $desktopBat -Encoding ASCII
}

function Publish-Python {
    if (-not (Resolve-Python)) {
        # winget's Python puts `python` on PATH (not `py`); Resolve-Python accepts either.
        if (-not (Install-ViaWingetIfMissing 'python' 'Python.Python.3.12' 'Python 3.12')) {
            throw "Python 3.9+ is required. Install it from https://python.org and re-run."
        }
    }
    $py = Resolve-Python
    if (-not $py) { throw "Python still not found on PATH after install." }

    $verOut = & $py.Exe @($py.Pre + @('-c', 'import sys;print(sys.version_info[0]);print(sys.version_info[1])'))
    $maj = [int]$verOut[0]; $min = [int]$verOut[1]
    if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 9)) { throw "Python $maj.$min is too old; RusNet needs 3.9+." }

    if (Test-Path $pyVenv) {
        Write-Host "Cleaning old install -> $pyVenv" -ForegroundColor DarkGray
        try { Remove-Item -Recurse -Force $pyVenv -ErrorAction Stop }
        catch { throw "Could not remove the old venv at $pyVenv (is a rusnet process using it?): $($_.Exception.Message)" }
    }
    New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
    Write-Host "Creating virtual environment -> $pyVenv" -ForegroundColor Cyan
    & $py.Exe @($py.Pre + @('-m', 'venv', $pyVenv))
    if ($LASTEXITCODE -ne 0) { return $false }
    $venvPy = Join-Path $pyVenv 'Scripts\python.exe'

    Write-Host "Installing rusnet (desktop + interfaces extras) -> $pyDir" -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }
    & $venvPy -m pip install --upgrade "$repo[desktop,interfaces]" | Out-Host
    if ($LASTEXITCODE -ne 0) { return $false }

    Write-RunnerBats
    Get-Date -Format o | Out-File -LiteralPath $pyStamp -Encoding ASCII -Force
    return (Test-Path (Join-Path $pyVenv 'Scripts\rusnet.exe'))
}

# The double-click launcher (MAT-T67). It asks first: 1) Deploy & Run reruns this script with -Force (so both halves
# always rebuild) and then opens the viewer; 2) Run opens the deployed viewer without calling this script. Written on
# every run (and alone with -LauncherOnly), but only when it changed: it is the batch file running this script, and cmd
# reads it as it goes. CRLF, because cmd can miss a goto label in an LF-only batch file.
function Write-Launcher {
    $content = @"
@echo off
title RusNet
rem Generated by $repo\run.ps1 - edits here are overwritten.
set "DEPLOY_PS1=$repo\run.ps1"
set "APP_EXE=%~dp0Windows\RusNet.Viewer.exe"
echo.
echo   RusNet
echo     1^) Deploy ^& Run
echo     2^) Run
echo.
choice /c 12 /n /m "  Choose 1 or 2: "
if errorlevel 2 goto run
:deploy
if exist "%DEPLOY_PS1%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%DEPLOY_PS1%" -Force
    if errorlevel 1 echo Redeploy failed - launching whatever is already in this folder instead.
) else (
    echo Source repo not found at "%DEPLOY_PS1%" - launching existing build without redeploying.
)
goto launch
:run
if not exist "%APP_EXE%" if exist "%DEPLOY_PS1%" (
    echo RusNet is not deployed yet - deploying it first.
    goto deploy
)
:launch
if not exist "%APP_EXE%" (
    echo Nothing is deployed at "%APP_EXE%".
    pause
    exit /b 1
)
start "RusNet" "%APP_EXE%" %*
exit /b 0
"@ -replace "`r?`n", "`r`n"
    if (-not (Test-Path $launcherBat) -or (Get-Content -Raw -LiteralPath $launcherBat) -ne $content) {
        Set-Content -LiteralPath $launcherBat -Value $content -Encoding ASCII -NoNewline
        Write-Host "Wrote $launcherBat" -ForegroundColor DarkGray
    }
    if (Test-Path $staleBat) { Remove-Item -LiteralPath $staleBat -Force }
}

# ── Deploy ──────────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $deployRoot | Out-Null
Write-Launcher
if ($LauncherOnly) { exit 0 }
Sync-SharedSource

$failed = $false
$didSomething = $false

if ($Force -or (Test-WindowsNeedsPublish)) {
    $didSomething = $true
    try {
        if (Publish-Windows) { Write-Host "Deployed $winExe" -ForegroundColor Green }
        else { Write-Host "Publishing RusNet.Viewer FAILED." -ForegroundColor Red; $failed = $true }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        $failed = $true
    }
}

if ($Force -or (Test-PythonNeedsInstall)) {
    $didSomething = $true
    try {
        if (Publish-Python) { Write-Host "Deployed $pyDir" -ForegroundColor Green }
        else { Write-Host "Installing the Python package FAILED." -ForegroundColor Red; $failed = $true }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        $failed = $true
    }
}

if (-not $didSomething) { Write-Host 'RusNet is up to date.' -ForegroundColor DarkGray }

if (-not $failed -and $Launch) {
    if (Test-Path $winExe) { Start-Process -FilePath $winExe -WorkingDirectory $winDir }
    else { Write-Host "Nothing deployed at $winExe." -ForegroundColor Red; $failed = $true }
}

if ($failed) { Write-Host 'Deploy FAILED.' -ForegroundColor Red; exit 1 }
exit 0
