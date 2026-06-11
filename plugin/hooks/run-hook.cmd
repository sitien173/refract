@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-hook-windows.ps1" %*
exit /b %ERRORLEVEL%
