@echo off
setlocal

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "Tools\Generator.py"
) else (
    python "Tools\Generator.py"
)


set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [CharacterSetGenerator] Tools\Generator.py failed with exit code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
