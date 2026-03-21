# Firduty — School Duty Roster System

**Version 3.2.0** · FastAPI · Flutter · PostgreSQL (Supabase) · Firebase FCM · Koyeb

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Project Structure](#3-project-structure)
4. [Prerequisites](#4-prerequisites)
5. [First-Time Setup Checklist](#5-first-time-setup-checklist)
6. [Backend Setup](#6-backend-setup)
7. [Database Setup](#7-database-setup)
8. [Flutter App Setup](#8-flutter-app-setup)
9. [Firebase Setup](#9-firebase-setup)
10. [Notifications Setup](#10-notifications-setup)
11. [Admin UI Setup](#11-admin-ui-setup)
12. [Environment Variables Reference](#12-environment-variables-reference)
13. [Running the Full System Locally](#13-running-the-full-system-locally)
14. [Building for Production](#14-building-for-production)
15. [Koyeb Deployment](#15-koyeb-deployment)
16. [Development Workflow](#16-development-workflow)
17. [Troubleshooting](#17-troubleshooting)
18. [Production Notes](#18-production-notes)

---

## 1. Project Overview

Firduty automates duty roster management for schools in Oman.

| Actor | What they do |
|---|---|
| **Admin** | Creates duty locations and shifts; builds weekly plans; approves teacher accounts; monitors the dashboard |
| **Teacher** | Registers via the Flutter app; receives push notifications about assigned duties; confirms attendance; earns points |

**Core workflow:**
1. Admin creates shifts and locations once
2. Every Thursday at 16:00 (Muscat timezone), the scheduler auto-clones the latest published week as a draft for next week
3. Admin fills in assignments in the planner and publishes the week
4. Assigned teachers receive FCM push notifications (Android native + Web Push / iOS PWA)
5. Teachers confirm duty attendance from the app; points are awarded based on punctuality

---

## 2. System Architecture

```
┌─────────────────────────────────────────────┐
│        Flutter App (Android APK + Web PWA)  │  ← teachers
│  lib/screens/ · lib/services/              │
│  Android: FCM native push                   │
│  Web/iOS: FCM Web Push via service worker   │
└──────────────┬──────────────────────────────┘
               │  REST API (JSON)
               ▼
┌─────────────────────────────────────────────┐
│           FastAPI Backend (Koyeb)           │
│  routers/ · services/ · jobs/               │
│  APScheduler (weekly auto-clone, monthly    │
│  points rebuild)                            │
└──────────┬────────────────┬─────────────────┘
           │                │
  ┌────────▼───────┐  ┌─────▼──────────────────┐
  │  PostgreSQL    │  │  Firebase Admin SDK     │
  │  (Supabase)    │  │  (FCM push dispatch)    │
  └────────────────┘  └────────────────────────┘

┌─────────────────────────────────────────────┐
│         Admin Web UI (static HTML/JS)       │  ← school admins
│  admin_ui/ · no build step required         │
│  Served from any static host or Koyeb       │
└─────────────────────────────────────────────┘
```

---

## 3. Project Structure

```
firduty/
├── backend/                    FastAPI application (Python)
│   ├── main.py                 App entry point, router registration
│   ├── config.py               Settings class, all env var reads
│   ├── database.py             SQLAlchemy engine + session
│   ├── scheduler.py            APScheduler jobs (auto-clone, monthly reset)
│   ├── requirements.txt        Python dependencies
│   ├── alembic.ini             Alembic migration config
│   ├── .env.example            Copy to .env for local dev
│   ├── alembic/versions/       Alembic migration scripts
│   ├── models/                 SQLAlchemy ORM models
│   ├── schemas/                Pydantic request/response schemas
│   ├── routers/                FastAPI route handlers
│   ├── services/               Business logic
│   └── jobs/                   Scheduler job implementations
│
├── firduty_app/                Flutter mobile + web app (Dart)
│   ├── lib/
│   │   ├── main.dart           App entry, Firebase init, routing
│   │   ├── firebase_options.dart  Firebase platform config
│   │   ├── app_theme.dart      Brand colors + Material 3 theme
│   │   ├── screens/            UI screens
│   │   └── services/
│   │       ├── api_service.dart    All HTTP calls (single URL source of truth)
│   │       └── notification_service.dart  FCM setup
│   ├── android/
│   │   └── app/google-services.json  Firebase Android config
│   ├── web/
│   │   ├── index.html          PWA shell + SW registration
│   │   └── firebase-messaging-sw.js  FCM background push handler
│   └── pubspec.yaml            Flutter package config
│
├── admin_ui/                   Admin web interface (pure HTML/JS)
│   ├── *.html                  Dashboard, planner, teachers, reports pages
│   ├── css/style.css
│   └── js/                     Page scripts + shared auth/i18n
│
└── migrations/                 Manual SQL migration scripts (legacy)
```

---

## 4. Prerequisites

Install these before starting:

### Required for everyone

| Tool | Min version | Install |
|---|---|---|
| Git | any | https://git-scm.com |
| Python | ≥ 3.10 | https://python.org |
| Flutter SDK | ≥ 3.19 | https://flutter.dev/docs/get-started/install |
| Dart | bundled with Flutter | — |
| Chrome browser | any | For Flutter Web dev |

### Required for Android builds

| Tool | Notes |
|---|---|
| Android Studio | Installs Android SDK, emulator tools |
| Android SDK | API level ≥ 33 recommended |
| JDK | ≥ 17 (bundled with Android Studio) |
| USB debug-enabled device **or** Android/Genymotion emulator | For running the app |

### Required for Firebase setup

| Tool | Notes |
|---|---|
| Firebase CLI | `npm install -g firebase-tools` then `firebase login` |
| FlutterFire CLI | `dart pub global activate flutterfire_cli` |
| Node.js | ≥ 16 (required by Firebase CLI) |

### Required for backend

| Tool | Notes |
|---|---|
| Python ≥ 3.10 | `python3 --version` to check |
| pip | Bundled with Python |
| PostgreSQL client (`psql`) | Optional — for running SQL manually |

---

## 5. First-Time Setup Checklist

Run these steps in order for a complete working system:

```
[ ] 1.  Clone the repository
[ ] 2.  Set up the backend Python environment
[ ] 3.  Configure backend .env (database, admin credentials, etc.)
[ ] 4.  Run Alembic migrations to create the database schema
[ ] 5.  Start the backend server
[ ] 6.  Create a Firebase project
[ ] 7.  Register the Android app in Firebase and download google-services.json
[ ] 8.  Register the Web app in Firebase
[ ] 9.  Run flutterfire configure to generate firebase_options.dart
[ ] 10. Fill in kVapidPublicKey in firebase_options.dart
[ ] 11. Fill in firebase-messaging-sw.js with real Firebase web config
[ ] 12. flutter pub get
[ ] 13. Run Flutter app on Android or Web
[ ] 14. Open Admin UI, log in, create a shift and location
[ ] 15. Register as a teacher in the Flutter app
[ ] 16. Approve the teacher in the Admin UI
[ ] 17. Assign the teacher to a duty in the Week Planner and publish
[ ] 18. Verify the teacher receives a push notification
```

---

## 6. Backend Setup

### 6a. Clone and enter the project

```bash
git clone https://github.com/YOUR-USERNAME/firduty.git
cd firduty
```

### 6b. Create a Python virtual environment

```bash
cd backend/

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Windows (Command Prompt)
.venv\Scripts\activate.bat
```

### 6c. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 6d. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```dotenv
# PostgreSQL connection string from Supabase (or local Postgres)
DATABASE_URL=postgresql://user:password@host:5432/dbname

# JWT signing key — generate with:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-64-character-random-string

# Admin login credentials for the Admin Web UI
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-strong-password

# CORS — use * for local dev, set specific origins in production
ALLOWED_ORIGINS=*
```

> Firebase and VAPID keys are optional for local development.
> Push notifications will simply not work until they are configured.

### 6e. Start the backend

```bash
uvicorn main:app --reload --port 8000
```

The API is now available at:
- **API root:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

---

## 7. Database Setup

### 7a. New installation

```bash
cd backend/
alembic upgrade head
```

This creates all required tables from scratch. If `DATABASE_URL` is not set, SQLite is used automatically at `backend/firduty.db` — convenient for local dev with no PostgreSQL required.

### 7b. Production database (Supabase)

1. Create a new project at https://supabase.com
2. Go to **Project Settings → Database → Connection string (URI)**
3. Copy the URI and set it as `DATABASE_URL` in your `.env`
4. Run `alembic upgrade head`

### 7c. Existing database — schema drift fix

If your production database was created before v2.3.0 and is missing the `email`/`status` columns:

```bash
cd backend/
alembic stamp 0001        # mark 0001 as already applied
alembic upgrade 0002      # apply only the column additions
```

Or run `migrations/004_production_fix.sql` directly in the Supabase SQL editor.

---

## 8. Flutter App Setup

### 8a. Install dependencies

```bash
cd firduty_app/
flutter pub get
```

### 8b. Verify Flutter environment

```bash
flutter doctor
```

Resolve any issues shown before continuing.

### 8c. API base URL — quick reference

The backend URL is injected at build/run time via `--dart-define=API_BASE_URL=...`.
The table below shows the correct value for each environment:

| Environment | Correct `API_BASE_URL` |
|---|---|
| Flutter Web (Chrome) | `http://localhost:8000` |
| Android Studio Emulator (AVD) | `http://10.0.2.2:8000` |
| **Genymotion Emulator** | **`http://10.0.3.2:8000`** |
| Physical device (same WiFi) | `http://<YOUR-LAN-IP>:8000` |
| Production | `https://your-app.koyeb.app` |

> `API_BASE_URL` must **not** have a trailing slash.
>
> To find your LAN IP: `ifconfig | grep "inet "` (macOS/Linux) · `ipconfig` (Windows)

---

## 8d. Genymotion Networking — Full Guide

This section explains how the network path works inside Genymotion and how to
configure the Flutter app to reach the backend running on your host machine.

### Why a special IP is needed

Android emulators run in a virtual machine that has its own virtual network.
They cannot use `localhost` because that resolves to the emulator itself, not
the host machine where the backend is running.

Each emulator platform reserves a special host alias:

| Emulator | Host alias | Notes |
|---|---|---|
| **Genymotion** | **`10.0.3.2`** | Standard Genymotion host alias in all versions ≥ 2.0 |
| Android Studio AVD | `10.0.2.2` | Built into the QEMU-based Android emulator |
| `localhost` / `127.0.0.1` | ❌ Won't work | Resolves to the emulator itself |
| `169.254.0.101` | ❌ Wrong | Legacy/bridge IP used in very old Genymotion versions — unreliable |

### Step-by-step: running Firduty on Genymotion

**1. Start the backend on your host machine:**

```bash
cd backend/
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> Use `--host 0.0.0.0` so the backend listens on all interfaces,
> not just `127.0.0.1`. This is required for the emulator to reach it.

**2. Verify the backend is reachable from the host:**

Open a browser on your host machine and check:
- Health check: http://localhost:8000/health → should return `{"status":"ok"}`
- Swagger UI:   http://localhost:8000/docs   → should show the API explorer

**3. Start Genymotion and boot a device.**

**4. Verify connectivity from inside Genymotion (optional but recommended):**

Open the browser inside the Genymotion emulator and navigate to:
```
http://10.0.3.2:8000/health
```
You should see `{"status":"ok"}`. If you see "Connection refused", check:
- The backend is running with `--host 0.0.0.0`
- Your host firewall is not blocking port 8000

**5. Run the Flutter app targeting the Genymotion device:**

```bash
cd firduty_app/

# List devices — confirm Genymotion appears
flutter devices

# Run with the correct host alias
flutter run \
  -d <genymotion-device-id> \
  --dart-define=API_BASE_URL=http://10.0.3.2:8000
```

### Quick command reference

```bash
# Flutter Web (Chrome)
flutter run -d chrome \
  --dart-define=API_BASE_URL=http://localhost:8000

# Android Studio Emulator (AVD)
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000

# Genymotion Emulator  ← USE THIS FOR GENYMOTION
flutter run \
  --dart-define=API_BASE_URL=http://10.0.3.2:8000

# Physical Android device (replace with your actual LAN IP)
flutter run \
  --dart-define=API_BASE_URL=http://192.168.1.42:8000
```

### Finding your LAN IP (for physical device testing)

```bash
# macOS / Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig | findstr "IPv4"
```

Use the `192.168.x.x` address you find as the `API_BASE_URL` host.

---

### 8e. Run on Android (any emulator or device)

```bash
# List available devices
flutter devices

# Run — pick the correct IP from the table in 8c
flutter run -d <device-id> --dart-define=API_BASE_URL=http://10.0.3.2:8000
```

### 8f. Run on Web (Chrome)

```bash
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

---

## 9. Firebase Setup

Firebase is required for push notifications. The app runs without it, but teachers won't receive push alerts.

### 9a. Create a Firebase project

1. Go to https://console.firebase.google.com
2. Click **Add project**, name it (e.g. `firduty`)
3. Disable Google Analytics if not needed, or enable it (optional)

### 9b. Register the Android app

1. In your Firebase project, click **Add app → Android**
2. Set the **Android package name** to match `firduty_app/android/app/build.gradle`:
   ```
   com.example.firduty_mobile
   ```
3. Download `google-services.json`
4. Place it at: `firduty_app/android/app/google-services.json`

### 9c. Register the Web app

1. Click **Add app → Web**
2. Give it a nickname (e.g. `firduty-web`)
3. You do NOT need Firebase Hosting — just register the app
4. Note down the config object shown:
   ```js
   {
     apiKey: "...",
     authDomain: "...",
     projectId: "...",
     storageBucket: "...",
     messagingSenderId: "...",
     appId: "..."
   }
   ```

### 9d. Run FlutterFire CLI to generate firebase_options.dart

```bash
# Install FlutterFire CLI if not already installed
dart pub global activate flutterfire_cli

# From inside firduty_app/
cd firduty_app/
flutterfire configure
```

Select your Firebase project when prompted. This generates `lib/firebase_options.dart` with all platform values filled in.

> If `flutterfire configure` fails, you can manually fill in `firebase_options.dart`
> using the values from your `google-services.json` (Android) and Firebase Console web config.

### 9e. Set up the VAPID key for Web Push

VAPID keys allow Firebase to send Web Push notifications to browsers and iOS Safari PWA.

1. Firebase Console → **Project Settings** → **Cloud Messaging** tab
2. Scroll to **Web Push certificates**
3. Click **Generate key pair**
4. Copy the **Key pair** value (the public key)
5. Open `firduty_app/lib/firebase_options.dart` and set:
   ```dart
   const String kVapidPublicKey = 'YOUR_VAPID_PUBLIC_KEY_HERE';
   ```
6. Also set it in `backend/.env`:
   ```dotenv
   VAPID_PUBLIC_KEY=YOUR_VAPID_PUBLIC_KEY_HERE
   ```

### 9f. Update firebase-messaging-sw.js

The file `firduty_app/web/firebase-messaging-sw.js` must contain your real Firebase web config so background push notifications work in the browser.

Open the file and verify the `firebase.initializeApp({...})` block matches the values in `firebase_options.dart → FirebaseOptions.web`.

```js
firebase.initializeApp({
  apiKey:            "YOUR_API_KEY",
  authDomain:        "YOUR_PROJECT.firebaseapp.com",
  projectId:         "YOUR_PROJECT_ID",
  storageBucket:     "YOUR_PROJECT.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId:             "YOUR_WEB_APP_ID",
});
```

> **Important:** The service worker is cached by the browser. After updating it,
> open Chrome DevTools → Application → Service Workers → click **Update** to force reload.

### 9g. Set up Firebase Admin SDK for the backend

The backend uses Firebase Admin SDK to send FCM push notifications.

1. Firebase Console → **Project Settings** → **Service accounts**
2. Click **Generate new private key**
3. Download the JSON file
4. Save it as `backend/firebase-credentials.json`
5. Set in `backend/.env`:
   ```dotenv
   FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
   ```

For Koyeb (no file system persistence), use the inline JSON option:
```dotenv
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}
```

---

## 10. Notifications Setup

### Android notifications

- FCM native tokens are used automatically
- Notification channel `firduty_channel` is created on first launch
- Android 13+ requires explicit notification permission (requested by the app)
- Background messages: shown by the OS automatically
- Foreground messages: shown via `flutter_local_notifications`

**Requirements:**
- `google-services.json` must be in `firduty_app/android/app/`
- Firebase Admin SDK credentials must be set in the backend

### Web push / iOS PWA notifications

- FCM Web Push via VAPID keys
- Works on Chrome, Edge, Firefox, Safari 16.4+ (iOS/iPadOS PWA)
- Background messages handled by `firebase-messaging-sw.js`
- Foreground messages: handled by `notification_service.dart`

**Requirements:**
- `kVapidPublicKey` must be set in `firebase_options.dart`
- `VAPID_PUBLIC_KEY` must be set in backend `.env`
- `firebase-messaging-sw.js` must have the real Firebase web config
- iOS: the user must have added the app to Home Screen ("Add to Home Screen" in Safari)
- iOS Safari 16.4+ minimum

**iOS limitations:**
- Push only works when the PWA is installed to the Home Screen
- iOS Safari does not support background push for regular browser tabs
- The notification permission dialog may not appear on older iOS

---

## 11. Admin UI Setup

No build step required. Pure HTML/JS.

### Option A — open directly in browser

```bash
# macOS
open admin_ui/login.html

# Linux
xdg-open admin_ui/login.html

# Windows
start admin_ui/login.html
```

### Option B — serve locally (recommended)

```bash
cd admin_ui/
python3 -m http.server 3000
```
Open: http://localhost:3000/login.html

### Configure API URL for local dev

The Admin UI reads the API base URL from `localStorage`. For local development:

1. Open the Admin UI login page in Chrome
2. Open DevTools → Application → Local Storage → `http://localhost:3000`
3. Add:
   - Key: `firduty_api`
   - Value: `http://localhost:8000`
4. Refresh the page

### Default credentials

Use the values of `ADMIN_USERNAME` and `ADMIN_PASSWORD` from your `.env`.
Defaults are `admin` / `admin123` — **change these in production**.

---

## 12. Environment Variables Reference

All backend variables go in `backend/.env` (local) or Koyeb service environment (production).

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | SQLite | PostgreSQL URI from Supabase (or local Postgres) |
| `SECRET_KEY` | **Yes** | `dev-secret-key-...` | JWT signing key — 64 random hex chars |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `1440` | JWT lifetime (24 hours) |
| `ADMIN_USERNAME` | **Yes** | `admin` | Admin Web UI login username |
| `ADMIN_PASSWORD` | **Yes** | `admin123` | Admin Web UI login password — **change this** |
| `FIREBASE_CREDENTIALS_PATH` | Recommended | `./firebase-credentials.json` | Path to Firebase service account JSON |
| `FIREBASE_CREDENTIALS_JSON` | Alternative | — | Entire Firebase JSON as an env var string |
| `VAPID_PRIVATE_KEY` | For web push | — | VAPID private key (base64url) |
| `VAPID_PUBLIC_KEY` | For web push | — | VAPID public key — must also be in `firebase_options.dart` |
| `VAPID_CONTACT_EMAIL` | For web push | `admin@yourschool.com` | Email in VAPID claims |
| `PORT` | No | `8000` | Injected by Koyeb automatically |
| `ALLOWED_ORIGINS` | **Yes** | `*` | Comma-separated CORS origins |
| `RUN_SCHEDULER` | No | `true` | Set `false` on extra instances to prevent duplicate jobs |
| `SCHEDULER_JITTER` | No | `30` | Random seconds added to job triggers |

### Flutter app variable (build-time only)

| Variable | Where | Description |
|---|---|---|
| `API_BASE_URL` | `--dart-define` at build/run time | Backend URL, no trailing slash |

### Flutter app file variables

| Variable | File | Description |
|---|---|---|
| `kVapidPublicKey` | `lib/firebase_options.dart` | VAPID public key for web push token |

---

## 13. Running the Full System Locally

### Terminal 1 — Backend

```bash
cd backend/
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> Use `--host 0.0.0.0` so the backend is reachable from Genymotion (`10.0.3.2`)
> and from physical devices on the same WiFi network.

### Terminal 2 — Admin UI

```bash
cd admin_ui/
python3 -m http.server 3000
```

Open http://localhost:3000/login.html

### Terminal 3 — Flutter app

```bash
cd firduty_app/

# Genymotion emulator
flutter run --dart-define=API_BASE_URL=http://10.0.3.2:8000

# Android Studio emulator (AVD)
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000

# Flutter Web (Chrome)
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000
```

### End-to-end verification flow

1. Open Swagger UI: http://localhost:8000/docs → Authorize → create a shift and location
2. Open Admin UI: http://localhost:3000/login.html → log in
3. Open Flutter app → register as a teacher
4. Admin UI → Teachers → approve the teacher
5. Flutter app → teacher should now see the home screen
6. Admin UI → Week Planner → assign the teacher to a slot → Publish Week
7. Flutter app → teacher receives push notification (if Firebase is configured)
8. Flutter app → Today tab → Confirm the duty

---

## 14. Building for Production

### Android APK

```bash
cd firduty_app/
flutter build apk --release \
  --dart-define=API_BASE_URL=https://your-app.koyeb.app
```

Output: `build/app/outputs/flutter-apk/app-release.apk`

### Flutter Web (PWA)

```bash
cd firduty_app/
flutter build web --release \
  --dart-define=API_BASE_URL=https://your-app.koyeb.app \
  --base-href "/"
```

Output: `build/web/` — deploy this directory to any static host (Netlify, Vercel, Koyeb Static, etc.)

---

## 15. Koyeb Deployment

### Backend

1. Push `backend/` contents to a GitHub repository
2. Create a Koyeb service:
   - **Type:** Web service
   - **Runtime:** Python 3.11
   - **Build command:** `pip install -r requirements.txt`
   - **Run command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Root directory:** `backend/`
3. Set all environment variables from Section 12
4. After first deploy, run migrations:
   ```bash
   # From your local machine, pointing at the production DATABASE_URL:
   cd backend/
   alembic upgrade head
   ```

### Flutter Web / PWA

Build with `flutter build web --release ...` then deploy `build/web/` to:
- Netlify: drag-and-drop or `netlify deploy --prod --dir build/web`
- Vercel: `vercel --prod build/web`
- Koyeb Static: upload `build/web/`

### Keep-alive (free tier)

The repository includes `.github/workflows/keepalive.yml` which pings the Koyeb service every 14 minutes to prevent the free tier from sleeping.

---

## 16. Development Workflow

### Recommended startup sequence

```bash
# Terminal 1: backend (always first) — bind to all interfaces for emulator access
cd backend && source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Admin UI (optional)
cd admin_ui && python3 -m http.server 3000

# Terminal 3: Flutter app (pick the right URL for your setup)
cd firduty_app
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000    # Web
flutter run --dart-define=API_BASE_URL=http://10.0.3.2:8000               # Genymotion
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000               # AVD
```

### Common commands

```bash
# Install/update Flutter dependencies
cd firduty_app && flutter pub get

# Regenerate l10n strings (after editing .arb files)
cd firduty_app && flutter gen-l10n

# Clean Flutter build cache
cd firduty_app && flutter clean && flutter pub get

# Backend: run tests
cd backend && pytest

# Backend: new migration after changing models
cd backend && alembic revision --autogenerate -m "describe change"
cd backend && alembic upgrade head
```

### Hot restart vs full restart

| Action | Dart side | Firebase side | When to use |
|---|---|---|---|
| **Hot reload** (`r`) | Code patched | Unchanged | UI-only changes |
| **Hot restart** (`R`) | Dart VM restarted | **Web**: JS runtime SURVIVES (Firebase app still alive) | State reset |
| **Full restart** (stop + run) | Full restart | Full restart | Firebase config changes |

> On Flutter Web, `Firebase.apps.isEmpty` guard prevents the `duplicate-app` error on hot restart.
> On Android, the Dart VM is torn down on hot restart, so Firebase.apps is always empty — no issue.

---

## 17. Planner Feature Guide

This section documents features added in v3.x that change admin workflow.

---

### 17a. Re-publishing after edits (always-on Publish button)

**Previous behaviour:** After a day was published, the "Publish Day" button was replaced with a static "Published ✓" badge. The admin could not re-publish after making corrections.

**New behaviour:** The Publish Day button is **always clickable**:

| Day state | Button label | Button colour |
|---|---|---|
| Never published | Publish Day | Green |
| Previously published | ↻ Re-publish Day | Amber |

The Publish Week button in the toolbar is also always available.

Both actions are **idempotent on the backend** — calling publish on an already-published week or day is safe. The week's version counter increments on each full-week publish.

**How to edit and re-publish:**
1. Load the week in the planner.
2. Drag/tap teachers to re-assign slots.
3. Click **↻ Re-publish Day** (for a single day) or **Publish Week** (for all days).
4. The notify-scope dialog appears — choose who to notify.

---

### 17b. Notify-scope dialog

Every publish action (Publish Week and Re-publish Day) now shows a modal instead of the old `confirm()` browser prompt. This lets the admin choose exactly who receives a push notification.

```
┌─────────────────────────────────────────────┐
│  Publish the entire week?                   │
│  Who should receive a push notification?    │
│                                             │
│  🔔 Notify all assigned teachers            │
│  📋 Notify affected teachers only (3)       │
│  🔕 Publish without notifying               │
│  ✕  Cancel                                  │
└─────────────────────────────────────────────┘
```

| Choice | Who gets notified | When to use |
|---|---|---|
| **Notify all** | Every teacher currently assigned in the week/day | First publish of a week |
| **Notify affected only** | Only teachers whose assignments changed in this editing session | Corrections after initial publish |
| **Publish without notifying** | Nobody | Admin proofing/testing, or when teachers have already been told verbally |
| **Cancel** | Nobody; no publish happens | Abort |

**"Affected teachers"** are tracked automatically by the planner. Any teacher dragged into or removed from a slot in the current session is added to the affected set. The count is shown in the button label. The set resets after a successful publish.

**API behaviour:** The `notify_scope` field is sent in the publish request body:

```json
PUT /weeks/2025-03-02/status
{
  "status": "published",
  "notify_scope": "affected",
  "notify_teacher_ids": [12, 34, 57]
}
```

`notify_scope` values: `"all"` | `"affected"` | `"none"`

For Publish Day, the same params are passed as query parameters:
```
PUT /weeks/2025-03-02/publish-day?day_date=2025-03-03&notify_scope=affected&notify_teacher_ids=12&notify_teacher_ids=34
```

---

### 17c. Break duty grid (fixed slots, static labels)

Break duties (First Break, Second Break) are now rendered as a **responsive CSS grid** instead of a single column.

- Each cell shows the **grade class label** (e.g. `1/A`, `2/B`) as a fixed badge — always visible, even when no teacher is assigned.
- Grade class labels are **pre-seeded** in the database and are not user-selectable. The admin only needs to drag a teacher to the correct cell.
- Slots are **fixed** — Sortable's ghost element is hidden with `display:none` inside the grid so cells never shift sideways during a drag.
- No +/− slot count controls for break duties (the number of classes is fixed by the school structure).

**On desktop:** Drag a teacher from the sidebar onto any break cell.
**On mobile:** Tap a break cell → bottom-sheet teacher picker opens → select teacher.

---

### 17d. Shift time editing in the planner

Every shift panel shows a compact time bar:

```
🕐 07:00 – 07:40  ✏️
```

Clicking ✏️ expands an inline editor:

```
🕐 07:00 – 07:40  ✏️
         [07:00] – [07:40]  [Save]  [Cancel]  — applies to all days
```

Saving calls `PUT /shifts/{id}` with the new times. Because shift times are stored globally in the `shifts` table (not per-day), the change automatically applies to:
- All days in the current week (planner re-renders immediately)
- All future weeks (they JOIN to the same shift row)
- Mobile duty cards (next refresh)

**Validation:** End time must be strictly after start time — enforced client-side before any API call and server-side in the shift endpoint.

---

## 18. Troubleshooting

### `[core/duplicate-app] A Firebase App named "[DEFAULT]" already exists`

**Cause:** Flutter Web hot restart — the Firebase JS SDK survives between Dart restarts.

**Fix (already applied in this codebase):**
```dart
// In main.dart — this is already in place:
try {
  if (Firebase.apps.isEmpty) {
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  }
} catch (e) {
  debugPrint('[Firebase] Init skipped: $e');
}
```

If you still see this error: do a **full restart** (stop the app completely and run again).

---

### App shows "Could not reach the server" on Genymotion

**Most common cause:** `API_BASE_URL` is set to `localhost`, `127.0.0.1`, or the Android Studio alias `10.0.2.2`. None of these resolve to your host machine from inside Genymotion.

**Fix:** Use the Genymotion host alias `10.0.3.2`:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.3.2:8000
```

**Also check:**
1. The backend is started with `--host 0.0.0.0` (not the default `127.0.0.1`):
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
2. Your host machine firewall is not blocking port 8000
3. From inside the Genymotion browser, navigate to `http://10.0.3.2:8000/health` — it should return `{"status":"ok"}`

---

### App shows "API_BASE_URL is not configured"

**Cause:** The app was run without `--dart-define=API_BASE_URL=...`.

**Fix:** Always pass the URL:
```bash
flutter run --dart-define=API_BASE_URL=http://10.0.3.2:8000   # Genymotion
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # AVD
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000  # Web
```

---

### App shows "Endpoint not found (404)" or "Not Found"

**Cause:** The backend is reachable but the URL path is wrong. Usually caused by a trailing slash in `API_BASE_URL` or a wrong path in a request.

**Fix:**
1. Make sure `API_BASE_URL` does **not** end with `/`
   - ❌ `http://10.0.3.2:8000/`
   - ✅ `http://10.0.3.2:8000`
2. In debug mode, `api_service.dart` logs every request with the full URL:
   ```
   [API] GET http://10.0.3.2:8000/teachers/5/status → 404
           body: {"detail":"Teacher not found"}
   ```
   Check the logged URL and compare it against the Swagger UI at `http://localhost:8000/docs`.

---

### App shows "Server is starting up" (502/503)

**Cause:** The Koyeb free tier is sleeping after inactivity. The first request wakes it up.

**Fix:** Wait 10–20 seconds and try again. Consider setting up the keepalive workflow in `.github/workflows/keepalive.yml` to prevent sleep.

---

### Flutter: no devices found

```bash
flutter devices    # list available devices
flutter emulators  # list available emulators
flutter emulators --launch <emulator-id>
```

If Android emulator is not listed:
- Open Android Studio → Virtual Device Manager
- Create a new virtual device (Pixel series recommended, API 33+)
- Start it, then run `flutter devices` again

For Genymotion:
- Ensure Genymotion is open and the device is running
- Ensure the Genymotion ADB bridge is enabled: Genymotion Settings → ADB → Use custom Android SDK tools
- Point it to your Android SDK path

---

### Flutter Web: CORS error when calling backend

Set `ALLOWED_ORIGINS=*` in `backend/.env` for local development.

For production, set specific origins:
```dotenv
ALLOWED_ORIGINS=https://your-admin-ui.netlify.app,https://your-flutter-web.vercel.app
```

---

### Backend: `DATABASE_URL environment variable is required`

Set `DATABASE_URL` in `backend/.env`. For local SQLite testing:
```dotenv
DATABASE_URL=sqlite:///./firduty.db
```

> Note: `config.py` raises a `ValueError` if `DATABASE_URL` is empty. This is intentional.

---

### Push notifications not working (Android)

1. Check `google-services.json` is in `firduty_app/android/app/`
2. Check `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` is set in backend `.env`
3. Check the teacher's device token was registered: look at `POST /teachers/{id}/device-token` in Swagger
4. Check Android notification permission: Settings → Apps → Firduty → Notifications → Enable

---

### Push notifications not working (Web / iOS PWA)

1. Verify `firebase-messaging-sw.js` has the **real** Firebase config values (not placeholders)
2. Verify `kVapidPublicKey` in `firebase_options.dart` is set
3. Verify `VAPID_PUBLIC_KEY` in backend `.env` is set and matches
4. Check the service worker is registered: Chrome DevTools → Application → Service Workers
5. Check notification permission: browser URL bar lock icon → Notifications → Allow
6. iOS: the app MUST be installed as a PWA (Safari → Share → Add to Home Screen)

**Force-refresh the service worker (Chrome):**
DevTools → Application → Service Workers → check "Update on reload" → refresh page

---

### Service worker not activating (Chrome)

```
chrome://serviceworker-internals/
```

Find your service worker URL and click **Unregister**, then reload the app.

---

### `flutter pub get` fails

```bash
flutter clean
flutter pub cache repair
flutter pub get
```

---

### Backend 422 Unprocessable Entity from Swagger

**Cause:** Swagger sends `application/x-www-form-urlencoded` but the endpoint may expect JSON.

**Fix:** Use `/auth/admin/login` (form body) for Swagger, and `/auth/admin/login/json` (JSON) for the Admin UI.

---

### `GET /locations/ returns only one item`

**Cause:** Pydantic v1 installed instead of v2.

**Fix:**
```bash
cd backend/
pip install "pydantic>=2.0.0"
pip install -r requirements.txt
```

---

### Supabase: `column email does not exist`

Your database schema is outdated. Run:
```bash
cd backend/
alembic stamp 0001
alembic upgrade 0002
```

---

## 19. Production Notes

### Security checklist before going live

- [ ] Change `ADMIN_PASSWORD` to a strong random password
- [ ] Change `SECRET_KEY` to a 64-character random hex string
- [ ] Set `ALLOWED_ORIGINS` to specific domains (not `*`)
- [ ] Store `firebase-credentials.json` securely (Koyeb secrets or env var)
- [ ] Never commit `.env`, `firebase-credentials.json`, or `google-services.json` to Git
- [ ] Rotate VAPID keys if they were ever exposed

### Notification caveats

- **Android:** Notifications work in both foreground and background
- **Web Chrome/Edge/Firefox:** Notifications work when the browser is open (even in background tabs)
- **iOS Safari PWA:** Requires iOS 16.4+; app must be added to Home Screen; background push works when the PWA is installed
- **iOS Safari (browser tab, not PWA):** Push notifications do NOT work on iOS Safari in a regular tab

### Scheduler

Two background jobs run automatically:

| Job | Schedule | Description |
|---|---|---|
| `auto_clone` | Every Thursday 16:00 Muscat | Auto-clones the latest published week as a draft for next week |
| `monthly_reset` | 1st of each month 20:05 Muscat | Rebuilds monthly points summary for all teachers |

Both jobs are **idempotent** — running them twice is safe.

**Multi-instance note:** If Koyeb scales to multiple instances, each instance runs the scheduler. Set `RUN_SCHEDULER=false` on all instances except one to prevent duplicate runs.

### CORS for production

```dotenv
ALLOWED_ORIGINS=https://your-admin-ui.example.com,https://your-flutter-web.example.com
```

### Database

Use Supabase free tier for production. The connection string format is:
```
postgresql://postgres:PASSWORD@db.PROJECT-REF.supabase.co:5432/postgres
```

Enable **Row Level Security (RLS)** on Supabase if direct database access from the frontend is ever used. (Currently only the backend API accesses the database directly.)

## 20. v3.2.0 Feature Guide

This section documents all changes introduced in v3.2.0.

---

### 20a. Publish Day / Re-publish Day now visible to teachers (Phase 1 fix)

**Root cause (fixed):** `publish_day()` in `week_service.py` set `day.is_published = True`
but never changed `week.status`. Both teacher schedule endpoints gated visibility on
`week.status == "published"`, so publishing a single day was completely invisible.

**Three fixes applied:**

1. `week_service.py → publish_day()` — now also promotes `week.status = "published"`
   when the first day is published (idempotent — safe to call repeatedly).

2. `teachers.py → _build_schedule_response()` — now gates per-day visibility on
   `day.is_published` rather than `week_plan.status`, so a teacher sees today's
   duties as soon as that specific day is published, even if other days are still
   unpublished.

3. `teachers.py → _build_week_response()` — now skips days where `is_published == False`,
   so the weekly view only shows days that have been explicitly published.

No SQL migrations required — `day_plans.is_published` already existed.

---

### 20b. Duty reminder notifications (Phase 2)

**New backend job:** `jobs/duty_reminders.py` runs every 60 seconds via APScheduler.

| Notification type | When sent | Template key |
|---|---|---|
| `reminder_15m` | 14–15 minutes before shift start | `reminder_location` / `reminder_break` |
| `duty_started` | 0–1 minute past shift start | `start_location` / `start_break` |

**Deduplication:** Each sent notification is recorded in `notification_logs`
(UNIQUE constraint on `teacher_id + assignment_id + notification_type`).
The job can safely run multiple times — it uses INSERT-with-conflict to skip
already-sent rows.

**New Supabase SQL** (run in Supabase SQL Editor):

```sql
CREATE TABLE IF NOT EXISTS notification_logs (
    id                SERIAL PRIMARY KEY,
    teacher_id        INTEGER NOT NULL REFERENCES teachers(id)    ON DELETE CASCADE,
    assignment_id     INTEGER NOT NULL REFERENCES assignments(id)  ON DELETE CASCADE,
    notification_type VARCHAR(30)  NOT NULL,
    sent_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    status            VARCHAR(10)  NOT NULL DEFAULT 'sent',
    CONSTRAINT uq_notif_teacher_assignment_type
        UNIQUE (teacher_id, assignment_id, notification_type)
);
CREATE INDEX IF NOT EXISTS ix_notif_teacher_id ON notification_logs (teacher_id);
CREATE INDEX IF NOT EXISTS ix_notif_sent_at    ON notification_logs (sent_at);
```

---

### 20c. Teacher Login flow (Phase 3)

Teachers now log in using **name + email only** — no password, no OTP.

**How it works:**

1. First time: Teacher opens the app → **Login screen**
   - Taps "Don't have an account?" → **Registration screen**
   - Fills name + email → `POST /teachers/register` → status = `pending`
   - Admin approves in Admin UI → status = `approved`
2. Return visits: Teacher opens app → **Login screen**
   - Enters same name + email → `POST /teachers/login`
   - Backend matches email (case-insensitive), soft-verifies name
   - Returns teacher record; Flutter stores `teacher_id` in SharedPreferences
   - Navigates to `/home` (approved) or `/pending` (awaiting approval)

**New endpoint:**

```
POST /teachers/login
Body: { "name": "Ahmed Ali", "email": "ahmed@school.edu.om" }

200 → teacher record (approved)
403 → pending or inactive
404 → no account with that email
409 → name does not match registered name for that email
```

**Session persistence:** `teacher_id` is stored in `SharedPreferences`. On every
app launch, `StartupScreen` reads it and routes directly to the appropriate screen
— no re-login required until the teacher explicitly logs out.

**Logout:** tap the logout icon (↪ ) in the top-right corner of the HomeScreen.
This clears `teacher_id` from SharedPreferences and returns to the Login screen.

---

### 20d. Flutter push notification tap navigation (Phase 4)

When a teacher taps a push notification (duty reminder or duty-started), the app:

- If **backgrounded** → `FirebaseMessaging.onMessageOpenedApp` fires → navigates to `/home`
- If **terminated** → `getInitialMessage()` returns the message on next launch → navigates to `/home`

This is wired via `NotificationService.navigatorKey`, a `GlobalKey<NavigatorState>`
set on the `MaterialApp` in `main.dart`.

---

### 20e. iOS PWA parity (Phase 5)

The Flutter web build is now fully configured as an iOS PWA:

| Feature | Status |
|---|---|
| Full-screen mode ("Add to Home Screen") | ✅ `apple-mobile-web-app-capable` |
| Status bar styling | ✅ `black-translucent` |
| Correct home-screen icon | ✅ `apple-touch-icon` (192px + 512px) |
| Notch/Dynamic Island safe area | ✅ `viewport-fit=cover` |
| iOS install instructions banner | ✅ Shown in Safari before PWA is installed |
| PWA manifest updated | ✅ Brand colors, correct names, maskable icons |
| Background push notifications | ✅ Via FCM Web Push — requires iOS Safari 16.4+ |

**How to install on iPhone:**

1. Open the app URL in **Safari** (not Chrome or other browsers)
2. The blue install banner will appear at the bottom automatically
3. Tap the **Share ⬆** button in Safari's toolbar
4. Choose **"Add to Home Screen"**
5. Tap **Add** — the app icon appears on the home screen
6. Open from the icon for full-screen, native-like experience

> **Push notifications on iOS PWA require:**
> - iOS 16.4 or later
> - The web app must be installed ("Add to Home Screen") — push does not work from the browser tab
> - Firebase VAPID key must be configured (see Section 9)
> - User must grant notification permission when prompted inside the app

---

### 20f. Admin UI — Publish Day flow (Phase 6)

The admin planner already had Publish Day and Re-publish Day buttons. With the Phase 1
backend fix, these now correctly make duties visible to teachers immediately — no need to
click "Publish Week" first.

**Workflow for partial publishing:**
1. Create or clone a week → edit assignments for Monday
2. Click **Publish Day** on Monday → teachers see Monday's duties immediately
3. Edit Tuesday → click **Re-publish Day** on Tuesday → teachers see Tuesday
4. Continue per-day or click **Publish Week** to publish all remaining days at once

The notify-scope dialog (Phase 3.1 from previous session) lets the admin choose
who receives push notifications on each publish action.

---

*Last updated: v3.2.0 — see CHANGELOG for version history.*
