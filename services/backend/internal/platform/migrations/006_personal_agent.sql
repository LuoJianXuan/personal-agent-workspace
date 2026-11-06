ALTER TABLE backend.parsed_documents ADD COLUMN IF NOT EXISTS sha256 text;
ALTER TABLE backend.parsed_documents ADD COLUMN IF NOT EXISTS parser_revision text;
ALTER TABLE backend.parsed_documents ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE backend.parsed_documents ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
UPDATE backend.parsed_documents
SET sha256=data->>'sha256', parser_revision=data->>'parser_revision', status=data->>'status'
WHERE sha256 IS NULL OR parser_revision IS NULL OR status IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS parsed_documents_identity
ON backend.parsed_documents(file_id,sha256,parser_revision);
ALTER TABLE backend.run_submissions ADD COLUMN IF NOT EXISTS trace_url text NOT NULL DEFAULT '';
INSERT INTO backend.schema_migrations(version) VALUES(6) ON CONFLICT DO NOTHING;
