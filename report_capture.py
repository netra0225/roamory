from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "report_screenshots"
OUT.mkdir(exist_ok=True)
DB = ROOT / "roamory.sqlite3"

if DB.exists():
    DB.unlink()

env = os.environ.copy()
env.update({
    "ROAMORY_SECRET_KEY": "report-screenshot-secret",
    "ROAMORY_SECURE_COOKIE": "0",
})

server = subprocess.Popen(
    [sys.executable, "-m", "flask", "--app", "app", "run", "--host", "127.0.0.1", "--port", "5000"],
    cwd=ROOT,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)

try:
    import urllib.request
    for _ in range(90):
        try:
            urllib.request.urlopen("http://127.0.0.1:5000/register", timeout=1)
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Roamory server did not start")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
        page.goto("http://127.0.0.1:5000/register", wait_until="networkidle")
        page.fill('input[name="full_name"]', "Netra Chauhan")
        page.fill('input[name="email"]', "report@example.com")
        page.fill('input[name="password"]', "reportpass123")
        page.fill('input[name="confirm_password"]', "reportpass123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Resolve seeded trip IDs directly from the local report database.
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        user = con.execute("SELECT id FROM users WHERE email=?", ("report@example.com",)).fetchone()
        user_id = user["id"]
        ongoing = con.execute(
            "SELECT id FROM trips WHERE user_id=? AND destination='Udaipur' ORDER BY id LIMIT 1",
            (user_id,),
        ).fetchone()["id"]
        completed = con.execute(
            "SELECT id FROM trips WHERE user_id=? AND end_date < date('now') ORDER BY end_date DESC LIMIT 1",
            (user_id,),
        ).fetchone()["id"]
        con.close()

        shots = [
            ("dashboard", "/dashboard"),
            ("my_trips", "/trips"),
            ("create_trip", "/trips/new"),
            ("overview", f"/trips/{ongoing}"),
            ("itinerary", f"/trips/{ongoing}/itinerary"),
            ("today", f"/trips/{ongoing}/today"),
            ("wallet", f"/trips/{ongoing}/wallet"),
            ("packing", f"/trips/{ongoing}/packing"),
            ("budget", f"/trips/{ongoing}/budget"),
            ("journal", f"/trips/{ongoing}/journal"),
            ("summary", f"/trips/{completed}/summary"),
            ("profile", "/profile"),
            ("settings", "/settings"),
        ]

        for name, route in shots:
            page.goto("http://127.0.0.1:5000" + route, wait_until="networkidle")
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)

        # A mobile evidence capture from the most travel-specific screen.
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        # Reuse authenticated storage state from the desktop context.
        storage = page.context.storage_state()
        mobile.close()
        context = browser.new_context(viewport={"width":390,"height":844}, storage_state=storage)
        mobile = context.new_page()
        mobile.goto(f"http://127.0.0.1:5000/trips/{ongoing}/today", wait_until="networkidle")
        mobile.screenshot(path=str(OUT / "mobile_today.png"), full_page=False)
        context.close()
        browser.close()

    # Build report-friendly paired evidence sheets. Screens stay untouched, only placed together.
    groups = [
        ("01_dashboard_trips", "dashboard.png", "my_trips.png", "Dashboard", "My Trips"),
        ("02_create_overview", "create_trip.png", "overview.png", "Create Trip", "Trip Overview"),
        ("03_itinerary_map", "itinerary.png", "today.png", "Itinerary", "Today"),
        ("04_wallet_packing", "wallet.png", "packing.png", "Travel Wallet", "Packing"),
        ("05_budget_journal", "budget.png", "journal.png", "Budget", "Journal"),
        ("06_summary_profile", "summary.png", "profile.png", "Trip Summary", "Profile"),
        ("07_settings_mobile", "settings.png", "mobile_today.png", "Settings", "Responsive Today"),
    ]

    font_height = 42
    gap = 24
    pad = 24
    for out_name, left_name, right_name, left_label, right_label in groups:
        left = Image.open(OUT / left_name).convert("RGB")
        right = Image.open(OUT / right_name).convert("RGB")
        target_h = 540
        left.thumbnail((820, target_h))
        right.thumbnail((820, target_h))
        canvas_h = max(left.height, right.height) + font_height + pad * 2
        canvas_w = left.width + right.width + gap + pad * 2
        canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((pad, 12), left_label, fill="black")
        draw.text((pad + left.width + gap, 12), right_label, fill="black")
        canvas.paste(left, (pad, font_height))
        canvas.paste(right, (pad + left.width + gap, font_height))
        canvas.save(OUT / f"{out_name}.png", quality=95)

    print("Captured report screenshots:", sorted(p.name for p in OUT.glob("*.png")))

finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

# trigger screenshot workflow
