param([switch]$Verification)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$path = Join-Path $root $(if ($Verification) { '.env.test' } else { '.env' })
if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Initialize the workspace environment first.' }
$content = [IO.File]::ReadAllText($path)
if ($content -match '(?m)^CONNECTION_SECRET_(ACTIVE_KEY_ID|KEYS)=[^\r\n]+') {
    if ($content -notmatch '(?m)^CONNECTION_SECRET_ACTIVE_KEY_ID=\S+' -or
        $content -notmatch '(?m)^CONNECTION_SECRET_KEYS=\S+' -or
        $content -notmatch '(?m)^PERSONAL_CONNECTIONS_ENABLED=true\s*$') {
        throw 'A personal connection configuration already exists. Resolve it without replacing the existing encryption keys.'
    }
    Write-Output 'Personal connection secret is already configured.'
    return
}
$blankSettings = '(?m)^(PERSONAL_CONNECTIONS_ENABLED=(true|false)?|CONNECTION_SECRET_(ACTIVE_KEY_ID|KEYS)=)(?=\r?$)\r?\n?'
$content = [regex]::Replace($content, $blankSettings, '')
$key = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$ring = @{ local_v1 = $key } | ConvertTo-Json -Compress
$block = @(
    'PERSONAL_CONNECTIONS_ENABLED=true'
    'CONNECTION_SECRET_ACTIVE_KEY_ID=local_v1'
    "CONNECTION_SECRET_KEYS='$ring'"
)
[IO.File]::WriteAllText($path, $content.TrimEnd() + "`n" + ($block -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output 'Personal connection secret configured in ignored deployment environment.'
