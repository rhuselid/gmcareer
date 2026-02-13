# Activate GMCareer env 'gmgame' in current shell. Run from repo root: .\scripts\activate.ps1
# Prefer venv 'gmgame'; fall back to conda env "gmgame" if present.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvName = "gmgame"
$venvScript = Join-Path $root "$venvName\Scripts\Activate.ps1"
if (Test-Path $venvScript) {
  & $venvScript
  return
}

if (Get-Command conda -ErrorAction SilentlyContinue) {
  $list = conda env list 2>$null
  if ($list -match $venvName) {
    conda activate $venvName
    return
  }
}

Write-Warning "No venv or conda env '$venvName' found. Run .\scripts\ensure-venv.ps1 (or conda env create -f environment.yml) first."
