# Firduty — School Duty Roster Management System

> Full-stack duty roster for schools with bilingual (Arabic/English) support,
> drag-and-drop weekly planning, teacher mobile app, push notifications,
> a points-based attendance system, and an admin analytics dashboard.

---

## What's New in v2.1

### Admin Dashboard
`admin_ui/dashboard.html` — a new page accessible from the navigation bar showing:
- Total active teachers, locations, and shift types
- Current and next week: total/assigned/unassigned slots, breakdown by day, by duty type, by teacher
- Teachers with no duties this week (distribution fairness)
- Ranked top teachers this week
- Warnings for unassigned slots and uneven distribution

### Two Duty Types
Duties now have a `duty_type` on the `Shift` model:

| duty_type | Example shifts | Teacher sees |
|---|---|---|
| `morning_endofday` | Morning Duty, End-of-Day Duty | Location name |
| `break` | Break 1, Break 2, Ramadan Break | Grade / Class |

Configuring duty types is done through the existing Shift CRUD
(`/shifts` endpoints). When creating a shift, set `duty_type` to
`"morning_endofday"` or `"break"`.

**Ramadan mode**: In Ramadan, simply do not add Break 2 to the week plan.
There is no separate setting — the planner is fully flexible. You may also
rename "Break 2" shift to "Ramadan Break" via the Shift edit screen.

### Grade/Class on Break Assignments
Break duty assignments carry a `grade_class` string (e.g. `"Grade 5A"`, `"الصف الخامس أ"`).
The planner shows an inline text input below each filled break-duty slot.
The teacher mobile app displays it in place of the location.

---

## Project Structure

```
firduty/
├── pyrightconfig.json
├── migrations/
│   └── 001_duty_types.sql        ← run this on existing databases
├── backend/
│   ├── main.py                   v2.1.0 — registers dashboard router
│   ├── models/
│   │   └── models.py             Shift.duty_type, ShiftLocation.location_id nullable,
│   │                             Assignment.grade_class
│   ├── schemas/
│   │   └── schemas.py            ShiftCreate/Out include duty_type;
│   │                             AssignmentUpdate includes grade_class;
│   │                             location nullable on ShiftLocationOut
│   ├── routers/
│   │   ├── dashboard.py          NEW — GET /admin/dashboard
│   │   ├── teachers.py           schedule/week responses include duty_type + grade_class
│   │   └── weeks.py              _serialize_week includes duty_type + grade_class;
│   │                             update_assignment passes grade_class
│   └── services/
│       ├── week_service.py       clone preserves grade_class; update_assignment has grade_class param;
│       │                         update_shift_location_slots accepts Optional location_id
│       ├── notification_service.py  duty-type-aware templates (break vs location)
│       └── points_service.py       confirmation detail returns duty_type + grade_class
├── admin_ui/
│   ├── dashboard.html            NEW — admin dashboard
│   ├── planner.html              updated nav bar
│   ├── js/
│   │   ├── dashboard.js          NEW — dashboard rendering
│   │   └── planner.js            break duty rendering + grade_class input
│   └── i18n/
│       ├── en.json               new keys: dashboard, duty types, grade/class
│       └── ar.json               same in Arabic
└── flutter_app/                  see Flutter section below
```

---

## Database Changes

Run `migrations/001_duty_types.sql` against your PostgreSQL database:

```bash
psql $DATABASE_URL -f migrations/001_duty_types.sql
```

The migration is idempotent — safe to run multiple times.

### SQLite (local dev)
Delete `firduty.db` and re-run `Base.metadata.create_all()`. All tables
are recreated with the new schema. If you need to preserve data, run:
```sql
ALTER TABLE shifts ADD COLUMN duty_type TEXT NOT NULL DEFAULT 'morning_endofday';
ALTER TABLE assignments ADD COLUMN grade_class TEXT;
```
(SQLite's `location_id` column is already effectively nullable — no change needed.)

---

## API Changes

### New endpoint
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/dashboard` | JWT | Dashboard statistics |

### Changed endpoints

**Shifts** — `POST /shifts/`, `PUT /shifts/{id}` now accept `duty_type: str`
```json
{ "name_en": "Break 1", "name_ar": "الاستراحة الأولى",
  "start_time": "10:00", "end_time": "10:20", "duty_type": "break" }
```

**Assignments** — `PUT /weeks/{week_start}/assignments` now accepts `grade_class`
```json
[{ "shift_location_id": 5, "slot_index": 0, "teacher_id": 3, "grade_class": "Grade 5A" }]
```

**Shift locations** — `PUT /weeks/{week_start}/shift-locations` `location_id` is now optional
```json
[{ "day_date": "2026-03-09", "shift_id": 4, "location_id": null, "slots_count": 2 }]
```

**Teacher schedule/week responses** now include:
```json
{
  "duty_type": "break",
  "grade_class": "Grade 5A",
  "location_name_en": null,
  "location_name_ar": null
}
```

---

## Flutter App Changes

Update `today_screen.dart` and `week_screen.dart` to check `duty_type`:

```dart
final dutyType = d['duty_type'] as String? ?? 'morning_endofday';
final isBreak = dutyType == 'break';

// Show location for morning/end-of-day
if (!isBreak) {
  final locName = isAr ? d['location_name_ar'] : d['location_name_en'];
  // render location row
}
// Show grade/class for break
if (isBreak) {
  final gradeClass = d['grade_class'] as String?;
  // render grade/class row
}
```

---

## Duty Type Configuration

### Morning / End-of-day duties (examples)
Create via `POST /shifts/`:
```json
{ "name_en": "Morning Duty",    "name_ar": "مناوبة الصباح",   "start_time": "07:00", "end_time": "07:30", "duty_type": "morning_endofday" }
{ "name_en": "End-of-Day Duty", "name_ar": "مناوبة النهاية", "start_time": "13:30", "end_time": "14:00", "duty_type": "morning_endofday" }
```

### Break duties (examples)
```json
{ "name_en": "Break 1",       "name_ar": "الاستراحة الأولى",  "start_time": "09:45", "end_time": "10:00", "duty_type": "break" }
{ "name_en": "Break 2",       "name_ar": "الاستراحة الثانية", "start_time": "11:30", "end_time": "11:45", "duty_type": "break" }
{ "name_en": "Ramadan Break", "name_ar": "استراحة رمضان",    "start_time": "10:30", "end_time": "10:45", "duty_type": "break" }
```

### Ramadan mode
In Ramadan, do not add Break 2 slots to the week plan. Optionally rename
Break 2's shift to "Ramadan Break" via `PUT /shifts/{id}` and update its times.
No code change or flag is needed.

---

## Environment Variables

No new environment variables were added. All existing variables continue
to work as documented in the v2.0 README.

---

## Setup

### Run migration (existing database)
```bash
psql $DATABASE_URL -f migrations/001_duty_types.sql
```

### Fresh install (SQLite)
```bash
cd backend
python -c "from database import Base, engine; Base.metadata.create_all(bind=engine)"
```

### Start backend
```bash
cd backend && uvicorn main:app --reload --port 8000
```

### Admin UI
```bash
cd admin_ui && python -m http.server 3000
# Dashboard: http://localhost:3000/dashboard.html
# Planner:   http://localhost:3000/planner.html
# Reports:   http://localhost:3000/reports.html
```

---

## Testing New Functionality

1. **Create a break shift**
   `POST /shifts/ {"name_en":"Break 1", "name_ar":"الاستراحة الأولى", "start_time":"10:00", "end_time":"10:20", "duty_type":"break"}`

2. **Create a week and add break slots**
   `PUT /weeks/2026-03-09/shift-locations [{"day_date":"2026-03-09","shift_id":<id>,"location_id":null,"slots_count":2}]`

3. **Assign teacher with grade**
   `PUT /weeks/2026-03-09/assignments [{"shift_location_id":<id>,"slot_index":0,"teacher_id":1,"grade_class":"Grade 5A"}]`

4. **Check teacher schedule** — verify `duty_type:"break"` and `grade_class:"Grade 5A"` appear

5. **Dashboard** — visit `/admin/dashboard` and confirm stats appear

6. **Clone week** — verify grade_class is preserved in the cloned week

7. **Publish week** — verify notifications fire; check logs for FCM output