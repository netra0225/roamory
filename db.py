import os
import re
import secrets
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

    activity_columns = db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='activities'"
    ).fetchall()
    activity_column_names = {row['column_name'] for row in activity_columns}
    if 'latitude' not in activity_column_names:
        db.execute('ALTER TABLE activities ADD COLUMN latitude REAL')
    if 'longitude' not in activity_column_names:
        db.execute('ALTER TABLE activities ADD COLUMN longitude REAL')

    db.execute(
        '''CREATE TABLE IF NOT EXISTS app_meta (
               id SERIAL PRIMARY KEY,
               meta_key TEXT NOT NULL UNIQUE,
               meta_value TEXT NOT NULL
           )'''
    )



def _init_sqlite_schema(db, schema_path: Path):
    db.executescript(schema_path.read_text(encoding='utf-8'))
    settings_columns = {row['name'] for row in db.execute('PRAGMA table_info(settings)').fetchall()}
    if 'starter_seeded' not in settings_columns:
        db.execute('ALTER TABLE settings ADD COLUMN starter_seeded INTEGER NOT NULL DEFAULT 0')

    activity_columns = {row['name'] for row in db.execute('PRAGMA table_info(activities)').fetchall()}
    if 'latitude' not in activity_columns:
        db.execute('ALTER TABLE activities ADD COLUMN latitude REAL')
    if 'longitude' not in activity_columns:
        db.execute('ALTER TABLE activities ADD COLUMN longitude REAL')

    db.execute(
        '''CREATE TABLE IF NOT EXISTS app_meta (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               meta_key TEXT NOT NULL UNIQUE,
               meta_value TEXT NOT NULL
           )'''
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


def _backfill_udaipur_showcase_itinerary(db):
    """Fill the previously empty final days of the built-in Udaipur showcase once."""
    migration_key = 'udaipur_showcase_days_4_6_v2'
    applied = db.execute(
        'SELECT id FROM app_meta WHERE meta_key = ?',
        (migration_key,),
    ).fetchone()
    if applied:
        return

    specs = {
        4: [
            ('Jagdish Temple and old city lanes', 'destination', '09:00', '10:45', 'Jagdish Temple', 24.5795, 73.6835, 0, 'Start early, then wander the lanes toward the lake.'),
            ('Bagore Ki Haveli and Gangaur Ghat', 'activity', '16:30', '18:30', 'Bagore Ki Haveli', 24.5799, 73.6814, 300, 'Stay through golden hour by the ghat.'),
        ],
        5: [
            ('Shilpgram arts village', 'activity', '10:00', '12:30', 'Shilpgram', 24.6086, 73.6505, 500, 'Keep time for the craft stalls and open-air exhibits.'),
            ('Fateh Sagar Lake sunset walk', 'destination', '17:00', '19:00', 'Fateh Sagar Lake', 24.6012, 73.6836, 0, 'Walk the promenade and stop for something cold.'),
        ],
        6: [
            ('Badi Lake morning drive', 'destination', '08:00', '10:30', 'Badi Lake', 24.6406, 73.6209, 1200, 'A quieter last morning outside the old city.'),
            ('Hathipole Market farewell stop', 'activity', '11:30', '13:00', 'Hathipole Market', 24.5858, 73.6907, 1500, 'Pick up small souvenirs before heading back.'),
        ],
    }

    trips = db.execute(
        '''SELECT id FROM trips
           WHERE LOWER(destination)=?
             AND (id=1 OR title=?)''',
        ('udaipur', 'Palaces, Lakes & Late Sunsets'),
    ).fetchall()

    for trip in trips:
        days = db.execute(
            '''SELECT id, day_number, date FROM trip_days
               WHERE trip_id=? AND day_number IN (4,5,6)
               ORDER BY day_number''',
            (trip['id'],),
        ).fetchall()
        for day in days:
            existing = db.execute(
                'SELECT COUNT(*) AS c FROM activities WHERE trip_id=? AND day_id=?',
                (trip['id'], day['id']),
            ).fetchone()['c']
            if existing:
                continue
            for name, kind, start, end, location, latitude, longitude, estimated, note in specs.get(day['day_number'], []):
                db.execute(
                    '''INSERT INTO activities
                       (trip_id,day_id,name,type,activity_date,start_time,end_time,location,
                        latitude,longitude,estimated_cost,actual_cost,notes,status)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        trip['id'], day['id'], name, kind, day['date'], start, end, location,
                        latitude, longitude, estimated, 0, note, 'planned',
                    ),
                )

    db.execute(
        'INSERT INTO app_meta (meta_key, meta_value) VALUES (?, ?)',
        (migration_key, '1'),
    )


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / 'schema.sql'

    if _using_postgres():
        _init_postgres_schema(db, schema_path)
    else:
        _init_sqlite_schema(db, schema_path)

    # Remove only the old built-in Summer Atlas showcase from existing accounts.
    db.execute(
        '''DELETE FROM trips
           WHERE destination = ?
             AND title IN (?, ?)''',
        (
            'Summer Atlas',
            'Five Places I Keep Thinking About',
            'Places that stayed with me',
        ),
    )
    _configure_persistent_secret(db)
    _backfill_udaipur_showcase_itinerary(db)
    db.commit()


def init_app(app):
    materialize_dashboard_assets(app.root_path)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
