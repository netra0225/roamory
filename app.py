from __future__ import annotations

import os
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template, request,
    send_from_directory, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import get_db, init_app as init_db_app
from starter_data import seed_starter_content
from recommendations import RecommendationError, resolve_destination, search_nearby_places
from trip_builder import build_trip_plan

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'txt'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

DEFAULT_IMAGES = {
    'coast': 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1600&q=86',
    'italy': 'https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=1600&q=86',
    'mountain': 'https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1600&q=86',
    'city': 'https://images.unsplash.com/photo-1499856871958-5b9627545d1a?auto=format&fit=crop&w=1600&q=86',
    'forest': 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=86',
    'travel': 'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=1600&q=86',
}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('ROAMORY_SECRET_KEY', secrets.token_hex(32)),
    DATABASE=str(BASE_DIR / 'roamory.sqlite3'),
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('ROAMORY_SECURE_COOKIE', '0') == '1',
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
init_db_app(app)


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login', next=request.path))
        return view(**kwargs)
    return wrapped_view


@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
        g.settings = None
        return
    g.user = get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    g.settings = get_db().execute('SELECT * FROM settings WHERE user_id = ?', (user_id,)).fetchone()


def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.before_request
def verify_csrf():
    if request.method == 'POST':
        expected = session.get('_csrf_token')
        supplied = request.form.get('csrf_token')
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description='Invalid or missing CSRF token.')


def allowed_file(filename: str, allowed: set[str]) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def save_upload(file_storage, allowed: set[str], prefix: str) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename, allowed):
        raise ValueError('Unsupported file type.')
    original = secure_filename(file_storage.filename)
    ext = original.rsplit('.', 1)[1].lower()
    filename = f'{prefix}-{secrets.token_hex(8)}.{ext}'
    file_storage.save(UPLOAD_DIR / filename)
    return filename


def safe_delete_upload(filename: str | None):
    if not filename:
        return
    path = UPLOAD_DIR / filename
    if path.exists() and path.is_file():
        path.unlink(missing_ok=True)


def get_trip_or_404(trip_id: int):
    trip = get_db().execute(
        'SELECT * FROM trips WHERE id = ? AND user_id = ?',
        (trip_id, g.user['id'])
    ).fetchone()
    if trip is None:
        abort(404)
    return trip


def trip_days(trip_id: int):
    return get_db().execute(
        'SELECT * FROM trip_days WHERE trip_id = ? ORDER BY day_number', (trip_id,)
    ).fetchall()


def trip_status(trip) -> str:
    today = date.today().isoformat()
    if today < trip['start_date']:
        return 'upcoming'
    if today > trip['end_date']:
        return 'completed'
    return 'ongoing'


def currency_symbol(code: str | None) -> str:
    return {'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥'}.get(code or 'INR', '₹')


def cover_for_trip(trip):
    if trip['cover_filename']:
        return url_for('static', filename=f"uploads/{trip['cover_filename']}")
    if trip['cover_url']:
        return trip['cover_url']
    destination = trip['destination'].lower()
    if any(k in destination for k in ('amalfi', 'como', 'italy', 'positano')):
        return DEFAULT_IMAGES['italy']
    if any(k in destination for k in ('banff', 'switzerland', 'mountain', 'alps')):
        return DEFAULT_IMAGES['mountain']
    if any(k in destination for k in ('udaipur', 'kyoto', 'paris', 'city')):
        return DEFAULT_IMAGES['city']
    if any(k in destination for k in ('bali', 'coast', 'beach', 'island')):
        return DEFAULT_IMAGES['coast']
    return DEFAULT_IMAGES['travel']


@app.context_processor
def inject_helpers():
    return {
        'trip_status': trip_status,
        'cover_for_trip': cover_for_trip,
        'currency_symbol': currency_symbol,
        'csrf_token': csrf_token,
        'today_iso': date.today().isoformat(),
    }



@app.route('/_health/recommendations')
def recommendation_health():
    try:
        destination = resolve_destination('Coonoor')
        selected = destination['selected']
        places = search_nearby_places(
            selected['latitude'],
            selected['longitude'],
            categories='attractions',
            max_results=5,
        )
        return {
            'ok': True,
            'destination': selected['name'],
            'provider': selected.get('provider'),
            'places': [place['name'] for place in places[:5]],
        }
    except RecommendationError as exc:
        return {'ok': False, 'error': str(exc)}, 503



@app.route('/')
def landing():
    if g.user:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/register', methods=('GET', 'POST'))
def register():
    if g.user:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        error = None
        if not full_name:
            error = 'Full name is required.'
        elif '@' not in email or '.' not in email.split('@')[-1]:
            error = 'Enter a valid email address.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        if error is None:
            db = get_db()
            try:
                cur = db.execute(
                    'INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)',
                    (full_name, email, generate_password_hash(password))
                )
                user_id = cur.lastrowid
                db.execute('INSERT INTO settings (user_id) VALUES (?)', (user_id,))
                seed_starter_content(db, user_id)
                db.execute('UPDATE settings SET starter_seeded=1 WHERE user_id=?', (user_id,))
                db.commit()
            except Exception as exc:
                if 'UNIQUE constraint failed' in str(exc):
                    error = 'An account with that email already exists.'
                else:
                    raise
            else:
                session.clear()
                session['user_id'] = user_id
                flash('Welcome to Roamory. A fully editable starter journey is ready so you can explore every feature.', 'success')
                return redirect(url_for('dashboard'))
        flash(error, 'error')
    return render_template('auth/register.html')


@app.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = get_db().execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Incorrect email or password.', 'error')
        else:
            session.clear()
            session['user_id'] = user['id']
            next_url = request.args.get('next')
            return redirect(next_url if next_url and next_url.startswith('/') else url_for('dashboard'))
    return render_template('auth/login.html')


@app.post('/logout')
@login_required
def logout():
    session.clear()
    flash('You are logged out.', 'info')
    return redirect(url_for('landing'))


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    trips = db.execute(
        'SELECT * FROM trips WHERE user_id = ? ORDER BY start_date', (g.user['id'],)
    ).fetchall()
    # Existing accounts from the first build may have opened onto a blank dashboard.
    # Seed the showcase only once; after that, users can delete everything and keep a true empty state.
    starter_seeded = g.settings['starter_seeded'] if g.settings and 'starter_seeded' in g.settings.keys() else 0
    if not trips and not starter_seeded:
        seed_starter_content(db, g.user['id'])
        db.execute('UPDATE settings SET starter_seeded=1 WHERE user_id=?', (g.user['id'],))
        db.commit()
        trips = db.execute(
            'SELECT * FROM trips WHERE user_id = ? ORDER BY start_date', (g.user['id'],)
        ).fetchall()
    ongoing = next((t for t in trips if trip_status(t) == 'ongoing'), None)
    upcoming = [t for t in trips if trip_status(t) == 'upcoming']
    completed = [t for t in trips if trip_status(t) == 'completed']
    readiness = None
    current_activity = None
    next_activity = None
    dashboard_memories = []
    dashboard_documents = []
    spent = 0
    current_day = None
    if ongoing:
        readiness = db.execute(
            '''SELECT
                (SELECT COUNT(*) FROM packing_items WHERE trip_id = ?) packed_total,
                (SELECT COUNT(*) FROM packing_items WHERE trip_id = ? AND packed = 1) packed_done,
                (SELECT COUNT(*) FROM documents WHERE trip_id = ?) docs,
                (SELECT COUNT(*) FROM activities WHERE trip_id = ?) activities,
                (SELECT COUNT(*) FROM activities WHERE trip_id = ? AND status = 'completed') completed_activities''',
            (ongoing['id'],) * 5
        ).fetchone()
        all_activities = db.execute(
            '''SELECT a.*, d.day_number FROM activities a JOIN trip_days d ON d.id=a.day_id
               WHERE a.trip_id=? ORDER BY a.activity_date, COALESCE(a.start_time,'23:59'), a.id''',
            (ongoing['id'],)
        ).fetchall()
        pending = [a for a in all_activities if a['status'] in ('planned','changed')]
        current_activity = pending[0] if pending else None
        next_activity = pending[1] if len(pending) > 1 else None
        if current_activity:
            current_day = db.execute('SELECT * FROM trip_days WHERE id=?', (current_activity['day_id'],)).fetchone()
        spent = db.execute('SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE trip_id=?', (ongoing['id'],)).fetchone()['s']
        dashboard_memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY memory_date DESC,id DESC LIMIT 3', (ongoing['id'],)).fetchall()
        dashboard_documents = db.execute('SELECT * FROM documents WHERE trip_id=? ORDER BY created_at DESC LIMIT 3', (ongoing['id'],)).fetchall()

    archive_memories = []
    archive_trip = completed[-1] if completed else None
    if archive_trip:
        archive_memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY memory_date LIMIT 5', (archive_trip['id'],)).fetchall()

    countdown = None
    if upcoming:
        try:
            countdown = max(0, (datetime.strptime(upcoming[0]['start_date'], '%Y-%m-%d').date() - date.today()).days)
        except ValueError:
            countdown = None

    return render_template(
        'dashboard.html', trips=trips, ongoing=ongoing, upcoming=upcoming, completed=completed, readiness=readiness,
        current_activity=current_activity, next_activity=next_activity, current_day=current_day, spent=spent,
        dashboard_memories=dashboard_memories, dashboard_documents=dashboard_documents,
        archive_trip=archive_trip, archive_memories=archive_memories, countdown=countdown
    )


@app.route('/trips')
@login_required
def trips():
    rows = get_db().execute(
        'SELECT * FROM trips WHERE user_id = ? ORDER BY start_date DESC', (g.user['id'],)
    ).fetchall()
    grouped = {'ongoing': [], 'upcoming': [], 'completed': []}
    for row in rows:
        grouped[trip_status(row)].append(row)
    return render_template('trips.html', grouped=grouped)


def ensure_trip_days(db, trip_id: int, start_date: str, end_date: str):
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    db.execute('DELETE FROM trip_days WHERE trip_id = ?', (trip_id,))
    current = start
    day_number = 1
    while current <= end:
        db.execute(
            'INSERT INTO trip_days (trip_id, day_number, date, title) VALUES (?, ?, ?, ?)',
            (trip_id, day_number, current.isoformat(), f'Day {day_number}')
        )
        current += timedelta(days=1)
        day_number += 1


def create_default_packing(db, trip_id: int):
    for idx, name in enumerate(('Essentials', 'Clothing', 'Toiletries', 'Electronics', 'Documents')):
        db.execute(
            'INSERT INTO packing_categories (trip_id, name, sort_order) VALUES (?, ?, ?)',
            (trip_id, name, idx)
        )


@app.route('/trips/new', methods=('GET', 'POST'))
@login_required
def create_trip():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        destination = request.form.get('destination', '').strip()
        start_date = request.form.get('start_date', '')
        end_date = request.form.get('end_date', '')
        description = request.form.get('description', '').strip()
        accent = request.form.get('accent', 'mediterranean')
        planned_budget = request.form.get('planned_budget', '0').strip() or '0'
        error = None
        try:
            start_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            if end_obj < start_obj:
                error = 'End date cannot be before start date.'
            budget_value = float(planned_budget)
            if budget_value < 0:
                error = 'Budget cannot be negative.'
        except ValueError:
            error = 'Enter valid trip dates and budget.'
        if not title or not destination or not start_date or not end_date:
            error = 'Trip title, destination and dates are required.'
        cover_filename = None
        if error is None:
            try:
                cover_filename = save_upload(request.files.get('cover'), ALLOWED_IMAGE_EXTENSIONS, 'trip')
            except ValueError as exc:
                error = str(exc)
        if error:
            flash(error, 'error')
        else:
            db = get_db()
            cur = db.execute(
                '''INSERT INTO trips
                (user_id, title, destination, start_date, end_date, description, cover_filename, accent, planned_budget)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (g.user['id'], title, destination, start_date, end_date, description, cover_filename, accent, budget_value)
            )
            trip_id = cur.lastrowid
            ensure_trip_days(db, trip_id, start_date, end_date)
            create_default_packing(db, trip_id)
            db.commit()
            flash('Trip created. Start shaping the route.', 'success')
            return redirect(url_for('trip_overview', trip_id=trip_id))
    return render_template('trip_form.html', trip=None)


@app.route('/trips/<int:trip_id>/edit', methods=('GET', 'POST'))
@login_required
def edit_trip(trip_id):
    trip = get_trip_or_404(trip_id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        destination = request.form.get('destination', '').strip()
        start_date = request.form.get('start_date', '')
        end_date = request.form.get('end_date', '')
        description = request.form.get('description', '').strip()
        accent = request.form.get('accent', trip['accent'])
        planned_budget = request.form.get('planned_budget', str(trip['planned_budget'])).strip() or '0'
        error = None
        try:
            if datetime.strptime(end_date, '%Y-%m-%d') < datetime.strptime(start_date, '%Y-%m-%d'):
                error = 'End date cannot be before start date.'
            budget_value = float(planned_budget)
            if budget_value < 0:
                error = 'Budget cannot be negative.'
        except ValueError:
            error = 'Enter valid trip dates and budget.'
        new_cover = None
        if error is None:
            try:
                new_cover = save_upload(request.files.get('cover'), ALLOWED_IMAGE_EXTENSIONS, 'trip')
            except ValueError as exc:
                error = str(exc)
        if error:
            flash(error, 'error')
        else:
            cover_filename = new_cover or trip['cover_filename']
            db = get_db()
            db.execute(
                '''UPDATE trips SET title=?, destination=?, start_date=?, end_date=?, description=?, cover_filename=?, accent=?, planned_budget=?
                   WHERE id=? AND user_id=?''',
                (title, destination, start_date, end_date, description, cover_filename, accent, budget_value, trip_id, g.user['id'])
            )
            if start_date != trip['start_date'] or end_date != trip['end_date']:
                activity_count = db.execute('SELECT COUNT(*) c FROM activities WHERE trip_id=?', (trip_id,)).fetchone()['c']
                if activity_count == 0:
                    ensure_trip_days(db, trip_id, start_date, end_date)
                else:
                    flash('Dates updated. Existing itinerary days were preserved to avoid deleting activities.', 'info')
            db.commit()
            if new_cover:
                safe_delete_upload(trip['cover_filename'])
            flash('Trip details updated.', 'success')
            return redirect(url_for('trip_overview', trip_id=trip_id))
    return render_template('trip_form.html', trip=trip)


@app.post('/trips/<int:trip_id>/delete')
@login_required
def delete_trip(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    files = db.execute('SELECT filename FROM documents WHERE trip_id=?', (trip_id,)).fetchall()
    images = db.execute('SELECT image_filename FROM memories WHERE trip_id=?', (trip_id,)).fetchall()
    db.execute('DELETE FROM trips WHERE id=? AND user_id=?', (trip_id, g.user['id']))
    db.commit()
    safe_delete_upload(trip['cover_filename'])
    for row in files:
        safe_delete_upload(row['filename'])
    for row in images:
        safe_delete_upload(row['image_filename'])
    flash('Trip deleted.', 'info')
    return redirect(url_for('trips'))


@app.route('/trips/<int:trip_id>')
@login_required
def trip_overview(trip_id):
    trip = get_trip_or_404(trip_id)
    days = trip_days(trip_id)
    activities = get_db().execute(
        '''SELECT a.*, d.day_number FROM activities a JOIN trip_days d ON d.id=a.day_id
           WHERE a.trip_id=? ORDER BY a.activity_date, a.start_time''', (trip_id,)
    ).fetchall()
    expenses = get_db().execute('SELECT COALESCE(SUM(amount),0) spent FROM expenses WHERE trip_id=?', (trip_id,)).fetchone()['spent']
    packing = get_db().execute(
        'SELECT COUNT(*) total, COALESCE(SUM(packed),0) packed FROM packing_items WHERE trip_id=?', (trip_id,)
    ).fetchone()
    docs = get_db().execute('SELECT COUNT(*) c FROM documents WHERE trip_id=?', (trip_id,)).fetchone()['c']
    memories = get_db().execute('SELECT * FROM memories WHERE trip_id=? ORDER BY memory_date DESC LIMIT 4', (trip_id,)).fetchall()
    completed = sum(1 for a in activities if a['status'] == 'completed')
    current = next((a for a in activities if a['status'] in ('planned', 'changed')), None)
    return render_template('overview.html', trip=trip, days=days, activities=activities, spent=expenses, packing=packing, docs=docs, memories=memories, completed=completed, current=current)


@app.route('/trips/<int:trip_id>/itinerary')
@login_required
def itinerary(trip_id):
    trip = get_trip_or_404(trip_id)
    days = trip_days(trip_id)
    selected_day = request.args.get('day', type=int)
    if selected_day is None and days:
        selected_day = days[0]['day_number']
    activities = get_db().execute(
        '''SELECT a.*, d.day_number FROM activities a JOIN trip_days d ON d.id=a.day_id
           WHERE a.trip_id=? ORDER BY d.day_number, COALESCE(a.start_time,'23:59'), a.id''', (trip_id,)
    ).fetchall()
    return render_template('itinerary.html', trip=trip, days=days, activities=activities, selected_day=selected_day)


@app.post('/trips/<int:trip_id>/build')
@login_required
def build_trip(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()

    existing = db.execute(
        'SELECT COUNT(*) c FROM activities WHERE trip_id=?', (trip_id,)
    ).fetchone()['c']
    if existing:
        flash('Build My Trip only fills an empty itinerary, so your existing plans stay untouched.', 'info')
        return redirect(url_for('itinerary', trip_id=trip_id))

    try:
        plan = build_trip_plan(trip)
    except RecommendationError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('itinerary', trip_id=trip_id))

    day_rows = {row['day_number']: row for row in trip_days(trip_id)}
    inserted = 0
    for planned_day in plan['days']:
        day = day_rows.get(planned_day['day_number'])
        if day is None:
            continue
        for item in planned_day['items']:
            db.execute(
                '''INSERT INTO activities
                (trip_id, day_id, name, type, activity_date, start_time, end_time, location,
                 estimated_cost, actual_cost, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    trip_id,
                    day['id'],
                    item['name'],
                    item['type'],
                    day['date'],
                    item['start_time'],
                    None,
                    item['location'],
                    item['estimated_cost'],
                    0,
                    item['notes'],
                    'planned',
                )
            )
            inserted += 1

    if not inserted:
        flash('We found the destination, but not enough verified places to build this trip.', 'error')
        return redirect(url_for('itinerary', trip_id=trip_id))

    db.commit()
    flash(f'Roamory built a simple {len(plan["days"])}-day itinerary with {inserted} suggested stops.', 'success')
    return redirect(url_for('itinerary', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/activities/new', methods=('GET', 'POST'))
@login_required
def add_activity(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    days = trip_days(trip_id)
    documents = db.execute('SELECT * FROM documents WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        activity_type = request.form.get('type', 'activity')
        day_id = request.form.get('day_id', type=int)
        selected = db.execute('SELECT * FROM trip_days WHERE id=? AND trip_id=?', (day_id, trip_id)).fetchone()
        document_id = request.form.get('document_id', type=int)
        memory_id = request.form.get('memory_id', type=int)
        if document_id and db.execute('SELECT id FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone() is None:
            document_id = None
        if memory_id and db.execute('SELECT id FROM memories WHERE id=? AND trip_id=?', (memory_id, trip_id)).fetchone() is None:
            memory_id = None
        if not name or selected is None:
            flash('Activity name and trip day are required.', 'error')
        else:
            estimated = request.form.get('estimated_cost', '0') or '0'
            actual = request.form.get('actual_cost', '0') or '0'
            try:
                estimated = max(0, float(estimated))
                actual = max(0, float(actual))
            except ValueError:
                flash('Costs must be valid numbers.', 'error')
                return render_template('activity_form.html', trip=trip, days=days, activity=None, documents=documents, memories=memories)
            db.execute(
                '''INSERT INTO activities
                (trip_id, day_id, name, type, activity_date, start_time, end_time, location, estimated_cost, actual_cost, notes, status, document_id, memory_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (trip_id, day_id, name, activity_type, selected['date'], request.form.get('start_time') or None,
                 request.form.get('end_time') or None, request.form.get('location','').strip(), estimated, actual,
                 request.form.get('notes','').strip(), request.form.get('status','planned'), document_id, memory_id)
            )
            db.commit()
            flash('Activity added to the route.', 'success')
            return redirect(url_for('itinerary', trip_id=trip_id, day=selected['day_number']))
    return render_template('activity_form.html', trip=trip, days=days, activity=None, documents=documents, memories=memories)


@app.route('/trips/<int:trip_id>/activities/<int:activity_id>')
@login_required
def activity_detail(trip_id, activity_id):
    trip = get_trip_or_404(trip_id)
    activity = get_db().execute(
        '''SELECT a.*, d.day_number FROM activities a JOIN trip_days d ON d.id=a.day_id
           WHERE a.id=? AND a.trip_id=?''', (activity_id, trip_id)
    ).fetchone()
    if activity is None:
        abort(404)
    document = None
    memory = None
    if activity['document_id']:
        document = get_db().execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (activity['document_id'], trip_id)).fetchone()
    if activity['memory_id']:
        memory = get_db().execute('SELECT * FROM memories WHERE id=? AND trip_id=?', (activity['memory_id'], trip_id)).fetchone()
    return render_template('activity_detail.html', trip=trip, activity=activity, document=document, memory=memory)


@app.route('/trips/<int:trip_id>/activities/<int:activity_id>/edit', methods=('GET','POST'))
@login_required
def edit_activity(trip_id, activity_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    activity = db.execute('SELECT * FROM activities WHERE id=? AND trip_id=?', (activity_id, trip_id)).fetchone()
    if activity is None:
        abort(404)
    days = trip_days(trip_id)
    documents = db.execute('SELECT * FROM documents WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    if request.method == 'POST':
        day_id = request.form.get('day_id', type=int)
        day = db.execute('SELECT * FROM trip_days WHERE id=? AND trip_id=?', (day_id, trip_id)).fetchone()
        name = request.form.get('name','').strip()
        document_id = request.form.get('document_id', type=int)
        memory_id = request.form.get('memory_id', type=int)
        if document_id and db.execute('SELECT id FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone() is None:
            document_id = None
        if memory_id and db.execute('SELECT id FROM memories WHERE id=? AND trip_id=?', (memory_id, trip_id)).fetchone() is None:
            memory_id = None
        if not name or day is None:
            flash('Activity name and day are required.', 'error')
        else:
            try:
                estimated = max(0, float(request.form.get('estimated_cost','0') or 0))
                actual = max(0, float(request.form.get('actual_cost','0') or 0))
            except ValueError:
                flash('Costs must be valid numbers.', 'error')
                return render_template('activity_form.html', trip=trip, days=days, activity=activity, documents=documents, memories=memories)
            db.execute(
                '''UPDATE activities SET day_id=?, name=?, type=?, activity_date=?, start_time=?, end_time=?, location=?,
                   estimated_cost=?, actual_cost=?, notes=?, status=?, document_id=?, memory_id=? WHERE id=? AND trip_id=?''',
                (day_id, name, request.form.get('type','activity'), day['date'], request.form.get('start_time') or None,
                 request.form.get('end_time') or None, request.form.get('location','').strip(), estimated, actual,
                 request.form.get('notes','').strip(), request.form.get('status','planned'), document_id, memory_id,
                 activity_id, trip_id)
            )
            db.commit()
            flash('Activity updated.', 'success')
            return redirect(url_for('activity_detail', trip_id=trip_id, activity_id=activity_id))
    return render_template('activity_form.html', trip=trip, days=days, activity=activity, documents=documents, memories=memories)


@app.post('/trips/<int:trip_id>/activities/<int:activity_id>/status')
@login_required
def set_activity_status(trip_id, activity_id):
    get_trip_or_404(trip_id)
    status = request.form.get('status', 'planned')
    if status not in {'planned','completed','skipped','changed'}:
        abort(400)
    db = get_db()
    result = db.execute('UPDATE activities SET status=? WHERE id=? AND trip_id=?', (status, activity_id, trip_id))
    if result.rowcount == 0:
        abort(404)
    db.commit()
    if status == 'completed':
        flash('Stamped complete — the route moved forward.', 'stamp')
    else:
        flash(f'Activity marked {status}.', 'success')
    return redirect(request.referrer or url_for('itinerary', trip_id=trip_id))


@app.post('/trips/<int:trip_id>/activities/<int:activity_id>/delete')
@login_required
def delete_activity(trip_id, activity_id):
    get_trip_or_404(trip_id)
    db = get_db()
    db.execute('DELETE FROM activities WHERE id=? AND trip_id=?', (activity_id, trip_id))
    db.commit()
    flash('Activity removed from the itinerary.', 'info')
    return redirect(url_for('itinerary', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/today')
@login_required
def today(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    today_value = date.today().isoformat()
    day = db.execute('SELECT * FROM trip_days WHERE trip_id=? AND date=?', (trip_id, today_value)).fetchone()
    if day is None:
        days = trip_days(trip_id)
        day = days[0] if days else None
    activities = []
    if day:
        activities = db.execute(
            '''SELECT * FROM activities WHERE trip_id=? AND day_id=?
               ORDER BY COALESCE(start_time,'23:59'), id''', (trip_id, day['id'])
        ).fetchall()
    current = next((a for a in activities if a['status'] in ('planned','changed')), None)
    current_idx = activities.index(current) if current in activities else -1
    next_activity = activities[current_idx + 1] if current_idx >= 0 and current_idx + 1 < len(activities) else None
    current_document = None
    if current and current['document_id']:
        current_document = db.execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (current['document_id'], trip_id)).fetchone()
    return render_template(
        'today.html', trip=trip, day=day, activities=activities, current=current,
        next_activity=next_activity, current_document=current_document
    )


@app.route('/trips/<int:trip_id>/wallet', methods=('GET','POST'))
@login_required
def wallet(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    if request.method == 'POST':
        file = request.files.get('file')
        title = request.form.get('title','').strip()
        if not title or not file or not file.filename:
            flash('Document title and file are required.', 'error')
        else:
            try:
                filename = save_upload(file, ALLOWED_DOCUMENT_EXTENSIONS, 'doc')
            except ValueError as exc:
                flash(str(exc), 'error')
            else:
                db.execute(
                    '''INSERT INTO documents (trip_id,title,type,document_date,note,filename,original_filename)
                       VALUES (?,?,?,?,?,?,?)''',
                    (trip_id, title, request.form.get('type','other'), request.form.get('document_date') or None,
                     request.form.get('note','').strip(), filename, secure_filename(file.filename))
                )
                db.commit()
                flash('Document tucked into your travel wallet.', 'wallet')
                return redirect(url_for('wallet', trip_id=trip_id))
    documents = db.execute('SELECT * FROM documents WHERE trip_id=? ORDER BY created_at DESC', (trip_id,)).fetchall()
    return render_template('wallet.html', trip=trip, documents=documents)


@app.route('/trips/<int:trip_id>/wallet/<int:document_id>/download')
@login_required
def download_document(trip_id, document_id):
    get_trip_or_404(trip_id)
    document = get_db().execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone()
    if document is None:
        abort(404)
    return send_from_directory(UPLOAD_DIR, document['filename'], as_attachment=True, download_name=document['original_filename'])


@app.route('/trips/<int:trip_id>/wallet/<int:document_id>/open')
@login_required
def open_document(trip_id, document_id):
    get_trip_or_404(trip_id)
    document = get_db().execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone()
    if document is None:
        abort(404)
    return send_from_directory(UPLOAD_DIR, document['filename'])


@app.post('/trips/<int:trip_id>/wallet/<int:document_id>/delete')
@login_required
def delete_document(trip_id, document_id):
    get_trip_or_404(trip_id)
    db = get_db()
    document = db.execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone()
    if document is None:
        abort(404)
    db.execute('DELETE FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id))
    db.commit()
    safe_delete_upload(document['filename'])
    flash('Document removed.', 'info')
    return redirect(url_for('wallet', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/wallet/<int:document_id>/edit', methods=('GET','POST'))
@login_required
def edit_document(trip_id, document_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    document = db.execute('SELECT * FROM documents WHERE id=? AND trip_id=?', (document_id, trip_id)).fetchone()
    if document is None:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        if not title:
            flash('Document title is required.', 'error')
        else:
            replacement = None
            try:
                replacement = save_upload(request.files.get('file'), ALLOWED_DOCUMENT_EXTENSIONS, 'doc')
            except ValueError as exc:
                flash(str(exc), 'error')
                return render_template('document_form.html', trip=trip, document=document)
            new_original = secure_filename(request.files['file'].filename) if replacement else document['original_filename']
            db.execute(
                '''UPDATE documents SET title=?, type=?, document_date=?, note=?, filename=?, original_filename=?
                   WHERE id=? AND trip_id=?''',
                (title, request.form.get('type','other'), request.form.get('document_date') or None,
                 request.form.get('note','').strip(), replacement or document['filename'], new_original,
                 document_id, trip_id)
            )
            db.commit()
            if replacement:
                safe_delete_upload(document['filename'])
            flash('Document updated.', 'success')
            return redirect(url_for('wallet', trip_id=trip_id))
    return render_template('document_form.html', trip=trip, document=document)


@app.route('/trips/<int:trip_id>/packing')
@login_required
def packing(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    categories = db.execute('SELECT * FROM packing_categories WHERE trip_id=? ORDER BY sort_order,id', (trip_id,)).fetchall()
    items = db.execute('SELECT * FROM packing_items WHERE trip_id=? ORDER BY id', (trip_id,)).fetchall()
    total = len(items)
    packed = sum(row['packed'] for row in items)
    return render_template('packing.html', trip=trip, categories=categories, items=items, total=total, packed=packed)


@app.post('/trips/<int:trip_id>/packing/categories')
@login_required
def add_packing_category(trip_id):
    get_trip_or_404(trip_id)
    name = request.form.get('name','').strip()
    if name:
        db = get_db()
        max_order = db.execute('SELECT COALESCE(MAX(sort_order),0) m FROM packing_categories WHERE trip_id=?', (trip_id,)).fetchone()['m']
        db.execute('INSERT INTO packing_categories (trip_id,name,sort_order) VALUES (?,?,?)', (trip_id,name,max_order+1))
        db.commit()
    return redirect(url_for('packing', trip_id=trip_id))


@app.post('/trips/<int:trip_id>/packing/items')
@login_required
def add_packing_item(trip_id):
    get_trip_or_404(trip_id)
    db = get_db()
    name = request.form.get('name','').strip()
    category_id = request.form.get('category_id', type=int)
    category = db.execute('SELECT * FROM packing_categories WHERE id=? AND trip_id=?', (category_id, trip_id)).fetchone()
    try:
        quantity = max(1, int(request.form.get('quantity','1') or 1))
    except ValueError:
        quantity = 1
    if name and category:
        db.execute('INSERT INTO packing_items (trip_id,category_id,name,quantity) VALUES (?,?,?,?)', (trip_id,category_id,name,quantity))
        db.commit()
    else:
        flash('Choose a category and enter an item.', 'error')
    return redirect(url_for('packing', trip_id=trip_id))


@app.post('/trips/<int:trip_id>/packing/items/<int:item_id>/toggle')
@login_required
def toggle_packing_item(trip_id, item_id):
    get_trip_or_404(trip_id)
    db = get_db()
    item = db.execute('SELECT * FROM packing_items WHERE id=? AND trip_id=?', (item_id,trip_id)).fetchone()
    if item is None:
        abort(404)
    db.execute('UPDATE packing_items SET packed=? WHERE id=?', (0 if item['packed'] else 1, item_id))
    db.commit()
    flash('Suitcase updated.', 'pack')
    return redirect(url_for('packing', trip_id=trip_id))


@app.post('/trips/<int:trip_id>/packing/items/<int:item_id>/delete')
@login_required
def delete_packing_item(trip_id, item_id):
    get_trip_or_404(trip_id)
    db = get_db()
    db.execute('DELETE FROM packing_items WHERE id=? AND trip_id=?', (item_id,trip_id))
    db.commit()
    return redirect(url_for('packing', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/packing/items/<int:item_id>/edit', methods=('GET','POST'))
@login_required
def edit_packing_item(trip_id, item_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    item = db.execute('SELECT * FROM packing_items WHERE id=? AND trip_id=?', (item_id,trip_id)).fetchone()
    if item is None:
        abort(404)
    categories = db.execute('SELECT * FROM packing_categories WHERE trip_id=? ORDER BY sort_order,id', (trip_id,)).fetchall()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        category_id = request.form.get('category_id', type=int)
        category = db.execute('SELECT * FROM packing_categories WHERE id=? AND trip_id=?', (category_id,trip_id)).fetchone()
        try:
            quantity = max(1, int(request.form.get('quantity','1') or 1))
        except ValueError:
            quantity = 1
        if not name or category is None:
            flash('Packing item and category are required.', 'error')
        else:
            db.execute('UPDATE packing_items SET name=?, category_id=?, quantity=? WHERE id=? AND trip_id=?',
                       (name,category_id,quantity,item_id,trip_id))
            db.commit()
            flash('Packing item updated.', 'success')
            return redirect(url_for('packing', trip_id=trip_id))
    return render_template('packing_item_form.html', trip=trip, item=item, categories=categories)


@app.route('/trips/<int:trip_id>/budget')
@login_required
def budget(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    expenses = db.execute('SELECT * FROM expenses WHERE trip_id=? ORDER BY expense_date DESC,id DESC', (trip_id,)).fetchall()
    spent = sum(row['amount'] for row in expenses)
    category_totals = db.execute('SELECT category, SUM(amount) total FROM expenses WHERE trip_id=? GROUP BY category ORDER BY total DESC', (trip_id,)).fetchall()
    return render_template('budget.html', trip=trip, expenses=expenses, spent=spent, category_totals=category_totals)


@app.post('/trips/<int:trip_id>/budget/expenses')
@login_required
def add_expense(trip_id):
    get_trip_or_404(trip_id)
    name = request.form.get('name','').strip()
    try:
        amount = float(request.form.get('amount',''))
        if amount < 0:
            raise ValueError
    except ValueError:
        flash('Enter a valid non-negative amount.', 'error')
        return redirect(url_for('budget', trip_id=trip_id))
    if not name or not request.form.get('expense_date'):
        flash('Expense name and date are required.', 'error')
        return redirect(url_for('budget', trip_id=trip_id))
    db = get_db()
    db.execute(
        'INSERT INTO expenses (trip_id,name,category,expense_date,amount,note) VALUES (?,?,?,?,?,?)',
        (trip_id,name,request.form.get('category','Other'),request.form.get('expense_date'),amount,request.form.get('note','').strip())
    )
    db.commit()
    flash('Expense added — your travel spend has been recalculated.', 'budget')
    return redirect(url_for('budget', trip_id=trip_id))


@app.post('/trips/<int:trip_id>/budget/expenses/<int:expense_id>/delete')
@login_required
def delete_expense(trip_id, expense_id):
    get_trip_or_404(trip_id)
    db = get_db()
    db.execute('DELETE FROM expenses WHERE id=? AND trip_id=?', (expense_id,trip_id))
    db.commit()
    flash('Expense deleted.', 'info')
    return redirect(url_for('budget', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/budget/expenses/<int:expense_id>/edit', methods=('GET','POST'))
@login_required
def edit_expense(trip_id, expense_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    expense = db.execute('SELECT * FROM expenses WHERE id=? AND trip_id=?', (expense_id,trip_id)).fetchone()
    if expense is None:
        abort(404)
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        try:
            amount = float(request.form.get('amount',''))
            if amount < 0:
                raise ValueError
        except ValueError:
            flash('Enter a valid non-negative amount.', 'error')
        else:
            if not name or not request.form.get('expense_date'):
                flash('Expense name and date are required.', 'error')
            else:
                db.execute(
                    '''UPDATE expenses SET name=?, category=?, expense_date=?, amount=?, note=?
                       WHERE id=? AND trip_id=?''',
                    (name, request.form.get('category','Other'), request.form.get('expense_date'), amount,
                     request.form.get('note','').strip(), expense_id, trip_id)
                )
                db.commit()
                flash('Expense updated.', 'success')
                return redirect(url_for('budget', trip_id=trip_id))
    return render_template('expense_form.html', trip=trip, expense=expense)


@app.route('/trips/<int:trip_id>/journal', methods=('GET','POST'))
@login_required
def journal(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        if not title:
            flash('Memory title is required.', 'error')
        else:
            try:
                image_filename = save_upload(request.files.get('image'), ALLOWED_IMAGE_EXTENSIONS, 'memory')
            except ValueError as exc:
                flash(str(exc), 'error')
            else:
                db.execute(
                    '''INSERT INTO memories (trip_id,title,memory_date,location,note,image_filename,mood)
                       VALUES (?,?,?,?,?,?,?)''',
                    (trip_id,title,request.form.get('memory_date') or None,request.form.get('location','').strip(),
                     request.form.get('note','').strip(),image_filename,request.form.get('mood','postcard'))
                )
                db.commit()
                flash('Memory developed into the journal.', 'develop')
                return redirect(url_for('journal', trip_id=trip_id))
    memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY created_at DESC,id DESC', (trip_id,)).fetchall()
    return render_template('journal.html', trip=trip, memories=memories)


@app.post('/trips/<int:trip_id>/journal/<int:memory_id>/delete')
@login_required
def delete_memory(trip_id, memory_id):
    get_trip_or_404(trip_id)
    db = get_db()
    memory = db.execute('SELECT * FROM memories WHERE id=? AND trip_id=?', (memory_id,trip_id)).fetchone()
    if memory is None:
        abort(404)
    db.execute('DELETE FROM memories WHERE id=? AND trip_id=?', (memory_id,trip_id))
    db.commit()
    safe_delete_upload(memory['image_filename'])
    flash('Memory removed.', 'info')
    return redirect(url_for('journal', trip_id=trip_id))


@app.route('/trips/<int:trip_id>/journal/<int:memory_id>/edit', methods=('GET','POST'))
@login_required
def edit_memory(trip_id, memory_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    memory = db.execute('SELECT * FROM memories WHERE id=? AND trip_id=?', (memory_id,trip_id)).fetchone()
    if memory is None:
        abort(404)
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        if not title:
            flash('Memory title is required.', 'error')
        else:
            replacement = None
            try:
                replacement = save_upload(request.files.get('image'), ALLOWED_IMAGE_EXTENSIONS, 'memory')
            except ValueError as exc:
                flash(str(exc), 'error')
                return render_template('memory_form.html', trip=trip, memory=memory)
            db.execute(
                '''UPDATE memories SET title=?, memory_date=?, location=?, note=?, image_filename=?, mood=?
                   WHERE id=? AND trip_id=?''',
                (title, request.form.get('memory_date') or None, request.form.get('location','').strip(),
                 request.form.get('note','').strip(), replacement or memory['image_filename'], request.form.get('mood','postcard'),
                 memory_id, trip_id)
            )
            db.commit()
            if replacement:
                safe_delete_upload(memory['image_filename'])
            flash('Journal page updated.', 'success')
            return redirect(url_for('journal', trip_id=trip_id))
    return render_template('memory_form.html', trip=trip, memory=memory)


@app.route('/trips/<int:trip_id>/summary')
@login_required
def summary(trip_id):
    trip = get_trip_or_404(trip_id)
    db = get_db()
    days = trip_days(trip_id)
    activities = db.execute('SELECT * FROM activities WHERE trip_id=? ORDER BY activity_date,start_time', (trip_id,)).fetchall()
    memories = db.execute('SELECT * FROM memories WHERE trip_id=? ORDER BY memory_date,id', (trip_id,)).fetchall()
    spent = db.execute('SELECT COALESCE(SUM(amount),0) s FROM expenses WHERE trip_id=?', (trip_id,)).fetchone()['s']
    photo_count = sum(1 for m in memories if m['image_filename'] or m['image_url'])
    return render_template('summary.html', trip=trip, days=days, activities=activities, memories=memories, spent=spent, photo_count=photo_count)


@app.route('/profile', methods=('GET','POST'))
@login_required
def profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name','').strip()
        if not full_name:
            flash('Name cannot be empty.', 'error')
        else:
            new_avatar = None
            try:
                new_avatar = save_upload(request.files.get('avatar'), ALLOWED_IMAGE_EXTENSIONS, 'avatar')
            except ValueError as exc:
                flash(str(exc), 'error')
                return render_template('profile.html')
            db = get_db()
            old_avatar = g.user['avatar_filename']
            db.execute('UPDATE users SET full_name=?, avatar_filename=? WHERE id=?', (full_name,new_avatar or old_avatar,g.user['id']))
            db.commit()
            if new_avatar:
                safe_delete_upload(old_avatar)
            flash('Profile updated.', 'success')
            return redirect(url_for('profile'))
    return render_template('profile.html')


@app.route('/settings', methods=('GET','POST'))
@login_required
def settings():
    if request.method == 'POST':
        currency = request.form.get('currency','INR')
        date_format = request.form.get('date_format','DD MMM YYYY')
        appearance = request.form.get('appearance','sunlit')
        if currency not in {'INR','USD','EUR','GBP','JPY'}:
            currency = 'INR'
        if appearance not in {'sunlit','paper','high-contrast'}:
            appearance = 'sunlit'
        db = get_db()
        db.execute('UPDATE settings SET currency=?, date_format=?, appearance=? WHERE user_id=?', (currency,date_format,appearance,g.user['id']))
        db.commit()
        flash('Preferences saved.', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')


@app.errorhandler(404)
def not_found(_error):
    return render_template('404.html'), 404


@app.errorhandler(400)
def bad_request(error):
    return render_template('error.html', code=400, title='That request could not be accepted.', message=getattr(error, 'description', 'Check the form and try again.')), 400


@app.errorhandler(500)
def server_error(_error):
    return render_template('error.html', code=500, title='Roamory hit a wrong turn.', message='The server could not finish that request. Your saved travel data has not been intentionally changed.'), 500


@app.errorhandler(413)
def too_large(_error):
    flash('That file is too large. The local upload limit is 8 MB.', 'error')
    return redirect(request.referrer or url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
