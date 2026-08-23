from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

IMAGE_MAP = {
    'udaipur': 'https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=1600&q=86',
    'amalfi': 'https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=1600&q=86',
    'banff': 'https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1600&q=86',
    'coast': 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1600&q=86',
    'kyoto': 'https://images.unsplash.com/photo-1528127269322-539801943592?auto=format&fit=crop&w=1600&q=86',
    'city': 'https://images.unsplash.com/photo-1499856871958-5b9627545d1a?auto=format&fit=crop&w=1600&q=86',
    'forest': 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=86',
}

PACKING_CATEGORIES = ['Essentials', 'Clothing', 'Toiletries', 'Electronics', 'Documents']


def _create_trip(db, user_id, title, destination, start, end, description, image, accent, budget):
    cur = db.execute(
        '''INSERT INTO trips
           (user_id,title,destination,start_date,end_date,description,cover_url,accent,planned_budget)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (user_id, title, destination, start.isoformat(), end.isoformat(), description, image, accent, budget),
    )
    trip_id = cur.lastrowid
    current = start
    day_no = 1
    while current <= end:
        db.execute(
            'INSERT INTO trip_days (trip_id,day_number,date,title) VALUES (?,?,?,?)',
            (trip_id, day_no, current.isoformat(), f'Day {day_no}'),
        )
        day_no += 1
        current += timedelta(days=1)
    for index, name in enumerate(PACKING_CATEGORIES):
        db.execute(
            'INSERT INTO packing_categories (trip_id,name,sort_order) VALUES (?,?,?)',
            (trip_id, name, index),
        )
    return trip_id


def _write_demo_document(filename: str, content: str) -> None:
    upload_dir = Path(__file__).resolve().parent / 'static' / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    if not path.exists():
        path.write_text(content, encoding='utf-8')


def seed_starter_content(db, user_id: int) -> dict[str, int]:
    """Give a new account a fully populated editable showcase.

    The product still supports true empty states after users delete the sample trips,
    but first launch immediately demonstrates every core Roamory section.
    """
    existing = db.execute('SELECT id FROM trips WHERE user_id=? LIMIT 1', (user_id,)).fetchone()
    if existing:
        return {'existing': existing['id']}

    today = date.today()
    ongoing_id = _create_trip(
        db,
        user_id,
        'Palaces, Lakes & Late Sunsets',
        'Udaipur',
        today - timedelta(days=2),
        today + timedelta(days=3),
        'A sunlit five-day city break with lake mornings, old architecture, local food and evenings left intentionally unhurried.',
        IMAGE_MAP['udaipur'],
        'sunflower',
        65000,
    )
    upcoming_id = _create_trip(
        db,
        user_id,
        'Blue Water, Lemon Evenings',
        'Amalfi Coast',
        today + timedelta(days=21),
        today + timedelta(days=27),
        'Ferries, cliffside towns, sea swims and a notebook full of places worth stopping for.',
        IMAGE_MAP['amalfi'],
        'mediterranean',
        125000,
    )
    completed_id = _create_trip(
        db,
        user_id,
        'Five Places I Keep Thinking About',
        'Summer Atlas',
        today - timedelta(days=90),
        today - timedelta(days=84),
        'A finished journey gathered as five distinct journal pages: coast, lake, spring streets, mountains and palace light.',
        IMAGE_MAP['coast'],
        'coral',
        98000,
    )

    # ---------- Ongoing Udaipur trip ----------
    days = db.execute('SELECT * FROM trip_days WHERE trip_id=? ORDER BY day_number', (ongoing_id,)).fetchall()
    ongoing_activities = [
        (0, 'Breakfast by Lake Pichola', 'restaurant', '08:30', '09:45', 'Ambrai Road', 1200, 1100, 'Ask for the outdoor table. Keep the camera nearby.', 'completed'),
        (0, 'City Palace morning walk', 'activity', '10:30', '13:00', 'City Palace', 900, 900, 'Audio guide first, then wander the courtyards.', 'completed'),
        (1, 'Saheliyon-ki-Bari gardens', 'destination', '09:30', '11:00', 'Saheliyon-ki-Bari', 300, 300, 'A quieter morning stop before the lake.', 'completed'),
        (1, 'Boat ride to Jag Mandir', 'activity', '11:30', '13:00', 'Lake Pichola', 1800, 0, 'Ticket counter near the main jetty.', 'planned'),
        (1, 'Old city blue-hour walk', 'destination', '17:40', '19:00', 'Gangaur Ghat', 0, 0, 'Carry the small camera, not the whole backpack.', 'changed'),
        (2, 'Coffee and sketchbook hour', 'restaurant', '10:00', '11:15', 'Hanuman Ghat', 850, 850, 'Window seat if possible.', 'completed'),
        (2, 'Sunset at Sajjangarh', 'activity', '16:30', '19:00', 'Monsoon Palace', 1600, 0, 'Leave before traffic builds near the hill road.', 'planned'),
        (2, 'Dinner overlooking the lake', 'restaurant', '20:15', '21:45', 'Hanuman Ghat', 2600, 0, 'Reservation under the trip name.', 'planned'),
    ]
    activity_ids = []
    for day_index, name, kind, start, end, location, estimated, actual, note, status in ongoing_activities:
        day = days[min(day_index, len(days) - 1)]
        cur = db.execute(
            '''INSERT INTO activities
               (trip_id,day_id,name,type,activity_date,start_time,end_time,location,estimated_cost,actual_cost,notes,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (ongoing_id, day['id'], name, kind, day['date'], start, end, location, estimated, actual, note, status),
        )
        activity_ids.append(cur.lastrowid)

    cats = db.execute('SELECT * FROM packing_categories WHERE trip_id=? ORDER BY sort_order', (ongoing_id,)).fetchall()
    cat = {row['name']: row['id'] for row in cats}
    packing = [
        ('Essentials', 'Passport copy', 1, 1), ('Essentials', 'Sunglasses', 1, 1), ('Essentials', 'Water bottle', 1, 1),
        ('Clothing', 'Linen shirts', 3, 1), ('Clothing', 'Evening outfit', 1, 0), ('Clothing', 'Comfortable sandals', 1, 1),
        ('Toiletries', 'Sunscreen', 1, 1), ('Toiletries', 'Mini first-aid pouch', 1, 0),
        ('Electronics', 'Camera battery', 2, 0), ('Electronics', 'Power bank', 1, 1), ('Electronics', 'Charging cable', 2, 1),
        ('Documents', 'Hotel confirmation', 1, 1), ('Documents', 'Boat ticket screenshot', 1, 0),
    ]
    for category, name, qty, packed in packing:
        db.execute(
            'INSERT INTO packing_items (trip_id,category_id,name,quantity,packed) VALUES (?,?,?,?,?)',
            (ongoing_id, cat[category], name, qty, packed),
        )

    for name, category, offset, amount, note in [
        ('Boutique stay', 'Stay', -2, 18500, 'Two nights posted'),
        ('Airport transfer', 'Transport', -2, 1400, 'Prepaid cab'),
        ('Lake breakfast', 'Food', -1, 1100, 'Breakfast + coffee'),
        ('City Palace entry', 'Activities', -1, 900, 'Entry + audio guide'),
        ('Local crafts', 'Shopping', -1, 2350, 'Small blue pottery pieces'),
    ]:
        db.execute(
            'INSERT INTO expenses (trip_id,name,category,expense_date,amount,note) VALUES (?,?,?,?,?,?)',
            (ongoing_id, name, category, (today + timedelta(days=offset)).isoformat(), amount, note),
        )

    stay_file = f'demo-{user_id}-udaipur-stay.txt'
    boat_file = f'demo-{user_id}-lake-boat.txt'
    palace_file = f'demo-{user_id}-monsoon-palace.txt'
    _write_demo_document(
        stay_file,
        'ROAMORY DEMO DOCUMENT\n\nLake Stay Confirmation\nUdaipur\nCheck-in: current trip\nReference: RMY-UDR-204\nThis is sample content and can be deleted from Travel Wallet.\n',
    )
    _write_demo_document(
        boat_file,
        'ROAMORY DEMO TICKET\n\nLake Pichola Boat Ride\nBoarding: Main Jetty\nReference: RMY-BOAT-118\nThis is sample content and can be deleted from Travel Wallet.\n',
    )
    doc1 = db.execute(
        '''INSERT INTO documents (trip_id,title,type,document_date,note,filename,original_filename)
           VALUES (?,?,?,?,?,?,?)''',
        (ongoing_id, 'Lake stay confirmation', 'hotel', today.isoformat(), 'Check-in details and reference number.', stay_file, 'Lake-Stay-Confirmation.txt'),
    ).lastrowid
    doc2 = db.execute(
        '''INSERT INTO documents (trip_id,title,type,document_date,note,filename,original_filename)
           VALUES (?,?,?,?,?,?,?)''',
        (ongoing_id, 'Lake Pichola boat ticket', 'activity', today.isoformat(), 'Main jetty · arrive 20 minutes early.', boat_file, 'Boat-Ticket.txt'),
    ).lastrowid
    _write_demo_document(
        palace_file,
        'ROAMORY DEMO TICKET\n\nMonsoon Palace Sunset Entry\nEntry window: 16:00–18:30\nReference: RMY-SAJ-527\nThis is sample content and can be deleted from Travel Wallet.\n',
    )
    doc3 = db.execute(
        '''INSERT INTO documents (trip_id,title,type,document_date,note,filename,original_filename)
           VALUES (?,?,?,?,?,?,?)''',
        (ongoing_id, 'Monsoon Palace sunset entry', 'activity', today.isoformat(), 'Entry window 16:00–18:30.', palace_file, 'Monsoon-Palace-Entry.txt'),
    ).lastrowid
    # Link itinerary stops to wallet documents so Today and Activity Details demonstrate the relationship.
    if len(activity_ids) > 3:
        db.execute('UPDATE activities SET document_id=? WHERE id=?', (doc2, activity_ids[3]))
    if len(activity_ids) > 6:
        db.execute('UPDATE activities SET document_id=? WHERE id=?', (doc3, activity_ids[6]))

    ongoing_memories = [
        ('Blue hour from the ghat', today.isoformat(), 'Gangaur Ghat', 'The lake turned silver just before the palace lights appeared.', IMAGE_MAP['udaipur'], 'lake'),
        ('A courtyard worth lingering in', (today - timedelta(days=1)).isoformat(), 'City Palace', 'Painted doors, cool stone and a very good excuse to stop checking the time.', IMAGE_MAP['city'], 'postcard'),
    ]
    ongoing_memory_ids = []
    for title, memory_date, location, note, image, mood in ongoing_memories:
        cur = db.execute(
            '''INSERT INTO memories (trip_id,title,memory_date,location,note,image_url,mood)
               VALUES (?,?,?,?,?,?,?)''',
            (ongoing_id, title, memory_date, location, note, image, mood),
        )
        ongoing_memory_ids.append(cur.lastrowid)
    if ongoing_memory_ids and len(activity_ids) > 1:
        db.execute('UPDATE activities SET memory_id=? WHERE id=?', (ongoing_memory_ids[1], activity_ids[1]))

    # ---------- Upcoming Amalfi trip ----------
    upcoming_days = db.execute('SELECT * FROM trip_days WHERE trip_id=? ORDER BY day_number', (upcoming_id,)).fetchall()
    for day_index, name, kind, time_, location, note in [
        (0, 'Naples to Positano transfer', 'transport', '10:30', 'Naples Centrale', 'Train + driver transfer.'),
        (0, 'Check in above the water', 'stay', '15:00', 'Positano', 'Ask for the terrace key.'),
        (1, 'Ferry to Capri', 'transport', '09:15', 'Positano Ferry Pier', 'Keep the ticket in Wallet.'),
        (2, 'Path of the Gods walk', 'activity', '08:00', 'Bomerano', 'Start before the heat.'),
    ]:
        day = upcoming_days[day_index]
        db.execute(
            '''INSERT INTO activities
               (trip_id,day_id,name,type,activity_date,start_time,location,notes,status)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (upcoming_id, day['id'], name, kind, day['date'], time_, location, note, 'planned'),
        )

    # ---------- Completed Summer Atlas trip ----------
    completed_days = db.execute('SELECT * FROM trip_days WHERE trip_id=? ORDER BY day_number', (completed_id,)).fetchall()
    completed_stops = [
        (0, 'Cliffside lunch in Positano', 'restaurant', '12:30', 'Positano'),
        (0, 'Swim below the town', 'activity', '16:00', 'Spiaggia Grande'),
        (1, 'Lake ferry morning', 'transport', '09:20', 'Lake Como'),
        (2, 'Spring side-street walk', 'destination', '08:10', 'Kyoto'),
        (3, 'First light at the lake', 'activity', '06:00', 'Banff National Park'),
        (4, 'Palace windows at blue hour', 'destination', '18:20', 'Udaipur'),
        (5, 'Long lunch without a plan', 'restaurant', '13:00', 'Old Town'),
        (6, 'Last postcard before home', 'general', '17:30', 'Station café'),
    ]
    for day_index, name, kind, time_, location in completed_stops:
        day = completed_days[day_index]
        db.execute(
            '''INSERT INTO activities
               (trip_id,day_id,name,type,activity_date,start_time,location,notes,status,actual_cost)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (completed_id, day['id'], name, kind, day['date'], time_, location, 'One of the stops that made the final journal.', 'completed', 1800 + day_index * 350),
        )

    for name, category, offset, amount in [
        ('Stays', 'Stay', -90, 42000), ('Ferries & trains', 'Transport', -89, 12800),
        ('Meals worth remembering', 'Food', -88, 17600), ('Museums & activities', 'Activities', -87, 10200),
        ('Postcards and small things', 'Shopping', -86, 4900),
    ]:
        db.execute(
            'INSERT INTO expenses (trip_id,name,category,expense_date,amount,note) VALUES (?,?,?,?,?,?)',
            (completed_id, name, category, (today + timedelta(days=offset)).isoformat(), amount, 'Final trip total'),
        )

    journal_pages = [
        ('Amalfi at Noon', 'Amalfi Coast', IMAGE_MAP['amalfi'], 'The walls were warm from the sun and every turn opened straight into blue water.', 'postcard'),
        ('Lake Como, After Rain', 'Lake Como', IMAGE_MAP['coast'], 'The boats started moving again before the clouds had fully left.', 'lake'),
        ('Kyoto in Spring', 'Kyoto', IMAGE_MAP['kyoto'], 'Pink petals collected at the edge of side streets like confetti after a party.', 'sunset'),
        ('Banff, First Light', 'Banff National Park', IMAGE_MAP['banff'], 'Cold hands, quiet water and a mountain reflection that looked almost too precise.', 'lake'),
        ('Udaipur Blue Hour', 'Udaipur', IMAGE_MAP['udaipur'], 'The lake turned silver just before the palace lights appeared.', 'lemon'),
    ]
    for idx, (title, location, image, note, mood) in enumerate(journal_pages):
        db.execute(
            '''INSERT INTO memories (trip_id,title,memory_date,location,note,image_url,mood)
               VALUES (?,?,?,?,?,?,?)''',
            (completed_id, title, (today - timedelta(days=90 - idx)).isoformat(), location, note, image, mood),
        )

    return {'ongoing': ongoing_id, 'upcoming': upcoming_id, 'completed': completed_id}
