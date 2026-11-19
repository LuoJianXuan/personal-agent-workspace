"""Explicit isolated Mock acceptance. No real model/search requests.
Run only after the verification stack is migrated and its MinIO config is ready.
"""
import concurrent.futures,hashlib,importlib.util,json,os,time,urllib.request,uuid
from pathlib import Path

def download(x,req,token,file):
    location=req('/files/'+file['id']+'/download-location',token=token)
    assert location['mode'] in ('stream','presigned')
    if location['mode']=='stream':
        raw=x.download(token,file)
    else:
        # A presigned URL is the only credential for object storage. Never
        # forward the Backend bearer token across the redirect/origin boundary.
        with urllib.request.urlopen(location['url'],timeout=25) as response:
            raw=response.read()
    assert hashlib.sha256(raw).hexdigest()==file['sha256']
    return raw

def main():
    if os.getenv('WORKSPACE_ARTIFACT_ACCEPTANCE')!='true':
        raise SystemExit('Set WORKSPACE_ARTIFACT_ACCEPTANCE=true only after test authorization')
    spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'))
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
    d=x.d;req=x.req
    _,u,b,m=x.setup()
    source=x.upload(u,'不可变原件.txt','原件内容')
    location=req('/files/'+source['id']+'/download-location',token=u)
    assert location['mode'] in ('stream','presigned')
    req('/files/'+source['id']+'/download-location',token=b,expect=404)
    assert download(x,req,u,source)=='原件内容'.encode()
    run=x.submit(u,m,'普通验收任务',[source['id']]);x.wait(run,u)
    first=req('/runs/'+run+'/artifacts','POST',token=u)
    again=req('/runs/'+run+'/artifacts','POST',token=u)
    assert first['id']==again['id']
    assert first['artifact_id'] and first['revision_id'] and first['version']==1
    lineage=req('/artifacts/'+first['artifact_id']+'/revisions',token=u)
    assert lineage['artifact']['current_revision_id']==first['revision_id']
    assert lineage['items'][0]['file']['sha256']==first['sha256']
    req('/artifacts/'+first['artifact_id']+'/revisions',token=b,expect=404)
    assert download(x,req,u,first)
    versions=req('/files/'+first['id']+'/versions',token=u)
    assert versions['items'][0]['id']==first['id']
    # Real gateway, checkpoint and publication; only the model output is Mock.
    version_run=x.submit(u,m,'mock:report mock:version '+first['id'],[first['id']])
    x.wait(version_run,u)
    published=req('/runs/'+version_run+'/artifacts',token=u)['items']
    derived=next(f for f in published if f['media_type']=='text/markdown')
    assert derived['artifact_id']==first['artifact_id'] and derived['version']==2
    assert derived['parent_file_id']==first['id']
    assert download(x,req,u,first)
    for f in published:
        assert f.get('revision_id') and f.get('artifact_id')
        assert f.get('source_thread_id')
        req('/files/'+f['id']+'/download-location',token=b,expect=404)
        download(x,req,u,f)
    d.run('run','--rm','--no-deps','backend','migrate')
    assert download(x,req,u,source)=='原件内容'.encode()
    result={'status':'passed','checks':['private download authorization','byte checksum','idempotent export','artifact revision metadata','source thread','repeatable migration preserves bytes'],'real_model_calls':0,'real_search_calls':0,'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    (d.ROOT/'docs/evidence/portable-artifacts-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: portable artifacts; provider must be checked in deployment configuration')
if __name__=='__main__':main()
