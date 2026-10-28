$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .venv\Scripts\python.exe)) { throw 'Run install_windows.bat first.' }
& .venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit 1 }
& .venv\Scripts\python.exe tools\build_release.py
exit $LASTEXITCODE
