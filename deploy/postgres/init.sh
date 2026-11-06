#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=backend_password="$BACKEND_DB_PASSWORD" --set=runtime_password="$RUNTIME_DB_PASSWORD" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE workspace FROM PUBLIC;
CREATE ROLE workspace_backend LOGIN PASSWORD :'backend_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE workspace_runtime LOGIN PASSWORD :'runtime_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE workspace TO workspace_backend, workspace_runtime;
CREATE SCHEMA backend AUTHORIZATION workspace_backend;
CREATE SCHEMA runtime AUTHORIZATION workspace_runtime;
CREATE SCHEMA runtime_harness_v2 AUTHORIZATION workspace_runtime;
REVOKE ALL ON SCHEMA backend FROM PUBLIC;
REVOKE ALL ON SCHEMA runtime FROM PUBLIC;
REVOKE ALL ON SCHEMA runtime_harness_v2 FROM PUBLIC;
ALTER ROLE workspace_backend SET search_path = backend;
ALTER ROLE workspace_runtime SET search_path = runtime;
SQL
