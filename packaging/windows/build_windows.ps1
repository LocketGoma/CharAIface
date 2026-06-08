# CharAIface Windows PyInstaller build helper

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SpecPath = Join-Path $ScriptPath "CharAIface.spec"
$DistPath = Join-Path $ProjectRoot "dist\windows"
$WorkPath = Join-Path $ProjectRoot "build\windows"

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

Write-Host "[CharAIface] Windows build completed: $DistPath\CharAIface"
