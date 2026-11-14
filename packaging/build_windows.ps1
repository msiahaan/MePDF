# Build MePDF Windows Portable ZIP & Inno Setup Installer (.exe)
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$Version = "1.0.0"
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = "python"
}

Write-Host "==> Using Python: $PythonExe" -ForegroundColor Cyan

# Ensure PyInstaller is installed
$ErrorActionPreference = "Continue"
& $PythonExe -m pip show pyinstaller >$null 2>&1
$HasPyInstaller = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if (-not $HasPyInstaller) {
    Write-Host "==> Installing PyInstaller..." -ForegroundColor Yellow
    & $PythonExe -m pip install pyinstaller
}

Write-Host "==> Step 1/4: Generating application icons..." -ForegroundColor Cyan
& $PythonExe packaging\generate_icons.py

Write-Host "==> Step 2/4: Building standalone Windows bundle via PyInstaller..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller --noconfirm --clean MePDF.spec

$InstallersDir = Join-Path $RootDir "dist\installers"
New-Item -ItemType Directory -Force -Path $InstallersDir | Out-Null

$PortableZip = Join-Path $InstallersDir "MePDF-Portable-$Version-win64.zip"
if (Test-Path $PortableZip) {
    Remove-Item $PortableZip -Force
}

Write-Host "==> Step 3/4: Creating Portable ZIP ($PortableZip)..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $RootDir "dist\MePDF\*") -DestinationPath $PortableZip -Force

# Locate Inno Setup Compiler (ISCC.exe)
$IsccCandidates = @(
    "iscc",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($candidate in $IsccCandidates) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        $IsccExe = $cmd.Source
        break
    }
    if (Test-Path $candidate) {
        $IsccExe = $candidate
        break
    }
}

if ($IsccExe) {
    Write-Host "==> Step 4/4: Compiling Windows Setup Wizard via Inno Setup ($IsccExe)..." -ForegroundColor Cyan
    & $IsccExe (Join-Path $RootDir "packaging\windows\mepdf_setup.iss")
    Write-Host "==> Done! Installers available in: $InstallersDir" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 6 (ISCC.exe) was not found locally. Portable ZIP was created at: $PortableZip"
    Write-Warning "Install Inno Setup 6 (https://jrsoftware.org/isdl.php) or use the GitHub Actions workflow to build MePDF-Setup-$Version-win64.exe."
}
