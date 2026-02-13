# Add a PowerShell profile hook so the GMCareer env auto-activates when you cd into the repo
# and deactivates when you leave. Run once from repo root: .\scripts\register-auto-activate.ps1
#
# Installs to BOTH profile paths so it works in Windows PowerShell 5.1 and PowerShell 7 (pwsh).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$marker = "GMCAREER_AUTO_ACTIVATED"
$blockMarker = "# --- GMCareer auto-activate (scripts\register-auto-activate.ps1)"
$endMarker = "# --- End GMCareer"

# Both profile paths so it works no matter which PowerShell you open (5.1 vs 7)
$profilePaths = @(
  (Join-Path $env:USERPROFILE "Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"),
  (Join-Path $env:USERPROFILE "Documents\PowerShell\Microsoft.PowerShell_profile.ps1")
)

$hook = @"

$blockMarker
`$promptFn = Get-Item function:Prompt -ErrorAction SilentlyContinue
if (`$promptFn -and `$promptFn.ScriptBlock.ToString() -notmatch 'GMCareer_OriginalPrompt') {
  `$global:GMCareer_OriginalPrompt = `$promptFn.ScriptBlock
}
function global:Prompt {
  `$pwd = (Get-Location).Path
  `$dir = `$pwd
  while (`$dir) {
    `$activateScript = Join-Path `$dir "scripts\activate.ps1"
    if (Test-Path `$activateScript) {
      if (`$env:$marker -ne `$dir) {
        Push-Location `$dir
        . (Join-Path `$dir "scripts\activate.ps1")
        Pop-Location
        `$env:$marker = `$dir
      }
      break
    }
    `$parent = Split-Path -Parent `$dir
    if (`$parent -eq `$dir) { break }
    `$dir = `$parent
  }
  if (-not `$dir) {
    if (`$env:$marker) {
      if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
      Remove-Item Env:$marker -ErrorAction SilentlyContinue
    }
  }
  if (`$global:GMCareer_OriginalPrompt) { return (& `$global:GMCareer_OriginalPrompt) }
  return "PS `$(`$pwd)> "
}
$endMarker

"@

function Update-ProfileWithHook {
  param([string]$profilePath, [string]$hookContent, [string]$blockMark, [string]$endMark)
  $profileDir = Split-Path -Parent $profilePath
  if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
  }
  $content = $null
  if (Test-Path $profilePath) {
    $content = Get-Content -Raw -Path $profilePath
  }
  $alreadyInstalled = $content -and $content.Contains($blockMark)
  if ($alreadyInstalled -and $content) {
    $start = $content.IndexOf($blockMark)
    $end = $content.IndexOf($endMark)
    if ($start -ge 0 -and $end -ge $start) {
      $end += $endMark.Length
      $before = $content.Substring(0, $start).TrimEnd()
      $after = $content.Substring($end).TrimStart()
      $newContent = if ($after) { $before + "`n`n" + $hookContent.Trim() + "`n`n" + $after } else { $before + "`n`n" + $hookContent.Trim() }
      Set-Content -Path $profilePath -Value $newContent -NoNewline
      return "updated"
    }
  }
  if ($alreadyInstalled) { return "unchanged" }
  Add-Content -Path $profilePath -Value $hookContent
  return "added"
}

$hookTrimmed = $hook.Trim()
$results = @()
foreach ($profilePath in $profilePaths) {
  $res = Update-ProfileWithHook -profilePath $profilePath -hookContent $hookTrimmed -blockMark $blockMarker -endMark $endMarker
  $name = if ($profilePath -like "*WindowsPowerShell*") { "Windows PowerShell 5.1" } else { "PowerShell 7" }
  $results += [pscustomobject]@{ Profile = $name; Path = $profilePath; Result = $res }
}

Write-Host "GMCareer auto-activate hook:"
foreach ($r in $results) {
  Write-Host "  [$($r.Result)] $($r.Profile)"
  Write-Host "    $($r.Path)"
}
Write-Host ""
Write-Host "The gmgame env will activate when you cd into the repo and deactivate when you leave."
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Close this terminal and open a NEW one (so the profile loads)."
Write-Host "  2. cd into GMCareer; the prompt should show (gmgame)."
Write-Host ""
Write-Host "If it still does not activate:"
Write-Host "  - Check execution policy: Get-ExecutionPolicy (should not be Restricted)."
Write-Host "  - Test profile: . `$PROFILE"
Write-Host "  - Ensure venv exists: .\scripts\ensure-venv.ps1"
Write-Host ""
