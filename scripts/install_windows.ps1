# CharAIface Windows installer
# Run from PowerShell: .\scripts\install_windows.ps1

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptPath
Set-Location $ProjectRoot

Write-Host "[CharAIface] Windows install started."
Write-Host "[CharAIface] Project root: $ProjectRoot"

$RequirementsFile = Join-Path $ProjectRoot "requirements.txt"
if (!(Test-Path $RequirementsFile)) {
    Write-Host "[ERROR] requirements.txt was not found." -ForegroundColor Red
    Write-Host "        Expected path: $RequirementsFile"
    exit 1
}

function Find-Python {
    $candidates = @(
        "py -3.12",
        "py -3",
        "python",
        "python3"
    )

    foreach ($candidate in $candidates) {
        $parts = $candidate.Split(" ")
        $exe = $parts[0]
        $args = @()
        if ($parts.Count -gt 1) {
            $args = $parts[1..($parts.Count - 1)]
        }

        try {
            $versionOutput = & $exe @args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $versionOutput) {
                return @($exe, $args, $versionOutput.Trim())
            }
        }
        catch {
            continue
        }
    }

    return $null
}

$PythonInfo = Find-Python
if ($null -eq $PythonInfo) {
    Write-Host "[ERROR] Python 3 was not found." -ForegroundColor Red
    Write-Host "        Please install Python 3.12 or newer, then run this script again."
    exit 1
}

$PythonExe = $PythonInfo[0]
$PythonArgs = @()
if ($PythonInfo[1] -is [array]) {
    $PythonArgs = $PythonInfo[1]
}
elseif ($PythonInfo[1]) {
    $PythonArgs = @($PythonInfo[1])
}
$PythonVersion = $PythonInfo[2]

Write-Host "[CharAIface] Python: $PythonExe $($PythonArgs -join ' ') ($PythonVersion)"

$VersionParts = $PythonVersion.Split(".")
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]

if ($Major -lt 3) {
    Write-Host "[ERROR] Python 3 is required." -ForegroundColor Red
    exit 1
}

if ($Major -eq 3 -and $Minor -lt 12) {
    Write-Host "[WARN] Python 3.12+ is recommended. Current version: $PythonVersion" -ForegroundColor Yellow
    Write-Host "       Install may still continue, but unsupported issues can occur."
}

$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (!(Test-Path $VenvDir)) {
    Write-Host "[CharAIface] Creating virtual environment: .venv"
    & $PythonExe @PythonArgs -m venv .venv
}
else {
    Write-Host "[CharAIface] Existing virtual environment found: .venv"
}

if (!(Test-Path $VenvPython)) {
    Write-Host "[ERROR] venv Python was not found: $VenvPython" -ForegroundColor Red
    exit 1
}

Write-Host "[CharAIface] Upgrading pip..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[CharAIface] Installing dependencies..."
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$CheckEnvScript = Join-Path $ProjectRoot "scripts\check_env.py"
if (Test-Path $CheckEnvScript) {
    Write-Host "[CharAIface] Running environment check..."
    & $VenvPython $CheckEnvScript
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else {
    Write-Host "[WARN] scripts\check_env.py was not found. Skipping environment check." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[CharAIface] Install completed."
Write-Host "Run the app with:"
Write-Host "  .\run_windows.ps1"
