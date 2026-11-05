[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$DestDir = Join-Path $RootDir "python-runtime"
$PythonExe = Join-Path $DestDir "python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Setting up Python embeddable runtime in: $DestDir"
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null

    $ZipUrl = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
    $ZipPath = Join-Path $RootDir "python-embed.zip"

    Write-Host "Downloading $ZipUrl ..."
    Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath

    Write-Host "Extracting Python runtime..."
    Expand-Archive -Path $ZipPath -DestinationPath $DestDir -Force
    Remove-Item -Path $ZipPath -Force

    Write-Host "Python embeddable runtime installed successfully."
} else {
    Write-Host "Python embeddable runtime already present at: $PythonExe"
}
