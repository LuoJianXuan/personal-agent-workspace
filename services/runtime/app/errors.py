"""Small shared execution errors and secret filtering; no model/SDK imports."""
import os
from datetime import datetime,timezone

class RunError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)

def secret_values():
    return tuple(value for name,value in os.environ.items() if value and len(value)>12 and (name.upper().endswith(('TOKEN','KEY','SECRET','PASSWORD')) or '_TOKEN_' in name.upper()))

def safe_text(text):
    for value in secret_values():text=text.replace(value,'[REDACTED]')
    return text

def safe_value(value):
    """Filter message payloads before the framework persists execution state."""
    if isinstance(value,str):return safe_text(value)
    if isinstance(value,list):return [safe_value(item) for item in value]
    if isinstance(value,dict):return {safe_text(key):safe_value(item) for key,item in value.items()}
    return value

class StreamRedactor:
    """Hold possible secret prefixes so chunk boundaries cannot defeat filtering."""
    def __init__(self):self.pending=''
    def feed(self,text):
        value=safe_text(self.pending+text);held=0
        for secret in secret_values():
            for size in range(min(len(secret)-1,len(value)),held,-1):
                if value.endswith(secret[:size]):held=size;break
        if held:self.pending=value[-held:];return value[:-held]
        self.pending='';return value
    def finish(self):
        value=safe_text(self.pending);self.pending='';return value

def budget_window(prefix):
    try:
        count=int(os.environ[prefix+'_CALL_BUDGET'])
        since=datetime.fromisoformat(os.environ[prefix+'_CALL_BUDGET_SINCE'])
        if count<1 or since.tzinfo is None or since>datetime.now(timezone.utc):raise ValueError()
        return count,since.isoformat()
    except (KeyError,ValueError):raise RunError(prefix+'_BUDGET_REQUIRED_OR_INVALID') from None
