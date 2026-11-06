param([switch]$Authorized, [switch]$KeepRunning, [switch]$SkipBuild)
$ErrorActionPreference='Stop'
if(-not $Authorized){throw 'Real Docker isolation acceptance requires explicit authorization.'}
$root=Split-Path $PSScriptRoot -Parent
$names=@('COMPUTE_BROKER_TOKEN','COMPUTE_BROKER_URL','WORKSPACE_PHASE1_AUTHORIZED','DOCKER_EXE','WORKSPACE_TEST_ENV','WORKSPACE_TEST_PROJECT');$previous=@{}
foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$computeDocker=$null;$computeArgs=@()
Push-Location $root
try {
 & "$PSScriptRoot/verify-phase1.ps1" -Authorized -KeepRunning -SkipBuild:$SkipBuild
 if($LASTEXITCODE -and $LASTEXITCODE -ne 0){throw 'Phase 1 prerequisite regression failed'}
 $command=Get-Command docker -ErrorAction SilentlyContinue
 $computeDocker=if($command){$command.Source}else{Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'}
 $computeArgs=@('compose','--env-file','.env.test','-p','agent-workspace-verification','-f','compose.yaml','-f','tests/compose/postgres-port.yaml','-f','tests/compose/isolated-stack.yaml','-f','tests/compose/mock-model.yaml','-f','tests/compose/web-fixture.yaml','--profile','compute')
 $env:COMPUTE_BROKER_TOKEN=[Guid]::NewGuid().ToString('N')+[Guid]::NewGuid().ToString('N')
 $env:COMPUTE_BROKER_URL='http://compute-broker:8002'
 & $computeDocker @computeArgs build compute-runner-image compute-broker runtime
 if($LASTEXITCODE -ne 0){throw 'Compute images did not build'}
 & $computeDocker @computeArgs up -d --wait compute-broker runtime
 if($LASTEXITCODE -ne 0){throw 'Compute services did not start'}
 $result=Get-Content services/runtime/tests/accept_compute.py -Raw -Encoding utf8 | & $computeDocker @computeArgs exec -T -e WORKSPACE_COMPUTE_AUTHORIZED=true runtime python -
 if($LASTEXITCODE -ne 0){throw 'Compute isolation acceptance failed'}
 $record=($result -join "`n")|ConvertFrom-Json
 $env:WORKSPACE_PHASE1_AUTHORIZED='true';$env:DOCKER_EXE=$computeDocker;$env:WORKSPACE_TEST_ENV='.env.test';$env:WORKSPACE_TEST_PROJECT='agent-workspace-verification'
 python -X utf8 scripts/accept-compute-flow.py
 if($LASTEXITCODE -ne 0){throw 'Compute Harness flow acceptance failed'}
 $remaining=& $computeDocker ps -aq --filter 'label=agent.workspace.compute=agent-workspace-verification-compute'
 $remainingVolumes=& $computeDocker volume ls -q --filter 'label=agent.workspace.compute=agent-workspace-verification-compute'
 if($remaining -or $remainingVolumes){throw 'Compute job containers/volumes remain after acceptance; preserve state for investigation'}
 $record|Add-Member -NotePropertyName cleanup -NotePropertyValue 'no labelled job containers or job volumes remain'
 $record|ConvertTo-Json -Depth 10|Set-Content docs/evidence/phase1-compute-results.json -Encoding utf8
 Write-Host 'Compute isolation acceptance passed. Real model/search calls: 0.'
} finally {
 if(-not $KeepRunning -and $computeDocker){& $computeDocker @computeArgs stop}
 foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
 Pop-Location
}
