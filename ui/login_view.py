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
        super().__init__(parent, fg_color=config.WHITE)
        self._on_login_success = on_login_success
        self._on_admin_requested = on_admin_requested
        self._authed_user: dict | None = None
        self._app_vars: list[tuple[ctk.BooleanVar, dict]] = []
        self._start_btn: ctk.CTkButton | None = None

        HeaderBar(self, "OU Lab Access", "Sign in to use lab equipment").pack(fill="x")

        # The two step frames live inside a single container so swapping is cheap.
        self._steps_container = ctk.CTkFrame(self, fg_color=config.WHITE)
        self._steps_container.pack(fill="both", expand=True, padx=20, pady=12)

        self._cred_step = self._build_credentials_step(self._steps_container)
        self._picker_step: ctk.CTkFrame | None = None  # built on demand

        self._show_credentials_step()

    # ---------- step 1: credentials ----------
    def _build_credentials_step(self, parent) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=config.WHITE)

        self._username = FormField(frame, "Username")
        self._username.pack(fill="x", pady=4)
        self._advisor = FormField(frame, "Advisor Last Name")
        self._advisor.pack(fill="x", pady=4)

        self._error = ctk.CTkLabel(
            frame, text="",
            font=theme.font_caption(),
            text_color=config.URGENT_RED,
        )
        self._error.pack(anchor="w", pady=(4, 0))

        ctk.CTkButton(
            frame, text="Continue",
            command=self._submit_credentials,
            font=theme.font_body_bold(),
            height=36,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", pady=(12, 4))

        ctk.CTkButton(
            frame, text="Admin Portal",
            command=self._on_admin_requested,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        return frame

    def _submit_credentials(self):
        un = self._username.value().strip()
        adv = self._advisor.value().strip()
        if not un or not adv:
            self._error.configure(text="Both fields are required.")
            return
        user = auth.verify_credentials(un, adv)
        if user is None:
            self._error.configure(text="Username or advisor name not recognized.")
            return
        self._error.configure(text="")
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
        # Clear any previous checkboxes
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

    def _show_picker_step(self):
        if self._picker_step is None:
            self._picker_step = self._build_picker_step(self._steps_container)
        self._cred_step.pack_forget()
        self._picker_step.pack(fill="both", expand=True)
        self._populate_picker()

    # ---------- public ----------
    def reset(self):
        self._authed_user = None
        self._username.set("")
        self._advisor.set("")
        self._error.configure(text="")
        self._show_credentials_step()
