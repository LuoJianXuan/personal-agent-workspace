CREATE TABLE backend.personal_connections (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES backend.users(id),
    connector_id text NOT NULL,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    credential_version bigint NOT NULL DEFAULT 0 CHECK (credential_version >= 0),
    grant_revision bigint NOT NULL DEFAULT 0 CHECK (grant_revision >= 0),
    status text NOT NULL DEFAULT 'disconnected' CHECK (status IN ('disconnected','ready','auth_required')),
    catalog jsonb NOT NULL DEFAULT '[]',
    grants jsonb NOT NULL DEFAULT '{}',
    UNIQUE(owner_id, connector_id),
    UNIQUE(id, owner_id)
);

CREATE TABLE backend.personal_credentials (
    connection_id uuid PRIMARY KEY,
    owner_id uuid NOT NULL,
    key_id text NOT NULL,
    ciphertext bytea NOT NULL,
    FOREIGN KEY(connection_id, owner_id) REFERENCES backend.personal_connections(id, owner_id)
);

CREATE TABLE backend.personal_probes (
    id uuid PRIMARY KEY,
    connection_id uuid NOT NULL UNIQUE,
    owner_id uuid NOT NULL,
    key_id text NOT NULL,
    ciphertext bytea NOT NULL,
    credential_version bigint NOT NULL,
    replaces_credential boolean NOT NULL,
    received boolean NOT NULL DEFAULT false,
    catalog jsonb,
    expires_at timestamptz NOT NULL DEFAULT now() + interval '30 minutes',
    FOREIGN KEY(connection_id, owner_id) REFERENCES backend.personal_connections(id, owner_id)
);

CREATE TABLE backend.personal_execution_access (
    execution_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES backend.run_submissions(run_id),
    owner_id uuid NOT NULL,
    connection_id uuid NOT NULL,
    tool_id text NOT NULL,
    args_hash text NOT NULL,
    credential_version bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(connection_id, owner_id) REFERENCES backend.personal_connections(id, owner_id)
);

-- Older servers must not surface the retired shared personal account either.
UPDATE backend.mcp_connections
SET data = data || jsonb_build_object('enabled', false, 'revision', (data->>'revision')::bigint + 1)
WHERE data->>'endpoint' = 'https://mcp.mcd.cn' AND data->>'enabled' = 'true';

INSERT INTO backend.schema_migrations(version) VALUES (8);
