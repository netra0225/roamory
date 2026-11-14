"""End-to-end smoke test for Roamory's submission-critical flows."""
import os
import re
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from app import app
from db import init_db


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token missing from form"
    return match.group(1)


def fake_trip_plan(start_date: str, day_count: int = 3):
    start = date.fromisoformat(start_date)
    days = []
    for index in range(day_count):
        number = index + 1
        days.append(
            {
                "day_number": number,
                "date": (start + timedelta(days=index)).isoformat(),
                "items": [
                    {
                        "name": f"Day {number} Sightseeing A",
                        "type": "activity",
                        "start_time": "10:00",
                        "location": f"Day {number} Area A",
                        "latitude": 24.58 + index * 0.01,
                        "longitude": 73.68 + index * 0.01,
                        "estimated_cost": 0,
                        "notes": "Suggested by Roamory",
                    },
                    {
                        "name": f"Day {number} Lunch",
                        "type": "restaurant",
                        "start_time": "13:00",
                        "location": f"Day {number} Food Area A",
                        "latitude": 24.581 + index * 0.01,
                        "longitude": 73.681 + index * 0.01,
                        "estimated_cost": 0,
                        "notes": "Suggested by Roamory",
                    },
                    {
                        "name": f"Day {number} Sightseeing B",
                        "type": "activity",
                        "start_time": "15:00",
                        "location": f"Day {number} Area B",
                        "latitude": 24.582 + index * 0.01,
                        "longitude": 73.682 + index * 0.01,
                        "estimated_cost": 0,
                        "notes": "Suggested by Roamory",
                    },
                    {
                        "name": f"Day {number} Dinner",
                        "type": "restaurant",
                        "start_time": "19:30",
                        "location": f"Day {number} Food Area B",
                        "latitude": 24.583 + index * 0.01,
                        "longitude": 73.683 + index * 0.01,
                        "estimated_cost": 0,
                        "notes": "Suggested by Roamory",
                    },
                ],
            }
        )
    return {"days": days}


fd, db_path = tempfile.mkstemp(prefix="roamory-smoke-", suffix=".sqlite3")
os.close(fd)
app.config.update(TESTING=True, DATABASE=db_path, SECRET_KEY="smoke-test-secret")

try:
    with app.app_context():
        init_db()

    with app.test_client() as client:
        # Registration + seeded dashboard.
        register_page = client.get("/register")
        assert register_page.status_code == 200
        token = csrf_from(register_page.get_data(as_text=True))
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "Roamory Tester",
                "email": "tester@example.com",
                "password": "testing123",
                "confirm_password": "testing123",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Trip at a glance." in response.data
        assert b"Travel Journal" in response.data

        # Core account pages render.
        assert client.get("/profile").status_code == 200
        assert client.get("/settings").status_code == 200
        assert client.get("/trips").status_code == 200

        # New trips auto-build a complete route with two restaurants on every day.
        start = date.today() + timedelta(days=30)
        end = start + timedelta(days=2)
        create_page = client.get("/trips/new")
        assert create_page.status_code == 200
        create_html = create_page.get_data(as_text=True)
        assert create_html.count('data-wizard-indicator=') == 3
        token = csrf_from(create_html)

        plan = fake_trip_plan(start.isoformat(), 3)
        with patch("app.build_trip_plan", return_value=plan), patch(
            "app._trip_forecast", return_value={"available": False, "days": []}
        ):
            response = client.post(
                "/trips/new",
                data={
                    "csrf_token": token,
                    "title": "Smoke Test Trip",
                    "destination": "Udaipur",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "description": "Automated smoke test",
                    "accent": "sunflower",
                    "planned_budget": "25000",
                },
                follow_redirects=True,
            )

        assert response.status_code == 200
        assert b"Smoke Test Trip" in response.data
        assert b"Udaipur" in response.data

        with app.app_context():
            db = __import__("db").get_db()
            trip = db.execute(
                "SELECT * FROM trips WHERE title=? ORDER BY id DESC LIMIT 1",
                ("Smoke Test Trip",),
            ).fetchone()
            assert trip is not None
            trip_id = trip["id"]

            restaurant_counts = db.execute(
                """SELECT d.day_number, COUNT(a.id) AS c
                   FROM trip_days d
                   LEFT JOIN activities a
                     ON a.day_id=d.id AND a.type='restaurant'
                   WHERE d.trip_id=?
                   GROUP BY d.day_number
                   ORDER BY d.day_number""",
                (trip_id,),
            ).fetchall()
            assert len(restaurant_counts) == 3
            assert all(row["c"] >= 2 for row in restaurant_counts)

        # Submission-critical trip pages all render.
        for route in (
            f"/trips/{trip_id}",
            f"/trips/{trip_id}/itinerary",
            f"/trips/{trip_id}/today",
            f"/trips/{trip_id}/wallet",
            f"/trips/{trip_id}/packing",
            f"/trips/{trip_id}/budget",
            f"/trips/{trip_id}/journal",
            f"/trips/{trip_id}/summary",
            f"/trips/{trip_id}/edit",
        ):
            with patch("app._trip_forecast", return_value={"available": False, "days": []}):
                page = client.get(route)
            assert page.status_code == 200, f"{route} returned {page.status_code}"

        itinerary_page = client.get(f"/trips/{trip_id}/itinerary")
        itinerary_html = itinerary_page.get_data(as_text=True)
        assert b"Build my trip" not in itinerary_page.data
        assert b"Day 1 Lunch" in itinerary_page.data
        assert b"Day 1 Dinner" in itinerary_page.data
        assert b"Add a location to a stop." not in itinerary_page.data

        # Budget write flow.
        budget_page = client.get(f"/trips/{trip_id}/budget")
        token = csrf_from(budget_page.get_data(as_text=True))
        response = client.post(
            f"/trips/{trip_id}/budget/expenses",
            data={
                "csrf_token": token,
                "amount": "450",
                "category": "Food",
                "name": "Smoke Test Lunch",
                "expense_date": start.isoformat(),
                "note": "Test expense",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Smoke Test Lunch" in response.data

        # Journal write flow.
        journal_page = client.get(f"/trips/{trip_id}/journal")
        token = csrf_from(journal_page.get_data(as_text=True))
        response = client.post(
            f"/trips/{trip_id}/journal",
            data={
                "csrf_token": token,
                "title": "Smoke Test Memory",
                "memory_date": start.isoformat(),
                "location": "Udaipur",
                "note": "A test memory",
                "mood": "postcard",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Smoke Test Memory" in response.data

        # The trip remains visible in the library after writes.
        trips_page = client.get("/trips")
        assert trips_page.status_code == 200
        assert b"Smoke Test Trip" in trips_page.data

    print("Roamory smoke test passed.")
finally:
    try:
        os.remove(db_path)
    except FileNotFoundError:
        pass
