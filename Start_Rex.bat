@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    start "REX" /min py -3 "%~dp0airex.py"
    exit /b 0
)

where python >nul 2>&1
if %errorlevel%==0 (
    start "REX" /min python "%~dp0airex.py"
    exit /b 0
)

echo Python was not found. Install Python 3, then run this launcher again.
pause
