"""Reusable widgets: ProgressRing, FormField, HeaderBar, WarningToast."""
import tkinter as tk

import customtkinter as ctk

import config
from ui import theme


class OUMark(tk.Canvas):
    """Circular OU monogram: crimson disc with white bold 'OU' text."""

    def __init__(self, parent, size: int = 44, bg: str = config.CRIMSON):
        super().__init__(
            parent, width=size, height=size,
            bg=bg, highlightthickness=0, bd=0,
        )
        self._size = size
        self._bg = bg
        self._draw()

    def _draw(self):
        s = self._size
        # Crimson filled disc
        self.create_oval(1, 1, s - 1, s - 1, fill=config.CRIMSON, outline=config.WHITE, width=2)
        # Bold "OU" centered
        self.create_text(
            s / 2, s / 2,
            text="OU",
            font=(config.FONT_FAMILY, int(s * 0.42), "bold"),
            fill=config.WHITE,
        )


class HeaderBar(ctk.CTkFrame):
    def __init__(self, parent, title: str, subtitle: str = "", show_mark: bool = True):
        super().__init__(
            parent,
            fg_color=config.CRIMSON,
            corner_radius=0,
            height=84,
        )
        self.pack_propagate(False)

        inner = ctk.CTkFrame(self, fg_color=config.CRIMSON, corner_radius=0)
        inner.pack(expand=True)

        if show_mark:
            mark_wrap = tk.Frame(inner, bg=config.CRIMSON)
            mark_wrap.pack(side="left", padx=(0, 12))
            OUMark(mark_wrap, size=48, bg=config.CRIMSON).pack()

        text_wrap = ctk.CTkFrame(inner, fg_color=config.CRIMSON)
        text_wrap.pack(side="left")

        ctk.CTkLabel(
            text_wrap, text=title,
            font=theme.font_h1(),
            text_color=config.WHITE,
            anchor="w",
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                text_wrap, text=subtitle,
                font=theme.font_caption(),
                text_color=config.WHITE,
                anchor="w",
            ).pack(anchor="w")


class FormField(ctk.CTkFrame):
    def __init__(self, parent, label: str, show: str | None = None):
        super().__init__(parent, fg_color="transparent")

        self._label = ctk.CTkLabel(
            self,
            text=label,
            font=theme.font_body_bold(),
            text_color=config.GRAY_900,
            anchor="w",
        )
        self._label.pack(fill="x", padx=2)

        self._entry = ctk.CTkEntry(
            self,
            font=theme.font_body(),
            height=36,
            corner_radius=6,
            border_width=1,
            border_color=config.GRAY_300,
            fg_color=config.WHITE,
            text_color=config.GRAY_900,
            show=show if show else "",
        )
        self._entry.pack(fill="x", pady=(4, 2))

        self._error = ctk.CTkLabel(
            self,
            text="",
            font=theme.font_caption(),
            text_color=config.URGENT_RED,
            anchor="w",
            height=16,
        )
        self._error.pack(fill="x", padx=2)

    def value(self) -> str:
        return self._entry.get()

    def set_value(self, v: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, v)

    def set_error(self, msg: str) -> None:
        self._error.configure(text=msg)
        self._entry.configure(border_color=config.URGENT_RED)

    def clear_error(self) -> None:
        self._error.configure(text="")
        self._entry.configure(border_color=config.GRAY_300)

    def focus(self) -> None:
        self._entry.focus_set()


class ProgressRing(tk.Canvas):
    """Circular countdown with color phase and optional flash."""

    def __init__(self, parent, size: int = 120):
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=config.WHITE,
            highlightthickness=0,
            bd=0,
        )
        self._size = size
        self._text_item = None
        self._arc_item = None
        self._ring_item = None
        self._draw(0, 1, "normal", False, "--:--")

    def _phase_color(self, phase: str, flash_on: bool) -> tuple[str, str]:
        if phase == "urgent":
            if flash_on:
                return config.URGENT_RED, config.WHITE
            return config.WARN_YELLOW, config.GRAY_900
        if phase == "warn":
            return config.WARN_YELLOW, config.GRAY_900
        return config.CRIMSON, config.WHITE

    def _draw(self, remaining: int, total: int, phase: str, flash_on: bool, text: str):
        self.delete("all")
        pad = 6
        w = self._size
        stroke = 9
        arc_color, _ = self._phase_color(phase, flash_on)

        # Background track (full gray ring)
        self.create_arc(
            pad, pad, w - pad, w - pad,
            start=0, extent=359.9,
            style="arc", outline=config.GRAY_100, width=stroke,
        )

        # Progress arc (colored, sweeps counter-clockwise from 12 o'clock)
        fraction = max(0.0, min(1.0, remaining / total if total else 0))
        extent = -360 * fraction
        if fraction > 0:
            self.create_arc(
                pad, pad, w - pad, w - pad,
                start=90, extent=extent,
                style="arc", outline=arc_color, width=stroke,
            )

        # Text color: arc color when flashing urgent (draws attention), else dark
        if phase == "urgent" and flash_on:
            text_color = config.URGENT_RED
        elif phase == "urgent":
            text_color = config.GRAY_900
        elif phase == "warn":
            text_color = config.GRAY_900
        else:
            text_color = config.CRIMSON

        self.create_text(
            w / 2, w / 2,
            text=text,
            font=(config.FONT_FAMILY, max(8, int(w * 0.22) - 2), "bold"),
            fill=text_color,
        )

    def update_state(self, remaining: int, total: int, phase: str, flash_on: bool):
        m, s = divmod(max(0, remaining), 60)
        text = f"{m:02d}:{s:02d}"
        self._draw(remaining, total, phase, flash_on, text)


class WarningToast(ctk.CTkToplevel):
    """Non-blocking warning popup that auto-dismisses, anchored near the active panel."""

    WIDTH = 280
    HEIGHT = 76

    def __init__(self, parent, title: str, message: str, color: str, duration_ms: int = 3500):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=color)

        sw = self.winfo_screenwidth()
        x = sw - self.WIDTH - config.ACTIVE_MARGIN
        y = config.ACTIVE_MARGIN + config.ACTIVE_HEIGHT + 8
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        inner = ctk.CTkFrame(self, fg_color=color, corner_radius=0)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        ctk.CTkLabel(
            inner, text=title,
            font=theme.font_body_bold(),
            text_color=config.WHITE,
        ).pack(padx=16, pady=(10, 0))
        ctk.CTkLabel(
            inner, text=message,
            font=theme.font_body(),
            text_color=config.WHITE,
        ).pack(padx=16, pady=(0, 10))

        self.after(10, self.deiconify)
        self.after(duration_ms, self._dismiss)

    def _dismiss(self):
        try:
            self.destroy()
        except Exception:
            pass
