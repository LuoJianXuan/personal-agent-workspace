param([switch]$Authorized)
$ErrorActionPreference = 'Stop'
if (-not $Authorized) { throw 'This runs application verification. Obtain user authorization, then pass -Authorized.' }
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$config = @{}
foreach ($line in (Get-Content -LiteralPath (Join-Path $ProjectRoot '.env'))) {
    if ($line -match '^([A-Z_]+)=(.*)$') { $config[$Matches[1]] = $Matches[2] }
}
$base = "http://localhost:$($config['WEB_PORT'])/api"
function Login-As($prefix) {
    $body = @{username=$config["SEED_${prefix}_USERNAME"]; password=$config["SEED_${prefix}_PASSWORD"]} | ConvertTo-Json
    return Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType 'application/json' -Body $body
}
$admin = Login-As 'ADMIN'
$user = Login-As 'USER_A'
$me = Invoke-RestMethod -Uri "$base/auth/me" -Headers @{Authorization="Bearer $($user.access_token)"}
if ($me.role -ne 'user') { throw 'Unexpected user role' }
$users = Invoke-RestMethod -Uri "$base/admin/users" -Headers @{Authorization="Bearer $($admin.access_token)"}
if ($users.items.Count -lt 3) { throw 'Demo seed missing' }
try {
    Invoke-RestMethod -Uri "$base/admin/users" -Headers @{Authorization="Bearer $($user.access_token)"} | Out-Null
    throw 'Expected ordinary user to be denied'
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 403) { throw }
}
function Expect-Status($uri, $status, $method = 'Get', $body = $null, $headers = @{}) {
    try {
        $args = @{Uri=$uri; Method=$method; Headers=$headers; ContentType='application/json'}
        if ($null -ne $body) { $args.Body = $body }
        Invoke-WebRequest @args | Out-Null
        throw "Expected HTTP $status"
    } catch {
        if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne $status) { throw }
    }
}
Expect-Status "$base/auth/me" 401
Expect-Status "$base/auth/me" 401 'Get' $null @{Authorization='Bearer invalid-token'}
Expect-Status "$base/auth/login" 401 'Post' (@{username=$config['SEED_USER_A_USERNAME'];password='deliberately-invalid'} | ConvertTo-Json)
Expect-Status "$base/auth/login" 400 'Post' (@{username=$config['SEED_USER_A_USERNAME'];password=$config['SEED_USER_A_PASSWORD'];user_id='cannot-override-identity'} | ConvertTo-Json)
Expect-Status "http://localhost:$($config['WEB_PORT'])/internal/health" 404
$page = Invoke-WebRequest -Uri "http://localhost:$($config['WEB_PORT'])/login"
if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'id="root"') { throw 'Web entry not served' }
Write-Host 'PASS: login, identity, admin users, ordinary-user 403, anonymous/invalid-token/wrong-password 401, unknown-field 400, public internal-path 404, Web entry 200. No model requests.'
