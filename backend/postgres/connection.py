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


def _connect(dsn, environment, readonly, migration):
    import psycopg
    from psycopg.rows import dict_row
    connection = psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
                                options='-c timezone=UTC -c statement_timeout=10000 -c lock_timeout=3000')
    try:
        if migration:
            login = connection.execute('SELECT session_user AS login').fetchone()['login']
            if login != 'tradebot_migrator':
                raise EnvironmentMismatch('migration connection requires the restricted migrator login')
            # Explicit connection mode only. NOINHERIT remains enforced for the
            # login; owner activation persists only on this migration connection.
            connection.execute('SET ROLE tradebot_owner')
        validate_environment(connection, environment)
        connection.commit()
        connection.read_only = readonly
        return connection
    except Exception:
        connection.close()
        raise


def connect(dsn, environment='preprod', readonly=False):
    """Connect as a runtime role without assuming or inheriting another role."""
    return _connect(dsn, environment, readonly, migration=False)


def connect_migrator(dsn, environment='preprod', readonly=False):
    """Explicit migration/inspection connection; only tradebot_migrator may use it.

    The foundation migrator deliberately has NOINHERIT and cannot read its
    identity marker before SET ROLE. Runtime connections never take this path.
    Lifecycle connections become available only after business grants are applied.
    """
    return _connect(dsn, environment, readonly, migration=True)
