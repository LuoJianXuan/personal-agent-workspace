"""Authorized, offline document and public-address boundary checks."""
import asyncio,hashlib,io,unittest,zipfile
from unittest.mock import patch
from docx import Document
from openpyxl import Workbook
from pypdf import PdfWriter
from app.documents import parse_document,DOCX,XLSX,PDF,checked_zip
from app.models import RunError
from app.research import normalized_url,public_address
from app.errors import StreamRedactor,safe_value

ID='11111111-1111-4111-8111-111111111111'

class StreamingSecrets(unittest.TestCase):
 def test_secret_split_across_chunks_is_redacted(self):
  with patch.dict('os.environ',{'EXAMPLE_API_KEY':'synthetic-secret-value-123'}):
   redactor=StreamRedactor()
   value=''.join(redactor.feed(chunk) for chunk in ('before synthetic-se','cret-value-','123 after'))+redactor.finish()
   self.assertEqual(value,'before [REDACTED] after')
 def test_nested_framework_message_payload_is_filtered(self):
  with patch.dict('os.environ',{'EXAMPLE_API_KEY':'synthetic-secret-value-123'}):
   value={'content':[{'text':'synthetic-secret-value-123'}],'calls':[{'args':{'value':'synthetic-secret-value-123'}}]}
   self.assertNotIn('synthetic-secret-value-123',str(safe_value(value)))
def parse(data,media):return parse_document(data,media,ID,hashlib.sha256(data).hexdigest())
class Documents(unittest.TestCase):
 def test_docx_preserves_paragraph_and_table_order(self):
  doc=Document();doc.add_paragraph('版本一预算100');table=doc.add_table(rows=1,cols=2);table.cell(0,0).text='项目';table.cell(0,1).text='150';doc.add_paragraph('版本二期限三周');out=io.BytesIO();doc.save(out)
  result=parse(out.getvalue(),DOCX);self.assertEqual(result['status'],'ready');self.assertIn('100',result['chunks'][0]['text']);self.assertIn('150',result['chunks'][1]['text']);self.assertIn('三周',result['chunks'][2]['text'])
 def test_xlsx_formula_without_cache_is_explicit(self):
  book=Workbook();sheet=book.active;sheet.append(['地区','金额']);sheet.append(['东',3]);sheet.append(['西','=1+2']);out=io.BytesIO();book.save(out)
  result=parse(out.getvalue(),XLSX);self.assertEqual(result['columns'],['地区','金额']);self.assertTrue(any('公式无缓存值' in w for w in result['warnings']))
 def test_blank_pdf_is_not_successful_text_extraction(self):
  writer=PdfWriter();writer.add_blank_page(width=200,height=200);out=io.BytesIO();writer.write(out)
  result=parse(out.getvalue(),PDF);self.assertEqual(result['status'],'unsupported');self.assertTrue(result['warnings'])
 def test_zip_traversal_and_macro_are_rejected(self):
  for name in ('../escape.xml','word/vbaProject.bin'):
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w') as z:z.writestr(name,'x')
   with self.assertRaises(RunError):checked_zip(out.getvalue())
class Network(unittest.IsolatedAsyncioTestCase):
 async def test_credentials_and_non_http_urls_are_rejected(self):
  for url in ('file:///etc/passwd','https://user:password@example.com','http://example.com:8080','https://example.com/?api_key=abc'):
   with self.assertRaises(RunError):normalized_url(url)
 async def test_all_dns_answers_must_be_public(self):
  async def records(*args,**kwargs):return [(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]
  with patch.object(asyncio.get_running_loop(),'getaddrinfo',records):
   with self.assertRaises(RunError):await public_address('example.com',443)
if __name__=='__main__':unittest.main()
