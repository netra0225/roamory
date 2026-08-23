import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(_error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = Path(current_app.root_path) / 'schema.sql'
    db.executescript(schema_path.read_text(encoding='utf-8'))
    # Lightweight migration for databases created by the first Roamory build.
    settings_columns = {row['name'] for row in db.execute('PRAGMA table_info(settings)').fetchall()}
    if 'starter_seeded' not in settings_columns:
        db.execute("ALTER TABLE settings ADD COLUMN starter_seeded INTEGER NOT NULL DEFAULT 0")
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
