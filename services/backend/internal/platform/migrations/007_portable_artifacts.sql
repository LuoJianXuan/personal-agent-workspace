ALTER TABLE backend.files ADD COLUMN storage_provider text NOT NULL DEFAULT 'local' CHECK(storage_provider IN ('local','s3'));
ALTER TABLE backend.files ADD COLUMN status text NOT NULL DEFAULT 'READY' CHECK(status IN ('PENDING','READY','FAILED'));
UPDATE backend.files SET status=data->>'status' WHERE data->>'status' IN ('PENDING','READY','FAILED');
CREATE TABLE backend.artifacts(
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES backend.users(id), title text NOT NULL,
 current_revision_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE backend.artifact_revisions(
 id uuid PRIMARY KEY, artifact_id uuid NOT NULL REFERENCES backend.artifacts(id), version integer NOT NULL CHECK(version>0),
 parent_revision_id uuid REFERENCES backend.artifact_revisions(id), file_id uuid UNIQUE NOT NULL REFERENCES backend.files(id),
 source_thread_id uuid, source_run_id uuid, source_execution_id uuid,
 status text NOT NULL CHECK(status IN ('PENDING','READY','FAILED')), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(artifact_id,version));
ALTER TABLE backend.artifacts ADD CONSTRAINT artifact_current_fk FOREIGN KEY(current_revision_id) REFERENCES backend.artifact_revisions(id);
CREATE TABLE backend.blob_cleanup(
 storage_provider text NOT NULL, storage_key text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(storage_provider,storage_key));
CREATE INDEX artifact_owner_idx ON backend.artifacts(owner_id,created_at DESC);
-- Backfill only unambiguous, same-owner, same-media parent chains. Cycles and broken
-- chains remain independent artifacts. Existing bytes and legacy JSON stay intact.
DO $$
DECLARE f record; parent_id uuid; parent_aid uuid; aid uuid; rid uuid; next_version integer; progressed integer;
BEGIN
 LOOP
  progressed:=0;
  FOR f IN SELECT * FROM backend.files WHERE data->>'source'='generated' AND status='READY'
    AND NOT EXISTS(SELECT 1 FROM backend.artifact_revisions r WHERE r.file_id=files.id)
    ORDER BY created_at,id
  LOOP
   aid:=NULL;rid:=f.id;parent_id:=NULL;parent_aid:=NULL;
   IF f.data->>'parent_file_id' ~ '^[0-9a-f-]{36}$' THEN
    SELECT r.id,r.artifact_id INTO parent_id,parent_aid FROM backend.artifact_revisions r JOIN backend.files pf ON pf.id=r.file_id
      WHERE r.file_id=(f.data->>'parent_file_id')::uuid AND pf.owner_id=f.owner_id
      AND pf.data->>'media_type'=f.data->>'media_type';
    IF parent_id IS NOT NULL THEN aid:=parent_aid;
    ELSIF EXISTS(SELECT 1 FROM backend.files pf WHERE pf.id=(f.data->>'parent_file_id')::uuid AND pf.owner_id=f.owner_id AND pf.data->>'source'='generated' AND pf.data->>'media_type'=f.data->>'media_type') THEN
      CONTINUE;
    END IF;
   END IF;
   IF aid IS NULL THEN
    aid:=f.id;INSERT INTO backend.artifacts(id,owner_id,title,created_at) VALUES(aid,f.owner_id,f.data->>'name',f.created_at);
   END IF;
   SELECT COALESCE(max(version),0)+1 INTO next_version FROM backend.artifact_revisions WHERE artifact_id=aid;
   INSERT INTO backend.artifact_revisions(id,artifact_id,version,parent_revision_id,file_id,source_thread_id,source_run_id,status,created_at)
    VALUES(rid,aid,next_version,parent_id,f.id,(SELECT thread_id FROM backend.run_submissions WHERE run_id=f.run_id),f.run_id,'READY',f.created_at);
   UPDATE backend.artifacts SET current_revision_id=rid WHERE id=aid;
   UPDATE backend.files SET data=data||jsonb_strip_nulls(jsonb_build_object('artifact_id',aid,'revision_id',rid,'version',next_version,'source_thread_id',(SELECT thread_id FROM backend.run_submissions WHERE run_id=f.run_id))) WHERE id=f.id;
   progressed:=progressed+1;
  END LOOP;
  EXIT WHEN progressed=0;
 END LOOP;
 FOR f IN SELECT * FROM backend.files WHERE data->>'source'='generated' AND status='READY' AND NOT EXISTS(SELECT 1 FROM backend.artifact_revisions r WHERE r.file_id=files.id) LOOP
  INSERT INTO backend.artifacts(id,owner_id,title,created_at) VALUES(f.id,f.owner_id,f.data->>'name',f.created_at);
  INSERT INTO backend.artifact_revisions(id,artifact_id,version,file_id,source_run_id,status,created_at) VALUES(f.id,f.id,1,f.id,f.run_id,'READY',f.created_at);
  UPDATE backend.artifacts SET current_revision_id=f.id WHERE id=f.id;
  UPDATE backend.files SET data=data||jsonb_build_object('artifact_id',f.id,'revision_id',f.id,'version',1) WHERE id=f.id;
 END LOOP;
END $$;
INSERT INTO backend.schema_migrations(version) VALUES(7);
