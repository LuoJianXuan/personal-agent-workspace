"""Physical storage and missing-object negative checks in isolated Compose only."""
import importlib.util,json,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('faults',Path(__file__).with_name('accept-faults.py'));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
x=f.x;d=x.d;req=x.req

def main():
 f.config();a,u,b,m=x.setup();r=x.submit(u,m,'storage check');x.wait(r,u)
 try:
  f.config(FAULT_FILE_ROOT='/proc/agent-workspace-storage-fault')
  req('/runs/'+r+'/artifacts','POST',token=u,expect=503)
  assert not req('/runs/'+r+'/artifacts',token=u)['items']
 finally:f.config()
 report=req('/runs/'+r+'/artifacts','POST',token=u);x.download(u,report)
 # Move only the freshly generated UUID object in this isolated volume, then restore.
 storage='/data/files/obj-'+report['id'];backup=storage+'.acceptance-backup'
 d.run('exec','-T','backend','mv',storage,backup)
 try:
  req('/files/'+report['id']+'/content',token=u,expect=503)
  req('/runs/'+r+'/artifacts','POST',token=u,expect=503)
 finally:d.run('exec','-T','backend','mv',backup,storage)
 x.download(u,report)
 result={'status':'passed','checks':['A21: unwritable storage yields 503 and zero READY files; retry works','A19/A21: missing physical object is a visible failure, repeated export cannot pretend READY; restored download hash matches'],'real_model_calls':0,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
 (d.ROOT/'docs/evidence/day6-storage-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS: physical storage failure and missing object',flush=True)
if __name__=='__main__':main()
