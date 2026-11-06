import unittest,json
from app.materials import summarize
from app.models import RunError
from app.canonical import canonical
from contracts.validate import validate
ID='11111111-1111-4111-8111-111111111111'
class MaterialsTests(unittest.TestCase):
 def args(self,agg='sum'):return dict(dimension='category',measure='amount',aggregation=agg,chart_type='bar')
 def test_decimal_and_zero(self):
  chart,text=summarize('category,amount\nA,0.1\nA,0.2\nB,-0\n',ID,self.args());validate('Chart',chart)
  self.assertEqual(chart['points'],[dict(label='A',value=.3),dict(label='B',value=0)])
 def test_average_and_count(self):
  self.assertEqual(summarize('category,amount\nA,1\nA,2',ID,self.args('avg'))[0]['points'][0]['value'],1.5)
  self.assertEqual(summarize('category,amount\nA,non-numeric',ID,self.args('count'))[0]['points'][0]['value'],1)
 def test_limits_and_nonfinite(self):
  for text in ['category,amount\nA,NaN','category,amount\nA,Infinity','category,amount\nA,abc','category,amount\nA,1,2','category,amount\n'+'\n'.join(f'{i},1' for i in range(51))]:
   with self.assertRaises(RunError):summarize(text,ID,self.args())
 def test_csv_formula_escape(self):
  _,text=summarize('category,amount\n=HYPERLINK(),1',ID,self.args());self.assertIn("'=HYPERLINK()",text)
 def test_canonical_unicode_and_numbers(self):
  raw,h=canonical({'z':-0.0,'a':1.0,'文本':'中\u2028文'});self.assertEqual(raw,'{"a":1,"z":0,"文本":"中\\u2028文"}')
  self.assertEqual(canonical({'b':1,'a':2})[1],canonical({'a':2,'b':1})[1])
if __name__=='__main__':unittest.main()
