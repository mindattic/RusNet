@echo off
rem ============================================================================
rem  RusNet run (Windows)
rem
rem  Double-click for a menu (MAT-T67):
rem    1) Deploy & Run - rebuild and redeploy BOTH halves (run.ps1 -Force -Launch):
rem         Windows app -> C:\Apps\RusNet\Windows
rem         Python app  -> C:\Apps\RusNet\Python
rem       then open RusNet.Viewer.exe. Extra arguments go to run.ps1.
rem    2) Run - open the deployed RusNet.Viewer.exe without redeploying.
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"
set "APP_EXE=C:\Apps\RusNet\Windows\RusNet.Viewer.exe"

echo.
echo   RusNet
echo     1^) Deploy ^& Run
echo     2^) Run
echo.
choice /c 12 /n /m "  Choose 1 or 2: "
if errorlevel 2 goto run

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: PowerShell was not found; cannot run run.ps1.
  pause
  exit /b 1
)

:deploy
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Force -Launch %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo All done. ) else ( echo Deploy did not complete ^(exit %RC%^). )
pause
exit /b %RC%

:run
if not exist "%APP_EXE%" (
  echo RusNet is not deployed yet - deploying it first.
  goto deploy
)
start "RusNet" "%APP_EXE%"
exit /b 0
