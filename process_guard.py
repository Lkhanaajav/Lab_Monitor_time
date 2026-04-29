"""Process lifecycle for the gated target application."""
import os
import subprocess
from typing import Optional

import psutil
import pygetwindow as gw


def _matching_procs(process_name: str):
    target = process_name.lower()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info["name"] or "").lower() == target:
                yield proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def purge_orphans(process_name: str) -> int:
    count = 0
    for proc in _matching_procs(process_name):
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except psutil.TimeoutExpired:
                proc.kill()
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return count


def spawn(process_name: str) -> int:
    return subprocess.Popen([process_name]).pid


def list_matching_pids(process_name: str) -> list[int]:
    return [proc.info["pid"] for proc in _matching_procs(process_name)]


def focus_window(window_hint: str) -> None:
    try:
        windows = gw.getWindowsWithTitle(window_hint)
    except Exception:
        return
    for w in windows:
        try:
            if w.isMinimized:
                w.restore()
            w.activate()
        except Exception:
            continue


def is_alive(pid: Optional[int]) -> bool:
    if pid is None:
        return False
    try:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except psutil.NoSuchProcess:
        return False


def terminate(pid: Optional[int]) -> None:
    if pid is None:
        return
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except psutil.TimeoutExpired:
            proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


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
