# Roamory — Prompt-to-Implementation Checklist

This checklist maps the master prompt to the rebuilt project. It is intended to prevent visual redesigns from accidentally deleting product functionality.

## Product + art direction

- [x] PLAN → TRAVEL → REMEMBER product structure
- [x] Editorial, travel-magazine composition rather than a generic SaaS dashboard
- [x] Scrapbook language: postcards, tickets, stamps, instant-film frames, tape, paper layers, handwritten notes and route marks
- [x] Photography-led layouts with multiple destination images
- [x] Mediterranean blue / sky / turquoise / tangerine / coral / yellow / warm paper palette
- [x] DM Serif Display editorial type + Manrope UI type + Caveat handwritten accent
- [x] Restrained radii, paper shadows and asymmetrical composition
- [x] Responsive desktop / tablet / mobile behavior
- [x] Reduced-motion support

## Global navigation

- [x] Dashboard
- [x] My Trips
- [x] Create Trip
- [x] Profile
- [x] Settings
- [x] Logout
- [x] Authenticated Roamory logo returns to Dashboard
- [x] Open-trip nav: Overview / Itinerary / Today / Wallet / Packing / Budget / Journal / Summary

## Landing + auth

- [x] Editorial landing hero
- [x] Plan → Travel → Remember explanation
- [x] Product previews
- [x] Login / Create Account CTAs
- [x] Register: full name / email / password / confirmation
- [x] Login / logout
- [x] Validation

## Dashboard

- [x] Ongoing trip prominent
- [x] Upcoming trips
- [x] Completed trip archive
- [x] Upcoming countdown
- [x] Readiness
- [x] Today shortcut/current stop
- [x] Create Trip
- [x] Photography + editorial collage
- [x] Visible launch points for all eight trip modules

## My Trips

- [x] Upcoming / Ongoing / Completed grouping
- [x] Destination / cover / dates / status
- [x] Open/manage
- [x] Create another trip

## Create Trip

- [x] Title
- [x] Destination
- [x] Start / end dates
- [x] Description
- [x] Cover image
- [x] Accent/theme
- [x] Details → Cover → Review → Create wizard
- [x] Edit / Delete
- [x] End date validation

## Trip Overview

- [x] Destination / title / cover / dates / days / status
- [x] Route progress
- [x] Current/next activity
- [x] Itinerary preview
- [x] Packing progress
- [x] Wallet count
- [x] Budget progress
- [x] Memory preview
- [x] Relevant section links

## Itinerary + activities

- [x] Day-by-day switching
- [x] Destination / stay / transport / activity / restaurant / general plan types
- [x] Name / type / date / start/end / location / estimate / actual / notes
- [x] Planned / Completed / Skipped / Changed
- [x] Dotted route with completed/current/future/skipped treatment
- [x] Route progress feedback after status change
- [x] Activity details
- [x] Edit / Delete / Complete / Skip / Change
- [x] Related Wallet document
- [x] Related Journal memory
- [x] Passport-stamp completion feedback

## Travel Wallet

- [x] Flight / train / bus / hotel / activity / reservation / ID / other
- [x] Title / type / date / note / format
- [x] Open / Download / Edit / Delete
- [x] Local Flask upload storage
- [x] Choose → preview → confirm upload sequence
- [x] Ticket-slide upload feedback

## Packing

- [x] Essentials / Clothing / Toiletries / Electronics / Documents
- [x] Custom categories
- [x] Add / edit / delete items
- [x] Quantity
- [x] Packed/unpacked toggle
- [x] Packed count/progress
- [x] State-driven suitcase fill

## Budget

- [x] INR default
- [x] Currency selectable in Settings
- [x] Planned / spent / remaining / percentage
- [x] Stay / Transport / Food / Activities / Shopping / Other
- [x] Expense name / category / date / amount / note
- [x] Edit / Delete
- [x] Category totals
- [x] Animated progress update after adding an expense
- [x] Over-budget state

## Today

- [x] Destination / day / date
- [x] Current / next activity
- [x] Time / location / notes
- [x] Relevant linked ticket/document
- [x] Complete / Skip / Change
- [x] Wallet / Add Expense / Add Memory shortcuts
- [x] Completion advances state/route and triggers stamp feedback
- [x] Mobile-focused layout

## Travel Journal

- [x] Physical digital-book metaphor rather than gallery/feed
- [x] Five starter destinations in completed archive
- [x] Destination-specific moods
- [x] Hero photograph + secondary photograph
- [x] Ticket fragment
- [x] Postage/passport detail
- [x] Tape / flower / annotation
- [x] Mini route
- [x] Journal sentence/date/location
- [x] Add / edit / delete memory
- [x] Instant-film development feedback after photo upload
- [x] CSS 3D page turning around book spine
- [x] Front/back page faces and shadow/layer treatment
- [x] Previous reverses page state
- [x] Reduced-motion fallback

## Completed Summary

- [x] Hero / destination / dates / Completed stamp
- [x] Journey route
- [x] Days
- [x] Completed activities
- [x] Photographs
- [x] Journal entries
- [x] Total spent
- [x] Multi-photo editorial memory arrangement
- [x] Final travel note

## Profile + Settings

- [x] Avatar
- [x] Name
- [x] Email
- [x] Edit profile
- [x] Currency
- [x] Date format
- [x] Appearance preference
- [x] Logout

## Shared states + accessibility

- [x] Empty states
- [x] Loading-button states
- [x] Validation/error handling
- [x] Delete confirmation dialog
- [x] Focus states
- [x] Semantic form labels
- [x] Keyboard-friendly native controls/dialogs
- [x] Reduced-motion support

## Backend + data

- [x] Python + Flask only
- [x] SQLite + Jinja2
- [x] Users
- [x] Trips
- [x] Trip Days
- [x] Activities
- [x] Expenses
- [x] Packing Categories
- [x] Packing Items
- [x] Documents
- [x] Memories
- [x] Settings
- [x] Password hashing
- [x] Flask sessions
- [x] Route protection
- [x] Resource ownership checks
- [x] Upload validation / type / size restrictions
- [x] CSRF protection for POST forms
- [x] No React / Next.js / Node.js / Express / Firebase / Supabase / MongoDB / Tailwind / Bootstrap
