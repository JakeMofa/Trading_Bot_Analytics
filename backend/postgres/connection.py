"""Restricted connection helper. Never executes schema DDL on startup."""
from .contract import DATABASES


class EnvironmentMismatch(RuntimeError):
    pass


def validate_environment(connection, environment='preprod'):
    expected = DATABASES.get(environment)
    if expected is None:
        raise EnvironmentMismatch('unsupported database environment')
    row = connection.execute('SELECT current_database() AS database_name').fetchone()
    if row['database_name'] != expected:
        raise EnvironmentMismatch('database name does not match requested environment')
    rows = connection.execute('SELECT singleton, environment, database_name, foundation_version '
                              'FROM ops.environment_identity').fetchall()
    if len(rows) != 1 or rows[0] != dict(singleton=True, environment=environment,
                                       database_name=expected, foundation_version=1):
        raise EnvironmentMismatch('foundation environment identity mismatch')


def connect(dsn, environment='preprod', readonly=False):
    import psycopg
    from psycopg.rows import dict_row
    connection = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
                                options='-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=3000')
    try:
        validate_environment(connection, environment)
        connection.commit()
        connection.read_only = readonly
        return connection
    except Exception:
        connection.close()
        raise
