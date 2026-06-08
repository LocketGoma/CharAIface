# CharAIface bootstrap installer build helper

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ScriptPath "CharAIfaceInstaller.spec"
$DistPath = Join-Path $ProjectRoot "dist\bootstrap"
$WorkPath = Join-Path $ProjectRoot "build\bootstrap-installer\pyinstaller"
$PyInstallerConfigDir = Join-Path $ProjectRoot "build\pyinstaller-config\bootstrap"

if (!(Test-Path $VenvPython)) {
    Write-Host "[ERROR] .venv Python was not found: $VenvPython" -ForegroundColor Red
    exit 1
}

& $VenvPython -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller is not installed in .venv." -ForegroundColor Red
    Write-Host "Install it with: .\.venv\Scripts\python -m pip install pyinstaller"
    exit 1
}

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $PyInstallerConfigDir | Out-Null
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfigDir

& $VenvPython "$ProjectRoot\packaging\bootstrap\build_installer_payload.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Installer payload build failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistPath `
    --workpath $WorkPath `
    $SpecPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Bootstrap installer build failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "[CharAIface] Bootstrap installer built: $DistPath\CharAIfaceInstaller.exe"
