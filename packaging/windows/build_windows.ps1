# CharAIface Windows PyInstaller build helper

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ScriptPath "CharAIface.spec"
$DistPath = Join-Path $ProjectRoot "dist\windows"
$WorkPath = Join-Path $ProjectRoot "build\windows"
$PyInstallerConfigDir = Join-Path $ProjectRoot "build\pyinstaller-config\windows"
$PythonUserBase = Join-Path $ProjectRoot "build\python-userbase\windows"
$PackagingBuiltinRoot = Join-Path $ProjectRoot "build\packaging-assets\windows\resources\builtin"
$PackagingSettingsRoot = Join-Path $ProjectRoot "build\packaging-assets\windows\resources\data"

$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUSERBASE = $PythonUserBase

if (!(Test-Path $VenvPython)) {
    Write-Host "[ERROR] .venv Python was not found: $VenvPython" -ForegroundColor Red
    Write-Host "Run .\run_windows.ps1 once or create the virtual environment first."
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
New-Item -ItemType Directory -Force -Path $PythonUserBase | Out-Null
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfigDir

& $VenvPython "$ProjectRoot\packaging\prepare_packaging_assets.py" `
    --source "$ProjectRoot\resources\builtin" `
    --target $PackagingBuiltinRoot

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Packaging asset preparation failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

if (Test-Path $PackagingSettingsRoot) {
    Remove-Item -Recurse -Force $PackagingSettingsRoot
}
New-Item -ItemType Directory -Force -Path $PackagingSettingsRoot | Out-Null
Copy-Item "$ProjectRoot\resources\data\settings.json.example" "$PackagingSettingsRoot\settings.json"
Copy-Item "$ProjectRoot\resources\data\settings.json.example" "$PackagingSettingsRoot\settings.json.example"

$env:CHARAIFACE_PACKAGING_BUILTIN_ROOT = $PackagingBuiltinRoot
$env:CHARAIFACE_PACKAGING_SETTINGS_ROOT = $PackagingSettingsRoot

& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistPath `
    --workpath $WorkPath `
    $SpecPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] PyInstaller build failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

& $VenvPython "$ProjectRoot\packaging\verify_packaged_resources.py" `
    --resources-root "$DistPath\CharAIface\_internal\resources"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Packaged resource verification failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "[CharAIface] Windows build completed: $DistPath\CharAIface"
