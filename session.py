"""Session lifecycle — state machine orchestrating audit log + process guard."""
import time
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import audit_log
import config
import process_guard

LogoutReason = Literal["Manual", "Timeout", "ProcessExit", "AppClose"]


@dataclass
class TickRecord:
    remaining_sec: int
    phase: Literal["normal", "warn", "urgent"]
    flash_on: bool


@dataclass
class SessionState:
    user: Optional[dict] = None
    start_ts: Optional[float] = None
    allowed_pid: Optional[int] = None
    status_report: str = "Runs Smoothly"
    _flash_on: bool = field(default=False, repr=False)

    @property
    def active(self) -> bool:
        return self.user is not None and self.start_ts is not None

    def clear(self) -> None:
        self.user = None
        self.start_ts = None
        self.allowed_pid = None
        self.status_report = "Runs Smoothly"
        self._flash_on = False


STATUS_BY_REASON = {
    "Manual": None,  # uses combobox value
    "Timeout": "FORGOT TO LOG OUT (Auto-Lock)",
    "ProcessExit": "Target app closed mid-session",
    "AppClose": "Portal closed mid-session",
}


def start_session(state: SessionState, user: dict) -> bool:
    process_guard.purge_orphans(config.TARGET_APP_NAME)
    try:
        pid = process_guard.spawn(config.TARGET_APP_NAME)
    except (FileNotFoundError, OSError):
        return False
    state.user = user
    state.start_ts = time.time()
    state.allowed_pid = pid
    state.status_report = "Runs Smoothly"
    state._flash_on = False
    return True


def end_session(state: SessionState, reason: LogoutReason) -> None:
    if not state.active:
        return
    user = state.user
    start_ts = state.start_ts
    pid = state.allowed_pid
    status = STATUS_BY_REASON[reason] or state.status_report

    try:
        audit_log.append_entry(user, start_ts, time.time(), status)
    except Exception as e:
        # If logging fails we must still clean up; surface the error via print
        # (UI callback will handle display).
        print(f"[audit_log] append failed: {e}")

    process_guard.terminate(pid)
    process_guard.purge_orphans(config.TARGET_APP_NAME)
    state.clear()


def seconds_remaining(state: SessionState) -> int:
    if not state.active:
        return 0
    elapsed = time.time() - state.start_ts
    return max(0, config.SESSION_LIMIT_SEC - int(elapsed))


def tick(state: SessionState) -> TickRecord:
    rem = seconds_remaining(state)
    if rem <= config.URGENT_START:
        phase: Literal["normal", "warn", "urgent"] = "urgent"
        state._flash_on = not state._flash_on
        flash = state._flash_on
    elif rem <= config.WARN_START:
        phase = "warn"
        flash = False
    else:
        phase = "normal"
        flash = False
    return TickRecord(remaining_sec=rem, phase=phase, flash_on=flash)
