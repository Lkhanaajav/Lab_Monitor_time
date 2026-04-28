"""OU Lab Access Portal — configuration constants."""
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent

TARGET_APP_NAME = "notepad.exe"
TARGET_APP_WINDOW_HINT = "Notepad"

# Shared data directory for multi-user lab PC.
# Falls back to app folder if PROGRAMDATA is unavailable.
_PROGRAMDATA = os.environ.get("PROGRAMDATA") or os.environ.get("ProgramData")
if _PROGRAMDATA:
    DATA_DIR = Path(_PROGRAMDATA) / "OU-Lab-Monitor"
else:
    DATA_DIR = _HERE

LEGACY_DATA_DIR = _HERE  # Where data lived before the move — used once for migration.

USER_LIST_FILE = DATA_DIR / "allowed_users.csv"
LOG_FILE = DATA_DIR / "usage_log.csv"
AUDIT_KEY_FILE = DATA_DIR / ".audit_key"

ADMIN_PASSWORD = "OU_Admin_2026"

TEST_MODE = True

if TEST_MODE:
    SESSION_LIMIT_SEC = 60
    WARN_START = 15
    URGENT_START = 5
else:
    SESSION_LIMIT_SEC = 1800
    WARN_START = 300
    URGENT_START = 60

CRIMSON = "#841617"
CRIMSON_HOVER = "#6b1213"
WHITE = "#FFFFFF"
GRAY_50 = "#FAFAFA"
GRAY_100 = "#F2F2F2"
GRAY_300 = "#D0D0D0"
GRAY_600 = "#6B6B6B"
GRAY_900 = "#1A1A1A"
WARN_YELLOW = "#F5C518"
URGENT_RED = "#D62828"
SUCCESS_GREEN = "#1E8E3E"

FONT_FAMILY = "Segoe UI"
FONT_SIZE_H1 = 22
FONT_SIZE_H2 = 16
FONT_SIZE_BODY = 12
FONT_SIZE_CAPTION = 10

LOGIN_GEOMETRY = "420x540"
ACTIVE_WIDTH = 280
ACTIVE_HEIGHT = 60
ACTIVE_COLLAPSED_WIDTH = 96
ACTIVE_MARGIN = 12
ADMIN_GEOMETRY = "920x540"

USER_FIELDS = (
    "first_name", "last_name", "cellphone", "email",
    "school_affiliation", "advisor_first", "advisor_last",
    "username", "equipment_name",
)
