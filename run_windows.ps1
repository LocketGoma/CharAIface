# CharAIface Windows launcher
# Run from PowerShell: .\run_windows.ps1

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptPath
Set-Location $ProjectRoot

Write-Host "[CharAIface] Windows launcher started."
Write-Host "[CharAIface] Project root: $ProjectRoot"

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$InstallScript = Join-Path $ProjectRoot "scripts\install_windows.ps1"
$RunScript = Join-Path $ProjectRoot "scripts\run_char_aiface.ps1"
$CheckEnvScript = Join-Path $ProjectRoot "scripts\check_env.py"
$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"

if (!(Test-Path $RequirementsFile)) {
    Write-Host "[ERROR] requirements.txt was not found." -ForegroundColor Red
    Write-Host "        Expected path: $RequirementsFile"
    exit 1
}

if (!(Test-Path $InstallScript)) {
    Write-Host "[ERROR] Install script was not found: $InstallScript" -ForegroundColor Red
    exit 1
}

if (!(Test-Path $RunScript)) {
    Write-Host "[ERROR] Run script was not found: $RunScript" -ForegroundColor Red
    exit 1
}

$NeedsInstall = $false

if (!(Test-Path $VenvPython)) {
    Write-Host "[CharAIface] Virtual environment was not found. Install will be started."
    $NeedsInstall = $true
}
elseif (Test-Path $CheckEnvScript) {
    Write-Host "[CharAIface] Running environment check..."
    & $VenvPython $CheckEnvScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[CharAIface] Environment check failed. Install will be started."
        $NeedsInstall = $true
    }
}
else {
    Write-Host "[WARN] scripts\check_env.py was not found. Skipping environment check."
}

if ($NeedsInstall) {
    & powershell -ExecutionPolicy Bypass -File $InstallScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Install failed." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

& powershell -ExecutionPolicy Bypass -File $RunScript
exit $LASTEXITCODE
