"""Active session panel — compact horizontal bar, collapsible."""
from typing import Callable

import customtkinter as ctk

import config
from session import TickRecord
from ui import theme
from ui.widgets import ProgressRing


class ActiveView(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        on_finish: Callable[[], None],
        on_status_change: Callable[[str], None],
        on_toggle_collapse: Callable[[bool], None],
    ):
        super().__init__(
            parent,
            fg_color=config.WHITE,
            corner_radius=0,
            border_width=1,
            border_color=config.GRAY_300,
        )
        self.pack_propagate(False)

        self._on_finish = on_finish
        self._on_status_change = on_status_change
        self._on_toggle_collapse = on_toggle_collapse
        self._collapsed = False

        # Far left: crimson accent strip
        accent = ctk.CTkFrame(self, fg_color=config.CRIMSON, corner_radius=0, width=4)
        accent.pack(side="left", fill="y")

        # Far right: collapse toggle (real pack'd widget, always visible)
        self._toggle_btn = ctk.CTkButton(
            self, text="›",
            width=18,
            command=self._toggle,
            font=ctk.CTkFont(family=config.FONT_FAMILY, size=16, weight="bold"),
            fg_color=config.GRAY_100,
            hover_color=config.CRIMSON,
            text_color=config.CRIMSON,
            corner_radius=0,
        )
        self._toggle_btn.pack(side="right", fill="y")

        # Ring
        self._ring = ProgressRing(self, size=52)
        self._ring.pack(side="left", padx=(4, 2), pady=2)

        # Divider
        self._divider = ctk.CTkFrame(self, fg_color=config.GRAY_100, width=1)
        self._divider.pack(side="left", fill="y", pady=6)

        # Right panel — hidden when collapsed
        self._right_panel = ctk.CTkFrame(self, fg_color=config.WHITE)
        self._right_panel.pack(side="left", fill="both", expand=True, padx=(4, 4), pady=3)

        self._status_var = ctk.StringVar(value="Runs Smoothly")
        ctk.CTkOptionMenu(
            self._right_panel,
            values=["Runs Smoothly", "Minor Glitch", "Hardware Issue"],
            variable=self._status_var,
            command=self._on_status_change,
            font=theme.font_caption(),
            fg_color=config.WHITE,
            button_color=config.GRAY_300,
            button_hover_color=config.CRIMSON,
            dropdown_fg_color=config.WHITE,
            dropdown_text_color=config.GRAY_900,
            dropdown_hover_color=config.GRAY_100,
            text_color=config.GRAY_900,
            corner_radius=3,
            height=22,
        ).pack(fill="x", pady=(0, 2))

        ctk.CTkButton(
            self._right_panel, text="FINISH SESSION",
            command=self._on_finish,
            font=theme.font_body_bold(),
            height=22,
            corner_radius=3,
            **{k: v for k, v in theme.CRIMSON_BUTTON_KW.items() if k != "corner_radius"},
        ).pack(fill="x")

    def _toggle(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._right_panel.pack_forget()
            self._divider.pack_forget()
            self._toggle_btn.configure(text="‹")
        else:
            # Re-pack in original order: divider before right_panel, both before toggle
            # Use pack_forget on toggle and re-pack everything to restore order
            self._toggle_btn.pack_forget()
            self._divider.pack(side="left", fill="y", pady=6)
            self._right_panel.pack(side="left", fill="both", expand=True, padx=(4, 4), pady=3)
            self._toggle_btn.pack(side="right", fill="y")
            self._toggle_btn.configure(text="›")
        self._on_toggle_collapse(self._collapsed)

    def expand_if_collapsed(self) -> None:
        if self._collapsed:
            self._toggle()

    def on_tick(self, record: TickRecord) -> None:
        self._ring.update_state(
            record.remaining_sec,
            config.SESSION_LIMIT_SEC,
            record.phase,
            record.flash_on,
        )

    def current_status(self) -> str:
        return self._status_var.get()
