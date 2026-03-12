# Firduty — School Duty Roster System

**Version 2.3.0** · FastAPI · Flutter · PostgreSQL (Supabase) · Koyeb

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Project Structure](#3-project-structure)
4. [Full Installation Guide](#4-full-installation-guide)
5. [Backend Stack](#5-backend-stack)
6. [Flutter App](#6-flutter-app)
7. [Admin Web UI](#7-admin-web-ui)
8. [Environment Variables](#8-environment-variables)
9. [Database Setup & Migrations](#9-database-setup--migrations)
10. [Koyeb Deployment](#10-koyeb-deployment)
11. [Authentication](#11-authentication)
12. [API Reference](#12-api-reference)
13. [Push Notifications](#13-push-notifications)
14. [Scheduler Jobs](#14-scheduler-jobs)
15. [Troubleshooting](#15-troubleshooting)
16. [Changelog](#16-changelog)

---

## 1. Project Overview

Firduty automates duty roster management for schools in Oman.

| Actor | What they do |
|---|---|
| **Admin** | Creates locations, shifts, and weekly duty plans via a web UI; publishes rosters; approves teacher accounts |
| **Teacher** | Registers via the Flutter mobile/web app; receives push notifications; confirms duty attendance; earns points |

**Core workflow:**
1. Admin sets up locations and shifts once
2. Each Thursday at 16:00 (Muscat), the scheduler auto-clones the latest published week as a draft for next week
3. Admin adjusts assignments in the planner, then publishes
4. Assigned teachers receive push notifications
5. Teachers confirm attendance; points are calculated based on punctuality

---

## 2. Architecture

```
┌─────────────────────────────────────────┐
│           Flutter App (PWA/Android)     │  ← teachers
│  lib/screens/ + lib/services/           │
│  Web: Flutter Web + Firebase Web Push   │
│  Android: native APK + FCM              │
└──────────────┬──────────────────────────┘
               │  REST / JSON
               ▼
┌─────────────────────────────────────────┐
│         FastAPI Backend (Koyeb)         │
│  routers/ + services/ + jobs/           │
│  APScheduler (background jobs)          │
└────────────┬──────────────┬─────────────┘
             │              │
     ┌───────▼──────┐  ┌────▼────────────────┐
     │  PostgreSQL  │  │  Firebase Admin SDK  │
     │  (Supabase)  │  │  (FCM push notify)   │
     └──────────────┘  └────────────────────--┘

┌─────────────────────────────────────────┐
│         Admin Web UI (static HTML/JS)   │  ← school admins
│  admin_ui/ — no build step required     │
│  Served from any static host or Koyeb   │
└──────────────────────────────────────────┘
```

---

## 3. Project Structure

```
firduty/                                   ← repository root
│
├── README.md                              ← this file
├── pyrightconfig.json                     ← Python type-checking config
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── keepalive.yml                  ← pings Koyeb every 14 min to prevent sleep
│
├── migrations/                            ← manual SQL migration scripts (legacy + emergency)
│   ├── 001_duty_types.sql                 ← adds duty_type to shifts
│   ├── 002_teacher_registration.sql       ← adds email + status to teachers
│   ├── 003_web_push.sql                   ← documents device_tokens.platform='web'
│   └── 004_production_fix.sql             ← idempotent emergency fix for production DB
│
├── backend/                               ← FastAPI application (deployed to Koyeb)
│   ├── main.py                            ← app entry point, router registration, lifespan
│   ├── config.py                          ← Settings class, all env var reads
│   ├── database.py                        ← SQLAlchemy engine, SessionLocal, Base, get_db()
│   ├── scheduler.py                       ← APScheduler setup, job registration, /scheduler/status
│   ├── requirements.txt                   ← Python dependencies (pinned major versions)
│   ├── alembic.ini                        ← Alembic configuration
│   ├── .env.example                       ← copy to .env for local dev
│   │
│   ├── alembic/                           ← Alembic migration framework
│   │   ├── env.py                         ← reads DATABASE_URL from env, sets target_metadata
│   │   ├── script.py.mako                 ← template for generated migration files
│   │   └── versions/
│   │       ├── 0001_initial_schema.py     ← creates all tables from scratch (new installs)
│   │       └── 0002_teacher_email_status.py  ← adds email + status columns (production fix)
│   │
│   ├── models/
│   │   ├── models.py                      ← all ORM models (Teacher, Shift, Location, WeekPlan …)
│   │   └── points_models.py               ← re-exports DutyConfirmation, MonthlyPointsSummary
│   │
│   ├── schemas/
│   │   └── schemas.py                     ← all Pydantic request/response schemas
│   │
│   ├── routers/
│   │   ├── auth.py                        ← POST /auth/admin/login, /login/json, GET /auth/validate
│   │   ├── teachers.py                    ← full teacher CRUD, register, approve, schedule
│   │   ├── locations.py                   ← location CRUD
│   │   ├── shifts.py                      ← shift CRUD
│   │   ├── weeks.py                       ← week plan create/clone/publish/assign
│   │   ├── points.py                      ← duty confirmation + monthly points
│   │   ├── reports.py                     ← monthly leaderboard + CSV export
│   │   └── dashboard.py                   ← GET /admin/dashboard stats
│   │
│   ├── services/
│   │   ├── auth_service.py                ← JWT create_access_token(), decode_token()
│   │   ├── week_service.py                ← week plan business logic, slot management
│   │   ├── points_service.py              ← duty confirmation scoring, monthly summaries
│   │   └── notification_service.py        ← FCM push via firebase-admin
│   │
│   └── jobs/
│       ├── auto_clone.py                  ← weekly auto-clone job (run every Thursday 16:00)
│       └── monthly_reset.py               ← monthly points rebuild (run 1st of month 20:05)
│
├── flutter_app/                           ← Flutter mobile + web app (teachers)
│   ├── pubspec.yaml                       ← Flutter package config (v2.3.0+3)
│   ├── l10n.yaml                          ← localisation config (AR + EN)
│   │
│   ├── lib/
│   │   ├── main.dart                      ← app entry point, Firebase init, routing
│   │   ├── app_theme.dart                 ← brand colours, text styles
│   │   ├── firebase_options.dart          ← generated by flutterfire configure (fill manually)
│   │   │
│   │   ├── screens/
│   │   │   ├── teacher_select_screen.dart ← first launch: enter name / pick teacher
│   │   │   ├── pending_screen.dart        ← shown while status = 'pending'
│   │   │   ├── today_screen.dart          ← today's duties + confirm button
│   │   │   ├── week_screen.dart           ← weekly duty calendar
│   │   │   └── points_screen.dart         ← monthly points leaderboard
│   │   │
│   │   ├── services/
│   │   │   ├── api_service.dart           ← all REST calls, safe JSON decoding, error messages
│   │   │   └── notification_service.dart  ← FCM token registration, foreground handler
│   │   │
│   │   ├── l10n/
│   │   │   ├── app_ar.arb                 ← Arabic strings
│   │   │   └── app_en.arb                 ← English strings
│   │   │
│   │   └── gen/                           ← generated by `flutter gen-l10n` (do not edit)
│   │       ├── app_localizations.dart
│   │       ├── app_localizations_ar.dart
│   │       └── app_localizations_en.dart
│   │
│   ├── assets/
│   │   ├── logo.png                       ← 512×512 app logo
│   │   ├── logo_small.png                 ← 256×256
│   │   └── app_icon.png                   ← 1024×1024 (used by flutter_launcher_icons)
│   │
│   ├── web/                               ← Flutter Web / PWA files
│   │   ├── index.html                     ← PWA shell, Firebase SDK config
│   │   ├── manifest.json                  ← PWA manifest (name, icons, display)
│   │   ├── firebase-messaging-sw.js       ← service worker — handles background push
│   │   └── icons/                         ← PWA icons (192, 512, maskable variants)
│   │
│   └── test/
│       └── widget_test.dart               ← placeholder widget test
│
└── admin_ui/                              ← Admin web interface (pure HTML + JS, no build step)
    ├── login.html                         ← login form
    ├── dashboard.html                     ← stats, chart, fairness warnings
    ├── planner.html                       ← drag-and-drop week planner
    ├── teachers.html                      ← teacher approval management
    ├── reports.html                       ← monthly points leaderboard + CSV
    ├── logo.png                           ← admin UI logo
    ├── favicon.ico / favicon-*.png        ← favicon set
    │
    ├── css/
    │   └── style.css                      ← all admin UI styles (RTL + LTR aware)
    │
    ├── js/
    │   ├── auth.js                        ← shared: apiFetch(), guardPage(), logout(), authHeaders()
    │   ├── i18n.js                        ← AR/EN runtime switching, loads i18n/ar.json or en.json
    │   ├── login.js                       ← JWT login, auto-redirect, Enter key, lang toggle
    │   ├── dashboard.js                   ← fetches /admin/dashboard, renders charts
    │   ├── planner.js                     ← week planner logic, SortableJS drag-and-drop
    │   └── teachers.js                    ← pending/approve endpoints
    │
    └── i18n/
        ├── ar.json                        ← Arabic UI strings
        └── en.json                        ← English UI strings
```

---

## 4. Full Installation Guide

This section covers everything needed to run the complete Firduty system from scratch.

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | ≥ 3.10 | [python.org](https://www.python.org/downloads/) |
| Flutter | ≥ 3.19 | [flutter.dev/docs/get-started/install](https://docs.flutter.dev/get-started/install) |
| Git | any | [git-scm.com](https://git-scm.com/) |
| Chrome | any | For Flutter Web development |
| PostgreSQL client (`psql`) | optional | For running manual SQL scripts |

> Flutter is only needed if you are building or modifying the mobile/web app.
> The Admin UI has no build requirements — just a browser.

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/firduty.git
cd firduty
```

---

### Step 2 — Backend setup

#### 2a. Create a virtual environment and install dependencies

```bash
cd backend/
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

#### 2b. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```dotenv
# Leave blank to use SQLite for local dev (no PostgreSQL needed)
DATABASE_URL=                          # or: postgresql://user:pass@host:5432/dbname

SECRET_KEY=your-random-64-char-string  # python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_USERNAME=admin
ADMIN_PASSWORD=yourpassword
ALLOWED_ORIGINS=*                      # use specific origins in production
```

Firebase and VAPID keys are optional for local development — push notifications will
be silently disabled if they are not set.

#### 2c. Set up the database

**SQLite (default for local dev — no setup needed):**
```bash
# DATABASE_URL not set → SQLite file created automatically at backend/firduty.db
alembic upgrade head
```

**PostgreSQL (Supabase or local):**
```bash
# Set DATABASE_URL in .env first, then:
alembic upgrade head
```

#### 2d. Start the backend

```bash
uvicorn main:app --reload --port 8000
```

The API is now available at:
- API root: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

### Step 3 — Admin Web UI setup

No build step required. The admin UI is plain HTML + JS.

**Option A — open directly:**
```bash
# On macOS
open admin_ui/login.html

# On Linux
xdg-open admin_ui/login.html

# On Windows
start admin_ui/login.html
```

**Option B — serve locally (recommended for full functionality):**
```bash
cd admin_ui/
python -m http.server 3000
```
Then open: http://localhost:3000/login.html

**Log in:**
Use `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env`.
The default API base URL in `login.js` is `https://YOUR-APP-NAME.koyeb.app/`.
For local development, open browser DevTools → Application → Local Storage and set:

```
key:   firduty_api
value: http://localhost:8000/
```

Then refresh the page.

> **Note:** `auth.js` must be loaded before each page's own script. Verify all four
> protected pages (`dashboard.html`, `planner.html`, `teachers.html`, `reports.html`)
> include `<script src="js/auth.js"></script>` as the first script tag.

---

### Step 4 — Flutter app setup

#### 4a. Install dependencies

```bash
cd flutter_app/
flutter pub get
```

#### 4b. Configure Firebase (required for push notifications)

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Register a **Web app** (for Flutter Web + iOS PWA push):
   - App nickname: `firduty-web`
3. Register an **Android app**:
   - Android package name: match the value in `android/app/build.gradle`
   - Download `google-services.json` → place at `flutter_app/android/app/google-services.json`
4. Run `flutterfire configure` inside `flutter_app/`:
   ```bash
   dart pub global activate flutterfire_cli
   flutterfire configure
   ```
   This updates `lib/firebase_options.dart` automatically.
5. Set up VAPID keys for Web Push:
   - Firebase Console → Project Settings → Cloud Messaging → Web Push certificates → Generate key pair
   - Copy the public key into `lib/firebase_options.dart` as `kVapidPublicKey`
   - Add the private key as `VAPID_PRIVATE_KEY` in your backend `.env`
6. Fill in `web/firebase-messaging-sw.js`:
   ```js
   firebase.initializeApp({
     apiKey: "...",
     projectId: "...",
     messagingSenderId: "...",
     appId: "...",
   });
   ```

> **Skip Firebase entirely for UI-only development.** The app will work without push
> notifications — just remove the `firebase_core` init call in `main.dart` to avoid
> startup errors.

#### 4c. Run the Flutter app

```bash
cd flutter_app/

# Web in Chrome (recommended for development)
flutter run -d chrome \
  --dart-define=API_BASE_URL=http://localhost:8000

# Android emulator / device
flutter run \
  --dart-define=API_BASE_URL=http://localhost:8000

# Android on Genymotion emulator
# (169.254.0.101 is the host machine IP visible from Genymotion)
flutter run \
  --dart-define=API_BASE_URL=http://169.254.0.101:8000
```

> `API_BASE_URL` **must** end without a trailing slash. If omitted, the app builds
> with a placeholder URL and will display a connection error.

#### 4d. Build for release

```bash
# Android APK
flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app

# Web (PWA — deploy the build/web/ directory)
flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app \
  --base-href "/"
```

---

### Step 5 — Verify the full stack locally

With all three components running, test the end-to-end flow:

1. **Swagger UI** → http://localhost:8000/docs → click 🔓 Authorize → log in
2. `POST /locations/` → create a test location
3. `POST /shifts/` → create a test shift
4. **Admin UI** → http://localhost:3000/login.html → log in
5. **Flutter app** → http://localhost:8000 (Chrome) → register as a teacher
6. **Admin UI → Teachers** → approve the registration
7. **Flutter app** → should now show duty screen

---

## 5. Backend Stack

| Component | Technology |
|---|---|
| Framework | FastAPI 0.104+ |
| ASGI server | Uvicorn |
| Database ORM | SQLAlchemy 2.0 |
| DB driver | psycopg2-binary (PostgreSQL) |
| Migrations | **Alembic** |
| Auth | JWT via python-jose + OAuth2PasswordBearer |
| Push notifications | firebase-admin (FCM) |
| Scheduler | APScheduler 3 |
| Validation | Pydantic v2 (pinned ≥ 2.0) |
| Timezone | pytz, Asia/Muscat |

---

## 6. Flutter App

Located in `flutter_app/`.

| Feature | Details |
|---|---|
| Platforms | Android (APK), Web (PWA) |
| iOS support | iOS Safari 16.4+ via PWA "Add to Home Screen" |
| Push — Android | Firebase Cloud Messaging (FCM native) |
| Push — Web/iOS | FCM Web Push via VAPID |
| Localisation | Arabic (default) + English |
| State | No external state management — simple setState |
| API | `lib/services/api_service.dart` |

**Build commands:**
```bash
# Android APK
flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app

# Web (PWA)
flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app \
  --base-href "/"
```

**Local emulator (Genymotion):**
```bash
flutter run --dart-define=API_BASE_URL=http://169.254.0.101:8000
```

---

## 7. Admin Web UI

Located in `admin_ui/`. Pure HTML + Vanilla JS — no build step.

| File | Purpose |
|---|---|
| `login.html` | JWT login form |
| `dashboard.html` | Stats, distribution chart, warnings |
| `planner.html` | Drag-and-drop weekly assignment editor |
| `teachers.html` | Approve / reject teacher registrations |
| `reports.html` | Monthly points leaderboard + CSV export |
| `js/auth.js` | Shared: `apiFetch()`, `guardPage()`, `logout()` |
| `js/login.js` | Login flow + token persistence |
| `js/i18n.js` | AR/EN runtime language switcher |

**Required:** add `<script src="js/auth.js"></script>` **before** each page's own
script on `dashboard.html`, `planner.html`, `teachers.html`, `reports.html`.

---

## 8. Environment Variables

Set these in your Koyeb service environment, or in `backend/.env` for local dev.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | `sqlite:///./firduty.db` | PostgreSQL connection string from Supabase |
| `SECRET_KEY` | **Yes** | `dev-secret-key-change-in-production` | JWT signing key — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `1440` | JWT lifetime (24 hours) |
| `ADMIN_USERNAME` | **Yes** | `admin` | Admin login username |
| `ADMIN_PASSWORD` | **Yes** | `admin123` | Admin login password — change in production |
| `FIREBASE_CREDENTIALS_PATH` | Recommended | `./firebase-credentials.json` | Path to Firebase service account JSON |
| `FIREBASE_CREDENTIALS_JSON` | Alternative to path | — | Entire Firebase JSON as a string (for Koyeb, avoids file volumes) |
| `VAPID_PRIVATE_KEY` | For web push | — | VAPID private key (base64url) |
| `VAPID_PUBLIC_KEY` | For web push | — | VAPID public key — also set in `flutter_app/lib/firebase_options.dart` |
| `VAPID_CONTACT_EMAIL` | For web push | `admin@yourschool.com` | Email in VAPID claims |
| `PORT` | No | `8000` | Injected by Koyeb automatically |
| `ALLOWED_ORIGINS` | **Yes** | `*` | Comma-separated CORS origins |
| `RUN_SCHEDULER` | No | `true` | Set `false` on extra instances to prevent duplicate jobs |
| `SCHEDULER_JITTER` | No | `30` | Random seconds added to scheduler triggers |

---

## 9. Database Setup & Migrations

### New installation

```bash
cd backend/
alembic upgrade head   # creates all tables from scratch
```

### Existing production database — schema drift fix

If your production database was created with `Base.metadata.create_all()` before
v2.3.0, the `teachers` table is missing the `email` and `status` columns.

**Option A — Alembic (recommended):**
```bash
cd backend/
# Skip migration 0001 (tables already exist), apply only 0002
alembic stamp 0001         # tell Alembic "0001 is already applied"
alembic upgrade 0002       # apply only the column additions
```

**Option B — Manual SQL (emergency, e.g. Supabase SQL Editor):**
```sql
-- Paste contents of migrations/004_production_fix.sql
-- The script is idempotent — safe to run multiple times
```

**Option C — Supabase SQL Editor:**
Open `migrations/004_production_fix.sql` and run it directly.

### Migration files

| File | Description |
|---|---|
| `alembic/versions/0001_initial_schema.py` | Creates all tables from scratch |
| `alembic/versions/0002_teacher_email_status.py` | Adds `email` and `status` to teachers + fixes nullable order columns |
| `migrations/001_duty_types.sql` | Legacy: adds `duty_type` to shifts (manual) |
| `migrations/002_teacher_registration.sql` | Legacy: adds email + status (manual) |
| `migrations/003_web_push.sql` | Legacy: documents `device_tokens.platform='web'` |
| `migrations/004_production_fix.sql` | **Emergency idempotent fix for production** |

### Generating future migrations

```bash
cd backend/
# After changing models/models.py:
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

### ORM model summary

| Table | Key columns |
|---|---|
| `teachers` | `id`, `name`, `email` (nullable), `status` (pending/approved), `active`, `preferred_language` |
| `device_tokens` | `teacher_id`, `token`, `platform` (android/web) |
| `locations` | `id`, `name_en`, `name_ar`, `order` |
| `shifts` | `id`, `name_en`, `name_ar`, `start_time`, `end_time`, `order`, `duty_type` |
| `week_plans` | `id`, `week_start_date` (unique), `status` (draft/published), `version` |
| `day_plans` | `id`, `week_plan_id`, `date` |
| `shift_locations` | `id`, `day_plan_id`, `shift_id`, `location_id` (nullable), `slots_count`, `order` |
| `assignments` | `id`, `shift_location_id`, `slot_index`, `teacher_id` (nullable), `grade_class` |
| `duty_confirmations` | `id`, `teacher_id`, `assignment_id`, `confirmed_at`, `points_earned` |
| `monthly_points_summary` | `teacher_id`, `year`, `month`, `total_points` |

---

## 10. Koyeb Deployment

### First-time deploy

1. Push `backend/` to a GitHub repo
2. Create a new Koyeb service:
   - **Type:** Web service
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Run command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Root directory:** `backend/`
3. Set all environment variables listed in Section 7
4. After first deploy, run migrations (see Section 8)

### Updating production

```bash
git push origin main   # triggers automatic redeploy on Koyeb
```

If you added or changed ORM models:
```bash
# After deploy completes:
alembic upgrade head   # from your local machine pointing at production DATABASE_URL
```

### Procfile (alternative run command)

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## 11. Authentication

### How it works

- Admin credentials are stored as environment variables (`ADMIN_USERNAME`, `ADMIN_PASSWORD`)
- Login returns a JWT signed with `SECRET_KEY`
- All protected endpoints require `Authorization: Bearer <token>` header
- Token lifetime defaults to 24 hours (`ACCESS_TOKEN_EXPIRE_MINUTES=1440`)

### Login endpoints

| Endpoint | Content-Type | Used by |
|---|---|---|
| `POST /auth/admin/login` | `application/x-www-form-urlencoded` | **Swagger UI Authorize button** |
| `POST /auth/admin/login/json` | `application/json` | Admin Web UI (`login.js`) |
| `GET /auth/validate` | — (JWT required) | Admin UI session check on page load |

Both login endpoints return:
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

### Logging in from Swagger UI

1. Open `https://YOUR-APP.koyeb.app/docs`
2. Click the 🔓 **Authorize** button
3. Enter `ADMIN_USERNAME` and `ADMIN_PASSWORD`
4. Click **Authorize** — Swagger will attach the token to all subsequent requests

### Admin UI login flow

`login.js` POSTs to `/auth/admin/login/json` with `{"username": "...", "password": "..."}`.
The returned `access_token` is stored in `localStorage` as `firduty_token`.

On every protected page load, `auth.js` (`guardPage()`) checks `localStorage` for a token
and optionally calls `GET /auth/validate` to confirm it is still valid.

`apiFetch(path, opts)` automatically attaches `Authorization: Bearer <token>` to every
API call and redirects to `login.html` on a `401` response.

---

## 12. API Reference

Base URL: `https://YOUR-APP.koyeb.app`

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/admin/login` | — | OAuth2 form login (Swagger) |
| POST | `/auth/admin/login/json` | — | JSON login (Admin UI) |
| GET | `/auth/validate` | JWT | Validate token, return identity |

### Teachers

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/teachers/` | — | List approved + active teachers |
| GET | `/teachers/all` | JWT | List ALL teachers (any status) |
| GET | `/teachers/pending` | JWT | List pending-approval teachers |
| POST | `/teachers/` | JWT | Create teacher (admin) |
| POST | `/teachers/register` | — | Self-register (creates pending) |
| POST | `/teachers/approve-all` | JWT | Approve all pending |
| PUT | `/teachers/{id}` | JWT | Update name/active/language |
| DELETE | `/teachers/{id}` | JWT | Deactivate (soft delete) |
| GET | `/teachers/{id}/status` | — | Status check (Flutter app) |
| POST | `/teachers/{id}/approve` | JWT | Approve one teacher |
| GET | `/teachers/{id}/schedule?date=YYYY-MM-DD` | — | Daily duties |
| GET | `/teachers/{id}/week?week_start=YYYY-MM-DD` | — | Weekly duties |
| POST | `/teachers/{id}/device-token` | — | Register FCM token |

**Create teacher example (admin):**
```json
POST /teachers/
Authorization: Bearer <token>

{ "name": "Ahmed Al-Rashidi", "preferred_language": "ar" }
```

**Self-register example (teacher):**
```json
POST /teachers/register

{ "name": "Ahmed Al-Rashidi", "email": "ahmed@school.edu.om" }
```

### Locations

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/locations/` | — | List all locations |
| POST | `/locations/` | JWT | Create location |
| PUT | `/locations/{id}` | JWT | Update location |
| DELETE | `/locations/{id}` | JWT | Delete location |

### Shifts

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/shifts/` | — | List all shifts |
| POST | `/shifts/` | JWT | Create shift |
| PUT | `/shifts/{id}` | JWT | Update shift |
| DELETE | `/shifts/{id}` | JWT | Delete shift |

`duty_type` values: `"morning_endofday"` or `"break"`

### Week Plans

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/weeks/current` | — | Current week plan (or null) |
| GET | `/weeks/{week_start}` | — | Specific week (YYYY-MM-DD) |
| POST | `/weeks/{week_start}/create` | JWT | Create empty draft week |
| POST | `/weeks/{week_start}/clone` | JWT | Clone from latest published |
| PUT | `/weeks/{week_start}/status` | JWT | Publish / set draft |
| PUT | `/weeks/{week_start}/shift-locations` | JWT | Set slots for a day+shift |
| PUT | `/weeks/{week_start}/assignments` | JWT | Assign teachers to slots |

### Points

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/points/teachers/{id}/confirm` | — | Confirm duty attendance |
| GET | `/points/teachers/{id}/monthly?year=&month=` | — | Monthly total + detail |
| POST | `/points/rebuild?year=&month=` | JWT | Rebuild summary cache |

**Confirmation scoring (Asia/Muscat):**
- Confirmed before or at shift start → **2 points**
- Confirmed within 5 minutes after start → **1 point**
- Confirmed more than 5 minutes late → **0 points**

### Admin Dashboard & Reports

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | JWT | Stats for current + next week |
| GET | `/admin/reports/monthly-points?year=&month=` | JWT | Leaderboard |
| GET | `/admin/reports/monthly-points/export/csv?year=&month=` | JWT | CSV download |
| GET | `/admin/reports/monthly-points/{teacher_id}?year=&month=` | JWT | Per-teacher detail |
| POST | `/admin/reports/monthly-points/rebuild?year=&month=` | JWT | Rebuild cache |

### Other

| Method | Path | Description |
|---|---|---|
| GET | `/` | Version and status |
| GET | `/health` | Health check for Koyeb |
| GET | `/scheduler/status` | Scheduler job status |

---

## 13. Push Notifications

### Android

Uses Firebase Cloud Messaging (FCM) native tokens.

1. Download `google-services.json` from Firebase Console
2. Place at `flutter_app/android/app/google-services.json`
3. Set `FIREBASE_CREDENTIALS_JSON` or `FIREBASE_CREDENTIALS_PATH` on Koyeb

### Web / iOS PWA

Uses FCM Web Push via VAPID keys.

**iOS requirements:**
- iOS Safari 16.4+ with "Add to Home Screen" (PWA installed)
- The VAPID public key must match between backend and Flutter app

**Setup steps:**
1. Firebase Console → Project Settings → Cloud Messaging → Web Push certificates
2. Generate a key pair → copy the public key
3. Set `VAPID_PUBLIC_KEY` in Koyeb env
4. Set `kVapidPublicKey` in `flutter_app/lib/firebase_options.dart`
5. Fill `firebase.initializeApp({...})` in `flutter_app/web/firebase-messaging-sw.js`

### Device token registration

`POST /teachers/{id}/device-token`
```json
{ "token": "fcm-or-web-push-token", "platform": "android" }
```
`platform` values: `"android"` or `"web"`

---

## 14. Scheduler Jobs

| Job | Schedule | Logic |
|---|---|---|
| `auto_clone` | Every Thursday 16:00 Muscat | Clones the latest published week to next week (draft) |
| `monthly_reset` | 1st of each month 20:05 Muscat | Rebuilds points summary for previous month; seeds current month |

Both jobs are **idempotent** — running them twice has no harmful effect.

Multi-instance note: if Koyeb scales to more than one instance, each instance runs
the scheduler. To prevent duplicate job runs: set `RUN_SCHEDULER=true` on one
instance and `RUN_SCHEDULER=false` on all others.

---

## 15. Troubleshooting

### POST /teachers/ → 500 "column email does not exist"

**Cause:** The database was created before the `email`/`status` columns were added to the ORM model.

**Fix:** Run migration 004:
```sql
-- Paste migrations/004_production_fix.sql in Supabase SQL Editor
```
Or via Alembic:
```bash
alembic stamp 0001
alembic upgrade 0002
```

---

### GET /locations/ or GET /shifts/ returns only one item

**Cause (historical):** Pydantic v1 was installed but schemas used `from_attributes = True` (v2 syntax). Without `orm_mode = True`, Pydantic v1 silently failed to deserialize ORM objects, causing response validation failures for all rows.

**Fix (v2.3.0):** `schemas.py` now sets **both** `from_attributes = True` (v2) **and** `orm_mode = True` (v1) on all ORM-backed schemas. `requirements.txt` pins `pydantic>=2.0.0` to prevent the v1 regression.

If you still see this after updating, confirm Pydantic v2 is installed:
```bash
python -c "import pydantic; print(pydantic.VERSION)"
```

---

### Swagger UI Authorize → 422 Unprocessable Entity

**Cause:** `/auth/admin/login` was accepting JSON but Swagger sends `application/x-www-form-urlencoded`.

**Fix (v2.3.0):** `/auth/admin/login` now uses `OAuth2PasswordRequestForm = Depends()`.
The original JSON endpoint is preserved at `/auth/admin/login/json`.

---

### CORS errors from Admin UI or Flutter Web

Set `ALLOWED_ORIGINS` to include your admin UI and Flutter Web origins:
```
ALLOWED_ORIGINS=https://your-admin.netlify.app,https://your-app.koyeb.app
```

For local development: `ALLOWED_ORIGINS=*` (never use `*` in production).

---

### Backend starts but Firebase push fails silently

Firebase initialisation is non-fatal — the app starts even without credentials.
Check logs for: `"Firebase credentials not found"`.
Fix: set `FIREBASE_CREDENTIALS_JSON` or ensure `firebase-credentials.json` is accessible.

---

### "dart:io import error" in Flutter Web build

`dart:io` is not available on Flutter Web. All I/O in `api_service.dart` uses `dart:convert`
and `package:http`. Do not import `dart:io` in any file that targets Web.

---

### Teacher sees "Account not yet approved"

The teacher registered (status = `pending`) but an admin has not approved them yet.
Approve via: **Admin UI → Teachers → Pending** or `POST /teachers/{id}/approve`.

---

### Koyeb keeps restarting — OOM or crash

Check `/health` endpoint response time. If the scheduler job is running a heavy query
on startup, set `SCHEDULER_JITTER=60` to spread load. Also ensure only one instance
runs the scheduler (`RUN_SCHEDULER=true` on one, `false` on others).

---

## 16. Changelog

### v2.3.0 (current)
- **Fix:** `POST /teachers/` HTTP 500 — added `email` + `status` columns via Alembic migration `0002`
- **Fix:** List endpoints returning single item — added `orm_mode = True` to all Pydantic schemas for v1 compat; pinned `pydantic>=2.0.0` in `requirements.txt`
- **Fix:** `list[X]` → `List[X]` in all response_model declarations (Python 3.8 compat)
- **Fix:** `order` columns now `NOT NULL` with `server_default='0'` — prevents Pydantic int validation error on legacy NULL rows
- **New:** Alembic migration framework — `alembic/`, `alembic.ini`, `alembic/env.py`, two versioned migrations
- **New:** `migrations/004_production_fix.sql` — idempotent emergency SQL fix
- **New:** `GET /auth/validate` — token validation endpoint
- **New:** `POST /auth/admin/login/json` — JSON login for Admin UI
- **New:** `admin_ui/js/auth.js` — shared `apiFetch()`, `guardPage()`, `logout()`
- **New:** `services/auth_service.py` — JWT create/decode
- **New:** `routers/locations.py`, `routers/shifts.py`, `routers/points.py`, `routers/reports.py`
- **New:** `database.py`, `models/points_models.py`
- **New:** `routers/__init__.py`, `models/__init__.py`, `services/__init__.py`
- **Improved:** All routers log DB errors with `logger.exception()` before re-raising HTTP 500
- **Improved:** `main.py` uses explicit `from routers.X import router as X_router` — no package-style import

### v2.2.0
- iOS PWA push notifications via Firebase Web Push (VAPID)
- `DeviceToken.platform` values: `'android'` | `'web'`
- VAPID environment variables added
- Flutter Web service worker (`firebase-messaging-sw.js`)

### v2.1.0
- Break duty type (`duty_type = 'break'`) — grade/class instead of location
- Duplicate-teacher-per-shift guard in `week_service.py`
- Safe JSON error handling in `api_service.dart`

### v2.0.0
- Teacher self-registration and approval flow
- JWT admin authentication
- Points system with monthly leaderboard
- APScheduler background jobs