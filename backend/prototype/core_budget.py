"""Persisted logical core admission, independent of physical/WAL and raw ledger caps."""
import re

def install(db,tables,rows,logical_bytes,row_limit,byte_limit):
    db.execute('CREATE TABLE IF NOT EXISTS ab_core_audit_budget(id INTEGER PRIMARY KEY CHECK(id=1),row_limit INTEGER NOT NULL,byte_limit INTEGER NOT NULL,row_count INTEGER NOT NULL,logical_bytes INTEGER NOT NULL)')
    old=db.execute('SELECT row_limit,byte_limit,row_count,logical_bytes FROM ab_core_audit_budget WHERE id=1').fetchone()
    if old is not None:
        if tuple(old)!=(row_limit,byte_limit,rows,logical_bytes):raise ValueError('core logical budget binding/accounting changed')
    else:db.execute('INSERT INTO ab_core_audit_budget VALUES(1,?,?,?,?)',(row_limit,byte_limit,rows,logical_bytes))
    if rows>row_limit or logical_bytes>byte_limit:raise ValueError('core logical admission limit')
    for table in tables:
        cols=[r[1] for r in db.execute('PRAGMA table_info('+table+')')]
        if any(not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',n) for n in [table,*cols]):raise ValueError('quota schema identity')
        new='ab72_logical_size('+','.join('NEW."'+c+'"' for c in cols)+')'
        old_size='ab72_logical_size('+','.join('OLD."'+c+'"' for c in cols)+')'
        for operation,count,delta in (('INSERT','+1','+'+new),('UPDATE','+0','+'+new+'-'+old_size),('DELETE','-1','-'+old_size)):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS ab_quota3_{table}_{operation} AFTER {operation} ON "{table}" BEGIN
UPDATE ab_core_audit_budget SET row_count=row_count{count},logical_bytes=logical_bytes{delta} WHERE id=1;
SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM ab_core_audit_budget WHERE id=1 AND row_count>=0 AND logical_bytes>=0 AND row_count<=row_limit AND logical_bytes<=byte_limit) THEN RAISE(ABORT,'core logical admission quota') END;
END''')
    return {'rows':rows,'logical_bytes':logical_bytes,'row_limit':row_limit,'byte_limit':byte_limit}
