$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectDir
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectDir ".build/pyinstaller-config"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "Codex-App-Easy-Switcher-Windows" `
  --icon "assets/app_icon_source.png" `
  app.py

$exe = Join-Path $projectDir "dist/Codex-App-Easy-Switcher-Windows.exe"
if (-not (Test-Path $exe)) {
  throw "Windows EXE was not created: $exe"
}

$hash = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLowerInvariant()
"$hash  Codex-App-Easy-Switcher-Windows.exe" |
  Set-Content -Encoding ascii (Join-Path $projectDir "dist/SHA256SUMS-Windows.txt")

Write-Host "Built: $exe"
