@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" -Elevate %*
set "xnebula_exit=%ERRORLEVEL%"
if not "%xnebula_exit%"=="0" if "%~1"=="" pause
exit /b %xnebula_exit%
