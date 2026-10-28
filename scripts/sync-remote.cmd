@echo off
setlocal
rem Use Windows built-in PowerShell; PowerShell 7 is not required.
where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Windows PowerShell was not found.
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-remote.ps1" %*
set "result=%errorlevel%"
if not "%result%"=="0" echo ERROR: Sync failed. Read the error above before retrying.
exit /b %result%
