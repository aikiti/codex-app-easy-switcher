$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectDir
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectDir ".build/pyinstaller-config"
$exe = Join-Path $projectDir "dist/Codex-App-Easy-Switcher-Windows.exe"

# A stale executable must never make a failed build look successful.
if (Test-Path $exe) {
  Remove-Item -Force $exe
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "Codex-App-Easy-Switcher-Windows" `
  --icon "assets/app_icon_source.png" `
  app.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $exe)) {
  throw "Windows EXE was not created: $exe"
}

$hash = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLowerInvariant()
"$hash  Codex-App-Easy-Switcher-Windows.exe" |
  Set-Content -Encoding ascii (Join-Path $projectDir "dist/SHA256SUMS-Windows.txt")

$noticeSource = Join-Path $projectDir "docs/THIRD_PARTY_LICENSES.txt"
$noticeDir = Join-Path $projectDir "dist/docs"
New-Item -ItemType Directory -Force -Path $noticeDir | Out-Null
Copy-Item -Force $noticeSource (Join-Path $noticeDir "THIRD_PARTY_LICENSES.txt")

Write-Host "Built: $exe"
