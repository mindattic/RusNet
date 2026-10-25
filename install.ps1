#Requires -Version 5.1
<#
.SYNOPSIS
  Install RusNet. Auto-installs any missing prerequisites via winget, then sets things up.

.DESCRIPTION
  -Target python  : ensure Python 3.9+, create .venv (unless -System), install requirements.txt
                    and the rusnet CLI.
  -Target windows : ensure the .NET SDK and the Edge WebView2 runtime, then publish the WPF /
                    WebView2 desktop app to dist\windows.
  -Target both    : do both.

  Missing prerequisites are installed with winget, using the same silent posture and mid-process
  PATH refresh as MindAttic.Launcher's setup.ps1 (Install-ViaWingetIfMissing). If winget isn't
  available, the script says what to install by hand and stops.

.EXAMPLE
  .\install.ps1                      # Python only, into .venv
  .\install.ps1 -Target both         # Python + the Windows app, auto-installing prereqs
  .\install.ps1 -Target windows      # just build the .NET app
  .\install.ps1 -System              # install Python into the current interpreter, no venv
#>
[CmdletBinding()]
param(
  [ValidateSet('python', 'windows', 'both')]
  [string]$Target = 'python',
  [switch]$System        # for -Target python: install into the current Python instead of .venv
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-OnPath([string]$cmd) {
  return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

# The MindAttic house pattern (see MindAttic.Launcher\setup.ps1): install a missing tool with
# winget, then re-read PATH from the registry so it's usable without opening a new shell.
function Install-ViaWingetIfMissing([string]$cmd, [string]$wingetId, [string]$label) {
  if (Test-OnPath $cmd) { Write-Host "$label found" -ForegroundColor Green; return $true }
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

function Install-Python {
  Write-Host "`n=== Python package ===" -ForegroundColor Cyan
  if (-not (Resolve-Python)) {
    # winget's Python puts `python` on PATH (not `py`); accept either after install.
    if (-not (Install-ViaWingetIfMissing 'python' 'Python.Python.3.12' 'Python 3.12')) {
      throw "Python 3.9+ is required. Install it from https://python.org and re-run."
    }
  }
  $py = Resolve-Python
  if (-not $py) { throw "Python still not found on PATH after install." }

  # Quote-free version probe (PowerShell 5.1 mangles quotes/% in a native -c one-liner).
  $verOut = & $py.Exe @($py.Pre + @('-c', 'import sys;print(sys.version_info[0]);print(sys.version_info[1])'))
  $maj = [int]$verOut[0]; $min = [int]$verOut[1]
  Write-Host "Found Python $maj.$min" -ForegroundColor Green
  if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 9)) { throw "Python $maj.$min is too old; RusNet needs 3.9+." }

  if ($System) {
    $pyExe = $py.Exe; $pyPre = $py.Pre
    Write-Host "Installing into the current Python (-System)." -ForegroundColor Yellow
  } else {
    $venv = Join-Path $root '.venv'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
      Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Cyan
      & $py.Exe @($py.Pre + @('-m', 'venv', $venv))
      if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment." }
    } else {
      Write-Host "Reusing existing .venv" -ForegroundColor Cyan
    }
    $pyExe = Join-Path $venv 'Scripts\python.exe'; $pyPre = @()
  }

  function Invoke-Py([string[]]$PipArgs) {
    & $pyExe @($pyPre + $PipArgs)
    if ($LASTEXITCODE -ne 0) { throw "Command failed: python $($PipArgs -join ' ')" }
  }
  Write-Host "Upgrading pip ..." -ForegroundColor Cyan
  Invoke-Py @('-m', 'pip', 'install', '--upgrade', 'pip')
  Write-Host "Installing requirements.txt ..." -ForegroundColor Cyan
  Invoke-Py @('-m', 'pip', 'install', '-r', 'requirements.txt')
  Write-Host "Installing the rusnet package (editable) ..." -ForegroundColor Cyan
  Invoke-Py @('-m', 'pip', 'install', '-e', '.')
  Write-Host "Python package installed." -ForegroundColor Green
}

function Install-Windows {
  Write-Host "`n=== Windows (.NET WebView2) app ===" -ForegroundColor Cyan
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

  $proj = Join-Path $root 'dotnet\RusNet.Viewer\RusNet.Viewer.csproj'
  $out  = Join-Path $root 'dist\windows'
  Write-Host "Publishing to dist\windows ..." -ForegroundColor Cyan
  dotnet publish $proj -c Release -o $out
  if ($LASTEXITCODE -ne 0) { throw "The .NET build failed." }
  Write-Host "Published: $out\RusNet.Viewer.exe" -ForegroundColor Green
}

switch ($Target) {
  'python'  { Install-Python }
  'windows' { Install-Windows }
  'both'    { Install-Python; Install-Windows }
}

Write-Host "`nRusNet install complete ($Target)." -ForegroundColor Green
if ($Target -ne 'windows') {
  if (-not $System) { Write-Host "Activate the venv:  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green }
  Write-Host "Try:" -ForegroundColor Green
  Write-Host "  python -m rusnet scan --open       # scan and open the report"
  Write-Host "  python -m rusnet.desktop            # native desktop viewer (with a Scan button)"
}
if ($Target -ne 'python') {
  Write-Host "Run the Windows app:  dist\windows\RusNet.Viewer.exe" -ForegroundColor Green
}
