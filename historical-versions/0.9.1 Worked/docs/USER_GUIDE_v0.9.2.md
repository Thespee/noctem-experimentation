# Noctem v0.9.3 User Guide
## UI/UX Overhaul + Quick Fixes

---

## What's New in v0.9.3 (Phase 1 Quick Fixes)

### NLP-First Task Editing (Upcoming + Projects)
- Click any task card to open an inline text editor.
- Edit in natural language, then press **Enter** to reprocess.
- Differential update behavior:
  - Only fields explicitly mentioned in edited text are updated.
  - Unmentioned fields are preserved.
- Example:
  - Original: `take out trash on monday #home !1`
  - Edited: `take out trash Sunday`
  - Result: due date updates to Sunday, while tags/importance remain unchanged unless explicitly changed.

### Projects Board: Date Picker Removed
- Inline task creation in project columns no longer uses a manual date input.
- Enter dates naturally in task text (e.g., `submit report friday 3pm`).

### New Date Alias
- `tmrw` now parses the same as `tomorrow`.

### Upcoming View: Unassigned Section
- Tasks without due dates now appear in an **Unassigned** section at the end of the upcoming board.
- Ordered from most recently created to oldest.
- Hidden automatically when empty.

### Recurring Calendar Import Fix
- ICS imports now expand recurring `RRULE` events into concrete occurrences in the import window.
- Handles repeating schedules such as every-other-week sessions.

### Legacy Quick-Link Compatibility
- Old links now redirect correctly:
  - `/tasks/settings` and `/task/settings` → Settings
  - `/tasks` and `/upcoming` → Upcoming
  - `/projects` → Projects board

---

## What's New in v0.9.2

### Complete UI Overhaul
Every page now shares a consistent dark theme inspired by Google Calendar's dark mode, with a unified sidebar navigation and mobile/desktop toggle.

**Color Palette:**
- Background: `#1f1f1f` / Surface: `#2d2d2d` / Sidebar: `#1a1a1a`
- Accent: `#8ab4f8` (blue) / Success: `#81c995` / Warning: `#fdd663` / Error: `#f28b82`

### Shared Base Template
All pages extend `base.html` with:
- **Collapsible sidebar** — hamburger menu on mobile, always-visible on desktop
- **Desktop/mobile toggle** — localStorage-backed switch to force mobile layout
- **Consistent navigation** — Dashboard, Calendar, Upcoming, Projects, Voice, Skills, Prompts, Settings

### Dashboard: 2-Week View
- **Two 7-day rows** (Mon–Sun): current week on top, next week below
- **Density banners** on each day card (color-coded: free/light/moderate/busy/packed)
- **14-day forecast column** retained
- Removed: overdue section, top priorities, AI suggestions, Goals & Projects panels
- **No auto-refresh** — removed the 30-second meta refresh

### Calendar View: Full 24h + All-Day Events
- Hours grid extends **0:00–24:00** (previously cut off early)
- **All-day events** shown as banners at the top of each day column
- Database: new `all_day` column on `time_blocks` with auto-migration
- ICS import: detects `DTSTART;VALUE=DATE` and marks events as all-day

### Upcoming Tasks View (New)
- Tasks grouped by day for the next 5 days + overdue section
- **Task check-off** — click the circle to mark done (calls `POST /api/tasks/<id>/complete`)
- **Inline task creation** — "+" button opens a Notion-style form (name + inherits day)
- **Horizontal scroll on desktop** — day columns scroll sideways; vertical stack on mobile
- Priority-colored check circles (red = high, yellow = medium, blue = low)

### Projects Board View (New)
- **Kanban-style columns** — one per project, plus Inbox for unassigned tasks
- **Task check-off** on every card
- **Inline card creation** — "+" at bottom of each column (name + optional due date)
- **Progress bars** — shows done/total per project
- **AI summary** line per project (if available)
- Columns scroll horizontally on desktop, stack vertically on mobile

### Task CRUD API
Three new endpoints power the inline creation and check-off:
- `POST /api/tasks` — Create task (`{name, due_date?, project_id?}`)
- `POST /api/tasks/<id>/complete` — Mark task done
- `POST /api/tasks/<id>/update` — Update fields (name, status, due_date, project_id, importance)
- `POST /api/tasks/<id>/reprocess` — Reprocess edited task text with NLP (explicit-field updates only)
- `GET /api/tasks/no-due-date` — List active tasks with no due date (for Upcoming “Unassigned” section)

### Whisper Fix
- Wrapped `faster-whisper` import in try/except at module level
- App starts cleanly even if `faster-whisper` is not installed
- `WhisperService.is_ready()` returns availability status

---

## Migrated Templates

All templates now extend `base.html`:
- `dashboard.html` — 2-week view with forecast
- `calendar_view.html` — weekly grid with all-day banners
- `tasks_upcoming.html` — rolling days with check-off
- `tasks_projects.html` — Kanban board
- `calendar.html` — ICS import/manage
- `voice.html` — voice journal upload & list
- `skills.html` — skill management
- `prompts.html` — LLM prompt editor
- `settings.html` — configuration

---

## Running Tests

```powershell
# Run v0.9.2 UI regression tests (32 tests)
.\venv\Scripts\python.exe -m pytest tests/test_v092_ui_overhaul.py -v

# Run v0.9.3 Phase 1 quick fix tests (7 tests)
.\venv\Scripts\python.exe -m pytest tests/test_v093_quick_fixes.py -v

# Run full test suite
.\venv\Scripts\python.exe -m pytest tests/ -v
```
