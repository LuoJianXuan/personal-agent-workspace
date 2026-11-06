ALTER TABLE runtime.runs ADD COLUMN IF NOT EXISTS engine_version text NOT NULL DEFAULT 'legacy';
ALTER TABLE runtime.runs ADD COLUMN IF NOT EXISTS active_ms bigint NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS runtime.sources(source_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),data jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS runtime.external_calls(execution_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),kind text NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
INSERT INTO runtime.schema_migrations(version) VALUES(5) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS runtime.run_skill_bindings(
  run_id uuid NOT NULL REFERENCES runtime.runs(run_id),
  skill_id text NOT NULL,
  data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,skill_id)
);
INSERT INTO runtime.schema_migrations(version) VALUES(6) ON CONFLICT DO NOTHING;
