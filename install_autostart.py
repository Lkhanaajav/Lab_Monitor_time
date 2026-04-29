"""Register/unregister an HKCU Run entry that launches watchdog.py at user login.

Per-user, no admin needed. The lab user must be logged in once for this to take
effect; thereafter every login triggers the watchdog (which then spawns main.py).

Usage:
    python install_autostart.py            # install
    python install_autostart.py uninstall   # remove
    python install_autostart.py status      # show whether it's set
"""
import sys
import winreg
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCHDOG = HERE / "watchdog.py"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "OULabMonitor"


def _command() -> str:
    watchdog_exe = HERE / "LabMonitorWatchdog.exe"
    if watchdog_exe.exists():
        return f'"{watchdog_exe}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw) if pythonw.exists() else sys.executable
    return f'"{exe}" "{WATCHDOG}"'


def install() -> None:
    cmd = _command()
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    finally:
        winreg.CloseKey(key)
    print(f"Autostart installed for current user.\n  {cmd}")


def uninstall() -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, VALUE_NAME)
        finally:
            winreg.CloseKey(key)
        print("Autostart removed.")
    except FileNotFoundError:
        print("Autostart was not installed.")


def status() -> None:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            print(f"Installed:\n  {value}")
        except FileNotFoundError:
            print("Not installed.")
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        print("Not installed.")


if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "install"
    if action == "uninstall":
        uninstall()
    elif action == "status":
        status()
    else:
        install()
