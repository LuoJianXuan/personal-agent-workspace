$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
function Invoke-Compose {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $workspaceDocker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe' }
    if (-not (Test-Path -LiteralPath $workspaceDocker)) { throw 'Docker Desktop is required. Install it and start its Linux engine.' }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot '.env'))) { throw 'Copy .env.example to .env and configure project-only secrets first.' }
    Push-Location $ProjectRoot
    try { & $workspaceDocker compose @args; if ($LASTEXITCODE -ne 0) { throw "docker compose failed (exit $LASTEXITCODE)" } }
    finally { Pop-Location }
}
