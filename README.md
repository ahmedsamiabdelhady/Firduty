# Firduty — School Duty Roster Management System

> Bilingual (Arabic / English) school duty roster — drag-and-drop weekly planning,
> teacher self-registration with admin approval, Flutter mobile app (Android native +
> iOS PWA), Firebase push notifications, a points-based attendance system, and an
> analytics dashboard.
>
> **Version 2.3.0** · Backend: FastAPI · Database: Supabase (PostgreSQL) ·
> Hosting: Koyeb · Notifications: Firebase FCM (Android) + Web Push (iOS PWA) ·
> App: Flutter 3.x

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
9. [Step 5 — Flutter App (Android + Web / iOS PWA)](#9-step-5--flutter-app-android--web--ios-pwa)
10. [Step 6 — Keep-Alive (Free Tier)](#10-step-6--keep-alive-free-tier)
11. [Environment Variables Reference](#11-environment-variables-reference)
12. [Database Models](#12-database-models)
13. [API Reference](#13-api-reference)
14. [Duty Types](#14-duty-types)
15. [Points System](#15-points-system)
16. [Background Jobs](#16-background-jobs)
17. [Notifications](#17-notifications)
18. [Teacher Registration & Approval Flow](#18-teacher-registration--approval-flow)
19. [Local Development](#19-local-development)
20. [Migrations (Existing Database)](#20-migrations-existing-database)
21. [Security Checklist](#21-security-checklist)
22. [Troubleshooting](#22-troubleshooting)
23. [Quick Reference](#23-quick-reference)

---

## 1. System Overview

Firduty is a school duty-roster management system with the following components:

| Component | Technology | Delivery |
|---|---|---|
| Backend API | Python + FastAPI | Koyeb (free tier) |
| Database | PostgreSQL | Supabase (free tier) |
| Admin Web UI | Vanilla HTML / CSS / JS | GitHub Pages or Netlify |
| Teacher App — Android | Flutter native APK | Direct download or Google Play |
| Teacher App — iOS | Flutter Web **PWA** | Safari → Add to Home Screen |
| Teacher App — Desktop | Flutter Web | Any modern browser |
| Push Notifications — Android | Firebase Cloud Messaging (FCM) | Firebase → Google Play Services |
| Push Notifications — iOS PWA | FCM Web Push (VAPID) | Firebase → Safari service worker |

### iOS architecture decision

iOS teachers use the **Flutter Web build** installed as a **Progressive Web App (PWA)** from Safari. This requires:

- No App Store submission
- No Apple Developer account ($99/year)
- No Xcode or macOS build machine

Push notifications on the iOS PWA are delivered via **Firebase Web Push** (VAPID). This requires iOS/iPadOS **16.4 or later** — Apple added Web Push support to Safari in that release. Teachers on older iOS versions see in-app messages only.

### Push notification flow

```
Backend scheduler fires a notification
  │
  ├─► Token platform = 'android'
  │     └─► firebase-admin MulticastMessage → FCM
  │               └─► Google Play Services → Android notification tray
  │
  └─► Token platform = 'web'   (iOS PWA or desktop browser)
        └─► firebase-admin MulticastMessage with WebpushConfig → FCM
                  └─► FCM Web Push (VAPID) → browser service worker
                            (firebase-messaging-sw.js)
                            └─► showNotification() → iOS / desktop notification centre
```

### Core features

- Bilingual Arabic / English UI throughout (teacher app + admin panel)
- Drag-and-drop weekly duty planner with automatic Thursday clone
- Two duty types: morning/end-of-day (requires location) and break (requires grade/class)
- Teacher self-registration with admin approval flow
- Presence confirmation with lateness-aware points scoring
- Monthly points leaderboard with CSV export
- 15-minute pre-duty reminders and duty-start notifications
- Live dashboard with coverage warnings and teacher distribution stats

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
| `pydantic[email]` | Request / response validation (validates teacher email on registration) |
| `firebase-admin` | Firebase Cloud Messaging — Android FCM tokens and Web Push (FCM web tokens) |
| `pytz` | Timezone handling (`Asia/Muscat`, UTC+4) |
| `apscheduler` | In-process background job scheduler |
| `python-dotenv` | `.env` file loader for local development |
| `aiofiles` | Async file I/O utilities |

### Admin UI (`admin_ui/`)

| Tool | Purpose |
|---|---|
| Vanilla HTML / CSS / JS | No build step — works from any static host |
| SortableJS (CDN) | Drag-and-drop teacher assignment in the planner |

**Pages:**

| File | Purpose |
|---|---|
| `login.html` | Admin authentication |
| `dashboard.html` | Live stats, distribution warnings, top teachers |
| `planner.html` | Drag-and-drop week roster planner |
| `reports.html` | Monthly points leaderboard with CSV export |
| `teachers.html` | Pending approval tab + All Teachers tab |

### Flutter App (`flutter_app/`)

| Package | Version | Purpose |
|---|---|---|
| `flutter_localizations` | SDK | Material / Cupertino locale delegates |
| `http` | `^1.2.1` | REST API calls |
| `shared_preferences` | `^2.2.3` | Teacher ID and language preference storage |
| `firebase_core` | `^2.30.1` | Firebase SDK initialisation (Android + Web) |
| `firebase_messaging` | `^14.9.4` | FCM push tokens — Android native and FCM web tokens |
| `flutter_local_notifications` | `^17.2.2` | Foreground notification display on Android only (guarded with `kIsWeb`) |
| `intl` | `^0.20.2` | `DateFormat` and locale utilities (pinned to match `flutter_localizations`) |

### Cloud Services

| Service | Role | Free tier |
|---|---|---|
| **Supabase** | Managed PostgreSQL with SSL and automatic backups | 500 MB storage, 2 projects |
| **Koyeb** | Backend hosting — auto-detects `Procfile` | 1 web service, sleeps on inactivity |
| **Firebase** | FCM push notifications (Android + Web Push for iOS PWA) | Spark plan — unlimited notifications |
| **GitHub Pages / Netlify** | Admin UI and Flutter web static hosting | Free |
| **GitHub Actions** | Keep-alive ping every 5 minutes | 2 000 minutes/month free |

---

## 3. Project Structure

```
firduty/
│
├── README.md                              ← this file (v2.3.0)
├── pyrightconfig.json                     ← Python type-checker config (0 errors)
├── .gitignore
│
├── .github/
│   └── workflows/
│       └── keepalive.yml                  ← pings /health every 5 min (prevents Koyeb sleep)
│
├── migrations/
│   ├── 001_duty_types.sql                 ← v2.1: duty_type column, nullable location_id, grade_class
│   ├── 002_teacher_registration.sql       ← v2.2: email + status columns on teachers
│   └── 003_web_push.sql                   ← v2.3: documentation migration (no schema changes)
│
├── backend/
│   ├── Procfile                           ← Koyeb start command
│   ├── requirements.txt
│   ├── .env.example                       ← copy to .env for local dev
│   ├── firebase-credentials.json          ← ⚠ add manually, never commit
│   │
│   ├── main.py                            ← FastAPI app + Firebase credential bootstrap
│   ├── config.py                          ← all env vars via Settings class (incl. VAPID keys)
│   ├── database.py                        ← SQLAlchemy engine (SSL for PostgreSQL)
│   ├── scheduler.py                       ← APScheduler + GET /scheduler/status
│   │
│   ├── models/
│   │   ├── models.py                      ← all ORM models
│   │   │                                      DeviceToken.platform: 'android' | 'web'
│   │   └── points_models.py               ← DutyConfirmation, MonthlyPointsSummary
│   │
│   ├── schemas/
│   │   └── schemas.py                     ← Pydantic v2 schemas
│   │                                          DeviceTokenCreate.platform: 'android' | 'web'
│   │
│   ├── routers/
│   │   ├── auth.py                        ← POST /auth/admin/login
│   │   ├── teachers.py                    ← CRUD + /register + /pending + /approve
│   │   ├── locations.py                   ← location CRUD
│   │   ├── shifts.py                      ← shift CRUD
│   │   ├── weeks.py                       ← week planning and assignment
│   │   ├── points.py                      ← confirm presence + monthly summary
│   │   ├── reports.py                     ← monthly leaderboard + CSV export
│   │   └── dashboard.py                   ← GET /admin/dashboard stats
│   │
│   ├── services/
│   │   ├── auth_service.py                ← JWT create / decode
│   │   ├── notification_service.py        ← FCM multicast with WebpushConfig for web tokens
│   │   ├── week_service.py                ← week create / clone / publish
│   │   └── points_service.py             ← confirmation scoring + detail builder
│   │
│   └── jobs/
│       ├── auto_clone.py                  ← Thursday 16:00: clone latest published week
│       └── monthly_reset.py               ← 1st of month 20:05: finalise monthly points
│
├── admin_ui/
│   ├── login.html, dashboard.html, planner.html, reports.html, teachers.html
│   ├── css/style.css                      ← Firduty brand palette (#7FB33F, #2E7DA7)
│   ├── js/
│   │   ├── auth.js                        ← shared auth: authHeaders(), apiFetch(), guardPage(), logout()
│   │   ├── i18n.js                        ← AR/EN runtime language switching (I18N.load/t/getLang)
│   │   ├── login.js                       ← JWT login flow, auto-redirect, Enter key support
│   │   ├── dashboard.js                   ← loads /admin/dashboard, renders stats + charts
│   │   ├── planner.js                     ← SortableJS drag-and-drop + grade_class inputs
│   │   └── teachers.js                    ← /pending + /approve endpoints
│   ├── favicon.ico, favicon-*.png, logo.png
│   └── i18n/ar.json, en.json
│
└── flutter_app/
    ├── pubspec.yaml                       ← dependencies; version 2.3.0+3
    ├── l10n.yaml                          ← ARB source dir, output: lib/gen
    │
    ├── assets/
    │   ├── logo.png                       ← 512×512 RGBA (splash, pending screen)
    │   ├── logo_small.png                 ← 256×256 RGBA (registration screen)
    │   └── app_icon.png                   ← 1024×1024 (flutter_launcher_icons input only)
    │
    ├── web/                               ← Flutter web build configuration
    │   ├── index.html                     ← iOS PWA meta tags, install banner, SW registration
    │   ├── manifest.json                  ← PWA manifest (standalone, Firduty brand colours)
    │   ├── firebase-messaging-sw.js       ← Service worker — background push on web/iOS
    │   └── icons/
    │       ├── Icon-192.png, Icon-512.png
    │       ├── Icon-maskable-192.png, Icon-maskable-512.png
    │       └── favicon-16x16.png, favicon-32x32.png
    │
    ├── lib/
    │   ├── main.dart                      ← Firebase init (with DefaultFirebaseOptions),
    │   │                                      kIsWeb platform detection, route table
    │   ├── app_theme.dart                 ← FirdutyColors + buildFirdutyTheme()
    │   ├── firebase_options.dart          ← per-platform Firebase config + kVapidPublicKey
    │   │
    │   ├── l10n/                          ← source ARB files — edit to add strings
    │   │   ├── app_en.arb
    │   │   └── app_ar.arb
    │   │
    │   ├── gen/                           ← auto-generated by flutter gen-l10n — do not edit
    │   │   ├── app_localizations.dart
    │   │   ├── app_localizations_en.dart
    │   │   └── app_localizations_ar.dart
    │   │
    │   ├── screens/
    │   │   ├── teacher_select_screen.dart ← exports RegistrationScreen (name + email form)
    │   │   ├── pending_screen.dart        ← hourglass UI; uses kIsWeb not dart:io
    │   │   ├── today_screen.dart          ← duty-type aware (location or grade/class)
    │   │   ├── week_screen.dart
    │   │   └── points_screen.dart
    │   │
    │   └── services/
    │       ├── api_service.dart           ← baseUrl from String.fromEnvironment('API_BASE_URL')
    │       └── notification_service.dart  ← kIsWeb split: _initAndroid / _initWeb
    │
    └── test/
        └── widget_test.dart
```

---

## 4. Prerequisites

### On your machine

| Tool | Minimum version | Install |
|---|---|---|
| Python | 3.12 | [python.org](https://www.python.org/downloads/) |
| Flutter SDK | 3.19+ | [flutter.dev/get-started](https://docs.flutter.dev/get-started/install) |
| Git | any | [git-scm.com](https://git-scm.com) |
| Android Studio | 2023+ | For Android emulator / SDK (or VS Code + Flutter extension) |
| Chrome | any | Required for `flutter build web` |

> **Xcode is not required.** iOS is delivered as a PWA — no native iOS build is needed.

Verify Flutter is ready:

```bash
flutter doctor
# All items should show ✅ or ⚠ (warnings OK, errors must be fixed before building)
```

Enable web support (run once):

```bash
flutter config --enable-web
```

### Accounts you need (all free)

| Service | URL |
|---|---|
| Supabase | [supabase.com](https://supabase.com) |
| Firebase | [console.firebase.google.com](https://console.firebase.google.com) |
| Koyeb | [koyeb.com](https://koyeb.com) |
| GitHub | [github.com](https://github.com) |
| Netlify *(optional)* | [netlify.com](https://netlify.com) — alternative to GitHub Pages for hosting |

---

## 5. Step 1 — Supabase (Database)

### 5.1 Create a project

1. Sign in at [supabase.com](https://supabase.com) → **New project**.
2. Name it `firduty`, set a strong **database password**, pick the nearest region.
3. Click **Create new project** — provisioning takes about 60 seconds.

### 5.2 Get the connection string

1. **Project Settings** (gear icon) → **Database** → **Connection string** → **URI** tab.
2. Copy the URI:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```
3. Replace `[YOUR-PASSWORD]` with the password you set in step 5.1.
4. **Save this string** — it becomes the `DATABASE_URL` environment variable.

> If your password contains special characters (`@`, `#`, `%`, etc.) they must be percent-encoded:
> ```python
> from urllib.parse import quote_plus; print(quote_plus("your_password"))
> ```

### 5.3 Tables

All tables are created **automatically** on first backend startup via `Base.metadata.create_all()`. No manual SQL is needed for a fresh installation.

> Upgrading an existing database? See [Section 20 — Migrations](#20-migrations-existing-database).

### 5.4 SSL

Supabase requires SSL. The `database.py` engine already sets `connect_args={"sslmode": "require"}` for all PostgreSQL URLs. No extra configuration needed.

### 5.5 Backups

Enable automatic backups in Supabase: **Database → Backups → Enable**.

---

## 6. Step 2 — Firebase (Push Notifications)

> Push notifications are **optional**. The backend starts normally and all other features work without them.

### 6.1 Create a Firebase project

1. Go to [console.firebase.google.com](https://console.firebase.google.com) → **Add project**.
2. Name it `firduty` and follow the wizard. Disable Google Analytics if not needed.
3. Click **Create project**.

### 6.2 Register the Android app

1. From the project overview click **Add app** → **Android icon**.
2. **Android package name**: `com.yourschool.firduty` (must match `applicationId` in `flutter_app/android/app/build.gradle`).
3. Click **Register app**.
4. Download **`google-services.json`** and place it at:
   ```
   flutter_app/android/app/google-services.json
   ```
5. Click **Next** through the remaining wizard steps (the `build.gradle` entries are already present in this project).

### 6.3 Register the Web app (required for iOS PWA push)

The Flutter Web build — which serves as the iOS PWA — uses Firebase's **Web SDK**, not the native iOS SDK. Register a web app to get the web config and VAPID key.

1. From the project overview click **Add app** → **Web icon** (`</>`).
2. Enter a nickname, e.g. `firduty-pwa`. Do **not** enable Firebase Hosting.
3. Click **Register app**.
4. Firebase shows a `firebaseConfig` object. **Copy and save all values** — you will need them for `firebase_options.dart` and `firebase-messaging-sw.js`.

### 6.4 Generate the VAPID key pair

VAPID keys are required for Web Push notifications (iOS Safari 16.4+ and desktop browsers).

1. In Firebase Console → **Project Settings** → **Cloud Messaging** tab.
2. Scroll to **Web Push certificates**.
3. Click **Generate key pair**.
4. Copy the **Key pair** value — this is your `VAPID_PUBLIC_KEY`.

> The private key is managed internally by Firebase and is not shown separately. The "key pair" shown here is the **public** key. Set it as `VAPID_PUBLIC_KEY` in your backend environment and as `kVapidPublicKey` in `firebase_options.dart`.

### 6.5 Generate the server private key (for the backend)

1. **Project settings** (gear) → **Service accounts** tab.
2. Click **Generate new private key** → confirm → a JSON file downloads.
3. Rename it `firebase-credentials.json`.
4. **Do not commit this file** — it is listed in `.gitignore`.
5. You will supply it to the backend in Step 7.5.

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

Confirm `.gitignore` prevents committing secrets:

```
backend/.env
backend/firebase-credentials.json
flutter_app/android/app/google-services.json
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

| Variable | Example value | Required |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres` | ✅ |
| `SECRET_KEY` | 64-char hex string | ✅ |
| `ADMIN_USERNAME` | `admin` | ✅ |
| `ADMIN_PASSWORD` | your chosen password | ✅ |
| `ALLOWED_ORIGINS` | `https://your-admin-ui.netlify.app,https://your-flutter-app.netlify.app` | ⚠️ set before go-live |
| `FIREBASE_CREDENTIALS_JSON` | entire contents of `firebase-credentials.json` | ❌ optional |
| `VAPID_PUBLIC_KEY` | key pair from Firebase Console → Cloud Messaging | ❌ required for iOS PWA push |
| `VAPID_PRIVATE_KEY` | *leave blank if using Firebase's built-in VAPID* | ❌ optional |
| `VAPID_CONTACT_EMAIL` | `admin@yourschool.com` | ❌ recommended |
| `RUN_SCHEDULER` | `true` | ❌ default `true` |

Generate a secure `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 7.5 Supply Firebase credentials to Koyeb

**Option A — Inline env var (recommended for free tier)**

1. Open `firebase-credentials.json`, select all, copy the entire JSON.
2. In Koyeb → **Environment variables** → add `FIREBASE_CREDENTIALS_JSON` → paste the JSON.
3. The backend detects this on startup, validates the JSON, writes it to a temp file, and initialises `firebase-admin` automatically.

**Option B — Koyeb Secrets volume**

1. Koyeb → **Secrets** → **Create secret** → type **File**.
2. Paste the `firebase-credentials.json` contents.
3. In your service → **Volumes** → mount the secret at `/app/firebase-credentials.json`.
4. Add env var: `FIREBASE_CREDENTIALS_PATH=/app/firebase-credentials.json`.

### 7.6 Configure the health check

In Koyeb service settings set **Health check path** to `/health`. This returns `{"status": "ok"}` and is also pinged by the keep-alive GitHub Action.

### 7.7 Deploy

Click **Deploy**. First deploy takes 2–3 minutes. When status turns green:

```
✅  https://YOUR-APP-NAME.koyeb.app
```

### 7.8 Verify the deployment

```bash
curl https://YOUR-APP-NAME.koyeb.app/health
# → {"status":"ok"}

curl https://YOUR-APP-NAME.koyeb.app/
# → {"service":"Firduty API","version":"2.3.0","status":"running"}

# Interactive API docs
open https://YOUR-APP-NAME.koyeb.app/docs

# Scheduler state
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status

# Database connected + tables created
curl https://YOUR-APP-NAME.koyeb.app/teachers/
# → [] (empty array = success)
```

---

## 8. Step 4 — Admin Web UI

The Admin UI is a set of static HTML/CSS/JS files. No build step or Node.js is needed.

### 8.1 Update the API base URL

In every JS file that contains `API_BASE`, update the fallback URL to your Koyeb deployment:

```
admin_ui/js/dashboard.js
admin_ui/js/planner.js
admin_ui/js/teachers.js
admin_ui/reports.html   ← inline <script>, variable named API
```

Find and replace:

```javascript
// Before
const API_BASE = localStorage.getItem('firduty_api') || 'https://YOUR-APP-NAME.koyeb.app/';
// After
const API_BASE = localStorage.getItem('firduty_api') || 'https://your-actual-app.koyeb.app/';
```

### 8.2 Deploy to Netlify (recommended)

1. [netlify.com](https://netlify.com) → **Add new site** → **Deploy manually**.
2. Drag and drop the `admin_ui/` folder into the upload area.
3. Netlify gives you a free HTTPS URL immediately.

For continuous deployment from GitHub:
- **Base directory**: `admin_ui` | **Publish directory**: `admin_ui` | No build command.

### 8.3 Deploy to GitHub Pages (alternative)

1. Push `admin_ui/` to your repository.
2. GitHub → repository → **Settings** → **Pages**.
3. **Source**: Deploy from a branch → **Branch**: `main` → **Folder**: `/admin_ui` → **Save**.

Available at: `https://YOUR-USERNAME.github.io/firduty/login.html`

After deploying, add the domain to `ALLOWED_ORIGINS` in Koyeb.

### 8.4 Admin UI pages

| Page | URL path | Purpose |
|---|---|---|
| Login | `/login.html` | Admin username + password → JWT stored in `localStorage` |
| Dashboard | `/dashboard.html` | Live stats: teacher counts, assignment coverage, distribution warnings, top teachers |
| Week Planner | `/planner.html` | Create/clone/publish weeks; drag teachers onto slots; enter grade/class for break duties |
| Monthly Report | `/reports.html` | Points leaderboard; per-teacher drill-down; export CSV |
| Teachers | `/teachers.html` | **Pending** tab (approve/reject self-registered teachers) + **All Teachers** tab |

### 8.5 Set up master data (first time only)

Use the API docs at `https://YOUR-APP-NAME.koyeb.app/docs` to seed required data.

**Add locations** (for morning / end-of-day shifts):

```json
POST /locations/
{ "name_en": "Main Gate",     "name_ar": "البوابة الرئيسية", "order": 1 }
{ "name_en": "Side Entrance", "name_ar": "المدخل الجانبي",   "order": 2 }
```

**Add shifts:**

```json
POST /shifts/
{ "name_en": "Morning Duty",    "name_ar": "مناوبة الصباح",
  "start_time": "07:00", "end_time": "07:30",
  "duty_type": "morning_endofday", "order": 1 }

{ "name_en": "Break 1",         "name_ar": "الاستراحة الأولى",
  "start_time": "09:45", "end_time": "10:00",
  "duty_type": "break", "order": 2 }

{ "name_en": "Break 2",         "name_ar": "الاستراحة الثانية",
  "start_time": "11:30", "end_time": "11:45",
  "duty_type": "break", "order": 3 }

{ "name_en": "End-of-Day Duty", "name_ar": "مناوبة النهاية",
  "start_time": "13:30", "end_time": "14:00",
  "duty_type": "morning_endofday", "order": 4 }
```

**Add teachers directly** (bypasses the approval flow):

```json
POST /teachers/
{ "name": "Ahmed Al-Rashidi", "preferred_language": "ar" }
```

---

## 9. Step 5 — Flutter App (Android + Web / iOS PWA)

The Flutter app produces two builds:

| Build | Command | Target audience |
|---|---|---|
| Android APK | `flutter build apk` | Android teachers |
| Web | `flutter build web` | iOS teachers (PWA) + desktop browser access |

### 9.1 Configure Firebase options

Fill in your Firebase project values in two files:

**`flutter_app/lib/firebase_options.dart`** — replace every `YOUR_*` placeholder with values from Firebase Console → Project Settings → Your apps.

**`flutter_app/web/firebase-messaging-sw.js`** — fill in the `firebase.initializeApp({...})` block with the same web app config values.

**Recommended approach — FlutterFire CLI:**

```bash
# Install once
dart pub global activate flutterfire_cli

# Run inside flutter_app/
cd flutter_app
flutterfire configure
# → auto-generates lib/firebase_options.dart for Android + Web
# → manually update web/firebase-messaging-sw.js with the same web config
```

### 9.2 Set the VAPID public key in Flutter

Edit `flutter_app/lib/firebase_options.dart`:

```dart
const String kVapidPublicKey = 'YOUR_VAPID_PUBLIC_KEY';
```

This is the **Key pair** value from Firebase Console → Project Settings → Cloud Messaging → Web Push certificates (generated in Step 6.4). The Flutter app uses it when calling `FirebaseMessaging.getToken(vapidKey: kVapidPublicKey)` to get a web push token on iOS/desktop.

### 9.3 Set the backend URL

The API base URL is injected at **build time** using `--dart-define`. It is read in `api_service.dart` via `String.fromEnvironment('API_BASE_URL')`.

```bash
# Android APK
flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR-APP-NAME.koyeb.app

# Web (iOS PWA + desktop)
flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP-NAME.koyeb.app \
  --base-href "/"
```

> For local development, run with `--dart-define=API_BASE_URL=http://localhost:8000` or `http://192.168.x.x:8000` for a physical device on the same network.

### 9.4 Place the Android Firebase config file

Download `google-services.json` from Firebase Console → Project Settings → Your apps → Android app → Download, and place it at:

```
flutter_app/android/app/google-services.json
```

This file is in `.gitignore` and must be placed manually on every machine that builds the Android APK.

### 9.5 Install packages and generate localisations

```bash
cd flutter_app
flutter pub get
flutter gen-l10n   # generates lib/gen/app_localizations*.dart
```

The generated files in `lib/gen/` are recreated on every `flutter gen-l10n` run. **Never edit them manually** — edit the source ARB files in `lib/l10n/` instead.

> If `lib/gen/` files are stale (e.g. after pulling changes), you will see `undefined getter` errors in the IDE. Run `flutter gen-l10n` to fix them.

### 9.6 Analyse before building

```bash
cd flutter_app
flutter analyze   # 0 errors expected
flutter test
```

### 9.7 Build the Android APK

```bash
cd flutter_app
flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR-APP-NAME.koyeb.app
# Output: build/app/outputs/flutter-apk/app-release.apk
```

Distribute the APK directly to teachers or publish via Google Play.

### 9.8 Build the Web app (iOS PWA + desktop)

```bash
cd flutter_app
flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP-NAME.koyeb.app \
  --base-href "/"
# Output: build/web/
```

**Deploy to Netlify (recommended):**

1. Drag and drop `flutter_app/build/web/` at [netlify.com](https://netlify.com) → **Deploy manually**.
2. Copy the HTTPS URL (e.g. `https://firduty-pwa.netlify.app`).

For continuous deployment, add `netlify.toml` inside `flutter_app/`:

```toml
[build]
  command = "flutter build web --release --dart-define=API_BASE_URL=$API_BASE_URL --base-href /"
  publish = "build/web"

[build.environment]
  API_BASE_URL = "https://YOUR-APP-NAME.koyeb.app"
```

**Deploy to GitHub Pages:**

```bash
flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP-NAME.koyeb.app \
  --base-href "/firduty/"
cp -r build/web ../docs
git add docs/ && git commit -m "deploy: web build" && git push
# Enable: GitHub → Settings → Pages → main branch → /docs folder
```

### 9.9 iOS PWA — teacher install instructions

Send teachers the HTTPS URL of the deployed web app. On their iPhone (iOS 16.4+):

1. Open the URL in **Safari** — must be Safari; Chrome on iOS cannot install PWAs.
2. Tap the **Share** button (⬆, at the bottom of the screen).
3. Scroll down and tap **"Add to Home Screen"**.
4. Confirm the name ("Firduty") and tap **"Add"**.

The Firduty icon appears on the home screen. Tapping it opens the app full-screen with no browser bar. Push notifications work after the teacher grants permission.

> The in-app install banner (`index.html`) also shows instructions automatically when the app is opened in Safari on iOS and is not yet installed.

### 9.10 App flow after setup

```
First launch
  └──► RegistrationScreen (name + email form)
         └──► POST /teachers/register → save teacher_id to SharedPreferences
         └──► PendingScreen (hourglass)
                └──► Check Status button → polls GET /teachers/{id}/status
                └──► Once approved: NotificationService.initialize() → HomeScreen

Subsequent launches
  └──► StartupScreen (spinner + Firduty logo)
         └──► Read teacher_id from SharedPreferences
               ├── No ID   → RegistrationScreen
               └── Has ID  → GET /teachers/{id}/status
                     ├── approved → NotificationService.initialize() → HomeScreen
                     ├── pending  → PendingScreen
                     └── 404      → clear SharedPreferences → RegistrationScreen
```

**Platform detection:**
All platform checks use `kIsWeb` from `flutter/foundation.dart`. `dart:io` is never imported — it is unavailable on Flutter Web. The platform string passed to the backend is `'web'` when `kIsWeb` is true, and `'android'` otherwise.

**Notification permission on iOS PWA:**
`FirebaseMessaging.requestPermission()` triggers the native browser notification dialog. On iOS Safari this dialog only appears when the app is running in **standalone mode** (i.e. installed via Add to Home Screen, not opened as a regular Safari tab). Teachers must install the PWA before they can grant notification permission.

---

## 10. Step 6 — Keep-Alive (Free Tier)

On Koyeb's free tier the service sleeps after inactivity. `.github/workflows/keepalive.yml` pings `/health` every 5 minutes to prevent sleep.

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

Go to **GitHub → Actions** and enable the workflow if prompted. It runs on a 5-minute cron and can also be triggered manually via `workflow_dispatch`.

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
| `FIREBASE_CREDENTIALS_JSON` | ❌ | — | Full `firebase-credentials.json` contents as a string (Option A) |
| `FIREBASE_CREDENTIALS_PATH` | ❌ | `./firebase-credentials.json` | Path to credentials file (Option B) |
| `VAPID_PUBLIC_KEY` | ❌ | `""` | Web Push VAPID public key — from Firebase Console → Cloud Messaging → Web Push certificates. Must match `kVapidPublicKey` in `firebase_options.dart` |
| `VAPID_PRIVATE_KEY` | ❌ | `""` | Web Push VAPID private key (leave blank if using Firebase's built-in key management) |
| `VAPID_CONTACT_EMAIL` | ❌ | `admin@yourschool.com` | Contact email embedded in VAPID push claims |
| `ALGORITHM` | ❌ | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ❌ | `1440` | JWT expiry in minutes (24 hours) |
| `PORT` | ❌ | `8000` | HTTP port — Koyeb injects this automatically |
| `RUN_SCHEDULER` | ❌ | `true` | Set `false` to disable background scheduler on this instance |
| `SCHEDULER_JITTER` | ❌ | `30` | Random extra seconds added to job trigger times |

---

## 12. Database Models

Tables are created automatically on first startup. All timestamps stored in UTC.

```
AppSetting
  key VARCHAR(100) PK
  value VARCHAR(255)
  updated_at DATETIME

Teacher
  id INT PK
  name VARCHAR(200)
  email VARCHAR(255) UNIQUE NULLABLE      ← set by self-registration; NULL for admin-created records
  status ENUM('pending','approved')       ← 'pending' after self-registration; default 'approved'
  active BOOL DEFAULT true
  preferred_language CHAR(2) DEFAULT 'ar'
  created_at DATETIME

DeviceToken
  id INT PK
  teacher_id FK→Teacher
  token VARCHAR(500) UNIQUE
  platform VARCHAR(10)                    ← 'android' (FCM token) | 'web' (FCM web token)
  updated_at DATETIME

Location
  id INT PK
  name_en VARCHAR(200)
  name_ar VARCHAR(200)
  order INT DEFAULT 0

Shift
  id INT PK
  name_en VARCHAR(200)
  name_ar VARCHAR(200)
  start_time TIME
  end_time TIME
  order INT DEFAULT 0
  duty_type ENUM('morning_endofday','break')

WeekPlan
  id INT PK
  week_start_date DATE (Sunday, unique)
  status ENUM('draft','published')
  version INT DEFAULT 1
  cloned_from_week_start DATE NULLABLE
  created_at DATETIME
  updated_at DATETIME

DayPlan
  id INT PK
  week_plan_id FK→WeekPlan
  date DATE

ShiftLocation
  id INT PK
  day_plan_id FK→DayPlan
  shift_id FK→Shift
  location_id FK→Location NULLABLE        ← NULL for break duties (no fixed location)
  slots_count INT DEFAULT 1
  order INT DEFAULT 0

Assignment
  id INT PK
  shift_location_id FK→ShiftLocation
  slot_index INT
  teacher_id FK→Teacher NULLABLE
  grade_class VARCHAR(100) NULLABLE       ← populated for break duties (e.g. "Grade 5A")

ChangeLog
  id INT PK
  week_plan_id FK→WeekPlan
  actor VARCHAR(100)
  action VARCHAR(100)
  payload_json TEXT NULLABLE
  created_at DATETIME

DutyConfirmation
  id INT PK
  teacher_id FK→Teacher
  assignment_id FK→Assignment
  confirmed_at DATETIME (UTC)
  points_earned INT (0 | 1 | 2)
  UNIQUE(teacher_id, assignment_id)
  INDEX(teacher_id, confirmed_at)

MonthlyPointsSummary
  id INT PK
  teacher_id FK→Teacher
  year INT
  month INT
  total_points INT DEFAULT 0
  updated_at DATETIME
  UNIQUE(teacher_id, year, month)
  INDEX(year, month)
```

**`DeviceToken.platform` values:**

| Value | Source | Delivery |
|---|---|---|
| `'android'` | `FirebaseMessaging.getToken()` on Android | FCM → Google Play Services |
| `'web'` | `FirebaseMessaging.getToken(vapidKey: ...)` in Flutter Web | FCM Web Push → browser service worker |

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
| POST | `/auth/admin/login` | — | **OAuth2 form body** (`application/x-www-form-urlencoded`). Used by Swagger UI Authorize button. Fields: `username`, `password` |
| POST | `/auth/admin/login/json` | — | **JSON body** (`application/json`). Used by Admin Web UI and API clients. Body: `{username, password}` |
| GET | `/auth/validate` | JWT | Confirm a token is valid. Returns `{username, role, expires_at}` |

Both login routes return:
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

All admin endpoints require `Authorization: Bearer <token>` header.

**How to log in from Swagger UI:**
1. Open `https://YOUR-APP-NAME.koyeb.app/docs`
2. Click the **Authorize** button (🔓 top right)
3. Enter your `ADMIN_USERNAME` and `ADMIN_PASSWORD`
4. Click **Authorize** — Swagger will attach the token to all subsequent requests automatically

**Token lifetime:** controlled by `ACCESS_TOKEN_EXPIRE_MINUTES` env var (default: 1440 minutes = 24 hours). After expiry, log in again.

### Teachers

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/teachers/` | — | List approved + active teachers (used by planner) |
| GET | `/teachers/all` | JWT | List every teacher regardless of status |
| GET | `/teachers/pending` | JWT | List teachers with `status='pending'` |
| POST | `/teachers/` | JWT | Admin-create a teacher directly (status defaults to `'approved'`) |
| POST | `/teachers/register` | — | Self-register: `{name, email}` → `{id, name, status:'pending'}`. HTTP 409 on duplicate email |
| POST | `/teachers/approve-all` | JWT | Approve every pending teacher → `{approved_count}` |
| PUT | `/teachers/{id}` | JWT | Update name / language / active flag |
| DELETE | `/teachers/{id}` | JWT | Soft-deactivate (`active=false`) |
| GET | `/teachers/{id}/status` | — | Returns `{id, name, status}`. HTTP 404 if deleted |
| POST | `/teachers/{id}/approve` | JWT | Approve one pending teacher |
| GET | `/teachers/{id}/schedule?date=YYYY-MM-DD` | — | Today's duties for an approved teacher (HTTP 403 for pending) |
| GET | `/teachers/{id}/week?week_start=YYYY-MM-DD` | — | Full week duties for an approved teacher |
| POST | `/teachers/{id}/device-token` | — | Register or refresh push token. Body: `{token, platform}` |

> **Route order:** Static paths (`/pending`, `/register`, `/approve-all`) are declared **before** `/{teacher_id}` in `teachers.py` to prevent FastAPI path-parameter shadowing.

### Locations

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/locations/` | — | List all locations |
| POST | `/locations/` | JWT | Create location |
| PUT | `/locations/{id}` | JWT | Update location |
| DELETE | `/locations/{id}` | JWT | Delete location |

### Shifts

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/shifts/` | — | List shifts (includes `duty_type`) |
| POST | `/shifts/` | JWT | Create shift |
| PUT | `/shifts/{id}` | JWT | Update shift |
| DELETE | `/shifts/{id}` | JWT | Delete shift |

### Week Planning

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/weeks/current` | — | Current published week plan |
| GET | `/weeks/{week_start}` | — | Specific week by `YYYY-MM-DD` Sunday |
| POST | `/weeks/{week_start}/create` | JWT | Create empty draft for a week |
| POST | `/weeks/{week_start}/clone` | JWT | Clone from latest published week |
| PUT | `/weeks/{week_start}/status` | JWT | Change status: `'draft'` → `'published'` |
| PUT | `/weeks/{week_start}/shift-locations` | JWT | Update slot counts and order |
| PUT | `/weeks/{week_start}/assignments` | JWT | Assign / unassign teachers; supports `grade_class` for break duties |

### Points & Confirmations

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/points/teachers/{id}/confirm` | — | Body: `{assignment_id}` → returns `points_earned` + bilingual message |
| GET | `/points/teachers/{id}/monthly?year=&month=` | — | Monthly total + per-duty confirmation history |

### Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | JWT | Live stats: week coverage, distribution, top teachers, warnings |
| GET | `/admin/reports/monthly-points?year=&month=` | JWT | Full monthly points leaderboard |
| GET | `/admin/reports/monthly-points/{id}?year=&month=` | JWT | Single teacher's duty-by-duty detail |
| GET | `/admin/reports/monthly-points/export/csv?year=&month=` | JWT | Download leaderboard as CSV |
| POST | `/admin/reports/monthly-points/rebuild?year=&month=` | JWT | Rebuild cached monthly totals |

### System

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Service info and version |
| GET | `/health` | Liveness probe — returns `{"status": "ok"}` |
| GET | `/scheduler/status` | Scheduler state, job IDs, and next run times |

---

## 14. Duty Types

Every `Shift` has a `duty_type` field that controls what the admin enters and what the teacher sees.

| `duty_type` | Used for | Admin enters | Teacher sees |
|---|---|---|---|
| `morning_endofday` | Morning gate duty, end-of-day duty | A **location** from the Location list | Location name + pin icon |
| `break` | Break 1, Break 2, Ramadan break | A **grade/class** text string | Grade/class + groups icon |

### Assigning a break duty slot with grade/class

In the planner UI a text input appears automatically under each filled break slot. In the API:

```json
PUT /weeks/2026-03-09/assignments
[{
  "shift_location_id": 5,
  "slot_index": 0,
  "teacher_id": 3,
  "grade_class": "Grade 5A"
}]
```

### Ramadan mode

Only add Break 1 to the week plan; omit Break 2. Optionally rename the shift:

```json
PUT /shifts/{break2_id}
{ "name_en": "Ramadan Break", "name_ar": "استراحة رمضان",
  "start_time": "10:30", "end_time": "10:45" }
```

No code changes or feature flags needed.

---

## 15. Points System

All time comparisons use **Asia/Muscat (UTC+4)** timezone.

### Scoring rules

| Confirmation time vs shift start | Points |
|---|---|
| At or before shift start time | **2 points** ✅ |
| 1–5 minutes after shift start | **1 point** ⏱ |
| More than 5 minutes after start | **0 points** ❌ |

### Business rules

- One confirmation per assignment per teacher — duplicates return HTTP 400.
- Only **published** week plans are confirmable — draft weeks return HTTP 400.
- Monthly totals accumulate per calendar month in Asia/Muscat timezone.
- On the 1st of each month at 20:05 AST the `monthly_reset` job finalises the previous month.
- Historical data is never deleted.

---

## 16. Background Jobs

Both jobs run **inside the backend process** via APScheduler. No Celery, Redis, or external cron needed.

| Job ID | Schedule (Asia/Muscat) | What it does |
|---|---|---|
| `auto_clone` | Every **Thursday at 16:00** | Clones latest published week → next week as Draft. Skips if next week already exists. |
| `monthly_reset` | **1st of every month at 20:05** | Recalculates `MonthlyPointsSummary` for all active teachers. |

Both jobs are idempotent — running twice has the same result as running once.

### Verify jobs are running

```bash
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
```

Expected response (truncated):

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

### Run jobs manually

```bash
cd backend
python jobs/auto_clone.py
python jobs/monthly_reset.py
```

### Multi-instance warning

If Koyeb scales to more than one instance, each runs its own scheduler. To prevent duplicate job execution: keep Koyeb at **1 instance**, or set `RUN_SCHEDULER=false` on all but one instance.

---

## 17. Notifications

### Delivery channels

| Platform | Token type | Delivery path | Min. OS |
|---|---|---|---|
| Android (native APK) | FCM registration token | FCM → Google Play Services | Android 8+ |
| iOS (PWA via Safari) | FCM web registration token | FCM Web Push → service worker | iOS 16.4+ |
| Desktop browser | FCM web registration token | FCM Web Push → service worker | Chrome 50+, Firefox 44+, Edge 17+ |

### When notifications fire

The APScheduler job in `scheduler.py` fires two events per duty:

- **15-minute reminder** — 15 minutes before the shift's `start_time`
- **Duty start** — at the exact `start_time`

### How web push works on iOS PWA (step by step)

1. Teacher installs the web app via Safari → **Add to Home Screen**.
2. Teacher opens the installed PWA (in standalone mode).
3. On first approval, the app calls `NotificationService.initialize(platform: 'web')`.
4. Flutter calls `FirebaseMessaging.requestPermission()` → Safari shows the native permission dialog.
5. On grant: `FirebaseMessaging.getToken(vapidKey: kVapidPublicKey)` → FCM web registration token.
6. Flutter sends the token to `POST /teachers/{id}/device-token` with `platform='web'`.
7. Backend stores the token in the `device_tokens` table.
8. When the scheduler fires, `send_notification_to_tokens()` builds a `messaging.MulticastMessage` with `WebpushConfig` (icon, badge, tap URL) and calls `messaging.send_multicast()`.
9. Firebase delivers the push via VAPID to the teacher's browser.
10. `firebase-messaging-sw.js` receives the `onBackgroundMessage` event and calls `self.registration.showNotification()`.
11. The notification appears in the iOS notification centre.

> **iOS Safari requirement:** The notification permission dialog (step 4) only appears when the PWA is running in **standalone mode** (opened from the home screen icon). It does not appear in a regular Safari browser tab. Teachers must install the PWA before granting notification permission.

### Notification templates

| Template key | Trigger | Content |
|---|---|---|
| `reminder_location` | 15 min before morning/end-of-day duty | Location name, shift name |
| `reminder_break` | 15 min before break duty | Grade/class, shift name |
| `start_location` | Duty starts — morning/end-of-day | Location name |
| `start_break` | Duty starts — break | Grade/class |
| `updated` | Admin publishes or edits week plan | No detail fields |

All templates are bilingual. Language is taken from `teacher.preferred_language` (`'ar'` or `'en'`).

---

## 18. Teacher Registration & Approval Flow

### Flow diagram

```
App Launch → StartupScreen (Firduty logo + spinner)
  │
  ├── No teacher_id in SharedPreferences
  │     └──► RegistrationScreen (/register)
  │           └──► POST /teachers/register
  │                  ├── 200 → save teacher_id → PendingScreen
  │                  └── 409 → inline error (email already registered)
  │
  └── teacher_id exists → GET /teachers/{id}/status
        ├── approved → NotificationService.initialize() → HomeScreen
        ├── pending  → PendingScreen
        │     ├── Check Status → re-polls status
        │     └── Use Another Account → clear prefs → RegistrationScreen
        └── 404 → clear prefs → RegistrationScreen
```

### Registration screen

`RegistrationScreen` (exported from `teacher_select_screen.dart`) contains:
- **Full Name** — required, non-empty
- **Email Address** — required, validated format
- **Register** button → `POST /teachers/register`

On success: saves `id` to `SharedPreferences`, navigates to PendingScreen.
On duplicate email (HTTP 409): shows inline error.

### Pending screen

`PendingScreen` shows while `status = 'pending'`:
- Hourglass icon + "Waiting for Approval" message
- **Check Status** — polls the backend; navigates to HomeScreen when approved
- **Use a different account** — clears storage and returns to RegistrationScreen
- Network error display with retry
- If backend returns HTTP 404 (teacher deleted by admin), storage is cleared automatically

### Admin approval (web UI)

Navigate to **Admin UI → Teachers** (`teachers.html`).

- **Pending Approval** tab: shows only `status='pending'` teachers with an **Approve** button per row. A red count badge shows the number of pending teachers.
- **All Teachers** tab: shows every teacher with status badge.
- **Approve All Pending** button at the top approves every pending teacher in a single API call.

### Backward compatibility

- All admin-created teachers have `status='approved'` by default — never blocked.
- `GET /teachers/` (planner sidebar) returns only `approved + active` teachers — pending registrations are hidden until approved.
- `/schedule` and `/week` return HTTP 403 for pending teachers.
- Push notifications are initialised only after approval is confirmed.

---

## 19. Local Development

### Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env — SQLite is the default (no Supabase needed for local dev)

# Create tables (fresh SQLite)
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# Start with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Open interactive docs
open http://localhost:8000/docs
```

### Admin UI

```bash
cd admin_ui
python -m http.server 3000
open http://localhost:3000/login.html
```

Update the `API_BASE` fallback in `dashboard.js`, `planner.js`, `teachers.js` and the inline `API` variable in `reports.html` to `http://localhost:8000`.

### Flutter App

```bash
cd flutter_app

flutter pub get
flutter gen-l10n

# Run on Android device or emulator
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator
flutter run --dart-define=API_BASE_URL=http://192.168.x.x:8000 # physical device on LAN

# Run as web app (for iOS PWA testing)
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000

# Analyse
flutter analyze   # 0 errors expected
```

> `10.0.2.2` is the Android emulator's alias for the host machine's `localhost`.

### Type checking (backend)

```bash
pip install pyright
pyright   # run from repository root; uses pyrightconfig.json
# Expected: 0 errors, 0 warnings
```

---

## 20. Migrations (Existing Database)

All migration scripts are **idempotent** — safe to run multiple times.

### Migration 001 — Duty types (v2.1)

```bash
psql $DATABASE_URL -f migrations/001_duty_types.sql
```

Adds `duty_type` to `shifts`, makes `location_id` nullable on `shift_locations`, adds `grade_class` to `assignments`.

### Migration 002 — Teacher registration (v2.2)

```bash
psql $DATABASE_URL -f migrations/002_teacher_registration.sql
```

Adds `email` (unique, nullable) and `status` (`pending`|`approved`, default `approved`) to `teachers`. Existing teachers keep `status='approved'` and are never blocked.

### Migration 003 — Web push (v2.3)

```bash
psql $DATABASE_URL -f migrations/003_web_push.sql
```

Documentation-only — adds a comment to `device_tokens.platform`. No structural changes are needed because the existing `token VARCHAR(500)` column is large enough for FCM web registration tokens, and `platform='web'` is simply stored as-is.

### SQLite (local development)

For a fresh local environment, delete and recreate:

```bash
cd backend
rm firduty.db
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"
```

---

## 21. Security Checklist

- [ ] `SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] `ADMIN_PASSWORD` — strong random password, not the default `admin123`
- [ ] `DATABASE_URL` — includes SSL (Supabase connection string already requires SSL)
- [ ] `FIREBASE_CREDENTIALS_JSON` / `firebase-credentials.json` — not committed to Git
- [ ] `google-services.json` — in `.gitignore`, placed manually on each build machine
- [ ] `VAPID_PUBLIC_KEY` in Koyeb env matches `kVapidPublicKey` in `firebase_options.dart`
- [ ] `ALLOWED_ORIGINS` — set to explicit domain(s) in production, not `*`
- [ ] Admin UI deployed on **HTTPS** — required for service workers and web push
- [ ] Flutter web deployed on **HTTPS** — required for PWA install prompt and push permission
- [ ] `API_BASE_URL` set via `--dart-define` at build time, not hardcoded in source

---

## 22. Troubleshooting

### Backend won't start on Koyeb

Check Koyeb build logs for Python import errors. The most common cause is a missing required environment variable. Ensure `DATABASE_URL`, `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` are all set.

---

### `psycopg2.OperationalError: SSL connection required`

Supabase requires SSL. The `database.py` engine passes `sslmode=require` automatically. Ensure your `DATABASE_URL` does not contain `?sslmode=disable`.

---

### `relation "teachers" does not exist` (500 error)

`Base.metadata.create_all()` failed silently. Check:
1. `DATABASE_URL` is correct and reachable from Koyeb.
2. The database password is correct (special characters must be percent-encoded).
3. The `postgres` user has `CREATE TABLE` permission (default on Supabase).

---

### Firebase credentials not found

Log message: `Firebase credentials not found at ./firebase-credentials.json`

Push notifications are disabled but the API runs normally. To enable notifications, set `FIREBASE_CREDENTIALS_JSON` in Koyeb (Option A in Step 7.5).

---

### Flutter: `google-services.json` not found

```
FAILURE: Execution failed for task ':app:processDebugGoogleServices'.
```

Place `google-services.json` at `flutter_app/android/app/google-services.json`.

---

### Flutter: undefined getter `pendingTitle` (or any l10n key)

The `lib/gen/` files are stale — `flutter gen-l10n` has not been run since the ARB files changed.

```bash
cd flutter_app && flutter gen-l10n
```

---

### Flutter: ambiguous import `RegistrationScreen`

```
The name 'RegistrationScreen' is defined in multiple libraries.
```

`main.dart` must use a scoped import:

```dart
import 'screens/teacher_select_screen.dart' show RegistrationScreen;
```

---

### iOS PWA: push notifications not working

Check in order:
1. **iOS version** — Web Push requires iOS/iPadOS 16.4 or later. Check in Settings → General → About.
2. **Installed as PWA** — The notification permission dialog only appears in standalone mode (opened from the home screen icon, not from a Safari tab). Teacher must complete "Add to Home Screen" first.
3. **VAPID key mismatch** — `kVapidPublicKey` in `firebase_options.dart` must match the key pair shown in Firebase Console → Project Settings → Cloud Messaging → Web Push certificates.
4. **Service worker not registered** — Open Safari → tap the share icon → tap "Web Inspector" (if using a Mac with developer mode enabled) or use Safari's error console to check for SW registration errors.
5. **HTTPS required** — The web app must be served over HTTPS. Both Netlify and GitHub Pages provide this.
6. **Backend not receiving token** — Check Koyeb logs for `POST /teachers/{id}/device-token` — confirm it returns `{"status": "registered"}`.

---

### iOS PWA: "Add to Home Screen" not appearing in Share menu

- The URL must be HTTPS.
- The page must serve a valid `manifest.json` (check the browser console for manifest errors).
- Safari must be the browser — Chrome on iOS uses WebKit but cannot install PWAs.

---

### Admin UI: CORS error in browser

The admin UI domain is not in `ALLOWED_ORIGINS`. Fix in Koyeb:

```
ALLOWED_ORIGINS=https://YOUR-USERNAME.github.io,https://your-site.netlify.app
```

---

### Admin UI: Teachers page renders without styling

The nav bar CSS is defined per-page. If you create a new admin page, copy the nav CSS block from `teachers.html`.

---

### Teacher stuck on Pending screen after admin approved

The app only re-checks status when the teacher taps **Check Status**. There is no automatic polling. Tap the button to trigger the check and navigate to HomeScreen.

---

### Scheduler jobs not firing

```bash
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
# Check "running": true and both job IDs are listed
```

If `"running": false`: confirm `RUN_SCHEDULER` is `true` (default). Check Koyeb logs for APScheduler startup errors.

---

### Week not auto-cloning on Thursday

`auto_clone` skips if: (a) there is no published week yet, or (b) next week already exists. Run manually to test:

```bash
cd backend && python jobs/auto_clone.py
```

---

### `flutter analyze` reports `withOpacity` deprecation

All screen files use `Color.withValues(alpha:)` — the non-deprecated replacement. If you see this in files you have edited, replace:

```dart
// Deprecated
someColor.withOpacity(0.5)
// Correct
someColor.withValues(alpha: 0.5)
```

---

### `dart:io` import error on web build

`dart:io` is not available on Flutter Web. Any file that imports it will fail to compile for web. Use `kIsWeb` from `flutter/foundation.dart` for platform detection instead. In this project, `dart:io` has been removed from all files; `Platform.isIOS` / `Platform.isAndroid` are never used.

---

## 23. Quick Reference

```bash
# ── Backend (local) ────────────────────────────────────────────────────────────
cd backend && uvicorn main:app --reload --port 8000

# ── Admin UI (local) ───────────────────────────────────────────────────────────
cd admin_ui && python -m http.server 3000

# ── Flutter (local — Android emulator) ────────────────────────────────────────
cd flutter_app && flutter pub get && flutter gen-l10n
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# ── Flutter (local — web / iOS PWA testing in Chrome) ─────────────────────────
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000

# ── Flutter production — Android APK ──────────────────────────────────────────
cd flutter_app && flutter build apk --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app

# ── Flutter production — Web (iOS PWA + desktop) ──────────────────────────────
cd flutter_app && flutter build web --release \
  --dart-define=API_BASE_URL=https://YOUR-APP.koyeb.app \
  --base-href "/"

# ── Regenerate localisation files ─────────────────────────────────────────────
cd flutter_app && flutter gen-l10n

# ── Analyse Flutter (0 errors expected) ───────────────────────────────────────
cd flutter_app && flutter analyze

# ── Database init (fresh local SQLite) ────────────────────────────────────────
cd backend && python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"

# ── Database migrations (existing PostgreSQL) ──────────────────────────────────
psql $DATABASE_URL -f migrations/001_duty_types.sql
psql $DATABASE_URL -f migrations/002_teacher_registration.sql
psql $DATABASE_URL -f migrations/003_web_push.sql

# ── Run background jobs manually ──────────────────────────────────────────────
cd backend && python jobs/auto_clone.py
cd backend && python jobs/monthly_reset.py

# ── Generate a secure SECRET_KEY ──────────────────────────────────────────────
python -c "import secrets; print(secrets.token_hex(32))"

# ── Generate VAPID keys (run once, store outputs in env vars) ─────────────────
pip install py-vapid && vapid --gen
# → vapid_private.pem (VAPID_PRIVATE_KEY) and vapid_public.pem (VAPID_PUBLIC_KEY)

# ── Type-check backend (0 errors expected) ────────────────────────────────────
pyright

# ── Health checks (production) ────────────────────────────────────────────────
curl https://YOUR-APP-NAME.koyeb.app/health
curl https://YOUR-APP-NAME.koyeb.app/scheduler/status
curl https://YOUR-APP-NAME.koyeb.app/teachers/
```