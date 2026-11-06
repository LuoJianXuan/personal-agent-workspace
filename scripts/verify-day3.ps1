param([switch]$Authorized, [switch]$KeepRunning)
$ErrorActionPreference = 'Stop'
if (-not $Authorized) { throw 'Obtain authorization to run tests, then pass -Authorized.' }
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$workspaceDocker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe' }
if (-not (Test-Path -LiteralPath $workspaceDocker)) { throw 'Docker Desktop is required.' }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot '.env.test'))) { throw 'Configure an isolated .env.test from .env.test.example first.' }
function Invoke-TestCompose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ComposeArgs)
    & $workspaceDocker compose --env-file .env.test -p agent-workspace-verification -f compose.yaml -f tests/compose/postgres-port.yaml -f tests/compose/isolated-stack.yaml -f tests/compose/mock-model.yaml @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Verification Compose command failed.' }
}
Push-Location $ProjectRoot
try {
    & $workspaceDocker compose build backend runtime demo-mcp web
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    Invoke-TestCompose up -d --wait postgres
    Invoke-TestCompose run --rm --no-deps backend migrate
    Invoke-TestCompose run --rm --no-deps runtime python -m app.migrate
    Invoke-TestCompose run --rm --no-deps backend seed
    Invoke-TestCompose up -d --wait backend runtime demo-mcp web
    $previousDockerExe = $env:DOCKER_EXE
    try {
        $env:DOCKER_EXE = $workspaceDocker
        python -X utf8 scripts/accept-day3.py
        if ($LASTEXITCODE -ne 0) { throw 'Day 3 integration acceptance failed.' }
    } finally { $env:DOCKER_EXE = $previousDockerExe }
    Get-Content services/runtime/tests/test_models.py -Raw -Encoding utf8 | & $workspaceDocker compose --env-file .env.test -p agent-workspace-verification -f compose.yaml -f tests/compose/postgres-port.yaml -f tests/compose/isolated-stack.yaml -f tests/compose/mock-model.yaml exec -T runtime python -
    if ($LASTEXITCODE -ne 0) { throw 'Runtime boundary tests failed.' }
    Write-Host 'Day 3 API/MCP acceptance passed. No real model calls were made.'
} finally {
    if (-not $KeepRunning) { Invoke-TestCompose stop }
    Pop-Location
}
