"""Translate standard framework messages into the existing durable UI contract."""
from uuid import UUID,uuid5
from .errors import safe_text,StreamRedactor

class MessageBridge:
    def __init__(self,engine,run):self.engine=engine;self.run=run;self.messages={};self.counter=0
    async def delta(self,chunk,metadata):
        text=chunk.content if isinstance(chunk.content,str) else ''.join(b.get('text','') for b in chunk.content if isinstance(b,dict) and b.get('type')=='text')
        if not text:return
        key=str(getattr(chunk,'id',None) or metadata.get('langgraph_checkpoint_ns') or 'main')
        if key not in self.messages:
            mid=str(uuid5(UUID(self.run),'harness-message:'+key));self.messages[key]={'id':mid,'text':'','index':0,'redactor':StreamRedactor()};self.counter+=1
            await self.engine.event(self.run,'message.started',{'message_id':mid})
        draft=self.messages[key]
        text=draft['redactor'].feed(text)
        if text:
            draft['text']+=text
            await self.engine.event(self.run,'message.delta',{'message_id':draft['id'],'chunk_index':draft['index'],'text':text});draft['index']+=1
    async def complete_intermediate(self):
        for d in self.messages.values():
            if not d.get('done'):
                d['text']+=d['redactor'].finish()
                await self.engine.event(self.run,'message.completed',{'message_id':d['id'],'text':d['text'],'is_final':False});d['done']=True
    def final_id(self,message):
        key=str(message.id)
        if key in self.messages:return self.messages[key]['id']
        return str(uuid5(UUID(self.run),'harness-final:'+key))
