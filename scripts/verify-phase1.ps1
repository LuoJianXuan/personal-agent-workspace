param([switch]$Authorized, [switch]$KeepRunning, [switch]$SkipBuild)
$ErrorActionPreference='Stop'
if (-not $Authorized) { throw 'Phase 1 regression requires explicit authorization.' }
$root=Split-Path $PSScriptRoot -Parent
$phaseDocker=$null;$phaseComposeArgs=@()
$previous=@{};foreach($name in @('WORKSPACE_PHASE1_AUTHORIZED','DOCKER_EXE','WORKSPACE_TEST_ENV','WORKSPACE_TEST_PROJECT')){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
Push-Location $root
try {
 & "$PSScriptRoot/verify-mock.ps1" -Authorized -KeepRunning -SkipBuild:$SkipBuild
 if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Existing regression failed' }
 $dockerCommand=Get-Command docker -ErrorAction SilentlyContinue
 $phaseDocker=if($dockerCommand){$dockerCommand.Source}else{Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'}
 $phaseComposeArgs=@('compose','--env-file','.env.test','-p','agent-workspace-verification','-f','compose.yaml','-f','tests/compose/postgres-port.yaml','-f','tests/compose/isolated-stack.yaml','-f','tests/compose/mock-model.yaml','-f','tests/compose/web-fixture.yaml')
 & $phaseDocker @phaseComposeArgs up -d --build --wait web-fixture runtime
 if($LASTEXITCODE -ne 0){throw 'Phase 1 isolated startup failed'}
 $env:WORKSPACE_PHASE1_AUTHORIZED='true';$env:DOCKER_EXE=$phaseDocker;$env:WORKSPACE_TEST_ENV='.env.test';$env:WORKSPACE_TEST_PROJECT='agent-workspace-verification'
 python -X utf8 scripts/accept-phase1.py
 if($LASTEXITCODE -ne 0){throw 'Phase 1 integration failed'}
 python -X utf8 scripts/accept-phase1-depth.py
 if($LASTEXITCODE -ne 0){throw 'Phase 1 context/files/spreadsheet acceptance failed'}
 python -X utf8 scripts/accept-personal-agent.py
 if($LASTEXITCODE -ne 0){throw 'Personal Agent S16-S20 acceptance failed'}
 $documentProcessResult=Get-Content services/runtime/tests/accept_document_process.py -Raw -Encoding utf8 | & $phaseDocker @phaseComposeArgs exec -T -e WORKSPACE_PHASE1_AUTHORIZED=true runtime python -
 if($LASTEXITCODE -ne 0){throw 'Bounded document process acceptance failed'}
 ($documentProcessResult -join "`n")|Set-Content docs/evidence/personal-agent-process-results.json -Encoding utf8
 python -X utf8 scripts/accept-entry-errors.py
 if($LASTEXITCODE -ne 0){throw 'Entry error/selection acceptance failed'}
 try {
  & $phaseDocker @phaseComposeArgs stop runtime
  if($LASTEXITCODE -ne 0){throw 'Could not drain verification Runtime for migration guard acceptance'}
  $migrationResult=Get-Content scripts/accept-phase1-migration.py -Raw -Encoding utf8 | & $phaseDocker @phaseComposeArgs run --rm --no-deps -T -e WORKSPACE_PHASE1_AUTHORIZED=true runtime python -
  if($LASTEXITCODE -ne 0){throw 'Migration guard acceptance failed'}
  ($migrationResult -join "`n")|Set-Content docs/evidence/phase1-migration-results.json -Encoding utf8
 } finally {
  & $phaseDocker @phaseComposeArgs up -d --no-deps --wait runtime
  if($LASTEXITCODE -ne 0){throw 'Verification Runtime did not recover after migration guard acceptance'}
 }
} finally {
 foreach($name in $previous.Keys){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
 if(-not $KeepRunning -and $phaseDocker){& $phaseDocker @phaseComposeArgs stop}
 Pop-Location
}
