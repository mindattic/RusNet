@echo off
rem ============================================================================
rem  RusNet installer (Windows)
rem
rem  Double-click for a menu, or pass an argument for a scripted install:
rem      install.bat python     - the scanner + CLI + desktop viewer (.venv)
rem      install.bat windows    - the .NET WebView2 desktop app (dist\windows)
rem      install.bat both       - both
rem
rem  Everything is delegated to install.ps1, which AUTO-INSTALLS any missing
rem  prerequisites (Python, the .NET SDK, the Edge WebView2 runtime) via winget,
rem  then sets up the chosen target.
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "INTERACTIVE=1"
set "TARGET=%~1"
if not "%TARGET%"=="" set "INTERACTIVE=0"

if "%INTERACTIVE%"=="0" goto parse_arg

:menu
echo.
echo   RusNet installer
echo   ----------------
echo     [P] Python     - the scanner + CLI + desktop viewer (creates .venv)
echo     [W] Windows    - the .NET WebView2 desktop app (publishes to dist\windows)
echo     [B] Both
echo     [Q] Quit
echo.
choice /c PWBQ /n /m "Choose what to install [P/W/B/Q]: "
if errorlevel 4 goto quit
if errorlevel 3 ( set "TARGET=both"    & goto run )
if errorlevel 2 ( set "TARGET=windows" & goto run )
if errorlevel 1 ( set "TARGET=python"  & goto run )

:parse_arg
if /i "%TARGET%"=="python"  ( set "TARGET=python"  & goto run )
if /i "%TARGET%"=="py"      ( set "TARGET=python"  & goto run )
if /i "%TARGET%"=="windows" ( set "TARGET=windows" & goto run )
if /i "%TARGET%"=="win"     ( set "TARGET=windows" & goto run )
if /i "%TARGET%"=="dotnet"  ( set "TARGET=windows" & goto run )
if /i "%TARGET%"=="both"    ( set "TARGET=both"    & goto run )
if /i "%TARGET%"=="all"     ( set "TARGET=both"    & goto run )
echo Unknown option "%TARGET%". Use: python ^| windows ^| both
exit /b 2

:run
where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: PowerShell was not found; cannot run install.ps1.
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Target %TARGET%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" ( echo All done. ) else ( echo Install did not complete ^(exit %RC%^). )
if "%INTERACTIVE%"=="1" pause
exit /b %RC%

:quit
echo Nothing installed.
exit /b 0
