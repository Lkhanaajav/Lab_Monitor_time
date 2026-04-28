"""Root application window — view switcher and session orchestrator."""
import customtkinter as ctk

import config
import process_guard
import session
from session import SessionState
from ui.active_view import ActiveView
from ui.admin_view import AdminWindow, prompt_admin_password
from ui.login_view import LoginView
from ui.widgets import WarningToast


class AppShell(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OU Lab Access")
        self.geometry(config.LOGIN_GEOMETRY)
        self.configure(fg_color=config.WHITE)
        self.minsize(380, 440)

        self.state_: SessionState = SessionState()

        self._login = LoginView(
            self,
            on_login_success=self._handle_login_success,
            on_admin_requested=self._handle_admin_requested,
        )
        self._active = ActiveView(
            self,
            on_finish=self._handle_finish,
            on_status_change=self._handle_status_change,
            on_toggle_collapse=self._handle_toggle_collapse,
        )

        self._tick_id: str | None = None
        self._watchdog_id: str | None = None
        self._starting_session = False
        self._active_collapsed = False
        self._last_phase: str = "normal"
        self._last_block_notified_at: float = 0.0
        self._show_login()

        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        self._schedule_watchdog()

    # ---------- view switching ----------
    def _show_login(self) -> None:
        self._active.pack_forget()
        self._login.pack(fill="both", expand=True)
        self._login.reset()
        self.overrideredirect(False)
        self.attributes("-topmost", False)
        self.title("OU Lab Access")
        self.minsize(380, 440)
        self.geometry(config.LOGIN_GEOMETRY)
        self._center_on_screen(*self._parse_size(config.LOGIN_GEOMETRY))

    def _show_active(self) -> None:
        self._login.pack_forget()
        self._active.pack(fill="both", expand=True)
        self._active_collapsed = False
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.minsize(1, 1)
        self._apply_active_geometry()
        self.deiconify()

    def _apply_active_geometry(self) -> None:
        w = config.ACTIVE_COLLAPSED_WIDTH if self._active_collapsed else config.ACTIVE_WIDTH
        h = config.ACTIVE_HEIGHT
        sw = self.winfo_screenwidth()
        x = sw - w - config.ACTIVE_MARGIN
        y = config.ACTIVE_MARGIN
        self.wm_geometry(f"{w}x{h}+{x}+{y}")
        self.update_idletasks()

    # ---------- event handlers ----------
    def _handle_login_success(self, user: dict) -> None:
        self._starting_session = True
        try:
            ok = session.start_session(self.state_, user)
        finally:
            self._starting_session = False
        if not ok:
            return
        process_guard.focus_window(config.TARGET_APP_WINDOW_HINT)
        self._last_phase = "normal"
        self._show_active()
        self._schedule_tick()

    def _handle_finish(self) -> None:
        self.state_.status_report = self._active.current_status()
        self._cancel_tick()
        session.end_session(self.state_, "Manual")
        self._show_login()

    def _handle_status_change(self, value: str) -> None:
        self.state_.status_report = value

    def _handle_toggle_collapse(self, collapsed: bool) -> None:
        self._active_collapsed = collapsed
        self._apply_active_geometry()

    def _handle_admin_requested(self) -> None:
        if prompt_admin_password(self):
            AdminWindow(self)

    def _handle_close(self) -> None:
        self._cancel_watchdog()
        if self.state_.active:
            self._cancel_tick()
            session.end_session(self.state_, "AppClose")
        self.destroy()

    # ---------- tick loop ----------
    def _schedule_tick(self) -> None:
        self._tick_id = self.after(1000, self._tick)

    def _cancel_tick(self) -> None:
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

    def _tick(self) -> None:
        self._tick_id = None
        if not self.state_.active:
            return

        record = session.tick(self.state_)
        self._active.on_tick(record)

        if record.phase != self._last_phase:
            self._handle_phase_transition(self._last_phase, record.phase, record.remaining_sec)
            self._last_phase = record.phase

        if record.remaining_sec <= 0:
            session.end_session(self.state_, "Timeout")
            self._show_login()
            return

        if not process_guard.is_alive(self.state_.allowed_pid):
            session.end_session(self.state_, "ProcessExit")
            self._show_login()
            return

        self._schedule_tick()

    def _handle_phase_transition(self, prev: str, new: str, remaining: int) -> None:
        if prev == "normal" and new == "warn":
            self._active.expand_if_collapsed()
            WarningToast(
                self,
                title="Session ending soon",
                message=f"{remaining} seconds remaining",
                color=config.WARN_YELLOW,
                duration_ms=3500,
            )
            self._beep(880, 180)
        elif new == "urgent":
            self._active.expand_if_collapsed()
            WarningToast(
                self,
                title="Session ending NOW",
                message=f"{remaining} seconds remaining — save your work",
                color=config.URGENT_RED,
                duration_ms=4000,
            )
            self._beep(1200, 250)

    def _beep(self, freq: int, duration_ms: int) -> None:
        import threading

        def _play():
            try:
                import winsound
                winsound.Beep(freq, duration_ms)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    # ---------- always-on watchdog ----------
    WATCHDOG_INTERVAL_MS = 2000

    def _schedule_watchdog(self) -> None:
        self._watchdog_id = self.after(self.WATCHDOG_INTERVAL_MS, self._watchdog_tick)

    def _cancel_watchdog(self) -> None:
        if self._watchdog_id is not None:
            try:
                self.after_cancel(self._watchdog_id)
            except Exception:
                pass
            self._watchdog_id = None

    def _watchdog_tick(self) -> None:
        self._watchdog_id = None
        try:
            if self._starting_session:
                return
            pids = process_guard.list_matching_pids(config.TARGET_APP_NAME)
            allowed = self.state_.allowed_pid if self.state_.active else None
            unauthorized = [p for p in pids if p != allowed]
            if unauthorized:
                for pid in unauthorized:
                    process_guard.terminate(pid)
                self._handle_unauthorized_launch()
        finally:
            self._schedule_watchdog()

    def _handle_unauthorized_launch(self) -> None:
        import time
        now = time.time()
        # Rate-limit the toast so it doesn't spam on repeated launches
        if now - self._last_block_notified_at < 4.0:
            return
        self._last_block_notified_at = now

        if not self.state_.active:
            try:
                self.deiconify()
                self.lift()
                self.focus_force()
            except Exception:
                pass
            try:
                WarningToast(
                    self,
                    title="Access blocked",
                    message="Sign in through the portal to use lab equipment.",
                    color=config.URGENT_RED,
                    duration_ms=3500,
                )
            except Exception:
                pass

    # ---------- utilities ----------
    @staticmethod
    def _parse_size(geom: str) -> tuple[int, int]:
        size = geom.split("+")[0]
        w, h = size.split("x")
        return int(w), int(h)

    def _center_on_screen(self, w: int, h: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
