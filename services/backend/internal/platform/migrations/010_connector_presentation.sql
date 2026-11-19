ALTER TABLE backend.connector_publication
    ADD COLUMN presentation jsonb NOT NULL DEFAULT '{}'::jsonb;
INSERT INTO backend.schema_migrations(version) VALUES (10);
