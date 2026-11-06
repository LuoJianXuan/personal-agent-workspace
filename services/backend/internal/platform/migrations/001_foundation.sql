CREATE TABLE backend.schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE backend.users(id uuid PRIMARY KEY, username varchar(100) UNIQUE NOT NULL, password_hash text NOT NULL, role text NOT NULL CHECK(role IN ('admin','user')), enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE backend.threads(id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES backend.users(id), tenant_id uuid NOT NULL, project_id uuid NOT NULL, title text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX threads_owner ON backend.threads(tenant_id,project_id,owner_id);
INSERT INTO backend.schema_migrations(version) VALUES(1);
