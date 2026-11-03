"""Static protocol SQL namespace; values and quoted SQL literals are untouched."""
import re
TABLES = {'generations','events','markets','outcomes','evidence','predictions',
          'feature_snapshots','prediction_details','candles','reference_prices',
          'metadata_pins','required_evidence','manifests'}
TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\b[A-Za-z_][A-Za-z_0-9]*\b")
def namespace(sql):
    return TOKEN.sub(lambda m: 'ab_'+m[0] if m[0] in TABLES else m[0],sql)
class ProtocolConnection:
    def __init__(self,native): self.native=native
    def execute(self,sql,args=()):return self.native.execute(namespace(sql),args)
    def executescript(self,sql):return self.native.executescript(namespace(sql))
    def __getattr__(self,name):return getattr(self.native,name)
    def __enter__(self):self.native.__enter__();return self
    def __exit__(self,*args):return self.native.__exit__(*args)
