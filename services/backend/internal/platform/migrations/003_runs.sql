CREATE TABLE backend.run_submissions (
 run_id uuid PRIMARY KEY, thread_id uuid NOT NULL REFERENCES backend.threads(id), owner_id uuid NOT NULL REFERENCES backend.users(id),
 idempotency_key text NOT NULL, request_hash text NOT NULL, snapshot_id uuid NOT NULL REFERENCES backend.capability_snapshots(id),
 start_payload jsonb NOT NULL, status text NOT NULL DEFAULT 'PENDING', active boolean NOT NULL DEFAULT true,
 cancel_requested boolean NOT NULL DEFAULT false, final_text text NOT NULL DEFAULT '', error_code text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(owner_id,idempotency_key));
CREATE UNIQUE INDEX run_thread_active ON backend.run_submissions(thread_id) WHERE active;
CREATE TABLE backend.messages(id uuid PRIMARY KEY, thread_id uuid NOT NULL REFERENCES backend.threads(id),run_id uuid NOT NULL REFERENCES backend.run_submissions(run_id),role text NOT NULL,text text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(run_id,role));
CREATE TABLE backend.dispatch_commands(command_id uuid PRIMARY KEY,run_id uuid UNIQUE NOT NULL REFERENCES backend.run_submissions(run_id),attempts integer NOT NULL DEFAULT 0,next_attempt timestamptz NOT NULL DEFAULT now(),accepted boolean NOT NULL DEFAULT false);
INSERT INTO backend.schema_migrations(version) VALUES(3);
