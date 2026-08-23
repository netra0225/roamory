"""Small end-to-end smoke test for local use after `pip install -r requirements.txt`."""
import os
import re
import tempfile

from app import app
from db import init_db


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, 'CSRF token missing from form'
    return match.group(1)


fd, db_path = tempfile.mkstemp(prefix='roamory-smoke-', suffix='.sqlite3')
os.close(fd)
app.config.update(TESTING=True, DATABASE=db_path, SECRET_KEY='smoke-test-secret')

try:
    with app.app_context():
        init_db()

    with app.test_client() as client:
        register_page = client.get('/register')
        assert register_page.status_code == 200
        token = csrf_from(register_page.get_data(as_text=True))
        response = client.post('/register', data={
            'csrf_token': token,
            'full_name': 'Roamory Tester',
            'email': 'tester@example.com',
            'password': 'testing123',
            'confirm_password': 'testing123',
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Everything that matters' in response.data
        assert b'Itinerary' in response.data
        assert b'Journal' in response.data

        create_page = client.get('/trips/new')
        token = csrf_from(create_page.get_data(as_text=True))
        response = client.post('/trips/new', data={
            'csrf_token': token,
            'title': 'Smoke Test Trip',
            'destination': 'Udaipur',
            'start_date': '2026-08-20',
            'end_date': '2026-08-22',
            'description': 'Automated smoke test',
            'accent': 'sunflower',
            'planned_budget': '25000',
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'Smoke Test Trip' in response.data
        assert b'Udaipur' in response.data

        trips_page = client.get('/trips')
        assert trips_page.status_code == 200
        assert b'Smoke Test Trip' in trips_page.data

    print('Roamory smoke test passed.')
finally:
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass
