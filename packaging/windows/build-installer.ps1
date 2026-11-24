# Build the Inno Setup installer around the PyInstaller folder.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1
#   powershell -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1 -SkipBuild
#
# Output: packaging/windows/release/Parley-Setup-<version>.exe

[CmdletBinding()]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$EnvDir = Join-Path $PSScriptRoot ".conda"
$Mamba = Join-Path $PSScriptRoot ".micromamba\Library\bin\micromamba.exe"
$DistDir = Join-Path $PSScriptRoot "dist"
$AppDir = Join-Path $DistDir "Parley"
$OutputDir = Join-Path $PSScriptRoot "release"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path (Join-Path $AppDir "Parley.exe")) -and -not $SkipBuild) {
    & (Join-Path $PSScriptRoot "install-windows.ps1")
}

if (-not (Test-Path (Join-Path $AppDir "Parley.exe"))) {
    throw "Parley.exe was not found. Run install-windows.ps1 first."
}

$env:PYTHONPATH = Join-Path $Root "src"
$Version = (& $Mamba run -p $EnvDir python -c "import sys; sys.path.insert(0, r'$($Root)\src'); import parley; print(parley.__version__)").Trim()
if (-not $Version) {
    throw "Could not read the Parley version."
}

$Iscc = @(
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $Iscc) {
    Write-Step "Installing Inno Setup"
    choco install innosetup -y --no-progress
    $Iscc = @(
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Iscc) {
    throw "Inno Setup 6 was not found."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Step "Building the installer for Parley $Version"
& $Iscc `
    "/DAppVersion=$Version" `
    "/DSourceDir=$AppDir" `
    "/DOutputDir=$OutputDir" `
    (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed."
}

$Installer = Join-Path $OutputDir "Parley-Setup-$Version.exe"
if (-not (Test-Path $Installer)) {
    throw "The installer was not produced."
}

$Hash = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLower()
$HashFile = "$Installer.sha256"
"$Hash  $(Split-Path $Installer -Leaf)" |
    Out-File -FilePath $HashFile -Encoding ascii

Write-Step "Done"
Write-Host "Installer: $Installer"
Write-Host "SHA-256:   $Hash"
