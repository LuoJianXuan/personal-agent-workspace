CREATE TABLE IF NOT EXISTS runtime.runs(run_id uuid PRIMARY KEY,thread_id uuid NOT NULL,request_hash text NOT NULL,start_payload jsonb NOT NULL,status text NOT NULL,mode text NOT NULL,seq bigint NOT NULL DEFAULT 0,final_text text NOT NULL DEFAULT '',error_code text NOT NULL DEFAULT '',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS runtime.run_events(event_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),seq bigint NOT NULL,data jsonb NOT NULL,UNIQUE(run_id,seq));
CREATE TABLE IF NOT EXISTS runtime.tool_executions(execution_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),status text NOT NULL,result text NOT NULL DEFAULT '');
INSERT INTO runtime.schema_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS runtime.model_calls(call_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),model_id uuid NOT NULL,model_revision integer NOT NULL,mode text NOT NULL,status text NOT NULL,usage jsonb NOT NULL DEFAULT '{}'::jsonb,error_code text NOT NULL DEFAULT '',created_at timestamptz NOT NULL DEFAULT now());

ALTER TABLE runtime.runs ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false;
ALTER TABLE runtime.runs ADD COLUMN IF NOT EXISTS resume_decision uuid;
ALTER TABLE runtime.runs ADD COLUMN IF NOT EXISTS resumed_approval uuid;
ALTER TABLE runtime.tool_executions ADD COLUMN IF NOT EXISTS request_hash text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS runtime.approvals(approval_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),execution_id uuid UNIQUE NOT NULL,proposal jsonb NOT NULL,status text NOT NULL DEFAULT 'PENDING',published boolean NOT NULL DEFAULT false,decision_id uuid);
CREATE TABLE IF NOT EXISTS runtime.artifact_events(artifact_key text NOT NULL,run_id uuid NOT NULL REFERENCES runtime.runs(run_id),file_id uuid NOT NULL,PRIMARY KEY(run_id,artifact_key));
CREATE TABLE IF NOT EXISTS runtime.faults(run_id uuid NOT NULL REFERENCES runtime.runs(run_id),name text NOT NULL,PRIMARY KEY(run_id,name));
INSERT INTO runtime.schema_migrations(version) VALUES(4) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS runtime.cancellations(run_id uuid PRIMARY KEY,command_id uuid NOT NULL);
ALTER TABLE runtime.tool_executions ADD COLUMN IF NOT EXISTS tool_name text NOT NULL DEFAULT '';
ALTER TABLE runtime.tool_executions ADD COLUMN IF NOT EXISTS decision_id uuid;
