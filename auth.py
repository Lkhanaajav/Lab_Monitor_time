"""User credential loading and verification."""
import csv
import os
from typing import Optional

import config


def load_users() -> tuple[dict[str, str], dict[str, dict]]:
    verify_map: dict[str, str] = {}
    detail_map: dict[str, dict] = {}
    if not config.USER_LIST_FILE.exists():
        return verify_map, detail_map
    with open(config.USER_LIST_FILE, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            username = row["username"].strip().lower()
            advisor = row["advisor_last"].strip().lower()
            verify_map[username] = advisor
            detail_map[username] = row
    return verify_map, detail_map


def verify_credentials(username: str, advisor_last: str) -> Optional[dict]:
    un = username.strip().lower()
    adv = advisor_last.strip().lower()
    verify_map, detail_map = load_users()
    if un in verify_map and verify_map[un] == adv:
        return detail_map[un]
    return None


def current_windows_username() -> str:
    """Return the logged-in Windows username (lowercase)."""
    username = os.environ.get("USERNAME") or ""
    if not username:
        try:
            username = os.getlogin()
        except OSError:
            username = ""
    return username.strip().lower()


def verify_windows_user() -> tuple[Optional[dict], str]:
    """
    Look up the current Windows username in allowed_users.csv.
    Returns (user_row, windows_username). user_row is None if not registered.
    """
    username = current_windows_username()
    if not username:
        return None, ""
    _, detail_map = load_users()
    return detail_map.get(username), username


def append_user(row: dict) -> None:
    file_exists = config.USER_LIST_FILE.exists()
    with open(config.USER_LIST_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(config.USER_FIELDS))
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in config.USER_FIELDS})
