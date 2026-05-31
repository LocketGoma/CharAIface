# CharAIface Windows internal runner
# Usually called by root run_windows.ps1

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Launcher = Join-Path $ProjectRoot "scripts\run_char_aiface.py"

if (!(Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment was not found: .venv" -ForegroundColor Red
    Write-Host "        Run install first:"
    Write-Host "        .\scripts\install_windows.ps1"
    exit 1
}

if (!(Test-Path $Launcher)) {
    Write-Host "[ERROR] scripts\run_char_aiface.py was not found." -ForegroundColor Red
    Write-Host "        Make sure this script is inside the CharAIface project."
    exit 1
}

Write-Host "[CharAIface] Starting CharAIface..."
& $VenvPython $Launcher @args
exit $LASTEXITCODE
