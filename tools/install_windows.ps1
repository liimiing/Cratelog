$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike '*WindowsApps*') { $python = $command.Source }
    }
    if (-not (Test-Path -LiteralPath $python)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer (winget) from Microsoft Store, then retry.' }
        & winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    }
    & $python -c 'import tkinter, sys; assert sys.maxsize > 2**32; assert sys.version_info >= (3,10)'
    if ($LASTEXITCODE -ne 0) { throw 'Python/Tk validation failed.' }
    if (-not (Test-Path .venv)) {
        & $python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
    }
    & .venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    # Official mpv release, pinned with the SHA256 published in winget-pkgs.
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($arch -eq 'Arm64') {
        $asset = 'aarch64'; $sha = 'A822ABEFFD0AC88951F4084F3425F949842AA17D616F880637EBE9041E482E97'
    } else {
        $asset = 'x86_64'; $sha = '4E197F729F5071C6772F35FFFD96E0F36E3E8A044BD9479B136BB09B7C6A80FF'
    }
    if (-not (Test-Path runtime\mpv\mpv.exe)) {
        New-Item -ItemType Directory -Force runtime\mpv | Out-Null
        $archive = Join-Path $env:TEMP ('cratelog-mpv-' + [guid]::NewGuid() + '.zip')
        try {
            Invoke-WebRequest "https://github.com/mpv-player/mpv/releases/download/v0.41.0/mpv-v0.41.0-$asset-pc-windows-msvc.zip" -OutFile $archive
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $sha) { throw 'mpv checksum mismatch.' }
            Expand-Archive -LiteralPath $archive -DestinationPath runtime\mpv -Force
        } finally { if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive } }
    }
    if ($env:CI -eq 'true') {
        & .venv\Scripts\python.exe tools\check_install.py
    } else {
        & .venv\Scripts\python.exe tools\check_install.py --playback
    }
    if ($LASTEXITCODE -ne 0) { throw 'Installation checks failed.' }
    Write-Host 'Ready. Double-click start_windows.bat.'
} catch { Write-Error $_; exit 1 }
