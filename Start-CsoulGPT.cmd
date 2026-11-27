@echo off
setlocal
cd /d "%~dp0" || exit /b 1

py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 (
    set "python_command=py -3"
    goto check
)
python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 (
    set "python_command=python"
    goto check
)

echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/.
goto failed

:check
%python_command% main.py web %*
if not errorlevel 1 exit /b 0

:failed
if /i not "%~1"=="--check" pause
exit /b 1
