[CmdletBinding()]
param (
    [Parameter(Position = 0)]
    [ValidateSet("status", "start", "stop", "restart", "install", "uninstall", "open")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AppScript = Join-Path $ScriptDir "app.py"
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RegName = "IdentityBuildingOS"
$StartupFolder = [System.Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupFolder "IdentityBuildingOS.lnk"
$Port = if ($env:PORT) { [int]$env:PORT } else { 8765 }
$AppUrl = "http://127.0.0.1:$Port"

function Get-PythonwPath {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $candidate = Join-Path (Split-Path -Parent $pyCmd.Source) "pythonw.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
        return $pyCmd.Source
    }
    throw "Python was not found in PATH. Please install Python and ensure it is in PATH."
}

function Get-ServiceProcess {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn -and $conn.OwningProcess -gt 0) {
        $p = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($p) {
            return $p
        }
    }
    $escapedScript = [regex]::Escape($AppScript)
    $procs = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue
    foreach ($proc in $procs) {
        if ($proc.CommandLine -and $proc.CommandLine -match $escapedScript) {
            $p = Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue
            if ($p) {
                return $p
            }
        }
    }
    return $null
}

function Test-StartupConfigured {
    $inReg = $false
    if (Test-Path $RegPath) {
        $prop = (Get-ItemProperty -Path $RegPath -Name $RegName -ErrorAction SilentlyContinue).$RegName
        if (-not [string]::IsNullOrEmpty($prop)) {
            $inReg = $true
        }
    }
    $inStartupFolder = Test-Path $ShortcutPath
    return ($inReg -or $inStartupFolder)
}

function Show-Status {
    $proc = Get-ServiceProcess
    $isAutostart = Test-StartupConfigured

    Write-Host "=====================================================" -ForegroundColor Cyan
    Write-Host "  Identity Building OS - Background Service Status" -ForegroundColor Cyan
    Write-Host "=====================================================" -ForegroundColor Cyan

    if ($proc) {
        $memMB = [math]::Round($proc.WorkingSet64 / 1MB, 2)
        Write-Host " [STATUS]  RUNNING (Active)" -ForegroundColor Green
        Write-Host " Process:  $($proc.ProcessName) (PID: $($proc.Id))"
        Write-Host " Memory:   $memMB MB"
        Write-Host " URL:      $AppUrl"

        try {
            $response = Invoke-RestMethod -Uri "$AppUrl/api/state" -TimeoutSec 3 -ErrorAction Stop
            Write-Host " API:      Healthy (Today: $($response.today))" -ForegroundColor Green
        } catch {
            Write-Host " API:      Starting or not responding yet" -ForegroundColor Yellow
        }
    } else {
        Write-Host " [STATUS]  STOPPED (Inactive)" -ForegroundColor Red
        Write-Host " URL:      $AppUrl (Offline)"
    }

    Write-Host "-----------------------------------------------------"
    if ($isAutostart) {
        Write-Host " Auto-start on boot/login: ENABLED" -ForegroundColor Green
        Write-Host " - Registry entry:         $RegPath\$RegName"
        Write-Host " - Startup shortcut:       $ShortcutPath"
    } else {
        Write-Host " Auto-start on boot/login: DISABLED" -ForegroundColor Yellow
        Write-Host " (Run '.\service.ps1 install' to enable auto-start)"
    }
    Write-Host "=====================================================" -ForegroundColor Cyan
}

function Start-AppService {
    $proc = Get-ServiceProcess
    if ($proc) {
        Write-Host "Identity Building OS is already running (PID: $($proc.Id))." -ForegroundColor Yellow
        Write-Host "Visit: $AppUrl" -ForegroundColor Cyan
        return
    }

    $pyw = Get-PythonwPath
    Write-Host "Starting Identity Building OS in the background..." -ForegroundColor Cyan
    Write-Host "Interpreter: $pyw"
    Write-Host "Script:      $AppScript"

    Start-Process -FilePath $pyw -ArgumentList "`"$AppScript`"" -WorkingDirectory $ScriptDir

    $started = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        $check = Get-ServiceProcess
        if ($check) {
            $started = $true
            break
        }
    }

    if ($started) {
        Write-Host "Identity Building OS started successfully (PID: $($check.Id))!" -ForegroundColor Green
        Write-Host "Dashboard available at: $AppUrl" -ForegroundColor Green
    } else {
        Write-Warning "Process started, but port $Port is not responding yet. Check logs or run python app.py directly to diagnose."
    }
}

function Stop-AppService {
    $proc = Get-ServiceProcess
    if (-not $proc) {
        Write-Host "Identity Building OS is not running." -ForegroundColor Yellow
        return
    }

    Write-Host "Stopping Identity Building OS (PID: $($proc.Id))..." -ForegroundColor Cyan
    Stop-Process -Id $proc.Id -Force -ErrorAction Stop
    Start-Sleep -Seconds 1
    Write-Host "Service stopped successfully." -ForegroundColor Green
}

function Install-AppStartup {
    $pyw = Get-PythonwPath
    $regCmd = "`"$pyw`" `"$AppScript`""

    Write-Host "Configuring Identity Building OS for Windows Startup..." -ForegroundColor Cyan

    Set-ItemProperty -Path $RegPath -Name $RegName -Value $regCmd
    Write-Host " [x] Registered in Windows Registry: $RegPath\$RegName" -ForegroundColor Green

    try {
        $wscript = New-Object -ComObject WScript.Shell
        $shortcut = $wscript.CreateShortcut($ShortcutPath)
        $shortcut.TargetPath = $pyw
        $shortcut.Arguments = "`"$AppScript`""
        $shortcut.WorkingDirectory = $ScriptDir
        $shortcut.Description = "Identity Building OS Background Service"
        $shortcut.Save()
        Write-Host " [x] Created Startup shortcut: $ShortcutPath" -ForegroundColor Green
    } catch {
        Write-Warning "Could not create startup shortcut: $_"
    }

    Start-AppService
    Write-Host "`nIdentity Building OS is now installed to run automatically on Windows startup!" -ForegroundColor Green
}

function Uninstall-AppStartup {
    Write-Host "Removing Identity Building OS from Windows Startup..." -ForegroundColor Cyan

    if (Test-Path $RegPath) {
        Remove-ItemProperty -Path $RegPath -Name $RegName -ErrorAction SilentlyContinue
        Write-Host " [x] Removed Registry startup entry." -ForegroundColor Green
    }

    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force -ErrorAction SilentlyContinue
        Write-Host " [x] Removed Startup folder shortcut." -ForegroundColor Green
    }

    Stop-AppService
    Write-Host "Identity Building OS removed from startup." -ForegroundColor Green
}

switch ($Action) {
    "status"    { Show-Status }
    "start"     { Start-AppService }
    "stop"      { Stop-AppService }
    "restart"   { Stop-AppService; Start-Sleep -Seconds 1; Start-AppService }
    "install"   { Install-AppStartup }
    "uninstall" { Uninstall-AppStartup }
    "open"      { Start-Process $AppUrl }
}
