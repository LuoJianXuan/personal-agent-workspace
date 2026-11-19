CREATE TABLE backend.connector_publication (
    connector_id text PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    enabled boolean NOT NULL,
    revision bigint NOT NULL CHECK (revision > 0)
);
INSERT INTO backend.schema_migrations(version) VALUES (9);
