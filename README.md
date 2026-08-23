# Roamory — Editorial Full-Stack Build

Roamory is a **Visual Trip Planner & Travel Journal** built as a complete BCA minor project with the required stack only:

- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Backend:** Python + Flask
- **Database:** SQLite
- **Templates:** Jinja2
- **Authentication:** Flask sessions + Werkzeug password hashing
- **Uploads:** Flask local storage

No React, Next.js, Node.js, Express, Firebase, Supabase, MongoDB, Bootstrap, Tailwind, or other frontend framework is used.

## What changed in this rebuild

The first build could technically reach the individual modules, but a newly registered account opened onto a nearly empty dashboard. That made the product look unfinished and hid the strongest parts of Roamory.

This rebuild changes the first-run experience structurally:

- A **fully editable starter travel world** is created once for a new account: an ongoing Udaipur trip, an upcoming Amalfi Coast trip, and a completed five-place travel archive.
- Existing accounts created with the earlier build are also upgraded: if the account has no trips yet, the starter content is populated once on Dashboard.
- If the user later deletes the starter trips, they **do not reappear**. Empty states remain real product states.
- Dashboard now visibly surfaces **Overview, Itinerary, Today, Wallet, Packing, Budget, Journal, and Summary** instead of hiding these sections behind an empty state.
- Photography, ticket stubs, instant-film frames, paper pieces, stamps, route marks, a mini wallet, suitcase state, receipt treatment and journal previews are part of the composition.

## Core product implemented

### Account
- Register / login / logout
- Session-protected routes
- Password hashing
- Profile + profile-photo upload
- Settings
- INR as the default currency with alternatives

### Dashboard + trip library
- Ongoing trip editorial hero
- Upcoming trips + countdown
- Completed archive
- Current/next activity
- Packing readiness
- Wallet document count
- Budget progress
- Journal preview
- Create Trip CTA
- My Trips grouped as Ongoing / Upcoming / Completed

### Create & manage trips
- 4-step frontend flow: **Details → Cover → Review → Create**
- Trip title, destination, dates, description, cover photo and accent/theme
- Edit and delete
- Server-side date/required-field validation
- Automatic Trip Day creation

### Trip Overview
- Cover, status, dates and day count
- Route completion
- Packing progress
- Wallet count
- Budget progress
- Current/next activity
- Memory preview
- Direct links to trip tools

### Itinerary + Activity Details
- Day-by-day planner
- Destination / Stay / Transport / Activity / Restaurant / General types
- Start/end time, location, estimated cost, actual cost, notes
- Planned / Completed / Skipped / Changed states
- Dotted route progress driven by real activity state
- Activity editing/deletion
- Related Wallet document selector
- Related Journal memory selector
- Passport-stamp completion state

### Today
- Travel-day focused interface
- Current and next activity
- Time, location and notes
- Relevant linked ticket/document
- Complete / Skip / Change actions
- Shortcuts to Wallet, Add Expense and Add Memory

### Travel Wallet
- Flight / train / bus / hotel / activity / reservation / ID / other document types
- Local file upload
- File preview before explicit confirmation
- Open / download / edit / delete
- Ticket-sliding-into-wallet feedback after upload

### Packing
- Essentials / Clothing / Toiletries / Electronics / Documents
- Add custom category
- Add / edit / delete item
- Quantity
- Packed/unpacked toggle
- Live packed count
- State-driven illustrated suitcase fill

### Budget
- Planned budget
- Spent / remaining / percentage
- Stay / Transport / Food / Activities / Shopping / Other
- Add / edit / delete expenses
- Category totals
- Animated progress after new expenses
- Over-budget treatment
- INR by default

### Journal — signature feature
- A **book**, not a masonry/gallery feed
- Five-location starter journal in the completed archive
- Destination-specific page moods
- Hero + secondary photography
- Ticket fragment
- Postage/passport details
- Tape, flower, handwritten annotation and mini route mark
- Add / edit / delete memories
- Photo-development feedback after image upload
- **CSS 3D page turn around the book spine** with front/back faces, layering and shadows
- `prefers-reduced-motion` fallback

### Completed Trip Summary
- Editorial cover + Completed stamp
- Journey route
- Days
- Completed activities
- Photographs
- Journal entries
- Total spent
- Multi-image memories arrangement
- Final travel note

## State-driven motion

The animations are tied to product state rather than being random decoration:

- Completing an itinerary stop progresses the route and triggers the passport stamp.
- Uploading a Wallet document triggers the ticket-slide state.
- Toggling packing changes the actual suitcase fill and gives packed-state feedback.
- Uploading a journal photo triggers instant-film development.
- Journal Next/Previous uses 3D page rotation around the spine.
- Reduced-motion users receive simpler transitions.

## Starter showcase data

The starter content is intentionally editable and deletable. It exists so the first screen demonstrates the actual product instead of presenting a blank database.

It contains:

- **Ongoing:** Udaipur — activities, expenses, packing, Wallet documents and memories
- **Upcoming:** Amalfi Coast — planned route
- **Completed:** Summer Atlas — Amalfi Coast, Lake Como, Kyoto, Banff and Udaipur journal pages + completed summary

You do **not** need to run `seed_demo.py` just to see a populated first-run UI anymore.

`seed_demo.py` remains available if you specifically want the separate demo login:

- Email: `demo@roamory.local`
- Password: `roamory123`

## Run locally on macOS

Open Terminal inside the extracted `roamory` folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

Register a new account. The starter showcase will be created automatically.

### If replacing the earlier build

The new `db.py` contains a small SQLite migration for the new first-run flag. If you keep your old local database, open Dashboard once; an account with no trips will receive the showcase once. If you use a fresh folder/database, registration creates it immediately.

After replacing files, use a hard refresh in Chrome if an old stylesheet is still cached:

```text
Command + Shift + R
```

## QA commands

After Flask is installed locally:

```bash
python smoke_test.py
```

Static checks used while packaging this build:

```bash
python -m py_compile app.py db.py starter_data.py seed_demo.py smoke_test.py
node --check static/js/app.js
```

All Jinja templates were also parsed and all `url_for(...)` endpoint references were checked against implemented Flask functions.

## Security scope

This stays understandable for a student/local project while keeping responsible basics:

- Passwords are hashed and never stored in plain text.
- POST forms use a session-bound CSRF token.
- Session cookies are HTTP-only and SameSite=Lax.
- Protected routes require an authenticated session.
- Trip-scoped resources are ownership-checked through their trip.
- Upload filenames are sanitized/randomized for user uploads.
- Upload extensions and an 8 MB size limit are enforced server-side.
- Server-side validation is used even when the browser validates first.

For deployment, provide a stable secret:

```bash
export ROAMORY_SECRET_KEY='replace-with-a-long-random-secret'
```

Set `ROAMORY_SECURE_COOKIE=1` when serving through HTTPS.

## Where the important UI lives

```text
roamory/
├── app.py                     # Flask routes / CRUD / auth / validation
├── db.py                      # SQLite setup + lightweight migration
├── schema.sql                 # Relational schema
├── starter_data.py            # Editable first-run visual showcase
├── seed_demo.py               # Optional separate demo account
├── static/
│   ├── css/style.css          # Full editorial visual system + motion
│   ├── js/app.js              # UI interactions / journal turn / wizard
│   └── uploads/               # User-uploaded local files at runtime
└── templates/
    ├── base.html
    ├── landing.html
    ├── dashboard.html
    ├── trips.html
    ├── trip_form.html
    ├── overview.html
    ├── itinerary.html
    ├── activity_detail.html
    ├── today.html
    ├── wallet.html
    ├── packing.html
    ├── budget.html
    ├── journal.html
    ├── summary.html
    ├── profile.html
    └── settings.html
```

See `REQUIREMENTS_CHECKLIST.md` for the prompt-to-implementation map.
