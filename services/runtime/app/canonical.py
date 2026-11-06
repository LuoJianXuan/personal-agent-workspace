import hashlib,json,math
def canonical(value):
    def normalize(v):
        if isinstance(v,float):
            if not math.isfinite(v):raise ValueError('non-finite number')
            return int(v) if v.is_integer() else v
        if isinstance(v,dict):return {k:normalize(x) for k,x in v.items()}
        if isinstance(v,list):return [normalize(x) for x in v]
        return v
    text=json.dumps(normalize(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    return text,hashlib.sha256(text.encode()).hexdigest()
