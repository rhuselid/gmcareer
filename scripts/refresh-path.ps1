# Reload User + Machine PATH into this session so 'python' works without restarting Cursor.
# Run in the same terminal where you'll use python: .\scripts\refresh-path.ps1

$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
Write-Host "PATH refreshed in this session. Try: python --version"
