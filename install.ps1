#Requires -Version 5.1
<#
.SYNOPSIS
  Install RusNet: set up a Python environment, install requirements.txt, and the rusnet CLI.

.DESCRIPTION
  By default this creates a local virtual environment in .venv and installs into it, so your
  system Python stays untouched. Pass -System to install into whatever `python` currently
  resolves to (e.g. an already-activated venv) instead.

  The RusNet core is standard-library only; requirements.txt (pywebview, psutil) enables the
  native desktop viewer and cleaner interface enumeration. `pip install -e .` adds the `rusnet`
  command and the `python -m rusnet` / `python -m rusnet.desktop` entry points.

.EXAMPLE
  .\install.ps1                 # create .venv and install everything into it
  .\install.ps1 -System         # install into the current Python instead of a venv
#>
[CmdletBinding()]
param(
  [switch]$System   # install into the current Python instead of creating .venv
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Resolve-Python {
  # Prefer the Windows launcher `py -3` (handles multiple installs); fall back to `python`.
  if (Get-Command py -ErrorAction SilentlyContinue) { return @{ Exe = 'py'; Pre = @('-3') } }
  if (Get-Command python -ErrorAction SilentlyContinue) { return @{ Exe = 'python'; Pre = @() } }
  throw "Python 3.9+ not found. Install it from https://python.org and re-run."
}

$py = Resolve-Python
# Print major and minor on their own lines - no quotes or % in the one-liner, which Windows
# PowerShell 5.1 would mangle when building the native command line.
$verOut = & $py.Exe @($py.Pre + @('-c', 'import sys;print(sys.version_info[0]);print(sys.version_info[1])'))
$maj = [int]$verOut[0]
$min = [int]$verOut[1]
Write-Host "Found Python $maj.$min" -ForegroundColor Cyan
if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 9)) {
  throw "Python $maj.$min is too old; RusNet needs 3.9 or newer."
}

if ($System) {
  $pyExe = $py.Exe
  $pyPre = $py.Pre
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
  $pyExe = Join-Path $venv 'Scripts\python.exe'
  $pyPre = @()
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

Write-Host ""
Write-Host "RusNet installed." -ForegroundColor Green
if (-not $System) {
  Write-Host "Activate the environment with:  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
}
Write-Host "Then try:" -ForegroundColor Green
Write-Host "  python -m rusnet scan --open       # scan and open the report"
Write-Host "  python -m rusnet.desktop            # native desktop viewer (with a Scan button)"
Write-Host "  python -m rusnet viewer --open      # empty viewer; drop any RusNet .json on it"
