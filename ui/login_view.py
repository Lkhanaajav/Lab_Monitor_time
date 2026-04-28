"""Login screen — credential entry + admin portal trigger."""
from typing import Callable

import customtkinter as ctk

import auth
import config
from ui import theme
from ui.widgets import FormField, HeaderBar


class LoginView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_login_success: Callable[[dict], None],
        on_admin_requested: Callable[[], None],
    ):
        super().__init__(parent, fg_color=config.WHITE, corner_radius=0)
        self._on_login_success = on_login_success
        self._on_admin_requested = on_admin_requested

        HeaderBar(self, "OU Lab Access", "Equipment access portal").pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=32, pady=24)

        ctk.CTkLabel(
            body,
            text="Sign in to begin your session",
            font=theme.font_h2(),
            text_color=config.GRAY_900,
        ).pack(anchor="w", pady=(0, 16))

        self._username = FormField(body, "OU NetID (4x4)")
        self._username.pack(fill="x", pady=(0, 10))

        self._advisor = FormField(body, "Advisor Last Name")
        self._advisor.pack(fill="x", pady=(0, 14))

        self._status = ctk.CTkLabel(
            body, text="", font=theme.font_caption(),
            text_color=config.URGENT_RED, anchor="w",
        )
        self._status.pack(fill="x")

        ctk.CTkButton(
            body, text="UNLOCK",
            command=self._on_unlock,
            font=theme.font_body_bold(),
            height=42,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", pady=(12, 6))

        ctk.CTkButton(
            body, text="Admin Portal",
            command=self._on_admin_requested,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x", pady=(0, 6))

        win_user = auth.current_windows_username()
        win_label = f"Sign in with Windows ({win_user})" if win_user else "Sign in with Windows"
        ctk.CTkButton(
            body, text=win_label,
            command=self._on_windows_login,
            font=theme.font_caption(),
            height=28,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(fill="x")

        parent.bind("<Return>", lambda e: self._on_unlock())
        self.after(100, self._username.focus)

    def _on_windows_login(self) -> None:
        self._username.clear_error()
        self._advisor.clear_error()
        self._status.configure(text="")
        user, win_username = auth.verify_windows_user()
        if user is None:
            if win_username:
                self._status.configure(
                    text=f"Windows account '{win_username}' is not registered. Ask admin to add you.",
                )
            else:
                self._status.configure(text="Could not read your Windows username.")
            return
        self._username.set_value("")
        self._advisor.set_value("")
        self._on_login_success(user)

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
            self._status.configure(text="Credentials not recognized. Check NetID and advisor name.")
            self._advisor.set_error(" ")
            self._username.set_error(" ")
            return

        self._username.set_value("")
        self._advisor.set_value("")
        self._on_login_success(user)

    def reset(self) -> None:
        self._username.set_value("")
        self._advisor.set_value("")
        self._username.clear_error()
        self._advisor.clear_error()
        self._status.configure(text="")
        self.after(100, self._username.focus)
