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


STATUS_BY_REASON = {
    "Manual": None,  # uses combobox value
    "Timeout": "FORGOT TO LOG OUT (Auto-Lock)",
    "AppClose": "Portal closed mid-session",
}


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
