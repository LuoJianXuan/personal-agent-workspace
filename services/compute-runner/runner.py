"""Trusted wrapper inside a fresh, credential-free, offline job container."""
import base64,io,json,os,subprocess,sys,time
from pathlib import Path

root=Path('/work');job=root/'job.json'
for _ in range(200):
    if job.exists():break
    time.sleep(.05)
result={'error':'COMPUTE_FAILED','files':[],'stdout':'','stderr':''}
try:
    data=json.loads(job.read_text());inputs=root/'inputs';outputs=root/'outputs';inputs.mkdir();outputs.mkdir()
    for f in data['files']:(inputs/f['id']).write_bytes(base64.b64decode(f['content'],validate=True))
    (root/'manifest.json').write_text(json.dumps({'files':[{'id':f['id'],'path':'/work/inputs/'+f['id']} for f in data['files']]}))
    code=root/'code.py';code.write_text(data['code'])
    with (root/'stdout').open('wb') as out,(root/'stderr').open('wb') as err:
        proc=subprocess.run([sys.executable,'-I','-u',str(code)],cwd=root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=30,env={'PATH':'/usr/local/bin:/usr/bin','PYTHONIOENCODING':'utf-8'})
    result['stdout']=(root/'stdout').read_bytes()[:65536].decode('utf-8',errors='replace');result['stderr']=(root/'stderr').read_bytes()[:65536].decode('utf-8',errors='replace')
    if proc.returncode:raise ValueError('COMPUTE_FAILED')
    types={'.csv':'text/csv','.md':'text/markdown','.json':'application/json','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    entries=list(outputs.iterdir())
    if len(entries)>5:raise ValueError('COMPUTE_OUTPUT_LIMIT')
    total=0
    for f in entries:
        if f.is_symlink() or not f.is_file() or f.suffix.lower() not in types or len(f.name)>120 or f.stat().st_nlink!=1:raise ValueError('COMPUTE_OUTPUT_INVALID')
        size=f.stat().st_size;total+=size
        if size>5*1024*1024 or total>10*1024*1024:raise ValueError('COMPUTE_OUTPUT_LIMIT')
        result['files'].append({'name':f.name,'media_type':types[f.suffix.lower()],'content':base64.b64encode(f.read_bytes()).decode()})
    result['error']=''
except subprocess.TimeoutExpired:result['error']='COMPUTE_TIMEOUT'
except Exception as e:result['error']=str(e) if str(e).startswith('COMPUTE_') else 'COMPUTE_FAILED';result['files']=[]
(root/'result.tmp').write_text(json.dumps(result),encoding='utf-8')
(root/'result.tmp').replace(root/'result.json')
# Keep the tmpfs mounted until the launcher retrieves the result and deletes us.
time.sleep(60)
