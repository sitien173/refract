@echo off
rem Windows entry point for the cross-platform hook dispatcher.
rem Delegates to run-hook.sh via bash so the existing .sh hooks are reused.
rem
rem Usage: run-hook.cmd <script-name> [args...]

setlocal

if "%~1"=="" (
    echo run-hook.cmd: missing script name 1>&2
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
bash "%SCRIPT_DIR%run-hook.sh" %*
exit /b %ERRORLEVEL%
