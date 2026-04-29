"""Mutual-watch process that keeps main.py alive.

If main.py dies (Task Manager kill, crash, taskkill), this respawns it
within ~1.5s. The watchdog itself is killable, but main.py spawns a fresh
one at startup, so defeating the kiosk requires killing both processes
roughly simultaneously.

Set OU_LAB_DISABLE_WATCHDOG=1 to disable spawn from main.py during dev.
Stop a running watchdog by terminating its PID (stored in .watchdog.pid)
or by exiting via the admin-authenticated close in the GUI.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

FROZEN = bool(getattr(sys, "frozen", False))
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
MAIN = HERE / "main.py"
MAIN_EXE_NAME = "LabMonitor.exe"

_PROGRAMDATA = os.environ.get("PROGRAMDATA") or os.environ.get("ProgramData")
DATA_DIR = Path(_PROGRAMDATA) / "OU-Lab-Monitor" if _PROGRAMDATA else HERE
PID_FILE = DATA_DIR / ".watchdog.pid"

POLL_INTERVAL_SEC = 1.5
RESPAWN_BACKOFF_SEC = 2.0


def _pythonw() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def _main_is_running() -> bool:
    me = os.getpid()
    main_exe_lower = MAIN_EXE_NAME.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] == me:
                continue
            name = (proc.info.get("name") or "").lower()
            if name == main_exe_lower:
                return True
            if name.startswith("python"):
                cmdline = proc.info.get("cmdline") or []
                if any("main.py" in (arg or "").lower() for arg in cmdline):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _spawn_main() -> None:
    if FROZEN:
        main_exe = HERE / MAIN_EXE_NAME
        if not main_exe.exists():
            return
        cmd = [str(main_exe)]
    else:
        cmd = [_pythonw(), str(MAIN)]

    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    env = os.environ.copy()
    env.pop("OU_LAB_DISABLE_WATCHDOG", None)
    try:
        subprocess.Popen(cmd, creationflags=flags, cwd=str(HERE), env=env)
    except OSError:
        pass


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    try:
        while True:
            try:
                if not _main_is_running():
                    _spawn_main()
                    time.sleep(RESPAWN_BACKOFF_SEC)
            except Exception:
                pass
            time.sleep(POLL_INTERVAL_SEC)
    finally:
        try:
            PID_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
