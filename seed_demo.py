from werkzeug.security import generate_password_hash

from app import app
from db import get_db
from starter_data import seed_starter_content

DEMO_EMAIL = 'demo@roamory.local'
DEMO_PASSWORD = 'roamory123'

with app.app_context():
    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE email=?', (DEMO_EMAIL,)).fetchone()
    if existing:
        seed_starter_content(db, existing['id'])
        db.execute('UPDATE settings SET starter_seeded=1 WHERE user_id=?', (existing['id'],))
        db.commit()
        print('Demo account already exists; starter content checked.')
        print(f'Login: {DEMO_EMAIL}')
        print(f'Password: {DEMO_PASSWORD}')
        raise SystemExit(0)

    cur = db.execute(
        'INSERT INTO users (full_name,email,password_hash) VALUES (?,?,?)',
        ('Mira Sen', DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD)),
    )
    user_id = cur.lastrowid
    db.execute(
        'INSERT INTO settings (user_id,currency,date_format,appearance) VALUES (?,?,?,?)',
        (user_id, 'INR', 'DD MMM YYYY', 'sunlit'),
    )
    seed_starter_content(db, user_id)
    db.execute('UPDATE settings SET starter_seeded=1 WHERE user_id=?', (user_id,))
    db.commit()

    print('Roamory showcase account created.')
    print(f'Login: {DEMO_EMAIL}')
    print(f'Password: {DEMO_PASSWORD}')
