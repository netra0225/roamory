from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

IMAGE_MAP = {
    'udaipur': 'https://images.unsplash.com/photo-1599661046289-e31897846e41?auto=format&fit=crop&w=1600&q=86',
    'nyc_journal': '/static/uploads/journal-nyc-times-square.jpg',
    'queenstown_journal': '/static/uploads/journal-queenstown-lake.jpg',
    'venice_journal': '/static/uploads/journal-venice-flowers.jpg',
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

    history = sync_curated_history(db, user_id, today=today)
    return {'ongoing': ongoing_id, **history}


def sync_curated_history(db, user_id: int, *, today: date | None = None) -> dict[str, int]:
    """Align My Trips with the curated journal pages."""
    today = today or date.today()

    db.execute(
        '''DELETE FROM trips
           WHERE user_id=? AND destination=? AND title=?''',
        (user_id, 'Amalfi Coast', 'Blue Water, Lemon Evenings'),
    )

    specs = [
        {
            'key': 'completed_new_york',
            'destination': 'New York City',
            'title': 'Neon, Yellow Cabs & Skyline Hours',
            'start': today - timedelta(days=210),
            'end': today - timedelta(days=205),
            'description': 'Times Square lights, Manhattan streets and a quiet look across the water at Liberty.',
            'cover': IMAGE_MAP['nyc_journal'],
            'accent': 'mediterranean',
            'budget': 110000,
            'activities': [
                ('Times Square evening walk', 'destination', '18:30', 'Times Square'),
                ('Statue of Liberty morning', 'activity', '10:00', 'New York Harbor'),
            ],
            'memories': [
                ('Times Square after dark', 'Times Square', '/static/uploads/journal-nyc-times-square.jpg', 'The city turned every light on at once.'),
                ('Liberty across the water', 'New York Harbor', '/static/uploads/journal-nyc-liberty.jpg', 'A still frame inside a city that rarely stays still.'),
            ],
        },
        {
            'key': 'completed_queenstown',
            'destination': 'Queenstown, New Zealand',
            'title': 'Lake Wakatipu & Mountain Light',
            'start': today - timedelta(days=160),
            'end': today - timedelta(days=155),
            'description': 'Lake Wakatipu, Skyline Gondola and mountain views finding their way into every frame.',
            'cover': IMAGE_MAP['queenstown_journal'],
            'accent': 'coral',
            'budget': 135000,
            'activities': [
                ('Lake Wakatipu waterfront', 'destination', '09:00', 'Lake Wakatipu'),
                ('Skyline Gondola', 'activity', '15:30', 'Queenstown'),
            ],
            'memories': [
                ('Gold light on Lake Wakatipu', 'Lake Wakatipu', '/static/uploads/journal-queenstown-lake.jpg', 'The lake held the last light longer than the streets did.'),
                ('Above Queenstown', 'Skyline Gondola', '/static/uploads/journal-queenstown-gondola.jpg', 'The town looked small once the gondola cleared the rooftops.'),
            ],
        },
        {
            'key': 'completed_venice',
            'destination': 'Venice, Italy',
            'title': 'Canals, Flowers & Aperitivo',
            'start': today - timedelta(days=110),
            'end': today - timedelta(days=105),
            'description': 'Canals, flower-lined facades, bridges and aperitivo beside the water.',
            'cover': IMAGE_MAP['venice_journal'],
            'accent': 'sunflower',
            'budget': 120000,
            'activities': [
                ('Canal-side morning walk', 'destination', '09:30', 'Venice'),
                ('Aperitivo beside the canal', 'restaurant', '17:30', 'Venice'),
            ],
            'memories': [
                ('The prettiest way to get lost', 'Venice', '/static/uploads/journal-venice-flowers.jpg', 'Every turn found another canal and another flower-covered facade.'),
                ('Aperitivo by the water', 'Venice', '/static/uploads/journal-venice-food.jpg', 'Lunch took its time while boats kept passing below.'),
            ],
        },
    ]

    result = {}
    for spec in specs:
        existing = db.execute(
            'SELECT id FROM trips WHERE user_id=? AND destination=? AND title=? LIMIT 1',
            (user_id, spec['destination'], spec['title']),
        ).fetchone()

        if existing:
            trip_id = existing['id']
        else:
            trip_id = _create_trip(
                db, user_id, spec['title'], spec['destination'],
                spec['start'], spec['end'], spec['description'],
                spec['cover'], spec['accent'], spec['budget'],
            )
            days = db.execute(
                'SELECT * FROM trip_days WHERE trip_id=? ORDER BY day_number',
                (trip_id,),
            ).fetchall()

            for index, (name, kind, time_, location) in enumerate(spec['activities']):
                day = days[min(index, len(days) - 1)]
                db.execute(
                    '''INSERT INTO activities
                       (trip_id,day_id,name,type,activity_date,start_time,location,notes,status)
                       VALUES (?,?,?,?,?,?,?,?,?)''',
                    (trip_id, day['id'], name, kind, day['date'], time_, location,
                     'From the curated Roamory journal.', 'completed'),
                )

            for index, (title, location, image, note) in enumerate(spec['memories']):
                db.execute(
                    '''INSERT INTO memories
                       (trip_id,title,memory_date,location,note,image_url,mood)
                       VALUES (?,?,?,?,?,?,?)''',
                    (trip_id, title, (spec['start'] + timedelta(days=index)).isoformat(),
                     location, note, image, 'postcard'),
                )

        result[spec['key']] = trip_id

    return result
