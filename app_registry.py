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
