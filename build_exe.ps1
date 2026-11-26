# Build standalone Windows executable (SerialDebugger.exe)
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm --onefile --windowed `
  --name SerialDebugger `
  --icon "assets\app.ico" `
  --add-data "ui;ui" `
  --add-data "assets;assets" `
  --exclude-module tkinter `
  --exclude-module unittest `
  --exclude-module setuptools `
  --exclude-module wheel `
  --exclude-module pip `
  --exclude-module pydoc `
  --exclude-module xmlrpc `
  main.py

Write-Host "`nBuild finished: $PSScriptRoot\dist\SerialDebugger.exe" -ForegroundColor Green
