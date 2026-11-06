. "$PSScriptRoot/common.ps1"
Invoke-Compose build backend runtime web demo-mcp
Invoke-Compose up -d --wait postgres
& "$PSScriptRoot/migrate.ps1"
& "$PSScriptRoot/seed.ps1"
Invoke-Compose up -d --wait backend runtime web demo-mcp
Write-Host 'Workspace started. Open http://localhost:5173 (or your configured WEB_PORT).'
