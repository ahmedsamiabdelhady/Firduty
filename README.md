# Firduty — School Duty Roster Management System

> Bilingual (Arabic / English) school duty roster — drag-and-drop weekly
> planning, Flutter mobile app for teachers, Firebase push notifications,
> a points-based attendance system, and an admin analytics dashboard.
>
> **Version 2.1.0** · Backend: FastAPI · Database: Supabase (PostgreSQL) ·
> Hosting: Koyeb · Notifications: Firebase FCM · App: Flutter 3.x

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Prerequisites](#4-prerequisites)
5. [Step 1 — Supabase (Database)](#5-step-1--supabase-database)
6. [Step 2 — Firebase (Push Notifications)](#6-step-2--firebase-push-notifications)
7. [Step 3 — Backend on Koyeb](#7-step-3--backend-on-koyeb)
8. [Step 4 — Admin Web UI](#8-step-4--admin-web-ui)
9. [Step 5 — Flutter Mobile App](#9-step-5--flutter-mobile-app)
10. [Step 6 — Keep-Alive (Free Tier)](#10-step-6--keep-alive-free-tier)
11. [Environment Variables Reference](#11-environment-variables-reference)
12. [Database Models](#12-database-models)
13. [API Reference](#13-api-reference)
14. [Duty Types](#14-duty-types)
15. [Points System](#15-points-system)
16. [Background Jobs](#16-background-jobs)
17. [Notifications](#17-notifications)
18. [Local Development](#18-local-development)
19. [Migrations (Existing Database)](#19-migrations-existing-database)
20. [Security Checklist](#20-security-checklist)
21. [Troubleshooting](#21-troubleshooting)
22. [Quick Reference](#22-quick-reference)

---

## 1. System Overview

Firduty has three integrated parts that work together:

| Part | Technology | Who uses it |
|---|---|---|
| **Backend API** | FastAPI + SQLAlchemy + PostgreSQL | Everything routes through here |
| **Admin Web App** | Vanilla HTML / CSS / JS | School administrators |
| **Teacher Mobile App** | Flutter (Android & iOS) | Teachers |

### Core features

- Admin plans weekly duty rosters via a drag-and-drop web planner
- Duties are structured as **Week → Day → Shift → Slot** (up to N teachers per slot)
- Two duty types per shift: **Morning/End-of-day** (shows a location) and **Break** (shows a grade/class)
- Teachers receive Firebase push notifications 15 minutes before duties and at start time
- Teachers confirm presence in the app and earn 0, 1, or 2 points based on punctuality
- Monthly points reset automatically on the 1st of each month
- Admin dashboard shows live stats, per-teacher distribution warnings, and fairness overview
- Fully bilingual — all teacher-facing content in Arabic and English

---

## 2. Tech Stack

### Backend (`backend/`)

| Package | Purpose |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn[standard]` | ASGI server |
| `SQLAlchemy` | ORM |
| `psycopg2-binary` | PostgreSQL driver with SSL support |
| `python-jose[cryptography]` | JWT token creation and validation |
| `passlib[bcrypt]` | Password hashing |
| `python-multipart` | Form data parsing |
| `pydantic[email]` | Request / response validation |
| `firebase-admin` | Firebase Cloud Messaging (push notifications) |
| `pytz` | Timezone handling (`Asia/Muscat`, UTC+4) |
| `apscheduler` | In-process background job scheduler |
| `python-dotenv` | `.env` file loader for local development |
| `aiofiles` | Async file I/O utilities |

### Admin UI (`admin_ui/`)

| Tool | Purpose |
|---|---|
| Vanilla HTML / CSS / JS | No framework dependency — works from any static host |
| SortableJS (CDN) | Drag-and-drop teacher assignment in the planner |

### Flutter App (`flutter_app/`)

| Package | Version | Purpose |
|---|---|---|
| `flutter_localizations` | SDK | Material / Cupertino locale delegates |
| `http` | `^1.2.1` | REST API calls |
| `shared_preferences` | `^2.2.3` | Teacher ID and language preference storage |
| `firebase_core` | `^2.30.1` | Firebase SDK initialisation |
| `firebase_messaging` | `^14.9.4` | FCM push notifications |
| `flutter_local_notifications` | `^17.2.2` | Foreground notification display |
| `intl` | `^0.19.0` | `DateFormat` and locale utilities |

### Cloud Services

| Service | Role | Free tier |
|---|---|---|
| **Supabase** | Managed PostgreSQL with SSL, automatic backups | 500 MB storage, 2 projects |
| **Koyeb** | Backend hosting — auto-detects `Procfile` | 1 web service, sleeps after inactivity |
| **Firebase** | FCM push notifications | Spark plan — unlimited notifications |
| **GitHub Pages / Netlify** | Admin UI static hosting | Free |
| **GitHub Actions** | Keep-alive ping every 5 min | 2 000 minutes/month free |

---

## 3. Project Structure

```
firduty/
│
├── README.md                          ← this file
├── pyrightconfig.json                 ← Python type-checker config (0 errors)
├── .gitignore                         ← excludes .env, firebase-credentials.json, etc.
│
├── .github/
│   └── workflows/
│       └── keepalive.yml              ← pings /health every 5 min (prevents Koyeb sleep)
│
├── migrations/
│   └── 001_duty_types.sql             ← idempotent PostgreSQL upgrade migration
│
├── backend/
│   ├── Procfile                       ← Koyeb start command
│   ├── requirements.txt               ← Python dependencies (no pinned versions)
│   ├── .env.example                   ← copy to .env for local dev
│   ├── firebase-credentials.json      ← ⚠ add manually, never commit (see .gitignore)
│   │
│   ├── main.py                        ← FastAPI app + Firebase credential bootstrap
│   ├── config.py                      ← reads all env vars via Settings class
│   ├── database.py                    ← SQLAlchemy engine (SSL for PG, no-SSL for SQLite)
│   ├── scheduler.py                   ← APScheduler jobs + GET /scheduler/status
│   │
│   ├── models/
│   │   ├── models.py                  ← all ORM models (Shift.duty_type, Assignment.grade_class)
│   │   └── points_models.py           ← re-exports from models.py (compatibility shim)
│   │
│   ├── schemas/
│   │   └── schemas.py                 ← Pydantic v2 schemas
│   │
│   ├── routers/
│   │   ├── auth.py                    ← POST /auth/admin/login
│   │   ├── teachers.py                ← teacher CRUD + schedule (duty_type / grade_class aware)
│   │   ├── locations.py               ← location CRUD
│   │   ├── shifts.py                  ← shift CRUD (includes duty_type field)
│   │   ├── weeks.py                   ← week planning + assignment (grade_class support)
│   │   ├── points.py                  ← confirm presence + monthly summary
│   │   ├── reports.py                 ← monthly leaderboard CSV/JSON
│   │   └── dashboard.py               ← GET /admin/dashboard stats
│   │
│   ├── services/
│   │   ├── auth_service.py            ← JWT create / decode
│   │   ├── notification_service.py    ← FCM multicast; duty-type-aware templates
│   │   ├── week_service.py            ← week create / clone / publish (grade_class preserved)
│   │   └── points_service.py         ← confirmation scoring + detail builder
│   │
│   └── jobs/
│       ├── auto_clone.py              ← called by scheduler Thursday 16:00
│       └── monthly_reset.py           ← called by scheduler 1st of month 20:05
│
├── admin_ui/
│   ├── login.html                     ← admin login page
│   ├── dashboard.html                 ← stat cards, bar chart, distribution warnings
│   ├── planner.html                   ← week drag-and-drop planner
│   ├── reports.html                   ← monthly points leaderboard
│   │
│   ├── css/
│   │   └── style.css
│   │
│   ├── js/
│   │   ├── i18n.js                    ← AR/EN runtime switching
│   │   ├── login.js
│   │   ├── dashboard.js
│   │   └── planner.js                 ← break duty grade/class inline inputs
│   │
│   └── i18n/
│       ├── en.json                    ← English strings (includes duty type labels)
│       └── ar.json                    ← Arabic strings
│
└── flutter_app/
    ├── pubspec.yaml                   ← all dependencies declared
    ├── l10n.yaml                      ← localisation gen config (arb-dir, output-dir)
    │
    ├── lib/
    │   ├── main.dart                  ← Firebase init, locale detection, route table
    │   │
    │   ├── l10n/                      ← source ARB files (edit these)
    │   │   ├── app_en.arb
    │   │   └── app_ar.arb
    │   │
    │   ├── gen/                       ← auto-generated by flutter gen-l10n (do not edit)
    │   │   └── app_localizations.dart
    │   │
    │   ├── screens/
    │   │   ├── teacher_select_screen.dart
    │   │   ├── today_screen.dart      ← duty_type aware: shows location OR grade/class
    │   │   ├── week_screen.dart       ← duty_type aware: correct icon + label per type
    │   │   └── points_screen.dart     ← duty_type aware in confirmation history rows
    │   │
    │   └── services/
    │       ├── api_service.dart       ← all HTTP calls (update baseUrl before build)
    │       └── notification_service.dart ← FCM + local notifications
    │
    └── test/
        └── widget_test.dart           ← minimal smoke test (Firebase-safe)
```

---

## 4. Prerequisites

### On your machine

| Tool | Minimum version | Install |
|---|---|---|
| Python | 3.12 | [python.org](https://www.python.org/downloads/) |
| Flutter SDK | 3.0 | [flutter.dev/get-started](https://docs.flutter.dev/get-started/install) |
| Git | any | [git-scm.com](https://git-scm.com) |

Verify Flutter is ready:
```bash
flutter doctor
# All items should show ✅ or ⚠ (warnings OK, errors need fixing)
```

### Accounts you need (all free)

| Service | URL |
|---|---|
| Supabase | [supabase.com](https://supabase.com) |
| Firebase | [console.firebase.google.com](https://console.firebase.google.com) |
| Koyeb | [koyeb.com](https://koyeb.com) |
| GitHub | [github.com](https://github.com) |

---

## 5. Step 1 — Supabase (Database)

### 5.1 Create a project

1. Sign in at [supabase.com](https://supabase.com) → **New project**.
2. Set a name (`firduty`), choose a strong **database password**, pick the region nearest your school.
3. Click **Create new project** — provisioning takes about 60 seconds.

### 5.2 Get the connection string

1. **Project Settings** (gear icon) → **Database** → **Connection string** → **URI** tab.
2. Copy the URI — it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```
3. Replace `[YOUR-PASSWORD]` with the password from step 5.1.
4. Save it — this becomes the `DATABASE_URL` environment variable.

### 5.3 Tables

All database tables are created **automatically** when the backend starts for the first time via `Base.metadata.create_all()`. You do not need to run any SQL manually for a fresh install.

> Upgrading an existing database? See [Section 19 — Migrations](#19-migrations-existing-database).

### 5.4 SSL

Supabase requires SSL for all connections. The `database.py` engine is already configured with `connect_args={"sslmode": "require"}` for all PostgreSQL URLs. No extra setup needed.

---

## 6. Step 2 — Firebase (Push Notifications)

> This step is optional. If you skip it, the backend starts normally and all features work except push notifications.

### 6.1 Create a Firebase project

1. Go to [console.firebase.google.com](https://console.firebase.google.com) → **Add project**.
2. Name it `firduty`, follow the wizard, and disable Google Analytics if not needed.

### 6.2 Register the Android app

1. Click the **Android icon** on the project overview.
2. **Android package name**: `com.yourschool.firduty`
   (must match `applicationId` in `flutter_app/android/app/build.gradle`).
3. Click **Register app** → download `google-services.json`.
4. Place the file at: `flutter_app/android/app/google-services.json`

### 6.3 Register the iOS app (optional)

1. Click the **iOS icon** on the project overview.
2. **Bundle ID**: `com.yourschool.firduty` (must match your Xcode bundle ID).
3. Click **Register app** → download `GoogleService-Info.plist`.
4. Place the file at: `flutter_app/ios/Runner/GoogleService-Info.plist`

> ⚠️ These files contain your Firebase project ID and API keys. They are safe to commit to a private repository, but should not be published publicly.

### 6.4 Generate the server private key (for the backend)

1. **Project settings** (gear) → **Service accounts** tab.
2. Click **Generate new private key** → confirm → a JSON file downloads.
3. Rename it `firebase-credentials.json`.
4. **Do not commit it.** It is in `.gitignore` by default.
5. You will supply it to Koyeb in Step 7.5.

---

## 7. Step 3 — Backend on Koyeb

### 7.1 Push your code to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR-USERNAME/firduty.git
git push -u origin main
```

Ensure `.gitignore` prevents committing secrets:
```
backend/.env
backend/firebase-credentials.json
firebase-creds-*.json
```

### 7.2 Create a Koyeb account

Sign up at [koyeb.com](https://koyeb.com) and connect your GitHub account when prompted.

### 7.3 Create a new Koyeb web service

1. **Create service** → **Web service** → **GitHub**.
2. Select your `firduty` repository.
3. Set **Branch** → `main`.
4. Set **Root directory** → `backend`.

Koyeb auto-detects the `Procfile`:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 7.4 Set environment variables in Koyeb

In the **Environment variables** section, add each variable:

| Variable | Example value | Required |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres` | ✅ |
| `SECRET_KEY` | output of `python -c "import secrets; print(secrets.token_hex(32))"` | ✅ |
| `ADMIN_USERNAME` | `admin` | ✅ |
| `ADMIN_PASSWORD` | your chosen password | ✅ |
| `ALLOWED_ORIGINS` | `https://your-admin-ui-domain.com` | ⚠️ set before go-live |
| `FIREBASE_CREDENTIALS_JSON` | entire contents of `firebase-credentials.json` | ❌ optional |
| `FIREBASE_CREDENTIALS_PATH` | `./firebase-credentials.json` | ❌ if using file option |
| `RUN_SCHEDULER` | `true` | ❌ default is `true` |
| `SCHEDULER_JITTER` | `30` | ❌ default is `30` |
| `ALGORITHM` | `HS256` | ❌ default |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | ❌ default (24 hours) |

Generate a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 7.5 Supply Firebase credentials to Koyeb

You have two options since you cannot commit `firebase-credentials.json` to Git:

**Option A — Inline env var (recommended for the free tier)**

1. Open `firebase-credentials.json` in a text editor and copy the entire JSON content.
2. Add it as the environment variable `FIREBASE_CREDENTIALS_JSON` in Koyeb.
3. The backend `main.py` detects this variable at startup, validates the JSON, writes it to a temp file, and sets `FIREBASE_CREDENTIALS_PATH` automatically before `firebase-admin` initialises.

**Option B — Koyeb Secrets volume**

1. In Koyeb → **Secrets** → create a secret of type **File**.
2. Paste the `firebase-credentials.json` contents.
3. Mount at `/app/firebase-credentials.json`.
4. Set `FIREBASE_CREDENTIALS_PATH=/app/firebase-credentials.json`.

### 7.6 Configure the health check

In your Koyeb service settings set **Health check path** to `/health`.  
This endpoint returns `{"status": "ok"}` and Koyeb uses it to verify liveness.

### 7.7 Deploy

Click **Deploy**. The first deploy takes 2–3 minutes. When the status turns green:

```
✅  https://YOUR-APP-NAME.koyeb.app
```

### 7.8 Verify the deployment

```bash
# Liveness
curl https://YOUR-APP-NAME.koyeb.app/health
# → {"status":"ok"}

# Service info
curl https://YOUR-APP-NAME.koyeb.app/
# → {"service":"Firduty API","version":"2.1.0","status":"running"}

# Swagger UI
open https://YOUR-APP-NAME.koyeb.app/docs

# Scheduler jobs and next run times
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
```

### 7.9 Verify database tables

```bash
curl https://YOUR-APP-NAME.koyeb.app/teachers/
# → [] (empty array = success: DB connected, tables created)
```

---

## 8. Step 4 — Admin Web UI

The admin UI is a set of static files. No build step required.

### 8.1 Update the API base URL

In `admin_ui/js/planner.js` and `admin_ui/js/dashboard.js` find the line:
```javascript
const API_BASE = localStorage.getItem('firduty_api') || 'https://YOUR-OLD-URL.koyeb.app/';
```
Replace the fallback URL with your Koyeb deployment URL.

Do the same in `admin_ui/js/login.js` if it contains a hardcoded URL.

### 8.2 Deploy to GitHub Pages (free)

1. **Settings** → **Pages** → **Source**: Deploy from a branch.
2. **Branch**: `main`, **Folder**: `/admin_ui` → **Save**.

Available at: `https://YOUR-USERNAME.github.io/firduty/`

### 8.3 Deploy to Netlify (alternative)

1. [netlify.com](https://netlify.com) → **Add new site** → **Import from Git**.
2. **Base directory**: `admin_ui` | **Publish directory**: `admin_ui` | no build command.
3. Click **Deploy site**.

### 8.4 Set up master data (first time only)

Use the API docs at `https://YOUR-APP-NAME.koyeb.app/docs` to seed the required data.

**Add teachers** — `POST /teachers/`
```json
{ "name": "Ahmed Al-Rashidi", "preferred_language": "ar" }
```

**Add locations** (for morning/end-of-day shifts) — `POST /locations/`
```json
{ "name_en": "Main Gate", "name_ar": "البوابة الرئيسية", "order": 1 }
```

**Add shifts** — `POST /shifts/`
```json
{ "name_en": "Morning Duty",   "name_ar": "مناوبة الصباح",
  "start_time": "07:00", "end_time": "07:30",
  "duty_type": "morning_endofday", "order": 1 }

{ "name_en": "Break 1",        "name_ar": "الاستراحة الأولى",
  "start_time": "09:45", "end_time": "10:00",
  "duty_type": "break", "order": 2 }

{ "name_en": "Break 2",        "name_ar": "الاستراحة الثانية",
  "start_time": "11:30", "end_time": "11:45",
  "duty_type": "break", "order": 3 }

{ "name_en": "End-of-Day Duty", "name_ar": "مناوبة النهاية",
  "start_time": "13:30", "end_time": "14:00",
  "duty_type": "morning_endofday", "order": 4 }
```

---

## 9. Step 5 — Flutter Mobile App

### 9.1 Install Flutter

Follow the guide for your OS: [docs.flutter.dev/get-started/install](https://docs.flutter.dev/get-started/install)

```bash
flutter doctor   # verify: no errors
```

### 9.2 Set the backend URL

Open `flutter_app/lib/services/api_service.dart` and update `baseUrl`:

```dart
static const String baseUrl = 'https://YOUR-APP-NAME.koyeb.app';
```

### 9.3 Place Firebase configuration files

These files must be added manually (they are excluded from Git by `.gitignore`).

**Android** — download from Firebase Console → Project settings → Your apps → Android:
```
flutter_app/android/app/google-services.json
```

**iOS** — download from Firebase Console → Project settings → Your apps → iOS:
```
flutter_app/ios/Runner/GoogleService-Info.plist
```

### 9.4 Configure Android build files

`flutter_app/android/build.gradle` — confirm this is present in `dependencies {}`:
```gradle
classpath 'com.google.gms:google-services:4.4.1'
```

`flutter_app/android/app/build.gradle` — confirm at the bottom:
```gradle
apply plugin: 'com.google.gms.google-services'
```

Also confirm `applicationId` matches what you registered in Firebase:
```gradle
android {
    defaultConfig {
        applicationId "com.yourschool.firduty"
        minSdkVersion 21
        targetSdkVersion 34
    }
}
```

### 9.5 Install packages and generate localisations

```bash
cd flutter_app

# Install all pub packages
flutter pub get

# Generate AppLocalizations from ARB files
# (also happens automatically on next build because generate: true is set in pubspec.yaml)
flutter gen-l10n
```

The generated file `lib/gen/app_localizations.dart` is what all screens import.
Never edit it manually — it is always recreated from `lib/l10n/app_en.arb` and `lib/l10n/app_ar.arb`.

### 9.6 Analyse before building

```bash
flutter analyze
# Should report 0 errors
```

### 9.7 Run on a device or emulator

```bash
flutter devices          # list available devices
flutter run -d <id>      # run on a specific device
```

### 9.8 Build a release APK (Android)

```bash
flutter build apk --release
# Output: flutter_app/build/app/outputs/flutter-apk/app-release.apk
```

### 9.9 Build for iOS (macOS required)

```bash
flutter build ios --release
```
Then open `flutter_app/ios/Runner.xcworkspace` in Xcode → Product → Archive → distribute via TestFlight.

### 9.10 First launch

1. Teacher opens the app → selects their name from the list.
2. Allows notification permissions when prompted.
3. The app registers the FCM token with the backend automatically.
4. **Today** tab shows today's duties if a week plan has been published by the admin.

### 9.11 Localisation: adding new strings

1. Add the key to both `lib/l10n/app_en.arb` and `lib/l10n/app_ar.arb`.
2. Run `flutter gen-l10n` (or just `flutter pub get`).
3. Use the new key as `AppLocalizations.of(context)!.yourKey`.

---

## 10. Step 6 — Keep-Alive (Free Tier)

On Koyeb's free tier the service sleeps after inactivity. The `.github/workflows/keepalive.yml` workflow pings `/health` every 5 minutes to prevent this.

### 10.1 Update the URL

Edit `.github/workflows/keepalive.yml`:
```yaml
- name: Ping health endpoint
  run: |
    curl -L --max-time 30 --fail https://YOUR-APP-NAME.koyeb.app/health
```

### 10.2 Push and enable

```bash
git add .github/workflows/keepalive.yml
git commit -m "chore: set keepalive URL"
git push
```

Go to **GitHub → Actions** and enable the workflow if prompted. It fires automatically every 5 minutes via cron and can be triggered manually via `workflow_dispatch`.

---

## 11. Environment Variables Reference

All variables are read by `backend/config.py`. For local development, copy `.env.example` to `.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | `sqlite:///./firduty.db` | Supabase PostgreSQL connection string |
| `SECRET_KEY` | ✅ | `dev-secret-key` | 32-byte hex JWT signing key — **change in production** |
| `ADMIN_USERNAME` | ✅ | `admin` | Admin login username |
| `ADMIN_PASSWORD` | ✅ | `admin123` | Admin login password — **change in production** |
| `ALLOWED_ORIGINS` | ⚠️ | `*` | Comma-separated CORS allowed origins — restrict before go-live |
| `FIREBASE_CREDENTIALS_JSON` | ❌ | — | Full contents of `firebase-credentials.json` as a string (Koyeb-friendly) |
| `FIREBASE_CREDENTIALS_PATH` | ❌ | `./firebase-credentials.json` | Path to the credentials file (used if `FIREBASE_CREDENTIALS_JSON` is not set) |
| `ALGORITHM` | ❌ | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `1440` | JWT expiry in minutes (24 hours) |
| `PORT` | ❌ | `8000` | HTTP port — Koyeb injects this automatically |
| `RUN_SCHEDULER` | ❌ | `true` | Set `false` to disable the background scheduler on an instance |
| `SCHEDULER_JITTER` | ❌ | `30` | Random extra seconds added to job triggers (reduces multi-instance collision) |

---

## 12. Database Models

Tables are created automatically on first startup. All times stored in UTC.

```
AppSetting
  key VARCHAR PK, value TEXT

Teacher
  id INT PK, name VARCHAR, active BOOL, preferred_language ('ar'|'en'), created_at

DeviceToken
  id INT PK, teacher_id FK→Teacher, token TEXT, platform ('android'|'ios'), updated_at

Location
  id INT PK, name_en VARCHAR, name_ar VARCHAR, order INT

Shift
  id INT PK, name_en VARCHAR, name_ar VARCHAR,
  start_time TIME, end_time TIME, order INT,
  duty_type ('morning_endofday'|'break')           ← added v2.1

WeekPlan
  id INT PK, week_start_date DATE (Sunday),
  status ('draft'|'published'), version INT,
  cloned_from_week_start DATE, created_at, updated_at

DayPlan
  id INT PK, week_plan_id FK→WeekPlan, date DATE

ShiftLocation
  id INT PK, day_plan_id FK→DayPlan,
  shift_id FK→Shift,
  location_id FK→Location  NULLABLE           ← nullable since v2.1 (break duties have no location)
  slots_count INT, order INT

Assignment
  id INT PK, shift_location_id FK→ShiftLocation,
  slot_index INT, teacher_id FK→Teacher (nullable),
  grade_class VARCHAR(100) NULLABLE            ← added v2.1 (break duties: grade / class text)

ChangeLog
  id INT PK, week_plan_id FK→WeekPlan, actor VARCHAR,
  action VARCHAR, payload_json TEXT, created_at

DutyConfirmation
  id INT PK, teacher_id FK→Teacher, assignment_id FK→Assignment,
  confirmed_at DATETIME (UTC), points_earned (0|1|2)
  UNIQUE(teacher_id, assignment_id)

MonthlyPointsSummary
  id INT PK, teacher_id FK→Teacher, year INT, month INT,
  total_points INT, updated_at
  UNIQUE(teacher_id, year, month)
```

---

## 13. API Reference

Interactive docs (Swagger UI):

| Environment | URL |
|---|---|
| Local | `http://localhost:8000/docs` |
| Production | `https://YOUR-APP-NAME.koyeb.app/docs` |

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/admin/login` | — | Returns a JWT `access_token` |

All admin endpoints require `Authorization: Bearer <token>` header.

### Master Data

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/teachers/` | — | List active teachers |
| GET | `/teachers/all` | JWT | List all teachers including inactive |
| POST | `/teachers/` | JWT | Create a teacher |
| PUT | `/teachers/{id}` | JWT | Update teacher (name, language, active) |
| DELETE | `/teachers/{id}` | JWT | Deactivate teacher |
| GET | `/locations/` | — | List locations |
| POST | `/locations/` | JWT | Create location |
| PUT | `/locations/{id}` | JWT | Update location |
| DELETE | `/locations/{id}` | JWT | Delete location |
| GET | `/shifts/` | — | List shifts (includes `duty_type`) |
| POST | `/shifts/` | JWT | Create shift |
| PUT | `/shifts/{id}` | JWT | Update shift |
| DELETE | `/shifts/{id}` | JWT | Delete shift |

### Week Planning

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/weeks/current` | — | Current week plan |
| GET | `/weeks/{week_start}` | — | Specific week by `YYYY-MM-DD` Sunday |
| POST | `/weeks/{week_start}/create` | JWT | Create empty draft |
| POST | `/weeks/{week_start}/clone` | JWT | Clone from latest published week |
| PUT | `/weeks/{week_start}/status` | JWT | Change status (publish draft) |
| PUT | `/weeks/{week_start}/shift-locations` | JWT | Update slot counts and order |
| PUT | `/weeks/{week_start}/assignments` | JWT | Assign / unassign teachers (supports `grade_class`) |

### Teacher App

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/teachers/{id}/schedule?date=YYYY-MM-DD` | — | Today's duties with `duty_type`, `grade_class`, `already_confirmed` |
| GET | `/teachers/{id}/week?week_start=YYYY-MM-DD` | — | Full week duties with `duty_type`, `grade_class` |
| POST | `/teachers/{id}/device-token` | — | Register or refresh FCM token |
| PUT | `/teachers/{id}` | — | Update preferred language |

### Points

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/points/teachers/{id}/confirm` | — | Confirm presence → returns `points_earned` + localised message |
| GET | `/points/teachers/{id}/monthly?year=&month=` | — | Monthly total + per-duty confirmation history |

### Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | JWT | Live stats: week coverage, teacher distribution, warnings |
| GET | `/admin/reports/monthly-points?year=&month=` | JWT | Full monthly leaderboard |
| GET | `/admin/reports/monthly-points/{id}` | JWT | Single teacher detail |
| GET | `/admin/reports/monthly-points/export/csv` | JWT | Download CSV |
| POST | `/admin/reports/monthly-points/rebuild` | JWT | Rebuild cached monthly totals |

### System

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Service info and version |
| GET | `/health` | Liveness probe (Koyeb health check) |
| GET | `/scheduler/status` | Scheduler state, job IDs, and next run times |

---

## 14. Duty Types

Every `Shift` has a `duty_type` field that controls what is shown to the teacher and what the admin enters in the planner.

| `duty_type` | Used for | Admin enters | Teacher sees |
|---|---|---|---|
| `morning_endofday` | Morning gate duty, end-of-day duty | A location (from the Location list) | Location name + pin icon |
| `break` | Break 1, Break 2, Ramadan break | A grade/class text string | Grade/class + groups icon |

### Creating shifts

```json
POST /shifts/
{ "name_en": "Morning Duty",    "name_ar": "مناوبة الصباح",
  "start_time": "07:00", "end_time": "07:30",
  "duty_type": "morning_endofday", "order": 1 }

{ "name_en": "Break 1",         "name_ar": "الاستراحة الأولى",
  "start_time": "09:45", "end_time": "10:00",
  "duty_type": "break", "order": 2 }
```

### Assigning a grade/class to a break duty slot

```json
PUT /weeks/2026-03-09/assignments
[{
  "shift_location_id": 5,
  "slot_index": 0,
  "teacher_id": 3,
  "grade_class": "Grade 5A"
}]
```

In the admin planner, a text input appears automatically inline under each filled break slot — no separate step needed.

### Ramadan mode

In Ramadan there is typically only one break period. Simply do not add Break 2 slots to the week plan. You can also rename the shift to reflect the shorter schedule:

```json
PUT /shifts/{break2_id}
{ "name_en": "Ramadan Break", "name_ar": "استراحة رمضان",
  "start_time": "10:30", "end_time": "10:45" }
```

No code changes or feature flags needed.

---

## 15. Points System

All time comparisons are performed in **Asia/Muscat (UTC+4)** timezone.

### Scoring rules

| Confirmation time vs shift start | Points |
|---|---|
| At or before shift start time | **2 points** ✅ |
| 1 – 5 minutes after shift start | **1 point** ⏱ |
| More than 5 minutes after start | **0 points** ❌ |

### Business rules

- One confirmation per assignment per teacher — duplicate attempts return HTTP 400.
- Only **published** week plans are confirmable — draft weeks return HTTP 400.
- Monthly totals accumulate per calendar month in Asia/Muscat timezone.
- On the 1st of each month at 20:05 AST the `monthly_reset` job finalises the previous month and seeds a zero-total entry for the new month for all active teachers.
- Historical data is never deleted — past months remain queryable forever.

---

## 16. Background Jobs

Both jobs run **inside the backend process** via APScheduler. No external cron service, Celery, or Redis is needed.

| Job ID | Schedule (Asia/Muscat) | What it does |
|---|---|---|
| `auto_clone` | Every **Thursday at 16:00** | Clones the latest published week plan → next week as Draft. Skips if next week already exists. |
| `monthly_reset` | **1st of every month at 20:05** | Recalculates and persists monthly `MonthlyPointsSummary` rows for all active teachers. |

Both jobs are idempotent — running them twice produces the same result as running them once.

### Verify jobs are scheduled

```bash
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
```

Expected (truncated):
```json
{
  "running": true,
  "timezone": "Asia/Muscat",
  "jitter_seconds": 30,
  "jobs": [
    { "id": "auto_clone",    "next_run_time": "2026-03-12T16:00:00+04:00" },
    { "id": "monthly_reset", "next_run_time": "2026-04-01T20:05:00+04:00" }
  ]
}
```

### Run jobs manually (for testing)

```bash
cd backend
python jobs/auto_clone.py
python jobs/monthly_reset.py
```

### Multi-instance warning

If Koyeb scales to more than one instance, each instance runs its own scheduler, so both jobs fire multiple times. To prevent this:
- Keep Koyeb at **1 instance** (recommended for a school system of this scale).
- Or set `RUN_SCHEDULER=true` on exactly **one** instance and `RUN_SCHEDULER=false` on all others.

---

## 17. Notifications

Push notifications are delivered via Firebase Cloud Messaging (FCM).

### When they fire

| Event | Who receives | Content |
|---|---|---|
| Week published | All teachers assigned that week | "Your schedule has been updated" |
| Week modified (re-publish) | All affected teachers | "Your schedule has been updated" |
| 15 minutes before duty | Assigned teacher | Reminder with location or class |
| At duty start time | Assigned teacher | Start alert with location or class |

### Notification templates by duty type

The notification content is selected based on `duty_type` and sent in the teacher's `preferred_language`.

**Morning/End-of-day duty — Arabic:**
```
تذكير: مناوبتك تبدأ بعد 15 دقيقة
الموقع: {location} | الفترة: {shift_name}
```

**Morning/End-of-day duty — English:**
```
Reminder: Your duty starts in 15 minutes
Location: {location} | Shift: {shift_name}
```

**Break duty — Arabic:**
```
تذكير: فترة الاستراحة تبدأ بعد 15 دقيقة
الفصل: {grade_class} | الفترة: {shift_name}
```

**Break duty — English:**
```
Reminder: Your break duty starts in 15 minutes
Class: {grade_class} | Shift: {shift_name}
```

---

## 18. Local Development

### Backend

```bash
cd backend

# 1 — Install dependencies
pip install -r requirements.txt

# 2 — Copy env template
cp .env.example .env
# Edit .env — for local dev the SQLite fallback works without a Supabase connection

# 3 — Create database tables (SQLite by default)
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# 4 — Start with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 5 — Open interactive docs
open http://localhost:8000/docs
```

### Admin UI

```bash
cd admin_ui
python -m http.server 3000
open http://localhost:3000/login.html
```

Update the `API_BASE` fallback in `js/planner.js`, `js/dashboard.js`, and `js/login.js` to `http://localhost:8000/`.

### Flutter App

```bash
cd flutter_app

# Install packages
flutter pub get

# Generate AppLocalizations (run once; also auto-runs on build)
flutter gen-l10n

# Update baseUrl in lib/services/api_service.dart:
#   static const String baseUrl = 'http://localhost:8000';
# If testing on a physical device, use your machine's LAN IP instead:
#   static const String baseUrl = 'http://192.168.x.x:8000';

# Analyse
flutter analyze   # should be 0 errors

# Run
flutter run
```

---

## 19. Migrations (Existing Database)

If you have an existing Firduty v2.0 database and are upgrading to v2.1, run the included migration script. It is **idempotent** — safe to run multiple times.

### PostgreSQL (Supabase production)

```bash
psql postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres \
     -f migrations/001_duty_types.sql
```

What the migration does:
1. Adds `duty_type` column to `shifts` table (default `morning_endofday` — all existing shifts are preserved).
2. Makes `location_id` nullable on `shift_locations` (break duties have no fixed location).
3. Adds `grade_class VARCHAR(100)` column to `assignments`.

### SQLite (local development)

For a fresh local environment, just delete the database and recreate it:

```bash
cd backend
rm firduty.db
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"
```

To preserve existing SQLite data, run these statements manually:

```sql
ALTER TABLE shifts ADD COLUMN duty_type TEXT NOT NULL DEFAULT 'morning_endofday';
ALTER TABLE assignments ADD COLUMN grade_class TEXT;
-- location_id on shift_locations is already nullable in SQLite — no change needed
```

---

## 20. Security Checklist

Complete every item before going live with real teacher data.

| # | Check | How |
|---|---|---|
| 1 | Change `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` → set in Koyeb |
| 2 | Change `ADMIN_PASSWORD` | Set a strong password in Koyeb env vars |
| 3 | Restrict `ALLOWED_ORIGINS` | Set to your admin UI domain only, e.g. `https://admin.yourschool.com` |
| 4 | Keep `firebase-credentials.json` out of Git | Verify it is in `.gitignore` |
| 5 | Keep `.env` out of Git | Verify it is in `.gitignore` |
| 6 | Use HTTPS everywhere | Koyeb provides automatic HTTPS on `*.koyeb.app` domains |
| 7 | Keep Koyeb at 1 instance | Prevents duplicate background job execution |
| 8 | Enable Supabase backups | Supabase dashboard → Database → Backups |

---

## 21. Troubleshooting

### Backend won't start on Koyeb

Check Koyeb build logs for Python import errors. The most common cause is a missing environment variable.

Ensure all four required variables are set: `DATABASE_URL`, `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.

---

### `psycopg2.OperationalError: SSL connection required`

Supabase requires SSL for all connections. `database.py` passes `sslmode=require` automatically.
Make sure your `DATABASE_URL` does not include `?sslmode=disable`.

---

### `relation "teachers" does not exist` (500 error)

`Base.metadata.create_all()` failed to create tables. Check:
1. `DATABASE_URL` is correct and reachable from Koyeb.
2. The Supabase database password is correct (no special characters that need URL-encoding).
3. The `postgres` user has `CREATE TABLE` permission (it does by default on Supabase).

---

### Firebase credentials not found

Log message: `Firebase credentials not found at ./firebase-credentials.json`

Push notifications are disabled but the API works normally. To enable them:
- Use Option A from Step 7.5: set `FIREBASE_CREDENTIALS_JSON` in Koyeb to the full JSON content.
- Or use Option B: mount the file via a Koyeb Secrets volume.

---

### Flutter: `google-services.json` not found

```
FAILURE: Execution failed for task ':app:processDebugGoogleServices'.
```

Place `google-services.json` at `flutter_app/android/app/google-services.json` (downloaded from Firebase Console → Project settings → Your apps → Android).

---

### Flutter: `lib/gen/app_localizations.dart` not found

The localisation file has not been generated yet. Run:
```bash
cd flutter_app
flutter pub get
flutter gen-l10n
```

If it still fails, check that `flutter_app/l10n.yaml` exists and contains:
```yaml
arb-dir: lib/l10n
output-dir: lib/gen
synthetic-package: false
```

---

### Flutter: push notifications not received on iOS

1. In Xcode, enable **Push Notifications** capability under **Signing & Capabilities**.
2. Test on a real device — APNs does not work on simulators.
3. Confirm `GoogleService-Info.plist` is placed inside `ios/Runner/`.

---

### Admin UI: CORS error in browser

The browser is blocking requests because the admin UI origin is not in `ALLOWED_ORIGINS`.

Fix in Koyeb:
```
ALLOWED_ORIGINS=https://YOUR-USERNAME.github.io,https://your-site.netlify.app
```

---

### Scheduler jobs not firing

```bash
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
# Check "running": true and both jobs appear in "jobs"
```

If `"running": false`:
- Confirm `RUN_SCHEDULER` is `true` (or not set — default is `true`).
- Check Koyeb logs for APScheduler startup errors.

If the service is on the free tier and has been sleeping, the keep-alive workflow in Step 10 prevents this.

---

### Week not auto-cloning on Thursday

The `auto_clone` job skips if:
1. There is no published week in the database yet.
2. The next week's plan already exists.

To test manually:
```bash
cd backend
python jobs/auto_clone.py
```

---

### `flutter analyze` reports deprecation warnings about `withOpacity`

All `Color.withOpacity()` calls in the screen files have already been replaced with `Color.withValues(alpha:)` (the non-deprecated API). If you see this warning in files you edited yourself, replace:
```dart
someColor.withOpacity(0.5)
// with:
someColor.withValues(alpha: 0.5)
```

---

## 22. Quick Reference

```bash
# ── Backend (local) ───────────────────────────────────────────────────────────
cd backend && uvicorn main:app --reload --port 8000

# ── Admin UI (local) ──────────────────────────────────────────────────────────
cd admin_ui && python -m http.server 3000

# ── Flutter ───────────────────────────────────────────────────────────────────
cd flutter_app && flutter pub get && flutter gen-l10n && flutter run

# ── Flutter production APK ────────────────────────────────────────────────────
cd flutter_app && flutter build apk --release

# ── Database init (fresh local SQLite) ───────────────────────────────────────
cd backend && python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# ── Database migration (existing PostgreSQL) ──────────────────────────────────
psql $DATABASE_URL -f migrations/001_duty_types.sql

# ── Run background jobs manually ─────────────────────────────────────────────
cd backend && python jobs/auto_clone.py
cd backend && python jobs/monthly_reset.py

# ── Generate a secure SECRET_KEY ─────────────────────────────────────────────
python -c "import secrets; print(secrets.token_hex(32))"

# ── Health checks (production) ───────────────────────────────────────────────
curl https://YOUR-APP-NAME.koyeb.app/health
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
curl https://YOUR-APP-NAME.koyeb.app/teachers/
```