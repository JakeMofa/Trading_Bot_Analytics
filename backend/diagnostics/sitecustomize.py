"""Opt-in generated-fixture markers. Never add this directory to production PYTHONPATH."""
import sqlite3,os,time,json
_original_connect=sqlite3.connect
class DiagnosticConnection(sqlite3.Connection):
 def _mark(self,event):
  if getattr(self,"_generated_trace",False) and os.environ.get("TRADEBOT_LOCK_PHASE")=="1":
   os.writev(2,[("LOCKDIAG "+json.dumps({"pid":os.getpid(),"event":event,"mono_ns":time.monotonic_ns(),"real_ns":time.time_ns()})+"\n").encode()])
 def commit(self):
  self._mark("commit_entry")
  try:return super().commit()
  finally:self._mark("commit_return")
 def execute(self,sql,*a,**k):
  begin=sql.strip().upper()=="BEGIN IMMEDIATE"
  if begin:self._mark("begin_entry")
  try:return super().execute(sql,*a,**k)
  finally:
   if begin:self._mark("begin_return")
def connect(database,*a,**k):
 k.setdefault("factory",DiagnosticConnection)
 from pathlib import Path
 path=Path(database)
 if (path.name!="fixture.db" or not path.parent.name.startswith("generated-retention-")
     or path.is_symlink() or path.parent.is_symlink() or "/opt/tradebot" in str(path.resolve())
     or path.parent.stat().st_uid!=os.getuid() or path.parent.stat().st_mode & 0o077):
  raise ValueError("trace instrumentation accepts private generated fixture only")
 db=_original_connect(database,*a,**k)
 db._generated_trace=str(database).endswith("/fixture.db") and "/generated-retention-" in str(database)
 return db
if os.environ.get("TRADEBOT_GENERATED_LOCK_TRACE") == "1":
 sqlite3.connect=connect
