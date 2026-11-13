"""Explicit checksum-ledger migrations and catalog drift validation.

Normal application startup calls validate_schema(), never apply_migrations().
Catalog expectations are captured in the owner-only ledger after reviewed SQL
runs in the same transaction; repeat/upgrade must match the saved catalog first.
"""
from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
import re

from .connection import connect_migrator, validate_environment
from .contract import SCHEMA_VERSION, canonical_json, content_hash, partition_name

MIGRATION_DIR = Path(__file__).with_name('migrations')
SCHEMAS = ['raw', 'core', 'ops', 'archive']
LOCK_ID = 701517502


class SchemaDrift(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str


def load_migrations(directory=MIGRATION_DIR):
    result = []
    for path in sorted(Path(directory).glob('*.sql')):
        match = re.fullmatch(r'(\d{4})_[a-z0-9_]+\.sql', path.name)
        if not match:
            raise SchemaDrift('unrecognized migration filename')
        blob = path.read_bytes()
        result.append(Migration(int(match[1]), path.name, hashlib.sha256(blob).hexdigest(), blob.decode('utf-8')))
    if [item.version for item in result] != list(range(1, len(result) + 1)):
        raise SchemaDrift('migration versions must be unique and contiguous')
    if not result:
        raise SchemaDrift('migration set is empty')
    return result


def validate_ledger(rows, migrations):
    expected = {item.version: item for item in migrations}
    if [row['version'] for row in rows] != list(range(1, len(rows) + 1)):
        raise SchemaDrift('migration ledger has a version gap')
    for row in rows:
        item = expected.get(row['version'])
        if item is None or row['name'] != item.name or row['checksum'] != item.checksum:
            raise SchemaDrift('applied migration checksum/name/version mismatch')
        if content_hash(row['catalog']) != row['catalog_hash']:
            raise SchemaDrift('migration catalog checksum mismatch')


def _rows(connection, sql, params=()):
    return connection.execute(sql, params).fetchall()


def catalog_snapshot(connection):
    """Fingerprint objects, definitions and effective ACLs, not business data.

    Dynamic generation children are checked separately. Their parent definition
    and every static schema object remain in this exact catalog snapshot.
    """
    queries = {
        'schemas': """SELECT n.nspname AS name,pg_get_userbyid(n.nspowner) AS owner,
            COALESCE(n.nspacl::text,'') AS acl FROM pg_namespace n
            WHERE n.nspname=ANY(%s) ORDER BY 1""",
        'relations': """SELECT n.nspname AS schema,c.relname AS name,c.relkind::text AS kind,
            pg_get_userbyid(c.relowner) AS owner,c.relpersistence::text AS persistence,
            c.relrowsecurity AS rls,c.relforcerowsecurity AS force_rls,
            COALESCE(c.relacl::text,'') AS acl,COALESCE(c.reloptions::text,'') AS options,
            COALESCE(pg_get_partkeydef(c.oid),'') AS partition_key,
            CASE WHEN c.relkind IN ('v','m') THEN pg_get_viewdef(c.oid,true) ELSE '' END AS view
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p','v','m','S','f')
            AND NOT c.relispartition ORDER BY 1,2""",
        'columns': """SELECT n.nspname AS schema,c.relname AS relation,a.attname AS name,
            a.attnum AS position,format_type(a.atttypid,a.atttypmod) AS type,
            a.attcollation::regcollation::text AS collation,a.attnotnull AS not_null,a.attidentity::text AS identity,a.attgenerated::text AS generated,
            COALESCE(pg_get_expr(d.adbin,d.adrelid),'') AS default_value,
            COALESCE(a.attacl::text,'') AS acl
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p','v','m','f') AND NOT c.relispartition
            AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,4""",
        'constraints': """SELECT n.nspname AS schema,COALESCE(c.relname,t.typname) AS relation,
            k.conname AS name,pg_get_constraintdef(k.oid,true) AS definition,
            k.convalidated AS validated,k.condeferrable AS deferrable,k.condeferred AS deferred
            FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace
            LEFT JOIN pg_class c ON c.oid=k.conrelid LEFT JOIN pg_type t ON t.oid=k.contypid
            WHERE n.nspname=ANY(%s) AND NOT COALESCE(c.relispartition,false) AND k.conparentid=0
            ORDER BY 1,2,3""",
        'indexes': """SELECT n.nspname AS schema,c.relname AS relation,ci.relname AS name,
            pg_get_indexdef(i.indexrelid) AS definition,i.indisvalid AS valid,i.indisready AS ready,
            i.indisreplident AS replica_identity,COALESCE(ci.reloptions::text,'') AS options,
            pg_get_userbyid(ci.relowner) AS owner FROM pg_index i
            JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_class ci ON ci.oid=i.indexrelid WHERE n.nspname=ANY(%s)
            AND NOT c.relispartition ORDER BY 1,2,3""",
        'functions': """SELECT n.nspname AS schema,p.proname AS name,
            pg_get_function_identity_arguments(p.oid) AS arguments,
            pg_get_functiondef(p.oid) AS definition,pg_get_userbyid(p.proowner) AS owner,
            COALESCE(p.proacl::text,'') AS acl FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY(%s) ORDER BY 1,2,3""",
        'types': """SELECT n.nspname AS schema,t.typname AS name,t.typtype::text AS kind,
            pg_get_userbyid(t.typowner) AS owner,t.typnotnull AS not_null,
            CASE WHEN t.typbasetype<>0 THEN format_type(t.typbasetype,t.typtypmod) ELSE '' END AS base,
            COALESCE(t.typdefault,'') AS default_value,COALESCE(t.typacl::text,'') AS acl
            FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
            WHERE n.nspname=ANY(%s) AND t.typtype IN ('d','e') ORDER BY 1,2""",
        'triggers': """SELECT n.nspname AS schema,c.relname AS relation,t.tgname AS name,
            pg_get_triggerdef(t.oid,true) AS definition,t.tgenabled::text AS enabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=ANY(%s) AND NOT t.tgisinternal AND NOT c.relispartition ORDER BY 1,2,3""",
        'policies': """SELECT schemaname,tablename,policyname,permissive,roles::text,cmd,qual,with_check
            FROM pg_policies WHERE schemaname=ANY(%s) ORDER BY 1,2,3""",
        'sequences': """SELECT schemaname,sequencename,sequenceowner,data_type::text,start_value,min_value,max_value,increment_by,cycle,cache_size FROM pg_sequences WHERE schemaname=ANY(%s) ORDER BY 1,2""",
        'enum_labels': """SELECT n.nspname,t.typname,e.enumlabel,e.enumsortorder::text FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=ANY(%s) ORDER BY 1,2,4""",
        'defaults': """SELECT n.nspname AS schema,pg_get_userbyid(d.defaclrole) AS owner,
            d.defaclobjtype::text AS kind,d.defaclacl::text AS acl FROM pg_default_acl d
            LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname=ANY(%s) OR d.defaclnamespace=0 ORDER BY 1,2,3""",
    }
    return {key: _rows(connection, sql, (SCHEMAS,)) for key, sql in queries.items()}


def validate_roles(connection):
    rows = _rows(connection, """SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin,rolinherit
        FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname""",
        (['tradebot_owner','tradebot_migrator','tradebot_app','tradebot_reader','tradebot_lifecycle'],))
    if len(rows) != 5 or any(any(row[key] for key in ('rolsuper','rolcreatedb','rolcreaterole','rolreplication','rolbypassrls')) for row in rows):
        raise SchemaDrift('required restricted roles are absent or privileged')
    by_name={row['rolname']:row for row in rows}
    if by_name['tradebot_owner']['rolcanlogin'] or by_name['tradebot_migrator']['rolinherit'] or by_name['tradebot_lifecycle']['rolinherit']:
        raise SchemaDrift('owner login or migration/lifecycle inheritance drift')
    memberships = _rows(connection, """SELECT member.rolname AS member,parent.rolname AS parent
        FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member
        JOIN pg_roles parent ON parent.oid=m.roleid
        WHERE member.rolname=ANY(%s) ORDER BY 1,2""",
        (['tradebot_owner','tradebot_migrator','tradebot_app','tradebot_reader','tradebot_lifecycle'],))
    if memberships != [{'member':'tradebot_migrator','parent':'tradebot_owner'}]:
        raise SchemaDrift('unexpected role membership')


def _validate_foundation(connection):
    validate_roles(connection)
    snapshot = catalog_snapshot(connection)
    expected_columns = {
        'environment_identity': [('singleton','boolean'),('environment','text'),('database_name','text'),('foundation_version','integer')],
        'foundation_smoke': [('id','integer'),('amount','numeric(30,18)'),('source_time','text'),('payload','text')],
    }
    relations = snapshot['relations']
    if not relations or any(row['schema']!='ops' or row['name'] not in expected_columns
                            or row['kind']!='r' or row['owner']!='tradebot_owner' for row in relations):
        raise SchemaDrift('unexpected objects before business-schema installation')
    names = {row['name'] for row in relations}
    if 'environment_identity' not in names:
        raise SchemaDrift('missing foundation identity')
    for name in names:
        columns = [row for row in snapshot['columns'] if row['relation']==name]
        if [(row['name'],row['type']) for row in columns] != expected_columns[name] or not all(row['not_null'] for row in columns):
            raise SchemaDrift('foundation column drift')
        expected_defaults = ['true','','',''] if name=='environment_identity' else ['']*4
        if [r['default_value'] for r in columns]!=expected_defaults or any(r['identity'] or r['generated'] or r['acl'] for r in columns):
            raise SchemaDrift('foundation column default or grant drift')
    if any(snapshot[key] for key in ('functions','types','triggers','policies','defaults','sequences','enum_labels')):
        raise SchemaDrift('unexpected foundation schema objects')
    if any(row['owner']!='tradebot_owner' for row in snapshot['schemas']) or len(snapshot['schemas']) != 4:
        raise SchemaDrift('foundation schema ownership drift')
    # Explicitly reject grants beyond the foundation's reviewed surface.
    expected_grants = {
        'environment_identity': {('tradebot_app','SELECT'),('tradebot_reader','SELECT')},
        'foundation_smoke': {('tradebot_app','SELECT'),('tradebot_app','INSERT'),('tradebot_reader','SELECT')},
    }
    for name in names:
        grants = _rows(connection, """SELECT grantee,privilege_type FROM information_schema.role_table_grants
            WHERE table_schema='ops' AND table_name=%s AND grantee<>'tradebot_owner' ORDER BY 1,2""", (name,))
        if {(r['grantee'],r['privilege_type']) for r in grants} != expected_grants[name]:
            raise SchemaDrift('foundation table grant drift')
    for row in snapshot['schemas']:
        privileges = _rows(connection, """SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
            a.privilege_type FROM pg_namespace n CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
            WHERE n.nspname=%s AND a.grantee<>n.nspowner""", (row['name'],))
        if {(r['grantee'],r['privilege_type']) for r in privileges} != {('tradebot_app','USAGE'),('tradebot_reader','USAGE')}:
            raise SchemaDrift('foundation schema grant drift')
    expected_constraint_counts = {'environment_identity':5, 'foundation_smoke':3}
    for name in names:
        constraints = [r for r in snapshot['constraints'] if r['relation']==name]
        if len(constraints) != expected_constraint_counts[name] or not all(r['validated'] for r in constraints):
            raise SchemaDrift('foundation constraint drift')
        definitions = {r['definition'] for r in constraints}
        if name=='environment_identity':
            identity = connection.execute('SELECT environment,database_name FROM ops.environment_identity').fetchone()
            required = {'PRIMARY KEY (singleton)','CHECK (singleton)',
                        "CHECK (environment = '%s'::text)" % identity['environment'],
                        "CHECK (database_name = '%s'::text)" % identity['database_name'],
                        'CHECK (foundation_version = 1)'}
        else:
            required = {'PRIMARY KEY (id)','CHECK (id >= 1 AND id <= 32)','CHECK (length(payload) = 128)'}
        if definitions != required:
            raise SchemaDrift('foundation constraint definition drift')
    if len(snapshot['indexes']) != len(names) or any(not row['valid'] or not row['ready'] for row in snapshot['indexes']):
        raise SchemaDrift('foundation index drift')


def validate_partitions(connection):
    """Permit only UUID-registered raw children with exact inherited shape/ACLs."""
    if connection.execute("SELECT to_regclass('archive.generations') AS name").fetchone()['name'] is None:
        return
    children = _rows(connection, """SELECT c.oid,n.nspname AS schema,c.relname AS name,
        pg_get_userbyid(c.relowner) AS owner,pg_get_expr(c.relpartbound,c.oid) AS bound,
        c.relrowsecurity AS rls,c.relforcerowsecurity AS force_rls,c.relpersistence::text AS persistence,
        COALESCE(c.reloptions::text,'') AS options,p.oid::regclass::text AS parent
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_inherits i ON i.inhrelid=c.oid JOIN pg_class p ON p.oid=i.inhparent
        WHERE n.nspname=ANY(%s) AND c.relkind IN ('r','p')""", (SCHEMAS,))
    generations = _rows(connection, 'SELECT generation_id,partition_name,state FROM archive.generations')
    by_name = {r['partition_name']:r for r in generations}
    for child in children:
        generation = by_name.get(child['name'])
        if generation is None or child['schema']!='raw' or child['parent']!='raw.events' or child['owner']!='tradebot_owner' or child['rls'] or child['force_rls'] or child['persistence']!='p' or child['options']:
            raise SchemaDrift('unregistered or altered raw partition')
        if child['name'] != partition_name(generation['generation_id']) or generation['state']=='retired' or child['bound'] != "FOR VALUES IN ('%s')" % generation['generation_id']:
            raise SchemaDrift('raw partition bound/identity/state mismatch')
        differences = _rows(connection, """SELECT attname,atttypid,atttypmod,attnotnull,attidentity,attgenerated FROM pg_attribute
            WHERE attrelid=%s AND attnum>0 AND NOT attisdropped EXCEPT
            SELECT attname,atttypid,atttypmod,attnotnull,attidentity,attgenerated FROM pg_attribute
            WHERE attrelid='raw.events'::regclass AND attnum>0 AND NOT attisdropped""", (child['oid'],))
        if differences:
            raise SchemaDrift('raw partition column drift')
        child_extras = connection.execute('''SELECT
            (SELECT count(*) FROM pg_attrdef WHERE adrelid=%s) +
            (SELECT count(*) FROM pg_attribute WHERE attrelid=%s AND attacl IS NOT NULL) +
            (SELECT count(*) FROM pg_rewrite WHERE ev_class=%s) AS n''',
            (child['oid'],child['oid'],child['oid'])).fetchone()['n']
        if child_extras:
            raise SchemaDrift('raw partition default, column grant, or rule drift')
        extra_constraints = connection.execute('SELECT count(*) AS n FROM pg_constraint WHERE conrelid=%s AND conislocal AND conparentid=0',(child['oid'],)).fetchone()['n']
        if extra_constraints:
            raise SchemaDrift('raw partition constraint drift')
        grants = _rows(connection, """SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
            a.privilege_type,a.is_grantable FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
            WHERE c.oid=%s AND a.grantee<>c.relowner""", (child['oid'],))
        if {(r['grantee'],r['privilege_type'],r['is_grantable']) for r in grants} != {
                ('tradebot_app','SELECT',False),('tradebot_app','INSERT',False),
                ('tradebot_reader','SELECT',False),('tradebot_lifecycle','SELECT',False)}:
            raise SchemaDrift('raw partition grant drift')
        if connection.execute('SELECT count(*) AS n FROM pg_trigger WHERE tgrelid=%s AND NOT tgisinternal',(child['oid'],)).fetchone()['n']:
            raise SchemaDrift('raw partition trigger drift')
        indexes = _rows(connection, """SELECT i.indisvalid,i.indisready,inh.inhparent IS NOT NULL AS inherited
            FROM pg_index i LEFT JOIN pg_inherits inh ON inh.inhrelid=i.indexrelid WHERE i.indrelid=%s""", (child['oid'],))
        parent_count = connection.execute("SELECT count(*) AS n FROM pg_index WHERE indrelid='raw.events'::regclass").fetchone()['n']
        if len(indexes)!=parent_count or any(not all(r.values()) for r in indexes):
            raise SchemaDrift('raw partition index drift')
    child_names = {r['name'] for r in children}
    if any(g['state'] not in ('prepared','retired') and g['partition_name'] not in child_names for g in generations):
        raise SchemaDrift('live generation is missing its partition')


def _ledger(connection):
    exists = connection.execute("SELECT to_regclass('ops.schema_migrations') AS name").fetchone()['name']
    return None if exists is None else _rows(connection, 'SELECT version,name,checksum,catalog,catalog_hash FROM ops.schema_migrations ORDER BY version')


def validate_schema(connection, environment='preprod', *, migrations=None, require_latest=True):
    validate_environment(connection, environment)
    validate_roles(connection)
    migrations = migrations if migrations is not None else load_migrations()
    rows = _ledger(connection)
    if not rows:
        raise SchemaDrift('business schema has not been explicitly migrated')
    validate_ledger(rows, migrations)
    if rows[-1]['catalog'] != catalog_snapshot(connection):
        raise SchemaDrift('schema, constraint, index, function, ownership, or grant drift detected')
    validate_partitions(connection)
    if require_latest and len(rows) != len(migrations):
        raise SchemaDrift('database migration version is not current')
    return rows[-1]['version']


def apply_migrations(connection, environment='preprod', *, directory=MIGRATION_DIR):
    migrations = load_migrations(directory)
    applied = []
    with connection.transaction():
        connection.execute('SET LOCAL ROLE tradebot_owner')
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        validate_environment(connection, environment)
        rows = _ledger(connection)
        if rows is None:
            _validate_foundation(connection)
            connection.execute('''CREATE TABLE ops.schema_migrations (
                version integer PRIMARY KEY CHECK(version>0),name text NOT NULL UNIQUE,
                checksum text NOT NULL CHECK(checksum ~ '^[0-9a-f]{64}$'),
                catalog jsonb NOT NULL,catalog_hash text NOT NULL CHECK(catalog_hash ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp())''')
            connection.execute('GRANT SELECT ON ops.schema_migrations TO tradebot_app,tradebot_reader,tradebot_lifecycle')
            rows = []
        elif not rows:
            raise SchemaDrift('unexplained empty migration ledger')
        else:
            validate_schema(connection, environment, migrations=migrations, require_latest=False)
        for migration in migrations[len(rows):]:
            connection.execute(migration.sql)
            snapshot = catalog_snapshot(connection)
            connection.execute('''INSERT INTO ops.schema_migrations(version,name,checksum,catalog,catalog_hash)
                VALUES(%s,%s,%s,%s::jsonb,%s)''', (migration.version,migration.name,migration.checksum,
                                                 canonical_json(snapshot),content_hash(snapshot)))
            applied.append(migration.version)
        validate_schema(connection, environment, migrations=migrations)
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=['preprod','production'], required=True)
    parser.add_argument('--dsn-file', type=Path, required=True, help='restricted file containing migrator DSN')
    parser.add_argument('--check', action='store_true', help='validate only; never execute migration DDL')
    args = parser.parse_args()
    dsn = args.dsn_file.read_text().strip()
    with connect_migrator(dsn, args.environment, readonly=args.check) as connection:
        result = validate_schema(connection,args.environment) if args.check else apply_migrations(connection,args.environment)
    print(json.dumps({'environment':args.environment,'operation':'check' if args.check else 'migrate','result':result}))


if __name__ == '__main__':
    main()
