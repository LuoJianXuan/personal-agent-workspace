CREATE TABLE backend.parsed_documents(file_id uuid PRIMARY KEY REFERENCES backend.files(id), data jsonb NOT NULL);
CREATE TABLE backend.document_jobs(id uuid PRIMARY KEY, file_id uuid UNIQUE NOT NULL REFERENCES backend.files(id), status text NOT NULL DEFAULT 'queued', lease_id uuid, lease_until timestamptz, attempts integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE backend.work_files(owner_id uuid NOT NULL, thread_id uuid NOT NULL REFERENCES backend.threads(id), path text NOT NULL, revision integer NOT NULL, data jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(owner_id,thread_id,path));
CREATE TABLE backend.work_file_versions(owner_id uuid NOT NULL,thread_id uuid NOT NULL,path text NOT NULL,revision integer NOT NULL,data jsonb NOT NULL,PRIMARY KEY(owner_id,thread_id,path,revision));
INSERT INTO backend.schema_migrations(version) VALUES(5);
