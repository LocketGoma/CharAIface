# CharAIface Windows installer build helper

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$AppPath = Join-Path $ProjectRoot "dist\windows\CharAIface\CharAIface.exe"
$IssPath = Join-Path $ScriptPath "CharAIface.iss"

$IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$IsccPath = if ($null -ne $IsccCommand) { $IsccCommand.Source } else { $null }
if ($null -eq $IsccPath) {
    $CommonPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($Path in $CommonPaths) {
        if ($Path -and (Test-Path $Path)) {
            $IsccPath = $Path
            break
        }
    }
}

if (!(Test-Path $AppPath)) {
    Write-Host "[ERROR] Windows app build was not found: $AppPath" -ForegroundColor Red
    Write-Host "Build it first with: powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build_windows.ps1"
    exit 1
}

if ($null -eq $IsccPath) {
    Write-Host "[ERROR] Inno Setup compiler was not found: ISCC.exe" -ForegroundColor Red
    Write-Host "Install Inno Setup 6, then rerun this script."
    exit 1
}

& $IsccPath $IssPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Inno Setup build failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "[CharAIface] Windows installer built: $ProjectRoot\dist\windows-installer\CharAIfaceSetup.exe"
