"""First-run bootstrap — ensure DATA_DIR exists, migrate legacy files, initialize CSVs."""
import csv
import shutil

import config


def _migrate_if_needed(src_name: str, dst: "config.Path") -> bool:
    """If legacy file exists and destination is missing, move it over. Returns True if migrated."""
    src = config.LEGACY_DATA_DIR / src_name
    if src == dst:
        return False
    if dst.exists():
        return False
    if src.exists():
        try:
            shutil.copy2(src, dst)
            return True
        except OSError:
            return False
    return False


def ensure_data_dir() -> None:
    """Create DATA_DIR if missing. Swallows PermissionError by falling back to app folder."""
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Fallback: rewrite paths to the app folder if we can't write to ProgramData.
        config.DATA_DIR = config.LEGACY_DATA_DIR
        config.USER_LIST_FILE = config.DATA_DIR / "allowed_users.csv"
        config.LOG_FILE = config.DATA_DIR / "usage_log.csv"
        config.AUDIT_KEY_FILE = config.DATA_DIR / ".audit_key"


def ensure_user_list() -> None:
    """Create allowed_users.csv with header if missing. Migrate from legacy location first."""
    _migrate_if_needed("allowed_users.csv", config.USER_LIST_FILE)
    if not config.USER_LIST_FILE.exists():
        with open(config.USER_LIST_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(config.USER_FIELDS))
            writer.writeheader()


def ensure_log_file() -> None:
    """Migrate usage_log.csv from legacy location if present."""
    _migrate_if_needed("usage_log.csv", config.LOG_FILE)
    # Don't create an empty log file — audit_log.append_entry writes the header on first row.


def ensure_audit_key() -> None:
    """Migrate .audit_key from legacy location if present; otherwise audit_log will generate on first use."""
    _migrate_if_needed(".audit_key", config.AUDIT_KEY_FILE)


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


def run() -> None:
    ensure_data_dir()
    ensure_user_list()
    ensure_log_file()
    ensure_audit_key()
    ensure_apps_file()
