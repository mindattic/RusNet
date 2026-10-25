@echo off
rem ============================================================================
rem  RusNet deploy (Windows)
rem
rem  Double-click to build and deploy BOTH halves - no menu, no picking:
rem      Windows app -> C:\Apps\RusNet\Windows
rem      Python app  -> C:\Apps\RusNet\Python
rem
rem  Pass -Force to rebuild/reinstall even if nothing looks changed, or -Launch
rem  to open RusNet.Viewer.exe afterwards. Everything is delegated to deploy.ps1.
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: PowerShell was not found; cannot run deploy.ps1.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo All done. ) else ( echo Deploy did not complete ^(exit %RC%^). )
pause
exit /b %RC%
