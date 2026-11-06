"""DeepAgents filesystem backed by scoped Backend APIs, never host paths."""
import fnmatch,hashlib,posixpath
from datetime import datetime,timezone
from deepagents.backends.protocol import BackendProtocol,ReadResult,WriteResult,EditResult,LsResult,GlobResult,GrepResult,FileDownloadResponse,FileUploadResponse
from .errors import RunError,safe_text

class WorkspaceBackend(BackendProtocol):
    def __init__(self,engine,start,skills=None):self.engine=engine;self.start=start;self.skills=skills or {}
    def path(self,path):
        if not isinstance(path,str) or len(path)>180 or '\\' in path or posixpath.normpath(path)!=path:raise RunError('WORKFILE_PATH_DENIED')
        if not path.startswith(('/inputs/','/skills/','/work/','/outputs/','/large_tool_results/','/conversation_history/')):raise RunError('WORKFILE_PATH_DENIED')
        return path
    async def get(self,path):
        self.path(path);await self.engine.authorize(self.start)
        if path.startswith('/inputs/'):
            file_id=path.split('/')[2]
            if path!='/inputs/'+file_id:raise RunError('WORKFILE_PATH_DENIED')
            from .materials import MaterialTools
            return await MaterialTools(self.engine,self.start).document_text(file_id)
        if path.startswith('/skills/'):
            parts=path.split('/')
            if len(parts)<4 or parts[2] not in self.skills:raise RunError('WORKFILE_NOT_FOUND')
            relative='/'.join(parts[3:])
            value=self.skills[parts[2]]['files'].get(relative)
            if value is None:raise RunError('WORKFILE_NOT_FOUND')
            return safe_text(value)
        r=await self.engine.backend.get('/internal/work-files',params={'run_id':self.start['run_id'],'path':path})
        if r.status_code!=200:raise RunError('WORKFILE_NOT_FOUND')
        return safe_text(r.json()['content'])
    async def aread(self,file_path,offset=0,limit=2000):
        try:
            text=await self.get(file_path)
            if limit<=0:return ReadResult(file_data={'content':'','encoding':'utf-8'},no_lines_requested=True)
            lines=text.splitlines();offset=max(0,offset);shown=lines[offset:offset+min(limit,2000)]
            now=datetime.now(timezone.utc).isoformat();data={'content':'\n'.join(shown),'encoding':'utf-8','created_at':now,'modified_at':now}
            if not shown:return ReadResult(file_data=data)
            end=offset+len(shown)
            return ReadResult(file_data=data,start_line=offset+1,end_line=end,total_lines=len(lines),next_offset=end if end<len(lines) else None)
        except RunError as e:return ReadResult(error=e.code)
    async def awrite(self,file_path,content):
        try:
            self.path(file_path)
            if file_path.startswith(('/inputs/','/skills/')):raise RunError('WORKFILE_READ_ONLY')
            await self.engine.authorize(self.start)
            r=await self.engine.backend.put('/internal/work-files',json={'run_id':self.start['run_id'],'path':file_path,'content':safe_text(content),'expected_revision':0})
            return WriteResult(path=file_path) if r.status_code==200 else WriteResult(error='WORKFILE_CONFLICT')
        except RunError as e:return WriteResult(error=e.code)
    async def aedit(self,file_path,old_string,new_string,replace_all=False):
        try:
            self.path(file_path)
            if file_path.startswith(('/inputs/','/skills/')):raise RunError('WORKFILE_READ_ONLY')
            await self.engine.authorize(self.start)
            r=await self.engine.backend.get('/internal/work-files',params={'run_id':self.start['run_id'],'path':file_path})
            if r.status_code!=200:raise RunError('WORKFILE_NOT_FOUND')
            f=r.json();n=f['content'].count(old_string)
            if not old_string or not n or (n>1 and not replace_all):raise RunError('WORKFILE_AMBIGUOUS_EDIT')
            content=safe_text(f['content'].replace(old_string,new_string,-1 if replace_all else 1))
            r=await self.engine.backend.put('/internal/work-files',json={'run_id':self.start['run_id'],'path':file_path,'content':content,'expected_revision':f['revision']})
            return EditResult(path=file_path,occurrences=n if replace_all else 1) if r.status_code==200 else EditResult(error='WORKFILE_CONFLICT')
        except RunError as e:return EditResult(error=e.code)
    async def entries(self):
        await self.engine.authorize(self.start)
        r=await self.engine.backend.get('/internal/work-files',params={'run_id':self.start['run_id']})
        if r.status_code!=200:raise RunError('WORKFILE_UNAVAILABLE')
        skills=[{'path':'/skills/'+skill_id+'/'+relative,'size':len(content.encode()),'is_dir':False} for skill_id,skill in self.skills.items() for relative,content in skill['files'].items()]
        return [{'path':f['path'],'size':len(f['content'].encode()),'is_dir':False} for f in r.json()['items']]+[{'path':'/inputs/'+f['id'],'is_dir':False} for f in self.start['file_refs']]+skills
    async def als(self,path):
        try:return LsResult(entries=[f for f in await self.entries() if f['path'].startswith(path.rstrip('/')+'/')])
        except RunError as e:return LsResult(error=e.code)
    async def aglob(self,pattern,path=None):
        try:return GlobResult(matches=[f for f in await self.entries() if f['path'].startswith(path or '/') and fnmatch.fnmatch(f['path'],pattern)])
        except RunError as e:return GlobResult(error=e.code)
    async def agrep(self,pattern,path=None,glob=None,*,max_count=None):
        try:
            if len(pattern)>200:raise RunError('INVALID_ARGUMENT')
            matches=[];cap=min(max_count or 100,100)
            for f in await self.entries():
                if not f['path'].startswith(path or '/') or (glob and not fnmatch.fnmatch(f['path'],glob)):continue
                for i,line in enumerate((await self.get(f['path'])).splitlines()):
                    if pattern in line:matches.append({'path':f['path'],'line':i+1,'text':line[:2000]})
                    if len(matches)>=cap:return GrepResult(matches=matches,truncated=True)
            return GrepResult(matches=matches)
        except RunError as e:return GrepResult(error=e.code)
    async def adownload_files(self,paths):
        out=[]
        for path in paths:
            try:
                if path.startswith('/inputs/'):raise RunError('INPUT_TEXT_VIEW_NOT_DOWNLOADABLE')
                out.append(FileDownloadResponse(path=path,content=(await self.get(path)).encode()))
            except RunError:out.append(FileDownloadResponse(path=path,error='file_not_found'))
        return out
    async def aupload_files(self,files):
        out=[]
        for path,data in files:
            try:r=await self.awrite(path,data.decode('utf-8'));out.append(FileUploadResponse(path=path,error='invalid_path' if r.error else None))
            except UnicodeError:out.append(FileUploadResponse(path=path,error='invalid_path'))
        return out
