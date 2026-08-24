import os
import re
import secrets
import sqlite3
from datetime import date
from pathlib import Path

from flask import current_app, g

from asset_bootstrap import materialize_dashboard_assets


ARCHIVE_TITLE = 'Places that stayed with me'
ARCHIVE_DESCRIPTION = (
    'A finished journey gathered into journal pages of coast, lake, spring streets, '
    'mountains and palace light.'
)


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
        return sql.replace('?', '%s')

    def execute(self, sql: str, params=()):
        statement = sql.strip()
        adapted = self._adapt_sql(statement)
        is_insert = bool(re.match(r'^INSERT\s+INTO\b', statement, flags=re.IGNORECASE))

        if is_insert and ' RETURNING ' not in adapted.upper():
            adapted = adapted.rstrip().rstrip(';') + ' RETURNING id'

        cursor = self._connection.cursor()
        try:
            cursor.execute(adapted, tuple(params))
        except self._psycopg.errors.UniqueViolation as exc:
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

    db.execute(
        '''CREATE TABLE IF NOT EXISTS app_meta (
               id SERIAL PRIMARY KEY,
               meta_key TEXT NOT NULL UNIQUE,
               meta_value TEXT NOT NULL
           )'''
    )

    db.execute(
        f'''CREATE OR REPLACE FUNCTION normalize_roamory_starter_archive()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.destination = 'Summer Atlas' THEN
                    NEW.title := '{ARCHIVE_TITLE}';
                    NEW.description := '{ARCHIVE_DESCRIPTION}';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql'''
    )
    db.execute('DROP TRIGGER IF EXISTS normalize_roamory_starter_archive_trigger ON trips')
    db.execute(
        '''CREATE TRIGGER normalize_roamory_starter_archive_trigger
           BEFORE INSERT OR UPDATE ON trips
           FOR EACH ROW EXECUTE FUNCTION normalize_roamory_starter_archive()'''
    )

    db.execute(
        '''CREATE OR REPLACE FUNCTION suppress_old_udaipur_journal_memory()
           RETURNS TRIGGER AS $$
           BEGIN
               IF NEW.title = 'Udaipur Blue Hour'
                  AND NEW.location = 'Udaipur'
                  AND EXISTS (
                      SELECT 1 FROM trips
                      WHERE id = NEW.trip_id AND destination = 'Summer Atlas'
                  ) THEN
                   RETURN NULL;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql'''
    )
    db.execute('DROP TRIGGER IF EXISTS suppress_old_udaipur_journal_memory_trigger ON memories')
    db.execute(
        '''CREATE TRIGGER suppress_old_udaipur_journal_memory_trigger
           BEFORE INSERT ON memories
           FOR EACH ROW EXECUTE FUNCTION suppress_old_udaipur_journal_memory()'''
    )


def _init_sqlite_schema(db, schema_path: Path):
    db.executescript(schema_path.read_text(encoding='utf-8'))
    settings_columns = {row['name'] for row in db.execute('PRAGMA table_info(settings)').fetchall()}
    if 'starter_seeded' not in settings_columns:
        db.execute('ALTER TABLE settings ADD COLUMN starter_seeded INTEGER NOT NULL DEFAULT 0')

    db.execute(
        '''CREATE TABLE IF NOT EXISTS app_meta (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               meta_key TEXT NOT NULL UNIQUE,
               meta_value TEXT NOT NULL
           )'''
    )

    title = ARCHIVE_TITLE.replace("'", "''")
    description = ARCHIVE_DESCRIPTION.replace("'", "''")
    db.executescript(
        f'''DROP TRIGGER IF EXISTS normalize_roamory_starter_archive_insert;
            CREATE TRIGGER normalize_roamory_starter_archive_insert
            AFTER INSERT ON trips
            WHEN NEW.destination = 'Summer Atlas'
            BEGIN
                UPDATE trips
                SET title = '{title}', description = '{description}'
                WHERE id = NEW.id;
            END;

            DROP TRIGGER IF EXISTS suppress_old_udaipur_journal_memory_insert;
            CREATE TRIGGER suppress_old_udaipur_journal_memory_insert
            AFTER INSERT ON memories
            WHEN NEW.title = 'Udaipur Blue Hour'
                 AND NEW.location = 'Udaipur'
                 AND EXISTS (
                     SELECT 1 FROM trips
                     WHERE id = NEW.trip_id AND destination = 'Summer Atlas'
                 )
            BEGIN
                DELETE FROM memories WHERE id = NEW.id;
            END;'''
    )


def _configure_persistent_secret(db):
    explicit_secret = os.getenv('ROAMORY_SECRET_KEY', '').strip()
    if explicit_secret:
        current_app.config['SECRET_KEY'] = explicit_secret
        return

    row = db.execute(
        'SELECT meta_value FROM app_meta WHERE meta_key = ?',
        ('session_secret',),
    ).fetchone()
    if row:
        current_app.config['SECRET_KEY'] = row['meta_value']
        return

    generated = secrets.token_hex(32)
    db.execute(
        'INSERT INTO app_meta (meta_key, meta_value) VALUES (?, ?)',
        ('session_secret', generated),
    )
    current_app.config['SECRET_KEY'] = generated


def _journal_template_context():
    """Provide one curated journal: ongoing Udaipur first, completed memories after it."""
    if not getattr(g, 'user', None):
        return {
            'journal_opening_trip': None,
            'completed_journal_memories': [],
        }

    today_value = date.today().isoformat()
    db = get_db()
    opening_trip = db.execute(
        '''SELECT * FROM trips
           WHERE user_id=? AND start_date<=? AND end_date>=?
           ORDER BY start_date DESC, id DESC LIMIT 1''',
        (g.user['id'], today_value, today_value),
    ).fetchone()

    completed_memories = db.execute(
        '''SELECT m.*, t.id AS source_trip_id, t.destination AS trip_destination,
                  t.title AS trip_title, t.start_date AS trip_start_date,
                  t.end_date AS trip_end_date, t.cover_filename AS trip_cover_filename,
                  t.cover_url AS trip_cover_url
           FROM memories m
           JOIN trips t ON t.id=m.trip_id
           WHERE t.user_id=?
             AND t.end_date < ?
             AND LOWER(COALESCE(m.location, '')) NOT LIKE '%udaipur%'
             AND LOWER(COALESCE(m.title, '')) NOT LIKE '%udaipur%'
           ORDER BY t.end_date DESC,
                    COALESCE(m.memory_date, t.end_date) DESC,
                    m.id DESC''',
        (g.user['id'], today_value),
    ).fetchall()

    return {
        'journal_opening_trip': opening_trip,
        'completed_journal_memories': completed_memories,
    }


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / 'schema.sql'

    if _using_postgres():
        _init_postgres_schema(db, schema_path)
    else:
        _init_sqlite_schema(db, schema_path)

    db.execute(
        '''UPDATE trips
           SET title = ?, description = ?
           WHERE destination = ?''',
        (ARCHIVE_TITLE, ARCHIVE_DESCRIPTION, 'Summer Atlas'),
    )

    # Remove the old starter Udaipur archive page. The curated Udaipur page now
    # opens the journal and must not be duplicated by the original demo memory.
    db.execute(
        '''DELETE FROM memories
           WHERE title=? AND location=?
             AND trip_id IN (SELECT id FROM trips WHERE destination=?)''',
        ('Udaipur Blue Hour', 'Udaipur', 'Summer Atlas'),
    )

    _configure_persistent_secret(db)
    db.commit()


def init_app(app):
    materialize_dashboard_assets(app.root_path)
    app.teardown_appcontext(close_db)
    app.context_processor(_journal_template_context)
    with app.app_context():
        init_db()
