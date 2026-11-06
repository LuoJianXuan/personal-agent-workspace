"""Fixed document parsers and exporter. No model, macros, shell or remote fetch."""
import csv,hashlib,io,json,zipfile
from defusedxml import ElementTree
from .errors import RunError

PDF='application/pdf'
DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def checked_zip(data):
    z=zipfile.ZipFile(io.BytesIO(data))
    info=z.infolist()
    if len(info)>2000 or sum(i.file_size for i in info)>32*1024*1024:raise RunError('DOCUMENT_EXPANSION_LIMIT')
    for i in info:
        if '..' in i.filename.split('/') or i.filename.startswith('/') or 'vbaproject' in i.filename.lower():raise RunError('DOCUMENT_UNSUPPORTED')
        if i.filename.endswith('.xml') and i.file_size<=8*1024*1024:ElementTree.fromstring(z.read(i))
    return z

def parse_document(data,media,file_id,sha):
    result={'file_id':file_id,'sha256':sha,'parser_revision':'phase1-2','status':'ready','error':'','warnings':[],'chunks':[],'columns':[]}
    if hashlib.sha256(data).hexdigest()!=sha:raise RunError('FILE_INTEGRITY_ERROR')
    def add(id,locator,text,page=None):
        if len(result['chunks'])>=5000:raise RunError('DOCUMENT_CHUNK_LIMIT')
        if len(text)>50000:raise RunError('DOCUMENT_CHUNK_TOO_LARGE')
        chunk={'id':id,'locator':locator,'text':text}
        if page:chunk['page']=page
        result['chunks'].append(chunk)
    if media==PDF:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data),strict=False)
        if reader.is_encrypted:raise RunError('DOCUMENT_ENCRYPTED')
        if len(reader.pages)>100:raise RunError('DOCUMENT_PAGE_LIMIT')
        for i,page in enumerate(reader.pages):
            stream=page.get_contents()
            if stream and len(stream.get_data())>8*1024*1024:raise RunError('DOCUMENT_EXPANSION_LIMIT')
            text=page.extract_text() or ''
            if not text.strip():result['warnings'].append(f'物理页 {i+1} 未提取到文字，可能需要 OCR')
            else:add('page-'+str(i+1),'物理页 '+str(i+1),text,i+1)
    elif media==DOCX:
        from docx import Document
        checked_zip(data)
        doc=Document(io.BytesIO(data))
        # Walk document XML in original order, preserving paragraph/table positions.
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        n=0
        for element in doc.element.body.iterchildren():
            kind=element.tag.rsplit('}',1)[-1]
            if kind=='p':
                n+=1;text=Paragraph(element,doc).text
                if text.strip():add('paragraph-'+str(n),'段落 '+str(n),text)
            elif kind=='tbl':
                n+=1;table=Table(element,doc)
                for row_id,row in enumerate(table.rows):add(f'table-{n}-{row_id+1}',f'表格 {n} 行 {row_id+1}',' | '.join(c.text for c in row.cells))
    elif media==XLSX:
        from openpyxl import load_workbook
        checked_zip(data)
        values=load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
        formulas=load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
        if len(values.sheetnames)>10:raise RunError('WORKSHEET_LIMIT')
        cells=0
        for index,name in enumerate(values.sheetnames):
            sheet=values[name];formula_sheet=formulas[name]
            for row_id,(row,source) in enumerate(zip(sheet.iter_rows(),formula_sheet.iter_rows())):
                cells+=len(row)
                if cells>100000:raise RunError('WORKBOOK_CELL_LIMIT')
                items=[]
                for value,formula in zip(row,source):
                    if formula.data_type=='f' and value.value is None:result['warnings'].append(f'公式无缓存值：{name}!{formula.coordinate}')
                    items.append('' if value.value is None else str(value.value))
                if not any(items):continue
                if row_id==0 and index==0:result['columns']=items
                out=io.StringIO();csv.writer(out).writerow(items)
                add(f'sheet-{index}-row-{row_id+1}',f'工作表 {name} · 行 {row_id+1}',out.getvalue())
        values.close();formulas.close()
        result['warnings']=list(dict.fromkeys(result['warnings']))[:100]
    else:raise RunError('PARSE_UNSUPPORTED')
    if not result['chunks']:
        result.update(status='unsupported',error='NO_EXTRACTABLE_TEXT')
    if len(json.dumps(result,ensure_ascii=False).encode())>2*1024*1024:raise RunError('DOCUMENT_TEXT_LIMIT')
    return result

def render_docx(title,markdown):
    from docx import Document
    from docx.shared import Pt
    doc=Document();style=doc.styles['Normal'];style.font.name='Microsoft YaHei';style.font.size=Pt(10.5)
    from docx.oxml.ns import qn
    style.element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei')
    doc.add_heading(title,0)
    table=None;columns=0
    for line in markdown.splitlines()[:5000]:
        if line.startswith('|') and line.endswith('|'):
            cells=[c.strip().replace('**','') for c in line.strip('|').split('|')]
            if all(set(c)<=set('-: ') for c in cells):continue
            if table is None or columns!=len(cells):columns=len(cells);table=doc.add_table(rows=0,cols=columns);table.style='Table Grid'
            for cell,value in zip(table.add_row().cells,cells):cell.text=value
            continue
        table=None
        if line.startswith('#'):level=min(3,len(line)-len(line.lstrip('#')));doc.add_heading(line.lstrip('# '),level)
        elif line.startswith(('- ','* ')):doc.add_paragraph(line[2:].replace('**',''),style='List Bullet')
        else:doc.add_paragraph(line.replace('**',''))
    out=io.BytesIO();doc.save(out)
    if out.tell()>5*1024*1024:raise RunError('FILE_TOO_LARGE')
    return out.getvalue()
