"""Create synthetic browser fixtures only in the isolated Mock acceptance stack."""
import importlib.util, json, uuid, os
from pathlib import Path
spec=importlib.util.spec_from_file_location('delivery',Path(__file__).with_name('accept-delivery.py'))
x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
d=x.d
assert d.TEST_PROJECT=='agent-workspace-verification' and d.ENV['WEB_PORT']=='5174'
a,u,b,m=x.setup()
skill=x.req('/admin/skills','POST',{'name':'回归技能 '+d.SUFFIX,'description':'用于验证技能选择与个人偏好','category':'业务回归','content':'请使用简明中文回答，并保留来源。','enabled':True,'revision':0},a)
x.req('/me/skills/'+skill['id']+'/enablement','PUT',{'enabled':False},u)
csv=x.upload(u,'回归销售.csv','地区,销售额\n东区,10\n西区,3\n东区,5\n')
text=x.upload(u,'回归资料.txt','回归项目代号：晨光。预算 123。')
malicious=x.upload(u,'回归安全预览.md','<script>alert("xss")</script>\n[x](javascript:alert(1))\n<img src=x onerror=alert(1)>\n正常内容：安全预览')
result={'model_id':m['id'],'model_name':m['name'],'skill_id':skill['id'],'skill_name':skill['name'],'csv_id':csv['id'],'text_id':text['id'],'malicious_file':malicious['id'],'real_model_calls':0}
(d.ROOT/'docs/evidence/regression-2026-11-04/ui-fixture.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
