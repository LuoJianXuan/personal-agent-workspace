param(
 [switch]$Authorized,
 [Parameter(Mandatory=$true)][string]$OrgId,
 [string]$LangfuseCompose=$env:LANGFUSE_COMPOSE_FILE,
 [string]$LangfuseEnv=$env:LANGFUSE_ENV_FILE
)
$ErrorActionPreference='Stop'
if(-not $Authorized){throw 'Persistent Langfuse Project/Key creation requires explicit authorization.'}
if([string]::IsNullOrWhiteSpace($LangfuseCompose) -or -not (Test-Path -LiteralPath $LangfuseCompose)){throw 'Pass -LangfuseCompose or set LANGFUSE_COMPOSE_FILE to an existing Langfuse Compose file.'}
if([string]::IsNullOrWhiteSpace($LangfuseEnv) -or -not (Test-Path -LiteralPath $LangfuseEnv)){throw 'Pass -LangfuseEnv or set LANGFUSE_ENV_FILE to an existing Langfuse env file.'}
$root=Split-Path $PSScriptRoot -Parent
$docker=Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'
$base=(Resolve-Path -LiteralPath $LangfuseCompose).Path
$baseEnv=(Resolve-Path -LiteralPath $LangfuseEnv).Path
$init=Join-Path $root 'deploy/langfuse-init.compose.yaml'
$projectId='personal-agent-demo'
$projectName='Personal Agent Demo'
function New-LangfuseKey([string]$prefix){
 $bytes=[Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
 return $prefix+[Convert]::ToHexString($bytes).ToLowerInvariant()
}
$public=New-LangfuseKey 'pk-lf-'
$secret=New-LangfuseKey 'sk-lf-'
$names=@('PERSONAL_LANGFUSE_ORG_ID','PERSONAL_LANGFUSE_PROJECT_ID','PERSONAL_LANGFUSE_PROJECT_NAME','PERSONAL_LANGFUSE_PUBLIC_KEY','PERSONAL_LANGFUSE_SECRET_KEY','LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY','LANGFUSE_BASE_URL','LANGFUSE_PUBLIC_URL','LANGFUSE_PROJECT_ID','LANGFUSE_TRACING_ENABLED','LANGFUSE_TRACING_ENVIRONMENT','WORKSPACE_PHASE1_AUTHORIZED','DOCKER_EXE','WORKSPACE_TEST_ENV','WORKSPACE_TEST_PROJECT')
$previous=@{};foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
try{
 $env:PERSONAL_LANGFUSE_ORG_ID=$OrgId
 $env:PERSONAL_LANGFUSE_PROJECT_ID=$projectId
 $env:PERSONAL_LANGFUSE_PROJECT_NAME=$projectName
 $env:PERSONAL_LANGFUSE_PUBLIC_KEY=$public
 $env:PERSONAL_LANGFUSE_SECRET_KEY=$secret
 & $docker compose --env-file $baseEnv -f $base -f $init up -d --force-recreate --wait langfuse-web
 if($LASTEXITCODE -ne 0){throw 'Langfuse headless project initialization failed.'}
 # Remove bootstrap credentials from the web container after the durable project/key exists.
 & $docker compose --env-file $baseEnv -f $base up -d --force-recreate --wait langfuse-web
 if($LASTEXITCODE -ne 0){throw 'Langfuse web did not recover after initialization.'}

 $env:LANGFUSE_PUBLIC_KEY=$public
 $env:LANGFUSE_SECRET_KEY=$secret
 $env:LANGFUSE_BASE_URL='http://host.docker.internal:3000'
 $env:LANGFUSE_PUBLIC_URL='http://localhost:3000'
 $env:LANGFUSE_PROJECT_ID=$projectId
 $env:LANGFUSE_TRACING_ENABLED='true'
 $env:LANGFUSE_TRACING_ENVIRONMENT='acceptance'
 Push-Location $root
 try{
  & $docker compose --env-file .env.test -p agent-workspace-verification -f compose.yaml -f tests/compose/postgres-port.yaml -f tests/compose/isolated-stack.yaml -f tests/compose/mock-model.yaml -f tests/compose/web-fixture.yaml up -d --no-deps --force-recreate --wait runtime
  if($LASTEXITCODE -ne 0){throw 'Verification Runtime did not start with Langfuse configuration.'}
  $env:WORKSPACE_PHASE1_AUTHORIZED='true';$env:DOCKER_EXE=$docker;$env:WORKSPACE_TEST_ENV='.env.test';$env:WORKSPACE_TEST_PROJECT='agent-workspace-verification'
  python -X utf8 scripts/accept-langfuse-real.py
  if($LASTEXITCODE -ne 0){throw 'Real local Langfuse ingestion acceptance failed.'}
 }finally{Pop-Location}
}finally{
 foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
 $public=$null;$secret=$null
}
