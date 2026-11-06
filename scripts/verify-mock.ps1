param([switch]$Authorized, [switch]$KeepRunning, [switch]$Fresh, [switch]$SkipBuild, [switch]$ResumeFresh)
$ErrorActionPreference = 'Stop'
if (-not $Authorized) { throw 'Tests require authorization. Pass -Authorized after confirmation.' }
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$workspaceDocker = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe' }
$testEnvironment = if ($Fresh -or $ResumeFresh) { '.env.fresh' } else { '.env.test' }
$testProject = if ($Fresh -or $ResumeFresh) { 'agent-workspace-fresh' } else { 'agent-workspace-verification' }
function Invoke-TestCompose {
 & $workspaceDocker compose --env-file $testEnvironment -p $testProject -f compose.yaml -f tests/compose/postgres-port.yaml -f tests/compose/isolated-stack.yaml -f tests/compose/mock-model.yaml @args
 if ($LASTEXITCODE -ne 0) { throw 'Isolated Compose operation failed.' }
}
Push-Location $ProjectRoot
$oldDocker=$env:DOCKER_EXE; $oldEnv=$env:WORKSPACE_TEST_ENV; $oldProject=$env:WORKSPACE_TEST_PROJECT; $oldTestPostgresPort=$env:TEST_POSTGRES_PORT
try {
 $env:TEST_POSTGRES_PORT = if ($Fresh -or $ResumeFresh) { '55435' } else { '55434' }
 if ($Fresh) {
  $existing = & $workspaceDocker volume ls --filter "label=com.docker.compose.project=$testProject" --format '{{.Name}}'
  if ($existing) { throw 'Fresh verification requires a new project without volumes. Existing fresh volumes are preserved; choose normal verification or archive them explicitly.' }
  if (Test-Path -LiteralPath $testEnvironment) { throw '.env.fresh exists; refusing to overwrite.' }
  $content = Get-Content .env.test.example -Raw
  foreach ($key in @('POSTGRES_PASSWORD','BACKEND_DB_PASSWORD','RUNTIME_DB_PASSWORD','JWT_SECRET','BACKEND_TO_RUNTIME_TOKEN','RUNTIME_TO_BACKEND_TOKEN','SEED_ADMIN_PASSWORD','SEED_USER_A_PASSWORD','SEED_USER_B_PASSWORD')) {
   $secret=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
   $content=[regex]::Replace($content, "(?m)^${key}=.*$", "${key}=$secret")
  }
  $content=$content -replace 'WEB_PORT=5174','WEB_PORT=5175'
  # Registry is a deployment choice, never copy credentials from development.
  $registryLine=Get-Content .env | Where-Object { $_ -match '^DOCKER_REGISTRY=' }
  if ($registryLine) { $content=[regex]::Replace($content,'(?m)^DOCKER_REGISTRY=.*$',$registryLine) }
  [IO.File]::WriteAllText((Join-Path $ProjectRoot $testEnvironment),$content,(New-Object Text.UTF8Encoding $false))
 }
 if (-not (Test-Path -LiteralPath $testEnvironment)) { throw 'Create isolated .env.test from .env.test.example.' }
 if (-not $SkipBuild) { Invoke-TestCompose build backend runtime demo-mcp web }
 Invoke-TestCompose up -d --wait postgres
 Invoke-TestCompose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/phase1.sql'
 Invoke-TestCompose run --rm --no-deps backend migrate
 Invoke-TestCompose run --rm --no-deps runtime python -m app.migrate
 Invoke-TestCompose run --rm --no-deps backend seed
 Invoke-TestCompose run --rm --no-deps backend seed
 Invoke-TestCompose up -d --wait backend runtime demo-mcp web
 $env:DOCKER_EXE=$workspaceDocker; $env:WORKSPACE_TEST_ENV=$testEnvironment; $env:WORKSPACE_TEST_PROJECT=$testProject
 foreach ($test in @('accept-day2.py','accept-day3.py','accept-delivery.py','accept-faults.py','accept-boundaries.py','accept-storage.py','accept-streams.py')) {
  python -X utf8 "scripts/$test"
  if ($LASTEXITCODE -ne 0) { throw "Acceptance failed: $test" }
 }
 foreach ($test in @('test_access.py','test_models.py','test_materials.py','test_phase1.py')) {
  Get-Content "services/runtime/tests/$test" -Raw -Encoding utf8 | & $workspaceDocker compose --env-file $testEnvironment -p $testProject -f compose.yaml -f tests/compose/postgres-port.yaml -f tests/compose/isolated-stack.yaml -f tests/compose/mock-model.yaml exec -T runtime python -
  if ($LASTEXITCODE -ne 0) { throw "Runtime test failed: $test" }
 }
 Write-Host "Mock acceptance passed in $testProject. Real model calls: 0. Browser acceptance is recorded separately."
} finally {
 if (-not $KeepRunning -and (Test-Path -LiteralPath $testEnvironment)) { Invoke-TestCompose stop }
 $env:DOCKER_EXE=$oldDocker; $env:WORKSPACE_TEST_ENV=$oldEnv; $env:WORKSPACE_TEST_PROJECT=$oldProject; $env:TEST_POSTGRES_PORT=$oldTestPostgresPort
 Pop-Location
}
