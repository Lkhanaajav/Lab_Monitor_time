"""Hash-chained tamper-evident usage log.

Threat model: defends against casual spreadsheet editing, not against a
local-admin adversary who can read .audit_key. For a single-PC lab prototype
this is the honest bar.
"""
import csv
import hmac
import os
import subprocess
from datetime import datetime
from hashlib import sha256

import config

COLUMNS = [
    "Date", "User", "4x4", "Advisor", "Equip",
    "Start", "End", "Min", "Status", "PrevHash", "RowHash",
]
LEGACY_COLUMNS = COLUMNS[:9]
GENESIS = "GENESIS"
UNIT_SEP = "\x1f"


def _load_or_create_key() -> bytes:
    if config.AUDIT_KEY_FILE.exists():
        with open(config.AUDIT_KEY_FILE, "rb") as f:
            return f.read()
    key = os.urandom(32)
    with open(config.AUDIT_KEY_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(config.AUDIT_KEY_FILE, 0o400)
    except OSError:
        pass
    if os.name == "nt":
        subprocess.run(
            ["attrib", "+h", "+s", str(config.AUDIT_KEY_FILE)],
            capture_output=True, check=False,
        )
    return key


def _row_hmac(prev_hash: str, row_fields: list[str], key: bytes) -> str:
    payload = (prev_hash + UNIT_SEP + UNIT_SEP.join(row_fields)).encode("utf-8")
    return hmac.new(key, payload, sha256).hexdigest()


def _unlock_log() -> None:
    if config.LOG_FILE.exists():
        try:
            os.chmod(config.LOG_FILE, 0o666)
        except OSError:
            pass
        if os.name == "nt":
            subprocess.run(
                ["attrib", "-h", "-s", "-r", str(config.LOG_FILE)],
                capture_output=True, check=False,
            )


def _lock_log() -> None:
    if not config.LOG_FILE.exists():
        return
    try:
        os.chmod(config.LOG_FILE, 0o444)
    except OSError:
        pass
    if os.name == "nt":
        subprocess.run(
            ["attrib", "+h", "+s", "+r", str(config.LOG_FILE)],
            capture_output=True, check=False,
        )


def _read_all_rows() -> list[list[str]]:
    if not config.LOG_FILE.exists():
        return []
    with open(config.LOG_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows


def _last_row_hash(rows: list[list[str]]) -> str:
    for row in reversed(rows[1:]):
        if len(row) >= len(COLUMNS) and row[-1]:
            return row[-1]
    return GENESIS


def append_entry(user: dict, start_ts: float, end_ts: float, status: str) -> None:
    _unlock_log()
    key = _load_or_create_key()
    rows = _read_all_rows()
    prev_hash = _last_row_hash(rows)

    duration = round((end_ts - start_ts) / 60, 2)
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


def read_entries() -> list[dict]:
    rows = _read_all_rows()
    if not rows:
        return []
    header, data = rows[0], rows[1:]
    entries = []
    for r in data:
        padded = r + [""] * (len(COLUMNS) - len(r))
        entries.append({COLUMNS[i]: padded[i] for i in range(len(COLUMNS))})
    return entries


def verify_chain() -> tuple[bool, int | None, str]:
    rows = _read_all_rows()
    if len(rows) <= 1:
        return True, None, "Log verified (0 rows)"

    key = _load_or_create_key()
    data_rows = rows[1:]
    prev_hash = GENESIS
    verified_count = 0
    skipped_legacy = 0

    for idx, row in enumerate(data_rows, start=1):
        if len(row) < len(COLUMNS) or not row[-1]:
            skipped_legacy += 1
            continue

        stored_prev = row[-2]
        stored_hash = row[-1]
        fields = row[:9]

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
    if skipped_legacy:
        msg += f"; {skipped_legacy} legacy row{'s' if skipped_legacy != 1 else ''} skipped (pre-hash format)"
    return True, None, msg


def rotate_if_needed() -> None:
    # TODO: implement archival rotation when row count exceeds threshold.
    # Must preserve chain-per-file semantics for verify_chain.
    pass
