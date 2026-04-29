"""OU Lab Access Portal — entry point."""
import os
import subprocess
import sys
from pathlib import Path

import psutil

import bootstrap
import config
from ui import theme
from ui.app_shell import AppShell

FROZEN = bool(getattr(sys, "frozen", False))
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
WATCHDOG_PID_FILE = config.DATA_DIR / ".watchdog.pid"
MAIN_PID_FILE = config.DATA_DIR / ".main.pid"
WATCHDOG_EXE_NAME = "LabMonitorWatchdog.exe"
MAIN_EXE_NAME = "LabMonitor.exe"


def _watchdog_alive() -> bool:
    if not WATCHDOG_PID_FILE.exists():
        return False
    try:
        pid = int(WATCHDOG_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    if not psutil.pid_exists(pid):
        return False
    try:
        proc = psutil.Process(pid)
        name = (proc.name() or "").lower()
        cmdline = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if name == WATCHDOG_EXE_NAME.lower():
        return True
    if name.startswith("python") and any("watchdog.py" in (arg or "").lower() for arg in cmdline):
        return True
    return False


def _ensure_watchdog() -> None:
    if os.environ.get("OU_LAB_DISABLE_WATCHDOG") == "1":
        return
    if _watchdog_alive():
        return

    if FROZEN:
        watchdog_exe = HERE / WATCHDOG_EXE_NAME
        if not watchdog_exe.exists():
            return
        cmd = [str(watchdog_exe)]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = str(pythonw) if pythonw.exists() else sys.executable
        cmd = [exe, str(HERE / "watchdog.py")]

    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    try:
        subprocess.Popen(cmd, creationflags=flags, cwd=str(HERE))
    except OSError:
        pass


def _another_main_alive() -> bool:
    """Return True if a different main-app process is already running.

    Excludes self and parent (PyInstaller bootloader has the same exe name as
    the extracted child).
    """
    me = os.getpid()
    try:
        my_parent_pid = psutil.Process(me).ppid()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        my_parent_pid = -1

    if not MAIN_PID_FILE.exists():
        return False
    try:
        pid = int(MAIN_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    if pid in (me, my_parent_pid):
        return False
    if not psutil.pid_exists(pid):
        return False
    try:
        proc = psutil.Process(pid)
        name = (proc.name() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if name == MAIN_EXE_NAME.lower():
        return True
    if name.startswith("python"):
        try:
            cmdline = proc.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        return any("main.py" in (arg or "").lower() for arg in cmdline)
    return False


def _claim_main_pid() -> None:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        MAIN_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def _release_main_pid() -> None:
    try:
        MAIN_PID_FILE.unlink()
    except OSError:
        pass


def main() -> None:
    bootstrap.run()
    if _another_main_alive():
        return
    _claim_main_pid()
    try:
        _ensure_watchdog()
        theme.apply_theme()
        app = AppShell()
        app.mainloop()
    finally:
        _release_main_pid()


if __name__ == "__main__":
    main()
