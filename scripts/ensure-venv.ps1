# Create project venv 'gmgame' in repo root and install requirements. Safe to run multiple times.
# Run from repo root: .\scripts\ensure-venv.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvName = "gmgame"
if (-not (Test-Path (Join-Path $root "requirements.txt"))) {
  Write-Error "Run from repo root or ensure scripts live under GMCareer. requirements.txt not found in $root"
  exit 1
}

Set-Location $root

$venvPath = Join-Path $root $venvName
# If old .venv exists, suggest removing it so we use gmgame
$oldVenv = Join-Path $root ".venv"
if (Test-Path $oldVenv) {
  Write-Warning "Found old '.venv'. This project now uses '$venvName'. Remove .venv to use gmgame: Remove-Item -Recurse -Force .venv"
}
if (-not (Test-Path $venvPath)) {
  Write-Host "Creating venv '$venvName' in $root ..."
  python -m venv $venvName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$activate = Join-Path $venvPath "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
  Write-Error "'$venvName' exists but Scripts\Activate.ps1 not found. Remove '$venvName' and run again."
  exit 1
}

& $activate
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Venv '$venvName' ready. Activate in this shell with: .\$venvName\Scripts\Activate.ps1"
Write-Host "Or run .\scripts\activate.ps1 when you cd into GMCareer (or use auto-activate)."
