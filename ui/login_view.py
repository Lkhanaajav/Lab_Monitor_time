"""Login view — credentials step + multi-app picker step."""
from typing import Callable

import customtkinter as ctk

import app_registry
import auth
import config
from ui import theme
from ui.widgets import FormField, HeaderBar


class LoginView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_login_success: Callable[[dict, list[dict]], None],
        on_admin_requested: Callable[[], None],
    ):
        super().__init__(parent, fg_color=config.WHITE, corner_radius=0)
        self._on_login_success = on_login_success
        self._on_admin_requested = on_admin_requested
        self._authed_user: dict | None = None
        self._app_vars: list[tuple[ctk.BooleanVar, dict]] = []
        self._start_btn: ctk.CTkButton | None = None

        HeaderBar(self, "OU Lab Access", "Equipment access portal").pack(fill="x")

        # The two step frames live inside a single container so swapping is cheap.
        self._steps_container = ctk.CTkFrame(self, fg_color=config.WHITE)
        self._steps_container.pack(fill="both", expand=True, padx=32, pady=24)

        self._cred_step = self._build_credentials_step(self._steps_container)
        self._picker_step: ctk.CTkFrame | None = None  # built on demand

        # Bind Enter key to submit credentials (only acts when credentials step is shown).
        parent.bind("<Return>", lambda e: self._on_unlock_if_visible())

        self._show_credentials_step()
        self.after(100, self._username.focus)

    # ---------- step 1: credentials ----------

    def _on_unlock_if_visible(self):
        """Fire _on_unlock only when the credentials step is currently mapped."""
        if self._picker_step is not None and self._picker_step.winfo_ismapped():
            return
        self._on_unlock()

    def _build_credentials_step(self, parent) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=config.WHITE)

        ctk.CTkLabel(
            frame,
            text="Sign in to begin your session",
            font=theme.font_h2(),
            text_color=config.GRAY_900,
        ).pack(anchor="w", pady=(0, 16))

        self._username = FormField(frame, "OU NetID (4x4)")
        self._username.pack(fill="x", pady=(0, 10))

        self._advisor = FormField(frame, "Advisor Last Name")
        self._advisor.pack(fill="x", pady=(0, 14))

        self._status = ctk.CTkLabel(
            frame, text="", font=theme.font_caption(),
            text_color=config.URGENT_RED, anchor="w",
        )
        self._status.pack(fill="x")

        ctk.CTkButton(
            frame, text="UNLOCK",
            command=self._on_unlock,
            font=theme.font_body_bold(),
            height=42,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", pady=(12, 6))

        ctk.CTkButton(
            frame, text="Admin Portal",
            command=self._on_admin_requested,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x", pady=(0, 6))

        win_user = auth.current_windows_username()
        win_label = (
            f"Sign in with Windows ({win_user})" if win_user else "Sign in with Windows"
        )
        ctk.CTkButton(
            frame, text=win_label,
            command=self._on_windows_login,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        return frame

    def _on_unlock(self) -> None:
        self._username.clear_error()
        self._advisor.clear_error()
        self._status.configure(text="")

        un = self._username.value().strip()
        adv = self._advisor.value().strip()

        has_error = False
        if not un:
            self._username.set_error("NetID required")
            has_error = True
        if not adv:
            self._advisor.set_error("Advisor last name required")
            has_error = True
        if has_error:
            return

        user = auth.verify_credentials(un, adv)
        if user is None:
            self._status.configure(
                text="Credentials not recognized. Check NetID and advisor name."
            )
            self._username.set_error(" ")
            self._advisor.set_error(" ")
            return

        self._username.set_value("")
        self._advisor.set_value("")
        self._authed_user = user
        self._show_picker_step()

    def _on_windows_login(self) -> None:
        self._username.clear_error()
        self._advisor.clear_error()
        self._status.configure(text="")
        user, win_username = auth.verify_windows_user()
        if user is None:
            if win_username:
                self._status.configure(
                    text=(
                        f"Windows account '{win_username}' is not registered. "
                        "Ask admin to add you."
                    ),
                )
            else:
                self._status.configure(text="Could not read your Windows username.")
            return
        self._username.set_value("")
        self._advisor.set_value("")
        self._authed_user = user
        self._show_picker_step()

    # ---------- step 2: app picker ----------

    def _build_picker_step(self, parent) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=config.WHITE)

        ctk.CTkLabel(
            frame, text="Select apps for this session",
            font=theme.font_h2(),
            text_color=config.GRAY_900,
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            frame, text="Pick one or more. Closing an app does not end your session.",
            font=theme.font_caption(),
            text_color=config.GRAY_600,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self._picker_list = ctk.CTkScrollableFrame(frame, fg_color=config.WHITE, height=180)
        self._picker_list.pack(fill="both", expand=True)

        self._start_btn = ctk.CTkButton(
            frame, text="Start Session",
            command=self._submit_picker,
            font=theme.font_body_bold(),
            height=36,
            state="disabled",
            **theme.CRIMSON_BUTTON_KW,
        )
        self._start_btn.pack(fill="x", pady=(8, 4))

        ctk.CTkButton(
            frame, text="Back",
            command=self._show_credentials_step,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        return frame

    def _populate_picker(self):
        # Clear any previous checkboxes.
        for child in list(self._picker_list.winfo_children()):
            child.destroy()
        self._app_vars = []

        apps = app_registry.load_apps()
        if not apps:
            ctk.CTkLabel(
                self._picker_list,
                text="No apps registered. Ask your admin to add one.",
                font=theme.font_body(),
                text_color=config.GRAY_600,
            ).pack(anchor="w", pady=8)
            self._start_btn.configure(state="disabled")
            return

        for app in apps:
            var = ctk.BooleanVar(value=False)
            row = ctk.CTkFrame(self._picker_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkCheckBox(
                row,
                text=app["display_name"],
                variable=var,
                command=self._update_start_button,
                font=theme.font_body(),
                text_color=config.GRAY_900,
                fg_color=config.CRIMSON,
                hover_color=config.CRIMSON_HOVER,
            ).pack(anchor="w")
            ctk.CTkLabel(
                row, text=app["exe_path"],
                font=theme.font_caption(),
                text_color=config.GRAY_600,
            ).pack(anchor="w", padx=(28, 0))
            self._app_vars.append((var, app))

        self._update_start_button()

    def _update_start_button(self):
        any_checked = any(v.get() for v, _ in self._app_vars)
        self._start_btn.configure(state="normal" if any_checked else "disabled")

    def _submit_picker(self):
        if self._authed_user is None:
            self._show_credentials_step()
            return
        selected = [app for var, app in self._app_vars if var.get()]
        if not selected:
            return
        self._on_login_success(self._authed_user, selected)

    # ---------- step switching ----------

    def _show_credentials_step(self):
        if self._picker_step is not None:
            self._picker_step.pack_forget()
        self._cred_step.pack(fill="both", expand=True)
        self.after(100, self._username.focus)

    def _show_picker_step(self):
        if self._picker_step is None:
            self._picker_step = self._build_picker_step(self._steps_container)
        self._cred_step.pack_forget()
        self._picker_step.pack(fill="both", expand=True)
        self._populate_picker()

    # ---------- public ----------

    def reset(self) -> None:
        self._authed_user = None
        self._username.set_value("")
        self._advisor.set_value("")
        self._username.clear_error()
        self._advisor.clear_error()
        self._status.configure(text="")
        self._show_credentials_step()
