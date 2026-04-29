# Multi-App Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single hard-coded `notepad.exe` target with an admin-managed list of registered apps; let users multi-select which apps to launch under one session timer.

**Architecture:** Admin-managed `registered_apps.csv` in `DATA_DIR` (parallel to `allowed_users.csv`). New `app_registry.py` module mirrors `auth.py`. `SessionState` tracks `allowed_pids: list[int]` and `selected_apps: list[dict]`. Watchdog policies the union of all registered exe basenames; during an active session, a re-launched copy of a *selected* app is **adopted** (PID added to `allowed_pids`) instead of killed. Login is split into two steps inside `LoginView` (credentials → picker). Admin gets a fourth tab with Add/Edit/Remove dialogs.

**Tech Stack:** Python 3, `customtkinter` for UI, `psutil` + `pygetwindow` for process control, CSV for storage, HMAC-SHA256 chained audit log.

**Spec reference:** `docs/superpowers/specs/2026-04-28-multi-app-control-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `config.py` | Modify | Replace `TARGET_APP_NAME` / `TARGET_APP_WINDOW_HINT` with `REGISTERED_APPS_FILE` and `APP_FIELDS` |
| `app_registry.py` | **New** | Load/append/update/remove rows in `registered_apps.csv`. Same shape as `auth.py` |
| `bootstrap.py` | Modify | Add `ensure_apps_file()` that creates the CSV with header and seeds one `Notepad` row |
| `process_guard.py` | Modify | Add `purge_orphans_many(exe_paths)` and `list_matching_pids_many(exe_paths)` helpers |
| `session.py` | Modify | `allowed_pids: list[int]` + `selected_apps: list[dict]`, drop `ProcessExit` reason, drop liveness check, multi-spawn with atomic rollback |
| `audit_log.py` | Modify | Add `Apps` column, extend HMAC chain over it, accept legacy 11-column rows in `verify_chain` |
| `ui/login_view.py` | Modify | Two-step flow: credentials → picker (checkboxes + Start Session/Back). `reset()` returns to step 1 |
| `ui/app_shell.py` | Modify | Receive `selected_apps`, wire to session, drop `ProcessExit` branch in `_tick`, update watchdog to multi-app + adoption rule |
| `ui/admin_view.py` | Modify | Add fourth "Manage Apps" tab with treeview + Add/Edit/Remove dialogs (uses `app_registry`) |

**Files unchanged:** `main.py`, `auth.py`, `ui/active_view.py`, `ui/widgets.py`, `ui/theme.py`.

---

## Task Order Rationale

Bottom-up so each task is independently runnable:

1. **Config + registry + bootstrap** (Tasks 1–3) — storage layer first; nothing UI yet.
2. **Process guard helpers** (Task 4) — pure functions, no callers yet.
3. **Audit log schema** (Task 5) — depends only on storage layout, not on session.
4. **Session state** (Task 6) — uses process guard + audit log.
5. **Admin "Manage Apps" tab** (Task 7) — exercises the registry end-to-end via UI before login flow changes.
6. **Login picker** (Task 8) — UI for selection.
7. **AppShell wire-up** (Task 9) — passes selection through, updates watchdog.
8. **Final end-to-end manual sweep** (Task 10) — runs the spec's full test plan.

Each task ends with a commit and a manual smoke check that validates only the slice that task introduced.

---

## Task 1: Config — replace single target with registered-apps storage

**Files:**
- Modify: `config.py:7-8` (remove `TARGET_APP_NAME`, `TARGET_APP_WINDOW_HINT`)
- Modify: `config.py:20-22` (add `REGISTERED_APPS_FILE` next to other paths)
- Modify: `config.py:62-66` (add `APP_FIELDS`)

- [ ] **Step 1: Edit `config.py`**

Open `config.py`. Find:

```python
TARGET_APP_NAME = "notepad.exe"
TARGET_APP_WINDOW_HINT = "Notepad"
```

Replace with nothing (delete both lines).

Find the path block:

```python
USER_LIST_FILE = DATA_DIR / "allowed_users.csv"
LOG_FILE = DATA_DIR / "usage_log.csv"
AUDIT_KEY_FILE = DATA_DIR / ".audit_key"
```

Add a line after it:

```python
USER_LIST_FILE = DATA_DIR / "allowed_users.csv"
LOG_FILE = DATA_DIR / "usage_log.csv"
AUDIT_KEY_FILE = DATA_DIR / ".audit_key"
REGISTERED_APPS_FILE = DATA_DIR / "registered_apps.csv"
```

Find:

```python
USER_FIELDS = (
    "first_name", "last_name", "cellphone", "email",
    "school_affiliation", "advisor_first", "advisor_last",
    "username", "equipment_name",
)
```

Add immediately after:

```python
APP_FIELDS = ("display_name", "exe_path", "window_hint")
```

- [ ] **Step 2: Verify nothing else references the deleted constants**

Run:

```bash
grep -rn "TARGET_APP_NAME\|TARGET_APP_WINDOW_HINT" --include="*.py" .
```

Expected: matches in `process_guard` callers, `session.py`, `ui/app_shell.py`. **Do NOT fix these yet** — later tasks rewrite those callers. The grep is just to confirm we know the blast radius.

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "config: introduce REGISTERED_APPS_FILE and APP_FIELDS

Removes the single hard-coded target. Callers will be migrated in
subsequent commits; the app will not run until those land."
```

Note: the app is in a temporarily broken state at this commit. That's acceptable because Tasks 2–6 land before any UI smoke test.

---

## Task 2: New `app_registry.py` module

**Files:**
- Create: `app_registry.py`

- [ ] **Step 1: Create the module**

Create `app_registry.py` with this content:

```python
"""Registered-application list — CSV-backed, admin-managed."""
import csv
from typing import Optional

import config


def load_apps() -> list[dict]:
    """Return all registered apps. Empty list if file missing or unreadable."""
    if not config.REGISTERED_APPS_FILE.exists():
        return []
    try:
        with open(config.REGISTERED_APPS_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                {k: (row.get(k, "") or "").strip() for k in config.APP_FIELDS}
                for row in reader
            ]
    except (OSError, csv.Error):
        return []


def find_app(display_name: str) -> Optional[dict]:
    target = display_name.strip().lower()
    for app in load_apps():
        if app["display_name"].lower() == target:
            return app
    return None


def append_app(row: dict) -> Optional[str]:
    """Append a new app. Returns None on success or a human-readable error string."""
    display = (row.get("display_name") or "").strip()
    exe = (row.get("exe_path") or "").strip()
    if not display:
        return "Display name is required."
    if not exe:
        return "Exe path is required."
    if find_app(display) is not None:
        return f"An app named '{display}' already exists."

    file_exists = config.REGISTERED_APPS_FILE.exists()
    with open(config.REGISTERED_APPS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(config.APP_FIELDS))
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: (row.get(k, "") or "").strip() for k in config.APP_FIELDS})
    return None


def remove_app(display_name: str) -> bool:
    """Remove the app with this display_name. Returns True if a row was removed."""
    target = display_name.strip().lower()
    apps = load_apps()
    kept = [a for a in apps if a["display_name"].lower() != target]
    if len(kept) == len(apps):
        return False
    _rewrite(kept)
    return True


def update_app(original_display_name: str, row: dict) -> Optional[str]:
    """Update the row matched by original_display_name to the new fields in `row`.

    Returns None on success or an error string. The new display_name may differ
    from original_display_name, but it must not collide with another existing app.
    """
    target = original_display_name.strip().lower()
    new_display = (row.get("display_name") or "").strip()
    new_exe = (row.get("exe_path") or "").strip()
    if not new_display:
        return "Display name is required."
    if not new_exe:
        return "Exe path is required."

    apps = load_apps()
    found = False
    updated: list[dict] = []
    for a in apps:
        if a["display_name"].lower() == target:
            updated.append({k: (row.get(k, "") or "").strip() for k in config.APP_FIELDS})
            found = True
        else:
            if a["display_name"].lower() == new_display.lower():
                # Renaming onto a different existing entry — collision.
                return f"An app named '{new_display}' already exists."
            updated.append(a)
    if not found:
        return f"No app named '{original_display_name}' found."
    _rewrite(updated)
    return None


def _rewrite(apps: list[dict]) -> None:
    with open(config.REGISTERED_APPS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(config.APP_FIELDS))
        writer.writeheader()
        for a in apps:
            writer.writerow({k: a.get(k, "") for k in config.APP_FIELDS})
```

- [ ] **Step 2: Manual smoke check from a Python REPL**

Run from repo root:

```bash
python -c "
import sys
sys.path.insert(0, '.')
import config
config.REGISTERED_APPS_FILE = config.Path('./_test_apps.csv')
import app_registry
print('initial:', app_registry.load_apps())
print('append1:', app_registry.append_app({'display_name': 'Notepad', 'exe_path': 'notepad.exe', 'window_hint': 'Notepad'}))
print('append-dup:', app_registry.append_app({'display_name': 'Notepad', 'exe_path': 'x', 'window_hint': ''}))
print('append-empty:', app_registry.append_app({'display_name': '', 'exe_path': 'x', 'window_hint': ''}))
print('append2:', app_registry.append_app({'display_name': 'Calculator', 'exe_path': 'calc.exe', 'window_hint': ''}))
print('all:', app_registry.load_apps())
print('update:', app_registry.update_app('Calculator', {'display_name': 'Calc', 'exe_path': 'calc.exe', 'window_hint': 'Calculator'}))
print('rename-collide:', app_registry.update_app('Calc', {'display_name': 'Notepad', 'exe_path': 'x', 'window_hint': ''}))
print('remove:', app_registry.remove_app('Calc'))
print('remove-missing:', app_registry.remove_app('NoSuch'))
print('final:', app_registry.load_apps())
"
rm -f _test_apps.csv
```

Expected output:
```
initial: []
append1: None
append-dup: An app named 'Notepad' already exists.
append-empty: Display name is required.
append2: None
all: [{'display_name': 'Notepad', 'exe_path': 'notepad.exe', 'window_hint': 'Notepad'}, {'display_name': 'Calculator', 'exe_path': 'calc.exe', 'window_hint': ''}]
update: None
rename-collide: An app named 'Notepad' already exists.
remove: True
remove-missing: False
final: [{'display_name': 'Notepad', 'exe_path': 'notepad.exe', 'window_hint': 'Notepad'}]
```

- [ ] **Step 3: Commit**

```bash
git add app_registry.py
git commit -m "app_registry: CSV-backed registered apps module

Mirrors auth.py shape. Provides load/append/update/remove with
duplicate-name and required-field validation."
```

---

## Task 3: Bootstrap — seed `registered_apps.csv`

**Files:**
- Modify: `bootstrap.py`

- [ ] **Step 1: Add `ensure_apps_file()` and call it from `run()`**

Open `bootstrap.py`. After the `ensure_audit_key` function (around line 53), add:

```python
def ensure_apps_file() -> None:
    """Create registered_apps.csv with header on first run, seeded with one Notepad row.

    Seeding preserves the pre-multi-app default so existing installs keep working
    until an admin curates the list.
    """
    if config.REGISTERED_APPS_FILE.exists():
        return
    with open(config.REGISTERED_APPS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(config.APP_FIELDS))
        writer.writeheader()
        writer.writerow({
            "display_name": "Notepad",
            "exe_path": "notepad.exe",
            "window_hint": "Notepad",
        })
```

Then update the `run()` function at the bottom to call it:

```python
def run() -> None:
    ensure_data_dir()
    ensure_user_list()
    ensure_log_file()
    ensure_audit_key()
    ensure_apps_file()
```

- [ ] **Step 2: Manual smoke check**

```bash
python -c "
import sys
sys.path.insert(0, '.')
import config
config.REGISTERED_APPS_FILE = config.Path('./_seed_test.csv')
import bootstrap
bootstrap.ensure_apps_file()
print(open('_seed_test.csv').read())
bootstrap.ensure_apps_file()  # second call is a no-op
print('---')
print(open('_seed_test.csv').read())
"
rm -f _seed_test.csv
```

Expected: file has header + one Notepad row. The two prints show identical contents (idempotent).

- [ ] **Step 3: Commit**

```bash
git add bootstrap.py
git commit -m "bootstrap: seed registered_apps.csv with default Notepad row"
```

---

## Task 4: `process_guard.py` — multi-app helpers

**Files:**
- Modify: `process_guard.py`

- [ ] **Step 1: Add basename helper and the two `_many` functions**

Open `process_guard.py`. Add this helper near the top (after the imports):

```python
import os
```

Add `os` to the existing imports if it's not there. Then add these two functions at the end of the file:

```python
def _basename_lower(path: str) -> str:
    """Return the lowercase basename of an exe path. Bare names pass through."""
    return os.path.basename(path).lower()


def purge_orphans_many(exe_paths: list[str]) -> int:
    """Terminate every running process whose name matches the basename of any exe_path.

    Used at session start (wipe the whole registered set) and at session end
    (catch any child processes spawned by the selected apps).
    """
    names = {_basename_lower(p) for p in exe_paths if p}
    if not names:
        return 0
    count = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info["name"] or "").lower() in names:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count


def list_matching_pids_many(exe_paths: list[str]) -> list[tuple[int, str]]:
    """Return (pid, basename_lower) pairs for every running proc matching any exe_path.

    The watchdog uses the basename to decide adopt vs. kill: if a PID is not
    in allowed_pids but its basename matches one of the *selected* apps, adopt it.
    """
    names = {_basename_lower(p) for p in exe_paths if p}
    if not names:
        return []
    out: list[tuple[int, str]] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            n = (proc.info["name"] or "").lower()
            if n in names:
                out.append((proc.info["pid"], n))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out
```

- [ ] **Step 2: Manual smoke check**

```bash
python -c "
import sys
sys.path.insert(0, '.')
import process_guard, subprocess, time
p = subprocess.Popen(['notepad.exe'])
time.sleep(0.6)
print('pids before:', process_guard.list_matching_pids_many([r'C:\\Windows\\System32\\notepad.exe', 'calc.exe']))
killed = process_guard.purge_orphans_many(['notepad.exe'])
print('killed:', killed)
time.sleep(0.3)
print('pids after:', process_guard.list_matching_pids_many(['notepad.exe']))
"
```

Expected: `pids before` lists at least one tuple with `'notepad.exe'`; `killed` is ≥1; `pids after` is `[]`.

- [ ] **Step 3: Commit**

```bash
git add process_guard.py
git commit -m "process_guard: add purge_orphans_many and list_matching_pids_many

Both work off the basename of each exe_path so absolute and bare paths
match correctly. PID listing returns (pid, basename) so the watchdog can
do per-app adoption decisions."
```

---

## Task 5: `audit_log.py` — add `Apps` column with legacy compatibility

**Files:**
- Modify: `audit_log.py`

- [ ] **Step 1: Update `COLUMNS` and `LEGACY_COLUMNS`**

Open `audit_log.py`. Replace lines 16–20:

```python
COLUMNS = [
    "Date", "User", "4x4", "Advisor", "Equip",
    "Start", "End", "Min", "Status", "PrevHash", "RowHash",
]
LEGACY_COLUMNS = COLUMNS[:9]
```

with:

```python
COLUMNS = [
    "Date", "User", "4x4", "Advisor", "Equip",
    "Start", "End", "Min", "Status", "Apps", "PrevHash", "RowHash",
]
# Two prior formats:
#   v1 (no hash, no apps): 9 columns ending at "Status"
#   v2 (hash chain, no apps): 11 columns (v1 + PrevHash + RowHash)
LEGACY_V1_COLUMNS = COLUMNS[:9]
LEGACY_V2_COLUMNS = COLUMNS[:9] + ["PrevHash", "RowHash"]
```

- [ ] **Step 2: Update `append_entry` to write `Apps`**

Replace the `append_entry` function (lines 92–120) with:

```python
def append_entry(
    user: dict,
    start_ts: float,
    end_ts: float,
    status: str,
    apps: list[str],
) -> None:
    _unlock_log()
    key = _load_or_create_key()
    rows = _read_all_rows()
    prev_hash = _last_row_hash(rows)

    duration = round((end_ts - start_ts) / 60, 2)
    apps_field = "; ".join(apps)
    fields = [
        datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d"),
        f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
        user.get("username", ""),
        user.get("advisor_last", ""),
        user.get("equipment_name", "N/A"),
        datetime.fromtimestamp(start_ts).strftime("%H:%M:%S"),
        datetime.fromtimestamp(end_ts).strftime("%H:%M:%S"),
        f"{duration}",
        status,
        apps_field,
    ]
    row_hash = _row_hmac(prev_hash, fields, key)

    file_exists = config.LOG_FILE.exists() and any(rows)
    with open(config.LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(COLUMNS)
        writer.writerow(fields + [prev_hash, row_hash])

    rotate_if_needed()
    _lock_log()
```

The HMAC payload is now 10 fields (Date through Apps) instead of 9.

- [ ] **Step 3: Update `verify_chain` to accept v1 and v2 legacy rows**

Replace the `verify_chain` function (lines 135–174) with:

```python
def verify_chain() -> tuple[bool, int | None, str]:
    rows = _read_all_rows()
    if len(rows) <= 1:
        return True, None, "Log verified (0 rows)"

    key = _load_or_create_key()
    data_rows = rows[1:]
    prev_hash = GENESIS
    verified_count = 0
    skipped_v1 = 0
    skipped_v2 = 0

    for idx, row in enumerate(data_rows, start=1):
        # v1: no hash columns at all (length <= 9, or last cell empty hash)
        if len(row) < len(LEGACY_V2_COLUMNS) or not row[-1]:
            skipped_v1 += 1
            continue

        # v2: 11 columns, no Apps field. Verify against the v2 layout but do
        # NOT chain into prev_hash for v3 rows — once we cross into v3 we
        # require unbroken v3-format chain. v2 rows are accepted but skipped
        # for chain continuity.
        if len(row) == len(LEGACY_V2_COLUMNS):
            stored_prev = row[-2]
            stored_hash = row[-1]
            fields = row[:9]
            expected = _row_hmac(prev_hash, fields, key)
            if stored_prev != prev_hash or not hmac.compare_digest(expected, stored_hash):
                # v2 chain broke — count as a skip rather than a hard failure,
                # because the chain format itself changed at the boundary.
                skipped_v2 += 1
                prev_hash = stored_hash  # advance anyway so v3 rows can chain
                continue
            prev_hash = stored_hash
            skipped_v2 += 1
            continue

        # v3: 12 columns including Apps
        stored_prev = row[-2]
        stored_hash = row[-1]
        fields = row[:10]

        if stored_prev != prev_hash:
            return False, idx, (
                f"Tampered at row {idx}: previous hash mismatch "
                f"(expected {prev_hash[:12]}…, got {stored_prev[:12]}…)"
            )

        expected = _row_hmac(prev_hash, fields, key)
        if not hmac.compare_digest(expected, stored_hash):
            return False, idx, (
                f"Tampered at row {idx}: row hash mismatch "
                f"(expected {expected[:12]}…, got {stored_hash[:12]}…)"
            )

        prev_hash = stored_hash
        verified_count += 1

    msg = f"Log verified ({verified_count} row{'s' if verified_count != 1 else ''})"
    skipped_parts = []
    if skipped_v1:
        skipped_parts.append(f"{skipped_v1} legacy v1 row{'s' if skipped_v1 != 1 else ''} (pre-hash)")
    if skipped_v2:
        skipped_parts.append(f"{skipped_v2} legacy v2 row{'s' if skipped_v2 != 1 else ''} (pre-Apps)")
    if skipped_parts:
        msg += "; " + ", ".join(skipped_parts) + " skipped"
    return True, None, msg
```

- [ ] **Step 4: Update `read_entries` for the new layout**

The function at line 123 already uses `len(COLUMNS)` and pads short rows with `""`. Since we expanded `COLUMNS`, it Just Works — old rows get a blank `Apps` field in the dict. Confirm by reading it; no edit required.

- [ ] **Step 5: Manual smoke check (round-trip a fake user + verify)**

```bash
rm -f /tmp/test_log.csv /tmp/test_key
python -c "
import sys
sys.path.insert(0, '.')
import config
config.LOG_FILE = config.Path('/tmp/test_log.csv')
config.AUDIT_KEY_FILE = config.Path('/tmp/test_key')
import audit_log, time
user = {'first_name':'A', 'last_name':'B', 'username':'ab', 'advisor_last':'Smith', 'equipment_name':'Lab1'}
audit_log.append_entry(user, time.time()-60, time.time(), 'Runs Smoothly', ['Notepad', 'Calculator'])
audit_log.append_entry(user, time.time()-60, time.time(), 'Runs Smoothly', ['Notepad'])
ok, bad, msg = audit_log.verify_chain()
print('ok=', ok, 'bad=', bad, 'msg=', msg)
print('---')
print(open('/tmp/test_log.csv').read())
"
```

Expected: `ok= True bad= None msg= Log verified (2 rows)`. The CSV shows the new 12-column header and `Apps` field populated as `Notepad; Calculator` and `Notepad`.

- [ ] **Step 6: Commit**

```bash
git add audit_log.py
git commit -m "audit_log: add Apps column to v3 schema with legacy compat

v1 (no hash) and v2 (hash, no Apps) rows are skipped during verification
but accepted as legacy. The HMAC chain advances through v2 rows so v3
entries written after the upgrade still chain consistently."
```

---

## Task 6: `session.py` — multi-PID, drop ProcessExit, atomic spawn

**Files:**
- Modify: `session.py`

- [ ] **Step 1: Update imports, types, and SessionState**

Open `session.py`. Replace lines 9–37 (imports, `LogoutReason`, dataclasses) with:

```python
"""Session lifecycle — state machine orchestrating audit log + process guard."""
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import audit_log
import config
import process_guard

LogoutReason = Literal["Manual", "Timeout", "AppClose"]


@dataclass
class TickRecord:
    remaining_sec: int
    phase: Literal["normal", "warn", "urgent"]
    flash_on: bool


@dataclass
class SessionState:
    user: Optional[dict] = None
    start_ts: Optional[float] = None
    allowed_pids: list[int] = field(default_factory=list)
    selected_apps: list[dict] = field(default_factory=list)
    status_report: str = "Runs Smoothly"
    _flash_on: bool = field(default=False, repr=False)

    @property
    def active(self) -> bool:
        return self.user is not None and self.start_ts is not None

    def clear(self) -> None:
        self.user = None
        self.start_ts = None
        self.allowed_pids = []
        self.selected_apps = []
        self.status_report = "Runs Smoothly"
        self._flash_on = False
```

- [ ] **Step 2: Update `STATUS_BY_REASON` (drop `ProcessExit`)**

Replace the `STATUS_BY_REASON` dict (lines 40–45) with:

```python
STATUS_BY_REASON = {
    "Manual": None,  # uses combobox value
    "Timeout": "FORGOT TO LOG OUT (Auto-Lock)",
    "AppClose": "Portal closed mid-session",
}
```

- [ ] **Step 3: Replace `start_session` with multi-app atomic spawn**

Replace the `start_session` function (lines 48–59) with:

```python
def start_session(
    state: SessionState,
    user: dict,
    selected_apps: list[dict],
    registered_apps: list[dict],
) -> tuple[bool, Optional[str]]:
    """Spawn every selected app under one session.

    Returns (True, None) on success, or (False, error_message) if any spawn
    fails. On failure, all already-spawned PIDs from this attempt are
    terminated so no orphans are left.

    `registered_apps` is the full admin list — used to purge stragglers across
    the entire registered set before launching.
    """
    if not selected_apps:
        return False, "No apps selected."

    process_guard.purge_orphans_many([a["exe_path"] for a in registered_apps])

    spawned: list[int] = []
    for app in selected_apps:
        try:
            pid = process_guard.spawn(app["exe_path"])
        except (FileNotFoundError, OSError) as e:
            for p in spawned:
                process_guard.terminate(p)
            return False, f"Could not start '{app['display_name']}' ({app['exe_path']}): {e}"
        spawned.append(pid)

    state.user = user
    state.start_ts = time.time()
    state.allowed_pids = spawned
    state.selected_apps = list(selected_apps)
    state.status_report = "Runs Smoothly"
    state._flash_on = False
    return True, None
```

- [ ] **Step 4: Replace `end_session` to terminate all PIDs and write Apps**

Replace the `end_session` function (lines 62–79) with:

```python
def end_session(
    state: SessionState,
    reason: LogoutReason,
    registered_apps: list[dict],
) -> None:
    if not state.active:
        return
    user = state.user
    start_ts = state.start_ts
    pids = list(state.allowed_pids)
    selected = list(state.selected_apps)
    status = STATUS_BY_REASON[reason] or state.status_report

    try:
        audit_log.append_entry(
            user,
            start_ts,
            time.time(),
            status,
            [a["display_name"] for a in selected],
        )
    except Exception as e:
        print(f"[audit_log] append failed: {e}")

    for pid in pids:
        process_guard.terminate(pid)
    process_guard.purge_orphans_many([a["exe_path"] for a in registered_apps])
    state.clear()
```

- [ ] **Step 5: `tick` no longer checks process liveness**

The existing `tick` function (lines 89–101) does not check liveness — that lived in `app_shell._tick`. Leave `tick` as-is.

- [ ] **Step 6: Manual smoke check**

```bash
rm -f /tmp/test_log.csv /tmp/test_key
python -c "
import sys
sys.path.insert(0, '.')
import config
config.LOG_FILE = config.Path('/tmp/test_log.csv')
config.AUDIT_KEY_FILE = config.Path('/tmp/test_key')
import session, time
state = session.SessionState()
user = {'first_name':'A','last_name':'B','username':'ab','advisor_last':'Smith','equipment_name':'Lab1'}
registered = [{'display_name':'Notepad','exe_path':'notepad.exe','window_hint':'Notepad'}]
ok, err = session.start_session(state, user, registered, registered)
print('start:', ok, err, 'pids:', state.allowed_pids)
time.sleep(1)
session.end_session(state, 'Manual', registered)
print('after end, active:', state.active)
print('--- log ---')
print(open('/tmp/test_log.csv').read())
"
```

Expected: `start: True None pids: [<some int>]`, then `after end, active: False`, log shows one row with `Apps = Notepad`. The notepad window opens then closes within ~1 second.

- [ ] **Step 7: Commit**

```bash
git add session.py
git commit -m "session: multi-app start/end with atomic spawn rollback

SessionState now tracks allowed_pids (list) and selected_apps. Drops
the ProcessExit reason because closed apps no longer end the session.
end_session writes one audit row with the joined display names."
```

---

## Task 7: Admin "Manage Apps" tab

**Files:**
- Modify: `ui/admin_view.py`

- [ ] **Step 1: Add the tab and import `app_registry`**

Open `ui/admin_view.py`. At the top of the file, add to the imports:

```python
import app_registry
```

Find the tab-creation block (around lines 35–41). Update to:

```python
        self._tabs.add("Usage Logs")
        self._tabs.add("Manage Users")
        self._tabs.add("Manage Apps")
        self._tabs.add("Integrity")

        self._build_logs_tab(self._tabs.tab("Usage Logs"))
        self._build_users_tab(self._tabs.tab("Manage Users"))
        self._build_apps_tab(self._tabs.tab("Manage Apps"))
        self._build_integrity_tab(self._tabs.tab("Integrity"))
```

- [ ] **Step 2: Add `_build_apps_tab` and helpers**

Insert this method block after `_open_registration` (around line 188), before `_build_integrity_tab`:

```python
    # ---------- Manage Apps tab ----------
    def _build_apps_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color=config.WHITE)
        container.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("Display Name", "Exe Path", "Window Hint")
        self._app_tree = ttk.Treeview(container, columns=cols, show="headings", height=12)
        widths = {"Display Name": 180, "Exe Path": 360, "Window Hint": 160}
        for c in cols:
            self._app_tree.heading(c, text=c)
            self._app_tree.column(c, width=widths.get(c, 140), anchor="w")
        self._app_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(container, orient="vertical", command=self._app_tree.yview)
        scroll.pack(side="right", fill="y")
        self._app_tree.configure(yscrollcommand=scroll.set)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        ctk.CTkButton(
            btn_row, text="Add App",
            command=self._open_app_add,
            font=theme.font_body_bold(),
            height=32, width=120,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Edit Selected",
            command=self._open_app_edit,
            font=theme.font_caption(),
            height=32, width=120,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Remove Selected",
            command=self._remove_app,
            font=theme.font_caption(),
            height=32, width=140,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Refresh",
            command=self._refresh_apps,
            font=theme.font_caption(),
            height=32, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)

        self._refresh_apps()

    def _refresh_apps(self):
        for item in self._app_tree.get_children():
            self._app_tree.delete(item)
        for a in app_registry.load_apps():
            self._app_tree.insert("", "end", values=(
                a.get("display_name", ""),
                a.get("exe_path", ""),
                a.get("window_hint", ""),
            ))

    def _selected_app_display_name(self) -> str | None:
        sel = self._app_tree.selection()
        if not sel:
            return None
        values = self._app_tree.item(sel[0], "values")
        return values[0] if values else None

    def _open_app_add(self):
        AppDialog(self, on_saved=self._refresh_apps, existing=None)

    def _open_app_edit(self):
        name = self._selected_app_display_name()
        if not name:
            messagebox.showinfo("Edit", "Select an app first.", parent=self)
            return
        existing = app_registry.find_app(name)
        if existing is None:
            messagebox.showerror("Edit", f"App '{name}' not found.", parent=self)
            self._refresh_apps()
            return
        AppDialog(self, on_saved=self._refresh_apps, existing=existing)

    def _remove_app(self):
        name = self._selected_app_display_name()
        if not name:
            messagebox.showinfo("Remove", "Select an app first.", parent=self)
            return
        if not messagebox.askyesno("Remove", f"Remove '{name}' from the registered list?", parent=self):
            return
        if not app_registry.remove_app(name):
            messagebox.showerror("Remove", f"App '{name}' not found.", parent=self)
        self._refresh_apps()
```

- [ ] **Step 3: Add the `AppDialog` class at the bottom of the file**

Insert this class at the end of `ui/admin_view.py`, after `prompt_admin_password`:

```python
class AppDialog(ctk.CTkToplevel):
    """Add or edit a registered app. If `existing` is given, dialog is in edit mode."""

    def __init__(self, parent, on_saved, existing: dict | None):
        super().__init__(parent)
        self._existing = existing
        self._on_saved = on_saved
        self.title("Edit App" if existing else "Add App")
        self.geometry("440x340")
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()

        title = "Edit App" if existing else "Add App"
        subtitle = "Update an existing entry" if existing else "Register a new app"
        HeaderBar(self, title, subtitle).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        self._fields: dict[str, FormField] = {}
        for fname in config.APP_FIELDS:
            label = fname.replace("_", " ").title()
            ff = FormField(body, label)
            ff.pack(fill="x", pady=4)
            if existing:
                ff.set(existing.get(fname, ""))
            self._fields[fname] = ff

        # Browse button next to exe_path
        browse_row = ctk.CTkFrame(body, fg_color="transparent")
        browse_row.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(
            browse_row, text="Browse…",
            command=self._browse_exe,
            font=theme.font_caption(),
            height=26, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(anchor="e")

        ctk.CTkButton(
            self, text="Save",
            command=self._save,
            font=theme.font_body_bold(),
            height=36,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", padx=16, pady=(4, 14))

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select executable",
            filetypes=[("Executables", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self._fields["exe_path"].set(path)

    def _save(self):
        row = {f: self._fields[f].value().strip() for f in config.APP_FIELDS}
        for f in config.APP_FIELDS:
            self._fields[f].clear_error()

        if self._existing is None:
            err = app_registry.append_app(row)
        else:
            err = app_registry.update_app(self._existing["display_name"], row)

        if err is not None:
            # Heuristic: route message to the relevant field if obvious
            if "Display name" in err:
                self._fields["display_name"].set_error(err)
            elif "Exe path" in err:
                self._fields["exe_path"].set_error(err)
            else:
                messagebox.showerror("Save failed", err, parent=self)
            return
        self._on_saved()
        self.destroy()
```

- [ ] **Step 4: Confirm `FormField` has `set()`. Add it if missing.**

Run:

```bash
grep -n "def set\|def value\|def clear_error\|def set_error" ui/widgets.py
```

If `FormField.set` is not present, open `ui/widgets.py` and add this method to the `FormField` class:

```python
    def set(self, value: str) -> None:
        try:
            self._entry.delete(0, "end")
            self._entry.insert(0, value)
        except Exception:
            pass
```

(The internal entry attribute name may differ — check the existing `value()` method in `FormField` for the actual attribute name and use it.)

- [ ] **Step 5: Manual smoke check (UI, no session yet)**

The session-launch path is still broken at this point (Task 9 fixes it), but the admin tab is reachable from the login window's admin shortcut. Run:

```bash
python main.py
```

Click the admin shortcut on the login window → enter password `OU_Admin_2026` → switch to "Manage Apps" tab. Expected:
- Treeview shows the seeded `Notepad` row from Task 3.
- "Add App" opens a dialog with three empty fields and a Browse button.
- Adding `Calculator / calc.exe / Calculator` adds it to the treeview and CSV.
- Adding another `Calculator` shows the duplicate error inline on the Display Name field.
- Selecting `Calculator` and clicking "Edit Selected" opens the dialog pre-filled.
- Selecting `Calculator` and clicking "Remove Selected" shows the confirmation, then removes it.

Close the app (the active session path is still broken — don't try to log in).

- [ ] **Step 6: Commit**

```bash
git add ui/admin_view.py ui/widgets.py
git commit -m "admin: Manage Apps tab with Add/Edit/Remove dialogs

Treeview backed by app_registry. Dialog has Browse button for the
exe path and routes registry validation errors back to the relevant
field."
```

---

## Task 8: Login picker — two-step flow

**Files:**
- Modify: `ui/login_view.py`

- [ ] **Step 1: Read the current `LoginView` to anchor changes**

Run:

```bash
cat ui/login_view.py
```

Note the constructor signature, the `on_login_success` callback shape, and the `reset()` method. The picker step is a new sub-frame that swaps with the credentials sub-frame.

- [ ] **Step 2: Refactor `LoginView` into two-step**

Replace the entire contents of `ui/login_view.py` with:

```python
"""Login view — credentials step + multi-app picker step."""
from typing import Callable

import customtkinter as ctk

import app_registry
import auth
import config
from ui import theme
from ui.widgets import FormField, HeaderBar


class LoginView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_login_success: Callable[[dict, list[dict]], None],
        on_admin_requested: Callable[[], None],
    ):
        super().__init__(parent, fg_color=config.WHITE)
        self._on_login_success = on_login_success
        self._on_admin_requested = on_admin_requested
        self._authed_user: dict | None = None
        self._app_vars: list[tuple[ctk.BooleanVar, dict]] = []
        self._start_btn: ctk.CTkButton | None = None

        HeaderBar(self, "OU Lab Access", "Sign in to use lab equipment").pack(fill="x")

        # The two step frames live inside a single container so swapping is cheap.
        self._steps_container = ctk.CTkFrame(self, fg_color=config.WHITE)
        self._steps_container.pack(fill="both", expand=True, padx=20, pady=12)

        self._cred_step = self._build_credentials_step(self._steps_container)
        self._picker_step: ctk.CTkFrame | None = None  # built on demand

        self._show_credentials_step()

    # ---------- step 1: credentials ----------
    def _build_credentials_step(self, parent) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=config.WHITE)

        self._username = FormField(frame, "Username")
        self._username.pack(fill="x", pady=4)
        self._advisor = FormField(frame, "Advisor Last Name")
        self._advisor.pack(fill="x", pady=4)

        self._error = ctk.CTkLabel(
            frame, text="",
            font=theme.font_caption(),
            text_color=config.URGENT_RED,
        )
        self._error.pack(anchor="w", pady=(4, 0))

        ctk.CTkButton(
            frame, text="Continue",
            command=self._submit_credentials,
            font=theme.font_body_bold(),
            height=36,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", pady=(12, 4))

        ctk.CTkButton(
            frame, text="Admin Portal",
            command=self._on_admin_requested,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        return frame

    def _submit_credentials(self):
        un = self._username.value().strip()
        adv = self._advisor.value().strip()
        if not un or not adv:
            self._error.configure(text="Both fields are required.")
            return
        user = auth.verify_credentials(un, adv)
        if user is None:
            self._error.configure(text="Username or advisor name not recognized.")
            return
        self._error.configure(text="")
        self._authed_user = user
        self._show_picker_step()

    # ---------- step 2: app picker ----------
    def _build_picker_step(self, parent) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=config.WHITE)

        ctk.CTkLabel(
            frame, text="Select apps for this session",
            font=theme.font_h2(),
            text_color=config.GRAY_900,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame, text="Pick one or more. Closing an app does not end your session.",
            font=theme.font_caption(),
            text_color=config.GRAY_600,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self._picker_list = ctk.CTkScrollableFrame(frame, fg_color=config.WHITE, height=180)
        self._picker_list.pack(fill="both", expand=True)

        self._start_btn = ctk.CTkButton(
            frame, text="Start Session",
            command=self._submit_picker,
            font=theme.font_body_bold(),
            height=36,
            state="disabled",
            **theme.CRIMSON_BUTTON_KW,
        )
        self._start_btn.pack(fill="x", pady=(8, 4))

        ctk.CTkButton(
            frame, text="Back",
            command=self._show_credentials_step,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        return frame

    def _populate_picker(self):
        # Clear any previous checkboxes
        for child in list(self._picker_list.winfo_children()):
            child.destroy()
        self._app_vars = []

        apps = app_registry.load_apps()
        if not apps:
            ctk.CTkLabel(
                self._picker_list,
                text="No apps registered. Ask your admin to add one.",
                font=theme.font_body(),
                text_color=config.GRAY_600,
            ).pack(anchor="w", pady=8)
            self._start_btn.configure(state="disabled")
            return

        for app in apps:
            var = ctk.BooleanVar(value=False)
            row = ctk.CTkFrame(self._picker_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(
                row,
                text=app["display_name"],
                variable=var,
                command=self._update_start_button,
                font=theme.font_body(),
                text_color=config.GRAY_900,
                fg_color=config.CRIMSON,
                hover_color=config.CRIMSON_HOVER,
            ).pack(anchor="w")
            ctk.CTkLabel(
                row, text=app["exe_path"],
                font=theme.font_caption(),
                text_color=config.GRAY_600,
            ).pack(anchor="w", padx=(28, 0))
            self._app_vars.append((var, app))

        self._update_start_button()

    def _update_start_button(self):
        any_checked = any(v.get() for v, _ in self._app_vars)
        self._start_btn.configure(state="normal" if any_checked else "disabled")

    def _submit_picker(self):
        if self._authed_user is None:
            self._show_credentials_step()
            return
        selected = [app for var, app in self._app_vars if var.get()]
        if not selected:
            return
        self._on_login_success(self._authed_user, selected)

    # ---------- step switching ----------
    def _show_credentials_step(self):
        if self._picker_step is not None:
            self._picker_step.pack_forget()
        self._cred_step.pack(fill="both", expand=True)

    def _show_picker_step(self):
        if self._picker_step is None:
            self._picker_step = self._build_picker_step(self._steps_container)
        self._cred_step.pack_forget()
        self._picker_step.pack(fill="both", expand=True)
        self._populate_picker()

    # ---------- public ----------
    def reset(self):
        self._authed_user = None
        self._username.set("")
        self._advisor.set("")
        self._error.configure(text="")
        self._show_credentials_step()
```

- [ ] **Step 3: Confirm widgets used here exist**

The view uses `FormField.set("")`, `HeaderBar`, `theme.font_*()`, `theme.CRIMSON_BUTTON_KW`, `theme.OUTLINE_BUTTON_KW`. Run:

```bash
grep -n "FormField\|HeaderBar\|CRIMSON_BUTTON_KW\|OUTLINE_BUTTON_KW\|font_h2\|font_body\|font_caption" ui/widgets.py ui/theme.py
```

Expected: all symbols present. If `FormField.set` was added in Task 7 Step 4 it's already there. If not, add it now using the snippet from Task 7 Step 4.

- [ ] **Step 4: Manual smoke check**

The session start path in `app_shell` is still expecting the old single-PID signature, so logging in fully will fail. We can still verify the picker flow visually:

```bash
python main.py
```

- Login form appears.
- Enter a non-existent username → "Username or advisor name not recognized."
- Enter empty fields → "Both fields are required."
- Enter valid creds (use a row from `allowed_users.csv`) → picker step appears with the seeded `Notepad` row visible.
- Start Session button is disabled until you check the box.
- Click `Back` → credentials step shown again, fields cleared.

Don't click `Start Session` (would crash because `app_shell` not updated yet). Close the window.

- [ ] **Step 5: Commit**

```bash
git add ui/login_view.py ui/widgets.py
git commit -m "login_view: two-step flow with app picker

After credential check, user picks apps to launch from the registered
list. Start Session is disabled until at least one box is checked.
on_login_success now takes (user, selected_apps)."
```

---

## Task 9: AppShell — wire selected_apps, multi-app watchdog with adoption

**Files:**
- Modify: `ui/app_shell.py`

- [ ] **Step 1: Update imports and `_handle_login_success`**

Open `ui/app_shell.py`. Replace the contents with:

```python
"""Root application window — view switcher and session orchestrator."""
import os
import time

import customtkinter as ctk

import app_registry
import config
import process_guard
import session
from session import SessionState
from ui.active_view import ActiveView
from ui.admin_view import AdminWindow, prompt_admin_password
from ui.login_view import LoginView
from ui.widgets import WarningToast


class AppShell(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OU Lab Access")
        self.geometry(config.LOGIN_GEOMETRY)
        self.configure(fg_color=config.WHITE)
        self.minsize(380, 440)

        self.state_: SessionState = SessionState()

        self._login = LoginView(
            self,
            on_login_success=self._handle_login_success,
            on_admin_requested=self._handle_admin_requested,
        )
        self._active = ActiveView(
            self,
            on_finish=self._handle_finish,
            on_status_change=self._handle_status_change,
            on_toggle_collapse=self._handle_toggle_collapse,
        )

        self._tick_id: str | None = None
        self._watchdog_id: str | None = None
        self._starting_session = False
        self._active_collapsed = False
        self._last_phase: str = "normal"
        self._last_block_notified_at: float = 0.0
        self._show_login()

        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self._schedule_watchdog()

    # ---------- view switching ----------
    def _show_login(self) -> None:
        self._active.pack_forget()
        self._login.pack(fill="both", expand=True)
        self._login.reset()
        self.overrideredirect(False)
        self.attributes("-topmost", False)
        self.title("OU Lab Access")
        self.minsize(380, 440)
        self.geometry(config.LOGIN_GEOMETRY)
        self._center_on_screen(*self._parse_size(config.LOGIN_GEOMETRY))

    def _show_active(self) -> None:
        self._login.pack_forget()
        self._active.pack(fill="both", expand=True)
        self._active_collapsed = False
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.minsize(1, 1)
        self._apply_active_geometry()
        self.deiconify()

    def _apply_active_geometry(self) -> None:
        w = config.ACTIVE_COLLAPSED_WIDTH if self._active_collapsed else config.ACTIVE_WIDTH
        h = config.ACTIVE_HEIGHT
        sw = self.winfo_screenwidth()
        x = sw - w - config.ACTIVE_MARGIN
        y = config.ACTIVE_MARGIN
        self.wm_geometry(f"{w}x{h}+{x}+{y}")
        self.update_idletasks()

    # ---------- event handlers ----------
    def _handle_login_success(self, user: dict, selected_apps: list[dict]) -> None:
        registered = app_registry.load_apps()
        self._starting_session = True
        try:
            ok, err = session.start_session(self.state_, user, selected_apps, registered)
        finally:
            self._starting_session = False
        if not ok:
            WarningToast(
                self,
                title="Could not start session",
                message=err or "Unknown error.",
                color=config.URGENT_RED,
                duration_ms=4500,
            )
            return
        for app in selected_apps:
            hint = app.get("window_hint") or ""
            if hint:
                process_guard.focus_window(hint)
        self._last_phase = "normal"
        self._show_active()
        self._schedule_tick()

    def _handle_finish(self) -> None:
        self.state_.status_report = self._active.current_status()
        self._cancel_tick()
        session.end_session(self.state_, "Manual", app_registry.load_apps())
        self._show_login()

    def _handle_status_change(self, value: str) -> None:
        self.state_.status_report = value

    def _handle_toggle_collapse(self, collapsed: bool) -> None:
        self._active_collapsed = collapsed
        self._apply_active_geometry()

    def _handle_admin_requested(self) -> None:
        if prompt_admin_password(self):
            AdminWindow(self)

    def _handle_close(self) -> None:
        self._cancel_watchdog()
        if self.state_.active:
            self._cancel_tick()
            session.end_session(self.state_, "AppClose", app_registry.load_apps())
        self.destroy()

    # ---------- tick loop ----------
    def _schedule_tick(self) -> None:
        self._tick_id = self.after(1000, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

    def _tick(self) -> None:
        self._tick_id = None
        if not self.state_.active:
            return

        record = session.tick(self.state_)
        self._active.on_tick(record)

        if record.phase != self._last_phase:
            self._handle_phase_transition(self._last_phase, record.phase, record.remaining_sec)
            self._last_phase = record.phase

        if record.remaining_sec <= 0:
            session.end_session(self.state_, "Timeout", app_registry.load_apps())
            self._show_login()
            return

        # NOTE: we no longer terminate the session when an allowed PID dies.
        # Per design, closed apps stay closed; the timer or FINISH SESSION
        # ends the session.

        self._schedule_tick()

    def _handle_phase_transition(self, prev: str, new: str, remaining: int) -> None:
        if prev == "normal" and new == "warn":
            self._active.expand_if_collapsed()
            WarningToast(
                self,
                title="Session ending soon",
                message=f"{remaining} seconds remaining",
                color=config.WARN_YELLOW,
                duration_ms=3500,
            )
            self._beep(880, 180)
        elif new == "urgent":
            self._active.expand_if_collapsed()
            WarningToast(
                self,
                title="Session ending NOW",
                message=f"{remaining} seconds remaining — save your work",
                color=config.URGENT_RED,
                duration_ms=4000,
            )
            self._beep(1200, 250)

    def _beep(self, freq: int, duration_ms: int) -> None:
        import threading

        def _play():
            try:
                import winsound
                winsound.Beep(freq, duration_ms)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    # ---------- always-on watchdog ----------
    WATCHDOG_INTERVAL_MS = 2000

    def _schedule_watchdog(self) -> None:
        self._watchdog_id = self.after(self.WATCHDOG_INTERVAL_MS, self._watchdog_tick)

    def _cancel_watchdog(self) -> None:
        if self._watchdog_id is not None:
            try:
                self.after_cancel(self._watchdog_id)
            except Exception:
                pass
            self._watchdog_id = None

    def _watchdog_tick(self) -> None:
        self._watchdog_id = None
        try:
            if self._starting_session:
                return

            registered = app_registry.load_apps()
            if not registered:
                return

            registered_paths = [a["exe_path"] for a in registered]
            seen = process_guard.list_matching_pids_many(registered_paths)
            allowed = set(self.state_.allowed_pids) if self.state_.active else set()

            killed_any = False
            if self.state_.active:
                selected_basenames = {
                    os.path.basename(a["exe_path"]).lower()
                    for a in self.state_.selected_apps
                }
            else:
                selected_basenames = set()

            for pid, basename in seen:
                if pid in allowed:
                    continue
                # During an active session, adopt re-launches of the user's selected apps.
                if self.state_.active and basename in selected_basenames:
                    self.state_.allowed_pids.append(pid)
                    continue
                # Otherwise: kill it.
                process_guard.terminate(pid)
                killed_any = True

            if killed_any and not self.state_.active:
                self._handle_unauthorized_launch()
        finally:
            self._schedule_watchdog()

    def _handle_unauthorized_launch(self) -> None:
        now = time.time()
        if now - self._last_block_notified_at < 4.0:
            return
        self._last_block_notified_at = now

        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass
        try:
            WarningToast(
                self,
                title="Access blocked",
                message="Sign in through the portal to use lab equipment.",
                color=config.URGENT_RED,
                duration_ms=3500,
            )
        except Exception:
            pass

    # ---------- utilities ----------
    @staticmethod
    def _parse_size(geom: str) -> tuple[int, int]:
        size = geom.split("+")[0]
        w, h = size.split("x")
        return int(w), int(h)

    def _center_on_screen(self, w: int, h: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
```

- [ ] **Step 2: Manual end-to-end smoke check (single app)**

```bash
python main.py
```

Log in with a valid user → check `Notepad` → `Start Session`. Notepad opens. Compact bar appears in the corner. Wait for warn/urgent transitions. Click `FINISH SESSION` → notepad closes, log row written. Open the admin portal → Usage Logs shows the row with `Apps = Notepad`.

- [ ] **Step 3: Manual smoke check (two apps + close-one + re-launch adoption)**

In admin → Manage Apps, add `Calculator / calc.exe / Calculator`. Log out (FINISH SESSION). Log back in, check `Notepad` and `Calculator`, Start Session. Both open.

- Manually close the calculator window. Wait 5 seconds. Confirm the timer continues, the active bar stays visible, and `is_alive` does not end the session.
- Re-launch `calc.exe` from the Start menu. Within 2 seconds (one watchdog tick) the calculator stays open — it gets adopted. Confirm in Task Manager that the new calc PID is not killed.
- Click `FINISH SESSION`. Both notepad (still open) and calculator (the adopted re-launch) close.
- Admin → Usage Logs → row shows `Apps = Notepad; Calculator`.

- [ ] **Step 4: Manual smoke check (watchdog blocks unselected registered app)**

With the same two-app session active, launch a non-selected registered app (if you have one — add another row in Manage Apps before starting the session). Confirm the watchdog terminates it within ~2 seconds and no toast appears (session is active).

- [ ] **Step 5: Manual smoke check (no session — block & toast)**

Log out. Manually launch `notepad.exe` from the Start menu. Within 2 seconds the watchdog kills it, the login window surfaces, and a red "Access blocked" toast appears. Rapid-launch 5 times in 2 seconds → toast appears once (rate-limit holds).

- [ ] **Step 6: Commit**

```bash
git add ui/app_shell.py
git commit -m "app_shell: wire multi-app sessions and adoption-aware watchdog

Login passes selected_apps to session.start_session. _tick no longer
ends the session on PID death (closed apps stay closed). Watchdog
checks all registered exes; PIDs not in allowed_pids are adopted if
they belong to the user's selected apps, otherwise terminated."
```

---

## Task 10: End-to-end manual sweep against the spec test plan

**Files:** none (verification only)

This task runs every numbered item from the spec's manual test plan back-to-back, on a clean install, to confirm nothing regressed across the implementation.

- [ ] **Step 1: Reset to a clean state**

```bash
rm -f "$PROGRAMDATA/OU-Lab-Monitor/registered_apps.csv"
rm -f "$PROGRAMDATA/OU-Lab-Monitor/usage_log.csv"
rm -f "$PROGRAMDATA/OU-Lab-Monitor/.audit_key"
```

(On Windows from a Git Bash shell. Skip the `usage_log.csv` line if you want to test legacy-row compat.)

- [ ] **Step 2: Run every numbered item from `docs/superpowers/specs/2026-04-28-multi-app-control-design.md` § Testing**

Open the spec and walk through items 1–25 in order. Confirm each. Note any failures.

For convenience, the items are:

1. Bootstrap creates seeded CSV.
2. Existing `usage_log.csv` integrity check still passes.
3–7. Admin Manage Apps tab CRUD.
8–12. Login picker behavior.
13–19. Multi-app session lifecycle.
20–21. Watchdog when no session active.
22–23. Audit log integrity (including hash mismatch on tamper).
24–25. Admin mutation during active session.

- [ ] **Step 3: If all pass, commit a marker**

```bash
git commit --allow-empty -m "verify: multi-app control end-to-end manual test plan passed"
```

If anything failed, file a fix as a separate commit referencing the failing item number from the spec.

---

## Self-Review Notes

**Spec coverage check:** Walked the spec section by section.
- Goal & decisions → Tasks 1–9 cover all five user-validated decisions.
- Architecture & file map → Task per file (Tasks 1, 2, 3, 4, 5, 6, 7, 8, 9 line up with each modified/new file).
- Data model → Task 1 (config), Task 2 (registry), Task 3 (bootstrap seed), Task 5 (audit log Apps column), Task 6 (SessionState dataclass).
- Session lifecycle → Task 6 (start/end), Task 9 (tick loop drops liveness check, watchdog adoption).
- UI → Task 7 (admin tab), Task 8 (picker), Task 9 (handler signature).
- Edge cases → covered as inline behavior in Tasks 6 (atomic spawn rollback, dead-PID terminate is no-op) and 9 (adoption rule, kill registered-but-unselected during session). The "registered_apps.csv corrupted" case is handled in Task 2 by `load_apps`'s try/except.
- Test plan → Task 10 walks every numbered item.

**Placeholder scan:** No TBDs, no "implement appropriate error handling," every code step shows the actual code, every command shows expected output.

**Type consistency:**
- `start_session(state, user, selected_apps, registered_apps) -> tuple[bool, Optional[str]]` defined Task 6, called Task 9. ✓
- `end_session(state, reason, registered_apps)` defined Task 6, called Task 9. ✓
- `audit_log.append_entry(user, start_ts, end_ts, status, apps: list[str])` defined Task 5, called Task 6. ✓
- `app_registry.{load_apps, append_app, update_app, remove_app, find_app}` defined Task 2, called Tasks 7, 8, 9. ✓
- `purge_orphans_many(exe_paths)` and `list_matching_pids_many(exe_paths) -> list[tuple[int, str]]` defined Task 4, called Tasks 6, 9. ✓
- `SessionState.{allowed_pids, selected_apps}` defined Task 6, read Task 9. ✓
- `LoginView(on_login_success=Callable[[dict, list[dict]], None], on_admin_requested=Callable)` defined Task 8, instantiated Task 9. ✓
