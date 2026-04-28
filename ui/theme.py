"""OU brand theming for CustomTkinter."""
import customtkinter as ctk

import config


def apply_theme() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")  # overridden per-widget via OU colors


def font_h1() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=config.FONT_SIZE_H1, weight="bold")


def font_h2() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=config.FONT_SIZE_H2, weight="bold")


def font_body() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=config.FONT_SIZE_BODY)


def font_body_bold() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=config.FONT_SIZE_BODY, weight="bold")


def font_caption() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=config.FONT_SIZE_CAPTION)


def font_timer() -> ctk.CTkFont:
    return ctk.CTkFont(family=config.FONT_FAMILY, size=28, weight="bold")


CRIMSON_BUTTON_KW = dict(
    fg_color=config.CRIMSON,
    hover_color=config.CRIMSON_HOVER,
    text_color=config.WHITE,
    corner_radius=6,
    border_width=0,
)

OUTLINE_BUTTON_KW = dict(
    fg_color=config.WHITE,
    hover_color=config.GRAY_100,
    text_color=config.CRIMSON,
    corner_radius=6,
    border_width=1,
    border_color=config.CRIMSON,
)
