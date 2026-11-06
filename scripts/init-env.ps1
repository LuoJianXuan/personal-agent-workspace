$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Target = Join-Path $ProjectRoot '.env'
if (Test-Path -LiteralPath $Target) { throw '.env already exists; refusing to overwrite secrets.' }
function New-Secret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}
$content = Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot '.env.example')
foreach ($key in @('POSTGRES_PASSWORD','BACKEND_DB_PASSWORD','RUNTIME_DB_PASSWORD','JWT_SECRET','BACKEND_TO_RUNTIME_TOKEN','RUNTIME_TO_BACKEND_TOKEN','SEED_ADMIN_PASSWORD','SEED_USER_A_PASSWORD','SEED_USER_B_PASSWORD')) {
    $content = [regex]::Replace($content, "(?m)^${key}=\r?$", "${key}=$(New-Secret)")
}
[IO.File]::WriteAllText($Target, $content, (New-Object Text.UTF8Encoding $false))
Write-Host 'Created ignored .env with independent random secrets. Read local .env to obtain demo login passwords; do not share it.'
