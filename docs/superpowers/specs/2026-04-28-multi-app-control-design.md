# Multi-App Control — Design

**Date:** 2026-04-28
**Project:** OU Lab Access Portal (Lab_Monitor_time)
**Status:** Approved (pending implementation plan)

## Goal

Replace the current single-app gating model (one hard-coded `notepad.exe` target) with an admin-managed list of registered apps. At login, a user picks one or more apps from that list to launch and run together under a single session timer.

## User-validated decisions

The design was driven by these answers from the requirements conversation:

1. **Storage model:** CSV file + new admin tab (option A from approaches).
2. **Multi-select at login:** user picks any subset of registered apps to launch together.
3. **Closing an app mid-session:** session keeps running. Only `FINISH SESSION` button or timer expiry ends the session. The `ProcessExit` end-reason is dropped.
4. **Watchdog scope:** any registered app launched without an active session is killed and the login portal is surfaced (current single-app behavior, extended to all registered apps).
5. **Audit logging:** one row per session with a new `Apps` column listing all picked display names, semicolon-joined.

## Architecture & file map

The change is contained: existing modules keep their roles, one new module is added, one config constant becomes a list backed by CSV.

### New module
- `app_registry.py` — same shape as `auth.py`, for the app list.
  - `load_apps() -> list[dict]`
  - `append_app(row) -> Optional[str]` (returns error message or None)
  - `remove_app(display_name) -> bool`
  - `update_app(display_name, row) -> Optional[str]`
  - Reads/writes `registered_apps.csv` in `DATA_DIR`.

### Modified modules

| Module | Change |
|---|---|
| `config.py` | Replace `TARGET_APP_NAME` / `TARGET_APP_WINDOW_HINT` with `REGISTERED_APPS_FILE` path and `APP_FIELDS = ("display_name", "exe_path", "window_hint")` |
| `bootstrap.py` | Add `ensure_apps_file()`: create `registered_apps.csv` with header on first run; seed it with the existing `Notepad / notepad.exe / Notepad` row so existing installs keep working |
| `process_guard.py` | Add `purge_orphans_many(names)` and `list_matching_pids_many(names)` helpers; existing per-name and per-PID functions stay unchanged |
| `session.py` | `SessionState.allowed_pid: int` becomes `allowed_pids: list[int]`. Add `selected_apps: list[dict]`. `start_session` takes `selected_apps` and spawns each. Drop `ProcessExit` reason. Drop liveness check from `tick` |
| `audit_log.py` | `COLUMNS` adds `Apps` column. HMAC chain extended to include it. Legacy 11-column rows still accepted by `verify_chain` |
| `ui/login_view.py` | Add a second step (app picker) after credentials. Both steps live inside `LoginView` via `_show_credentials_step()` / `_show_picker_step()` toggle |
| `ui/app_shell.py` | `_handle_login_success(user, selected_apps)`. Watchdog uses full registered-app list. Drop `ProcessExit` branch in `_tick` |
| `ui/admin_view.py` | Add fourth tab "Manage Apps" with treeview + Add/Edit/Remove dialogs |

### Files unchanged
`main.py`, `auth.py`, `ui/active_view.py`, `ui/widgets.py`, `ui/theme.py`.

## Data model

### `registered_apps.csv`

New file in `DATA_DIR`:

| Column | Example | Notes |
|---|---|---|
| `display_name` | `Notepad` | Shown on the user's checklist; unique key |
| `exe_path` | `notepad.exe` or `C:\Program Files\Foo\foo.exe` | Passed to `subprocess.Popen`. Bare names resolve via `PATH`; absolute paths used verbatim |
| `window_hint` | `Notepad` | Substring matched by `pygetwindow` for `focus_window`. Optional — blank means no focus action |

`bootstrap.ensure_apps_file()` seeds one row (`Notepad, notepad.exe, Notepad`) on first run.

### `usage_log.csv`

Adds an `Apps` column between `Status` and `PrevHash`:

```
Date, User, 4x4, Advisor, Equip, Start, End, Min, Status, Apps, PrevHash, RowHash
```

`Apps` is a semicolon-joined list of display names from the session (e.g., `Notepad; Calculator`). The HMAC chain extends to include this field.

**Backward compatibility for logs:** rows with the old 11-column format (no `Apps`) are treated as legacy by `verify_chain` — verified against the old field layout, then chain continues. New rows always use the 12-column format.

### `SessionState` (in memory)

```python
@dataclass
class SessionState:
    user: Optional[dict] = None
    start_ts: Optional[float] = None
    allowed_pids: list[int] = field(default_factory=list)
    selected_apps: list[dict] = field(default_factory=list)
    status_report: str = "Runs Smoothly"
    _flash_on: bool = field(default=False, repr=False)
```

## Session lifecycle & watchdog

### Login → session start

1. User enters credentials → `auth.verify_credentials` returns user dict (unchanged).
2. `LoginView` switches to the picker step: checkboxes for each registered app, `Start Session` button (disabled until ≥1 checked), `Back` button.
3. On `Start Session`, `LoginView` fires `on_login_success(user, selected_apps)`.
4. `session.start_session(state, user, selected_apps)`:
   - `process_guard.purge_orphans_many([app["exe_path"] for app in registered_apps])` — wipes all stragglers across the registered set.
   - Spawns each selected app in order, collecting PIDs into `state.allowed_pids`.
   - **Atomicity:** if any spawn fails (`FileNotFoundError` / `OSError`), terminate any already-spawned PIDs, return `False`, surface error toast naming the failing app.
   - On success, focus the first selected app's window via `focus_window`.

### Tick loop

- `session.tick` returns same `TickRecord` (no liveness check).
- `_tick` in `app_shell.py`: drops the `if not process_guard.is_alive(...)` branch entirely.
- Session ends only via `Manual` (FINISH SESSION), `Timeout`, or `AppClose` (portal closed).
- `ProcessExit` reason and its row in `STATUS_BY_REASON` are removed.

### Session end

`session.end_session(state, reason)`:
- Iterate `state.allowed_pids`, call `process_guard.terminate(pid)` on each.
- `purge_orphans_many` again over all registered exe paths to catch child processes.
- Write one audit row with `Apps = "; ".join(app["display_name"] for app in state.selected_apps)`.
- Clear state.

### Watchdog

- Every 2s, list PIDs across all registered exe paths via `list_matching_pids_many`.
- Allowed set = `state.allowed_pids` if a session is active, else empty.
- Any PID matching a registered exe but **not** in the allowed set → terminate.
- If a kill happened and no session is active, surface the existing "Access blocked. Sign in through the portal" toast.

### Re-launch adoption

If during an active session the watchdog sees a registered exe with a PID not in `allowed_pids` *and* that exe is in the user's `selected_apps`, the watchdog **adopts** the new PID (appends it to `allowed_pids`) instead of killing it. This lets users re-open one of their selected apps after closing it.

A registered exe that is **not** in `selected_apps` is still killed — only picked apps can be re-launched.

## UI changes

### Login flow — two steps inside `LoginView`

```
Step 1: Credentials  →  Step 2: App picker  →  start session
            ↑                  │
            └──── Back ────────┘
```

- Step 1: current login form, unchanged.
- Step 2: new sub-frame with title "Select apps for this session", scrollable list of `CTkCheckBox` rows (label = `display_name`, sublabel = `exe_path`), `Start Session` button (disabled until ≥1 checkbox on), `Back` link.
- Both steps live inside `LoginView` — no new view class.
- `LoginView.reset()` clears credentials AND drops back to step 1, so logout/timeout always returns to credentials.

### `AppShell`

- `_handle_login_success(user)` → `_handle_login_success(user, selected_apps)`.
- `selected_apps` stored on `SessionState` so audit log and watchdog can read it.

### Admin portal — new "Manage Apps" tab

- Tab order: `Usage Logs · Manage Users · Manage Apps · Integrity`.
- Treeview columns: `Display Name · Exe Path · Window Hint`.
- Buttons: `Add App` · `Edit Selected` · `Remove Selected` · `Refresh`.
- `Add App` opens dialog with three `FormField` widgets, plus a `Browse...` button next to `exe_path` opening `filedialog.askopenfilename` filtered to `*.exe`.
- `Edit Selected` opens the same dialog pre-filled.
- `Remove Selected` uses `messagebox.askyesno` confirmation.
- Validation on save: `display_name` required and unique; `exe_path` required; `window_hint` optional. Errors shown inline.

### Active session UI

`active_view.py` — no changes. Compact bar, ring, status dropdown, FINISH SESSION button all behave the same.

## Error handling & edge cases

| Situation | Behavior |
|---|---|
| `registered_apps.csv` missing on first run | `bootstrap.ensure_apps_file()` creates with header + seeded `Notepad` row |
| File exists but empty | Login picker shows "No apps registered. Ask your admin to add one." `Start Session` disabled. Watchdog list empty (no-op) |
| User picks app whose exe doesn't exist / not on PATH | `subprocess.Popen` raises `FileNotFoundError` → terminate already-spawned PIDs from this attempt, stay on picker, error toast naming the app |
| Spawn succeeds but app crashes immediately | Session keeps running. Dead PID stays in `allowed_pids` (terminate on dead PID is no-op). User can re-launch — watchdog adopts new PID per re-launch rule |
| Admin adds duplicate `display_name` | `app_registry.append_app` returns error string; UI shows "An app with that name already exists." |
| Admin edits `exe_path` mid-session | Old running PIDs unaffected; new path takes effect on next session |
| Admin removes app while session uses it | Session continues normally (PIDs and `selected_apps` snapshot in memory); audit row records display name. Watchdog stops policing the removed exe immediately |
| `registered_apps.csv` corrupted | `app_registry.load_apps()` catches `csv.Error`, returns `[]`, surfaces warning in admin Integrity tab. No auto-repair (avoids masking tampering) |
| User picks 5 apps; #3 fails to spawn | Terminate #1 and #2, do not start session, error toast names #3. All-or-nothing |
| Timer expires while only some selected apps still running | Terminate every PID in `allowed_pids` (no-op on dead PIDs is safe), write one audit row listing all selected apps |
| Watchdog kill loop with runaway re-launcher | Existing 4-second toast rate limit (`_last_block_notified_at`) handles this — no change |

## Testing — manual test plan

No test framework exists in the repo. Manual click-through validation organized by area:

### Bootstrap & migration
1. Delete `%PROGRAMDATA%\OU-Lab-Monitor\registered_apps.csv`. Launch app → file is created with header + one seeded `Notepad / notepad.exe / Notepad` row.
2. Open existing `usage_log.csv` from before the change. Verify integrity check still passes (legacy rows accepted).

### Admin — Manage Apps tab
3. Add `Calculator / calc.exe / Calculator` → row appears in treeview and CSV.
4. Try to add another app with display name `Calculator` → "already exists" error.
5. Add app with empty `display_name` → "Required" inline error.
6. Edit `Calculator` to `exe_path = C:\Windows\System32\calc.exe` → row updates.
7. Remove `Calculator` → confirmation → row gone from treeview and CSV.

### Login picker
8. With ≥2 apps registered, log in → picker appears with all unchecked, `Start Session` disabled.
9. Check 1 app → `Start Session` enables.
10. Click `Back` → credentials step with fields cleared.
11. Check 2 apps → `Start Session` → both apps launch, active bar shows, timer counts down.
12. Log in with 0 apps registered → picker shows "No apps registered" message, `Start Session` disabled.

### Multi-app session
13. Start session with 2 apps → close one manually → session keeps running, timer keeps counting.
14. Re-launch the closed app → watchdog adopts new PID, app stays open.
15. Try to launch a registered but **not selected** app → watchdog kills it, no toast (session active).
16. Click `FINISH SESSION` → all selected app windows close, audit log row written with both display names in `Apps` column.
17. Let timer expire on a 2-app session → same as #16, `Status = FORGOT TO LOG OUT (Auto-Lock)`.
18. Pick app whose `exe_path` doesn't exist → error toast names app, no session starts, picker still shown.
19. Pick 3 apps where #2 has bad path → #1 spawns then gets terminated, error toast names #2, no session, no orphan PIDs.

### Watchdog (no session active)
20. Log out, launch a registered app from desktop → watchdog kills it, "Access blocked" toast, login window surfaces.
21. Rapid-launch same app 5x in 2 seconds → toast appears once (rate limit holds).

### Audit log integrity
22. After several multi-app sessions, open Integrity tab → `Verify Log` reports all rows verified.
23. Hand-edit `Apps` cell of one row in `usage_log.csv`, re-verify → fails at that row with hash mismatch.

### Edge: admin mutation during session
24. Admin removes an app while session is using it → session continues, log row still records the removed app's display name.
25. Admin edits `exe_path` of an app mid-session → no effect until next session.

## Out of scope (deferred)

These were considered and explicitly excluded:

- Per-app time limits (one shared session timer covers all selected apps).
- Per-app icons in the login picker.
- App grouping / "equipment bundles" (admin can simulate this by naming related apps clearly; user picks them together).
- Concurrent sessions for multiple users on one PC (kiosk model preserved).
- Auto-relaunch of crashed apps (closed apps stay closed).
- Per-app entries in the audit log (one row per session with `Apps` column).
