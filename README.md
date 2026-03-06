# Firduty — School Duty Roster Management System

> A full-stack duty roster system for schools with bilingual (Arabic/English) support,
> drag-and-drop weekly planning, teacher mobile app, push notifications, and a
> points-based attendance system.
> Deployable locally or in the cloud (Koyeb + Supabase).

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Project Structure](#project-structure)
3. [Technology Stack](#technology-stack)
4. [Database Models](#database-models)
5. [API Reference](#api-reference)
6. [Points System](#points-system)
7. [Notifications](#notifications)
8. [Multi-Language Support](#multi-language-support)
9. [Environment Variables](#environment-variables)
10. [Setup & Installation](#setup--installation)
    - [Local Development](#local-development)
    - [Cloud Deployment — Koyeb + Supabase](#cloud-deployment--koyeb--supabase)
11. [Week Rules](#week-rules)
12. [Security Notes](#security-notes)
13. [Quick Reference](#quick-reference)

---

## System Overview

Firduty consists of three integrated parts:

| Component | Technology | Users |
|---|---|---|
| **Admin Web App** | FastAPI + Vanilla HTML/CSS/JS | School administrators |
| **Teacher Mobile App** | Flutter (Android & iOS) | Teachers |
| **Backend API** | FastAPI + SQLAlchemy + PostgreSQL | Serves both above |

### What it does

- Admin plans weekly duty rosters using a drag-and-drop interface
- Duties are organized by **day → shift → location → slot**
- Teachers receive push notifications 15 minutes before duties and at start time
- Teachers **confirm their presence** via the mobile app and earn points
- Points accumulate monthly and reset automatically each month
- Admin views a monthly leaderboard report with CSV export

---

## Project Structure

```
firduty/
├── README.md
├── pyrightconfig.json                   # Pylance import resolution (VS Code)
│                                        #   extraPaths: backend/ — fixes yellow underlines
│                                        #   include: backend/, jobs/
│
├── .vscode/
│   └── settings.json                    # python.analysis.extraPaths = ["./backend"]
│
├── backend/
│   ├── main.py                          # FastAPI app entry point
│   │                                    #   CORS reads ALLOWED_ORIGINS env var
│   │                                    #   Binds to 0.0.0.0:$PORT
│   │                                    #   GET /health for Koyeb health checks
│   │
│   ├── config.py                        # All settings read from environment variables
│   │                                    #   DATABASE_URL, SECRET_KEY, ALGORITHM
│   │                                    #   ADMIN_USERNAME, ADMIN_PASSWORD
│   │                                    #   FIREBASE_CREDENTIALS_PATH
│   │                                    #   PORT (default 8000)
│   │                                    #   ALLOWED_ORIGINS (default *)
│   │                                    #   TIMEZONE = Asia/Muscat
│   │
│   ├── database.py                      # SQLAlchemy engine + session factory
│   │                                    #   PostgreSQL: sslmode=require (Supabase)
│   │                                    #   pool_pre_ping=True for cloud connections
│   │                                    #   SQLite: local dev fallback (no SSL)
│   │
│   ├── Procfile                         # Koyeb start command:
│   │                                    #   web: uvicorn main:app --host 0.0.0.0 --port $PORT
│   │
│   ├── requirements.txt                 # Python dependencies (no pinned versions)
│   ├── .env.example                     # Environment variable template — copy to .env locally
│   ├── firebase-credentials.json        # ⚠️ Add manually — NEVER commit to git
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── models.py                    # Single source of truth for ALL ORM models:
│   │   │                                #   AppSetting, Teacher, DeviceToken
│   │   │                                #   Location, Shift
│   │   │                                #   WeekPlan, DayPlan, ShiftLocation, Assignment
│   │   │                                #   ChangeLog
│   │   │                                #   DutyConfirmation, MonthlyPointsSummary
│   │   └── points_models.py             # Re-exports only — imports from models.py
│   │                                    #   ⚠️ Do NOT redefine classes here
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py                   # Pydantic v2 request/response schemas
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                      # POST /auth/admin/login → JWT
│   │   ├── teachers.py                  # CRUD + schedule endpoint
│   │   │                                #   Returns assignment_id + already_confirmed
│   │   ├── locations.py                 # CRUD /locations (name_en + name_ar)
│   │   ├── shifts.py                    # CRUD /shifts (name_en + name_ar)
│   │   ├── weeks.py                     # Week planning:
│   │   │                                #   create, clone, publish, assignments, slots
│   │   ├── points.py                    # POST /points/teachers/{id}/confirm
│   │   │                                # GET  /points/teachers/{id}/monthly
│   │   └── reports.py                   # GET  /admin/reports/monthly-points
│   │                                    # GET  /admin/reports/monthly-points/{id}
│   │                                    # GET  /admin/reports/monthly-points/export/csv
│   │                                    # POST /admin/reports/monthly-points/rebuild
│   │
│   └── services/
│       ├── __init__.py
│       ├── auth_service.py              # JWT create/decode, bcrypt password hashing
│       ├── notification_service.py      # FCM multicast, bilingual templates (AR/EN)
│       ├── week_service.py              # Week create/clone/publish, slot + assignment logic
│       │                                #   Enforces no double-booking per shift per day
│       └── points_service.py            # calculate_points() — Asia/Muscat timezone scoring
│                                        # confirm_duty() — validate + record + cache update
│                                        # get_monthly_report() — leaderboard query
│                                        # rebuild_monthly_summary_for_all() — cron target
│
├── admin_ui/
│   ├── login.html                       # Admin login page (EN/AR)
│   ├── planner.html                     # Week planner — drag & drop assignments
│   ├── reports.html                     # Monthly points leaderboard + per-teacher drill-down
│   │                                    #   Summary cards, progress bars, CSV export
│   │
│   ├── css/
│   │   └── style.css                    # Full shared stylesheet
│   │                                    #   RTL + LTR, slots, tabs, modals, toasts
│   │
│   ├── js/
│   │   ├── i18n.js                      # i18n module: load(), t(), toggle()
│   │   │                                #   Sets dir="rtl" on <html> for Arabic
│   │   ├── login.js                     # Login form + JWT storage
│   │   └── planner.js                   # Full planner logic:
│   │                                    #   week load, day/shift tabs, SortableJS D&D
│   │                                    #   slot +/-, save draft, publish, clone
│   │
│   └── i18n/
│       ├── en.json                      # English UI strings (planner + reports)
│       └── ar.json                      # Arabic UI strings (planner + reports)
│
├── jobs/
│   ├── auto_clone.py                    # Weekly auto-clone cron script
│   │                                    #   Runs: Thursday 16:00 Muscat (12:00 UTC)
│   │                                    #   Finds latest published week
│   │                                    #   Clones → next week as Draft
│   │                                    #   Skips if target week already exists
│   │                                    #   Cron: 0 12 * * 4 python3 auto_clone.py
│   │
│   └── monthly_reset.py                 # Monthly points cache rebuild script
│                                        #   Runs: 1st of month 00:05 Muscat (20:05 UTC)
│                                        #   Finalizes previous month summary
│                                        #   Seeds new month for all teachers
│                                        #   Cron: 5 20 1 * * python3 monthly_reset.py
│
└── flutter_app/
    ├── pubspec.yaml                     # Dependencies + flutter generate: true (l10n)
    │
    └── lib/
        ├── main.dart                    # App entry point
        │                               #   Firebase.initializeApp()
        │                               #   Locale init (device → AR fallback)
        │                               #   3-tab HomeScreen: Today / Week / Points
        │
        ├── gen/                         # ⚙️ AUTO-GENERATED — run: flutter gen-l10n
        │   └── app_localizations.dart   #    DO NOT edit manually
        │
        ├── l10n/
        │   ├── app_en.arb               # English strings incl. pointsHint, confirmPresence
        │   └── app_ar.arb               # Arabic strings incl. pointsHint, confirmPresence
        │
        ├── screens/
        │   ├── teacher_select_screen.dart   # First-launch: dropdown + save teacher_id
        │   ├── today_screen.dart            # Today's duties
        │   │                               #   Confirm Presence button per duty card
        │   │                               #   Points hint (on time/late/missed rules)
        │   │                               #   Result dialog: emoji + points badge
        │   ├── week_screen.dart             # Full week duties grouped by date
        │   │                               #   Confirmed status shown per duty
        │   └── points_screen.dart           # Monthly points screen
        │                                   #   Month navigator, circular points counter
        │                                   #   On Time / Late / Missed stat chips
        │                                   #   Per-duty confirmation history list
        │
        └── services/
            ├── api_service.dart             # All HTTP calls:
            │                               #   getTeachers, getTeacherSchedule
            │                               #   getTeacherWeek, confirmDuty
            │                               #   getTeacherPoints, registerDeviceToken
            └── notification_service.dart    # FCM init, permission request
                                            # Local notification display (foreground)
                                            # Token registration + refresh handler
```

---

## Technology Stack

### Backend
| Package | Purpose |
|---|---|
| FastAPI | REST API framework |
| SQLAlchemy | ORM |
| PostgreSQL | Production database (Supabase) |
| SQLite | Local testing fallback |
| psycopg2-binary | PostgreSQL driver (SSL support) |
| python-jose[cryptography] | JWT tokens |
| passlib[bcrypt] | Password hashing |
| firebase-admin | Push notifications (FCM) |
| pytz | Timezone handling (Asia/Muscat) |
| pydantic[email] | Request/response validation |
| python-dotenv | Load .env for local dev |

### Admin UI
| Tool | Purpose |
|---|---|
| Vanilla HTML/CSS/JS | No framework dependency |
| SortableJS | Drag-and-drop assignment |
| Fetch API | REST calls with JWT |
| localStorage | Token + language preference |

### Flutter App
| Package | Purpose |
|---|---|
| http | REST API calls |
| firebase_messaging | Push notifications |
| flutter_local_notifications | Foreground notification display |
| shared_preferences | teacher_id + language storage |
| flutter_localizations + intl | AR/EN with automatic RTL |

### Cloud Infrastructure
| Service | Role |
|---|---|
| **Koyeb** | Backend hosting — auto-detects Procfile |
| **Supabase** | Managed PostgreSQL with SSL |

---

## Database Models

```
AppSetting            key/value store for admin configuration

Teacher               id, name, active, preferred_language('ar'|'en'), created_at
DeviceToken           id, teacher_id, token, platform('android'|'ios'), updated_at

Location              id, name_en, name_ar, order
Shift                 id, name_en, name_ar, start_time, end_time, order

WeekPlan              id, week_start_date(Sunday), status('draft'|'published'),
                      version, cloned_from_week_start, created_at, updated_at
DayPlan               id, week_plan_id, date
ShiftLocation         id, day_plan_id, shift_id, location_id, slots_count, order
Assignment            id, shift_location_id, slot_index, teacher_id(nullable)

ChangeLog             id, week_plan_id, actor, action, payload_json, created_at

DutyConfirmation      id, teacher_id, assignment_id, confirmed_at(UTC), points_earned(0|1|2)
                      UNIQUE(teacher_id, assignment_id)
                      INDEX(teacher_id, confirmed_at)

MonthlyPointsSummary  id, teacher_id, year, month, total_points, updated_at
                      UNIQUE(teacher_id, year, month)
                      INDEX(year, month)
```

Tables are created automatically on startup via `Base.metadata.create_all()`.

---

## API Reference

| Environment | Docs URL |
|---|---|
| Local | `http://localhost:8000/docs` |
| Production | `https://your-app.koyeb.app/docs` |

### Authentication
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/admin/login` | — | Returns JWT |

### Master Data
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/teachers/` | — | List active teachers |
| GET | `/teachers/all` | JWT | List all teachers |
| POST | `/teachers/` | JWT | Create teacher |
| PUT | `/teachers/{id}` | JWT | Update teacher |
| DELETE | `/teachers/{id}` | JWT | Deactivate teacher |
| GET/POST/PUT/DELETE | `/locations/` | JWT | Location CRUD |
| GET/POST/PUT/DELETE | `/shifts/` | JWT | Shift CRUD |

### Week Planning
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/weeks/current` | — | Current week plan |
| GET | `/weeks/{week_start}` | — | Specific week |
| POST | `/weeks/{week_start}/create` | JWT | Create empty draft |
| POST | `/weeks/{week_start}/clone` | JWT | Clone from published |
| PUT | `/weeks/{week_start}/status` | JWT | Publish week |
| PUT | `/weeks/{week_start}/shift-locations` | JWT | Update slot counts |
| PUT | `/weeks/{week_start}/assignments` | JWT | Assign teachers |

### Teacher App
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/teachers/{id}/schedule?date=` | — | Daily duties + confirmation status |
| GET | `/teachers/{id}/week?week_start=` | — | Weekly duties |
| POST | `/teachers/{id}/device-token` | — | Register FCM token |

### Points
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/points/teachers/{id}/confirm` | — | Confirm presence → earn points |
| GET | `/points/teachers/{id}/monthly?year=&month=` | — | Monthly total + history |

### Reports
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/reports/monthly-points?year=&month=` | JWT | Full leaderboard |
| GET | `/admin/reports/monthly-points/{id}?year=&month=` | JWT | Per-teacher detail |
| GET | `/admin/reports/monthly-points/export/csv?year=&month=` | JWT | Download CSV |
| POST | `/admin/reports/monthly-points/rebuild?year=&month=` | JWT | Rebuild cache |

### System
| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Health check (Koyeb) |

---

## Points System

### Scoring Rules

All times compared in **Asia/Muscat (UTC+4)** timezone.

| Confirmation time vs shift start | Points |
|---|---|
| At or before shift start | **2 points** ✅ |
| 1 – 5 minutes after start | **1 point** ⏱ |
| More than 5 minutes after start | **0 points** ❌ |

### Business Rules
- One confirmation per assignment per teacher — duplicates rejected (HTTP 400)
- Only **published** weeks are confirmable — draft weeks earn no points
- Points accumulate per calendar month in **Asia/Muscat** timezone
- Monthly totals reset automatically on the **1st of each month** via cron
- Historical data is preserved — any past month remains queryable

### Teacher Flow (Mobile App)
1. Open app → **Today** tab
2. Each duty card shows shift start time + points rules hint
3. Tap **Confirm Presence**
4. Result dialog shows: emoji + bilingual message + colored points badge
5. Button changes to **Confirmed ✓** (green) — locked, cannot confirm again

### Admin Report
Navigate to `reports.html` from the planner header:
- 4 summary cards: teachers / confirmations / total points / average
- Ranked leaderboard with progress bars
- Color pills: 🟢 On Time · 🟡 Late · ⚫ No Points
- Drill-down modal per teacher showing every confirmation with time
- CSV export (UTF-8 BOM for Excel Arabic compatibility)

---

## Notifications

| Trigger | Arabic | English |
|---|---|---|
| 15 min before | `تذكير: مناوبتك بعد 15 دقيقة — المكان: {location} — الفترة: {shift}` | `Reminder: Your duty starts in 15 minutes — Location: {location} — Shift: {shift}` |
| Duty start | `بدأت مناوبتك الآن — المكان: {location}` | `Your duty has started — Location: {location}` |
| Week modified | `تم تعديل مناوبتك للأسبوع — راجع التطبيق` | `Your duty schedule has been updated — Please check the app` |

- Titles: `المناوبات` (AR) / `Duty Roster` (EN)
- Draft weeks → no notifications
- Modified published weeks → only affected teachers notified

---

## Multi-Language Support

| Code | Language | Direction |
|---|---|---|
| `ar` | Arabic | RTL |
| `en` | English | LTR |

- **Admin UI** — Toggle `عربي | EN` in header. Persisted in `localStorage`. Arabic sets `dir="rtl"` on `<html>`.
- **Flutter App** — Follows device locale, falls back to Arabic. Manual toggle in header. Stored in `SharedPreferences`.
- **Notifications** — Sent in teacher's `preferred_language` from DB.
- **Locations & Shifts** — Both `name_en` and `name_ar` stored; frontend picks based on active language.

---

## Environment Variables

### `.env` (local development only)

```env
# Database — SQLite requires no setup
DATABASE_URL=sqlite:///./firduty.db

# Or use Supabase locally:
# DATABASE_URL=postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres

SECRET_KEY=any-local-dev-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json

PORT=8000
ALLOWED_ORIGINS=*
```

### Koyeb Environment Variables (production)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Supabase PostgreSQL connection string |
| `SECRET_KEY` | ✅ | Random 32-char hex string |
| `ADMIN_USERNAME` | ✅ | Admin login username |
| `ADMIN_PASSWORD` | ✅ | Admin login password |
| `ALLOWED_ORIGINS` | ⚠️ | Comma-separated allowed origins |
| `PORT` | ❌ | Injected automatically by Koyeb |
| `FIREBASE_CREDENTIALS_PATH` | ❌ | Only if using push notifications |

---

## Setup & Installation

### Local Development

#### 1. Backend

```bash
cd backend

# Install all dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# The default .env uses SQLite — no database setup needed for local dev

# Create tables (run once)
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# or: python main.py

# Docs: http://localhost:8000/docs
```

#### 2. Admin UI

```bash
cd admin_ui
python -m http.server 3000
# Open: http://localhost:3000/login.html
# Login: admin / admin123
```

Admin pages:
| URL | Page |
|---|---|
| `login.html` | Login |
| `planner.html` | Week planner (drag & drop) |
| `reports.html` | Monthly points leaderboard |

#### 3. Flutter App

```bash
cd flutter_app
flutter pub get
flutter gen-l10n          # Must run once — generates lib/gen/app_localizations.dart

# Set API URL in lib/services/api_service.dart:
# static const String baseUrl = 'http://localhost:8000';

flutter run
```

#### 4. Cron Jobs (manual test)

```bash
python jobs/auto_clone.py
python jobs/monthly_reset.py
```

---

### Cloud Deployment — Koyeb + Supabase

#### Step 1 — Supabase Database

1. Create project at [supabase.com](https://supabase.com)
2. Go to **Project Settings → Database → Connection string → URI**
3. Copy the connection string:
   ```
   postgresql://postgres:PASSWORD@db.YOURPROJECT.supabase.co:5432/postgres
   ```
4. Tables are created automatically on first backend startup — no manual migration needed

#### Step 2 — Deploy Backend on Koyeb

1. Go to [koyeb.com](https://koyeb.com) → **New service → GitHub**
2. Select your repository, set **root directory** to `backend/`
3. Koyeb auto-detects the `Procfile`:
   ```
   web: uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
4. Add environment variables:
   ```
   DATABASE_URL     = postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres
   SECRET_KEY       = <run: python -c "import secrets; print(secrets.token_hex(32))">
   ADMIN_USERNAME   = admin
   ADMIN_PASSWORD   = your-secure-password
   ALLOWED_ORIGINS  = https://your-admin-domain.com
   ```
5. Set **health check path** to `/health`
6. Deploy

#### Step 3 — Update API URL

**Admin UI** (`admin_ui/js/login.js` and `planner.js`):
```javascript
const API = localStorage.getItem('firduty_api') || 'https://your-app.koyeb.app';
```

**Flutter App** (`lib/services/api_service.dart`):
```dart
static const String baseUrl = 'https://your-app.koyeb.app';
```

#### Step 4 — Cron Jobs on Koyeb

Add two scheduled jobs in Koyeb dashboard:

| Job | Command | Schedule |
|---|---|---|
| Auto-clone | `python jobs/auto_clone.py` | `0 12 * * 4` |
| Monthly reset | `python jobs/monthly_reset.py` | `5 20 1 * *` |

#### Step 5 — Firebase (Push Notifications)

1. Upload `firebase-credentials.json` to your Koyeb service or use a secrets volume
2. Set `FIREBASE_CREDENTIALS_PATH` to the file path
3. If absent, the backend starts normally — push notifications silently disabled

---

## Week Rules

| Rule | Value |
|---|---|
| Week start | Sunday |
| Working days | Sunday – Thursday |
| Timezone | Asia/Muscat (UTC+4) |
| Draft | Editable, no notifications |
| Published | Notifications active |

---

## Security Notes

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

| Checklist | Detail |
|---|---|
| ✅ Change `SECRET_KEY` | Never use the default in production |
| ✅ Change `ADMIN_PASSWORD` | Never use `admin123` in production |
| ✅ Restrict `ALLOWED_ORIGINS` | Set to your actual admin domain |
| ✅ HTTPS | Koyeb provides HTTPS on `*.koyeb.app` automatically |
| ✅ `.gitignore` | Add `.env` and `firebase-credentials.json` |
| ✅ DB backups | Enable automatic backups in Supabase dashboard |

---

## Quick Reference

```bash
# ── Local ─────────────────────────────────────────────────────────────────────
cd backend && uvicorn main:app --reload --port 8000
cd admin_ui && python -m http.server 3000
cd flutter_app && flutter run
cd flutter_app && flutter gen-l10n

# Create tables
cd backend && python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# Test cron jobs
python jobs/auto_clone.py
python jobs/monthly_reset.py

# ── Production ────────────────────────────────────────────────────────────────
# Koyeb start command (Procfile)
uvicorn main:app --host 0.0.0.0 --port $PORT

# Health check
curl https://your-app.koyeb.app/health

# API docs
open https://your-app.koyeb.app/docs
```