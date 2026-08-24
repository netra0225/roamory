import os
import re
import sqlite3
from pathlib import Path

from flask import current_app, g

from asset_bootstrap import materialize_dashboard_assets


class _PostgresResult:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PostgresConnection:
    """Small compatibility layer so existing SQLite-style queries also work on Postgres."""

    def __init__(self, connection, psycopg_module):
        self._connection = connection
        self._psycopg = psycopg_module

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        # Roamory's existing queries use SQLite qmark placeholders.
        return sql.replace('?', '%s')

    def execute(self, sql: str, params=()):
        statement = sql.strip()
        adapted = self._adapt_sql(statement)
        is_insert = bool(re.match(r'^INSERT\s+INTO\b', statement, flags=re.IGNORECASE))

        # Every Roamory table has an integer id. RETURNING keeps the existing
        # cursor.lastrowid contract used throughout the Flask app.
        if is_insert and ' RETURNING ' not in adapted.upper():
            adapted = adapted.rstrip().rstrip(';') + ' RETURNING id'

        cursor = self._connection.cursor()
        try:
            cursor.execute(adapted, tuple(params))
        except self._psycopg.errors.UniqueViolation as exc:
            # Preserve the error shape the existing registration flow expects.
            self._connection.rollback()
            raise sqlite3.IntegrityError('UNIQUE constraint failed') from exc

        lastrowid = None
        if is_insert:
            returned = cursor.fetchone()
            if returned is not None:
                lastrowid = returned['id'] if isinstance(returned, dict) else returned[0]
        return _PostgresResult(cursor, lastrowid=lastrowid)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def _connect_postgres(database_url: str):
    import psycopg
    from psycopg.rows import dict_row

    # Render currently supplies postgresql:// URLs. Accept the legacy alias too.
    if database_url.startswith('postgres://'):
        database_url = 'postgresql://' + database_url[len('postgres://'):]
    connection = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
    return _PostgresConnection(connection, psycopg)


def _using_postgres() -> bool:
    return bool(os.getenv('DATABASE_URL', '').strip())


def get_db():
    if 'db' not in g:
        database_url = os.getenv('DATABASE_URL', '').strip()
        if database_url:
            g.db = _connect_postgres(database_url)
        else:
            database_path = os.getenv('ROAMORY_DATABASE_PATH', current_app.config['DATABASE'])
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(_error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _init_postgres_schema(db, schema_path: Path):
    schema = schema_path.read_text(encoding='utf-8')
    schema = re.sub(r'^PRAGMA\s+foreign_keys\s*=\s*ON;\s*$', '', schema, flags=re.IGNORECASE | re.MULTILINE)
    schema = schema.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')

    for statement in schema.split(';'):
        statement = statement.strip()
        if statement:
            db.execute(statement)

    columns = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='settings'"
    ).fetchall()
    settings_columns = {row['column_name'] for row in columns}
    if 'starter_seeded' not in settings_columns:
        db.execute('ALTER TABLE settings ADD COLUMN starter_seeded INTEGER NOT NULL DEFAULT 0')


def _init_sqlite_schema(db, schema_path: Path):
    db.executescript(schema_path.read_text(encoding='utf-8'))
    settings_columns = {row['name'] for row in db.execute('PRAGMA table_info(settings)').fetchall()}
    if 'starter_seeded' not in settings_columns:
        db.execute('ALTER TABLE settings ADD COLUMN starter_seeded INTEGER NOT NULL DEFAULT 0')


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / 'schema.sql'

    if _using_postgres():
        _init_postgres_schema(db, schema_path)
    else:
        _init_sqlite_schema(db, schema_path)

    # Migrate existing starter archive copy to the open-ended wording.
    db.execute(
        '''UPDATE trips
           SET title = ?, description = ?
           WHERE destination = ? AND title = ?''',
        (
            'Places that stayed with me',
            'A finished journey gathered into journal pages of coast, lake, spring streets, mountains and palace light.',
            'Summer Atlas',
            'Five Places I Keep Thinking About',
        ),
    )
    db.commit()


def init_app(app):
    materialize_dashboard_assets(app.root_path)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
