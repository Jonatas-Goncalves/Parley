# Create the conda-forge environment and build the PyInstaller folder.
#
# Usage (from a PowerShell prompt at the repository root):
#   powershell -ExecutionPolicy Bypass -File packaging/windows/install-windows.ps1
#
# Output: packaging/windows/dist/Parley/Parley.exe

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$EnvDir = Join-Path $PSScriptRoot ".conda"
$MambaDir = Join-Path $PSScriptRoot ".micromamba"
$Mamba = Join-Path $MambaDir "Library\bin\micromamba.exe"
$DistDir = Join-Path $PSScriptRoot "dist"
$BuildDir = Join-Path $PSScriptRoot "build"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path $Mamba)) {
    Write-Step "Downloading micromamba"
    New-Item -ItemType Directory -Force -Path $MambaDir | Out-Null
    $Archive = Join-Path $MambaDir "micromamba.tar.bz2"
    Invoke-WebRequest -Uri "https://micro.mamba.pm/api/micromamba/win-64/latest" -OutFile $Archive
    tar -xjf $Archive -C $MambaDir
    Remove-Item $Archive
}

if ($Force -and (Test-Path $EnvDir)) {
    Write-Step "Removing the previous environment"
    Remove-Item -Recurse -Force $EnvDir
}

if (-not (Test-Path (Join-Path $EnvDir "python.exe"))) {
    Write-Step "Creating the conda-forge environment"
    & $Mamba create -y -p $EnvDir -c conda-forge `
        "python=3.13" gtk4 pygobject pyinstaller pip
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the conda environment."
    }
}

Write-Step "Installing the Python packages"
& $Mamba run -p $EnvDir python -m pip install --upgrade pip
& $Mamba run -p $EnvDir python -m pip install -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Retrying without pyopenjtalk; Japanese speech will need it."
    $Filtered = Join-Path $env:TEMP "parley-requirements-windows.txt"
    Get-Content (Join-Path $Root "requirements.txt") |
        Where-Object { $_ -notmatch '^\s*pyopenjtalk' } |
        Set-Content -Path $Filtered -Encoding ascii
    & $Mamba run -p $EnvDir python -m pip install -r $Filtered
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the Python packages."
    }
}

function Get-VerifiedFile([string]$Uri, [string]$Destination, [string]$Sha256) {
    if (Test-Path $Destination) {
        $current = (Get-FileHash -Algorithm SHA256 -Path $Destination).Hash.ToLower()
        if ($current -eq $Sha256) { return }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
    $partial = "$Destination.part"
    Invoke-WebRequest -Uri $Uri -OutFile $partial
    $actual = (Get-FileHash -Algorithm SHA256 -Path $partial).Hash.ToLower()
    if ($actual -ne $Sha256) {
        Remove-Item -Force $partial
        throw "Checksum mismatch for $Uri"
    }
    Move-Item -Force $partial $Destination
}

$FontDir = Join-Path $Root "assets\fonts\noto-cjk"
Write-Step "Downloading Noto Sans CJK"
Get-VerifiedFile `
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTC/NotoSansCJK-Regular.ttc" `
    (Join-Path $FontDir "NotoSansCJK-Regular.ttc") `
    "b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
Get-VerifiedFile `
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE" `
    (Join-Path $FontDir "LICENSE.txt") `
    "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"

Write-Step "Building the PyInstaller folder"
$env:GI_TYPELIB_PATH = Join-Path $EnvDir "Library\lib\girepository-1.0"
$env:PATH = (Join-Path $EnvDir "Library\bin") + ";" +
            (Join-Path $EnvDir "Scripts") + ";" +
            $EnvDir + ";" + $env:PATH

& $Mamba run -p $EnvDir python -m PyInstaller `
    --noconfirm --clean `
    --distpath $DistDir `
    --workpath $BuildDir `
    (Join-Path $PSScriptRoot "parley.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

Write-Step "Done"
Write-Host "Executable: $DistDir\Parley\Parley.exe"
