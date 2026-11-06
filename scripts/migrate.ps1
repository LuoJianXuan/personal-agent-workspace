. "$PSScriptRoot/common.ps1"
Invoke-Compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/phase1.sql'
Invoke-Compose run --rm --no-deps backend migrate
Invoke-Compose run --rm --no-deps runtime python -m app.migrate
