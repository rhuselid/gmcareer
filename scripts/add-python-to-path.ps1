# Add Python 3.14 to User PATH permanently (persists across sessions and reboots).
# Run once: .\scripts\add-python-to-path.ps1

$pythonDir  = "$env:LOCALAPPDATA\Programs\Python\Python314"
$scriptsDir = "$env:LOCALAPPDATA\Programs\Python\Python314\Scripts"

if (-not (Test-Path "$pythonDir\python.exe")) {
  Write-Error "Python not found at $pythonDir. Edit this script if Python is installed elsewhere."
  exit 1
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$add = @()
if ($userPath -notlike "*$pythonDir*")        { $add += $pythonDir }
if ($userPath -notlike "*$scriptsDir*")      { $add += $scriptsDir }

if ($add.Count -eq 0) {
  Write-Host "Python and Scripts are already in your User PATH."
  exit 0
}

$newPath = ($userPath.TrimEnd(';') + ';' + ($add -join ';')).Replace(';;', ';')
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")

Write-Host "Added to User PATH: $($add -join ', ')"
Write-Host ""
Write-Host "Next steps (pick one):"
Write-Host "  A) In THIS terminal only - run: .\scripts\refresh-path.ps1"
Write-Host "  B) For all future terminals - fully quit Cursor (File > Exit), then reopen it."
Write-Host "  (New terminals only see the new PATH after the app that started them is restarted.)"
