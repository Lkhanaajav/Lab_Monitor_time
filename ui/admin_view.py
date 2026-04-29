"""Admin portal — logs, user management, integrity verification."""
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import app_registry
import audit_log
import auth
import config
from ui import theme
from ui.widgets import FormField, HeaderBar


class AdminWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("OU Lab Admin Portal")
        self.geometry(config.ADMIN_GEOMETRY)
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()

        HeaderBar(self, "OU Lab Admin Portal", "Logs · Users · Integrity").pack(fill="x")

        self._tabs = ctk.CTkTabview(
            self,
            fg_color=config.GRAY_50,
            segmented_button_selected_color=config.CRIMSON,
            segmented_button_selected_hover_color=config.CRIMSON_HOVER,
            segmented_button_unselected_color=config.GRAY_100,
            text_color=config.GRAY_900,
        )
        self._tabs.pack(fill="both", expand=True, padx=12, pady=12)

        self._tabs.add("Usage Logs")
        self._tabs.add("Manage Users")
        self._tabs.add("Manage Apps")
        self._tabs.add("Integrity")

        self._build_logs_tab(self._tabs.tab("Usage Logs"))
        self._build_users_tab(self._tabs.tab("Manage Users"))
        self._build_apps_tab(self._tabs.tab("Manage Apps"))
        self._build_integrity_tab(self._tabs.tab("Integrity"))

        ctk.CTkButton(
            self, text="Exit Lab Monitor",
            command=self._exit_app,
            font=theme.font_body_bold(),
            height=32, width=180,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(pady=(0, 12))

    def _exit_app(self) -> None:
        if not messagebox.askyesno(
            "Exit Lab Monitor",
            "Shut down the kiosk? The watchdog will also exit.\n"
            "Re-launch by running LabMonitor.exe.",
            parent=self,
        ):
            return
        self.master.exit_app()

    # ---------- Logs tab ----------
    def _build_logs_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color=config.WHITE)
        container.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("Date", "User", "4x4", "Advisor", "Equip", "Start", "End", "Min", "Status", "RowHash")
        self._tree = ttk.Treeview(container, columns=cols, show="headings", height=14)
        widths = {"Date": 90, "User": 140, "4x4": 80, "Advisor": 100, "Equip": 110,
                  "Start": 70, "End": 70, "Min": 50, "Status": 180, "RowHash": 110}
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=widths.get(c, 100), anchor="w")
        self._tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(container, orient="vertical", command=self._tree.yview)
        scroll.pack(side="right", fill="y")
        self._tree.configure(yscrollcommand=scroll.set)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        ctk.CTkButton(
            btn_row, text="Refresh",
            command=self._refresh_logs,
            font=theme.font_caption(),
            height=28, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Export to Excel",
            command=self._export_logs,
            font=theme.font_body_bold(),
            height=28, width=140,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="left", padx=4)

        self._refresh_logs()

    def _refresh_logs(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for entry in audit_log.read_entries():
            row_hash = entry.get("RowHash", "")
            short_hash = (row_hash[:10] + "…") if row_hash else "(legacy)"
            self._tree.insert("", "end", values=(
                entry.get("Date", ""), entry.get("User", ""), entry.get("4x4", ""),
                entry.get("Advisor", ""), entry.get("Equip", ""), entry.get("Start", ""),
                entry.get("End", ""), entry.get("Min", ""), entry.get("Status", ""),
                short_hash,
            ))

    def _export_logs(self):
        try:
            from openpyxl import Workbook
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "openpyxl is required to export to Excel.\n\nInstall it with:\n    pip install openpyxl",
                parent=self,
            )
            return

        all_entries = audit_log.read_entries()
        if not all_entries:
            messagebox.showinfo("Export", "No log entries to export.", parent=self)
            return

        dlg = ExportRangeDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        start_date, end_date, label = dlg.result

        entries = [
            e for e in all_entries
            if _entry_in_range(e.get("Date", ""), start_date, end_date)
        ]
        if not entries:
            messagebox.showinfo(
                "Export",
                f"No log entries between {start_date} and {end_date}.",
                parent=self,
            )
            return

        suffix = label or f"{start_date}_to_{end_date}"
        default_name = f"lab_usage_log_{suffix}.xlsx"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Usage Logs",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel Workbook", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "Usage Logs"
            ws.append(audit_log.COLUMNS)
            for entry in entries:
                ws.append([entry.get(col, "") for col in audit_log.COLUMNS])
            for col_idx, col_name in enumerate(audit_log.COLUMNS, start=1):
                max_len = max(
                    [len(col_name)] + [len(str(entry.get(col_name, ""))) for entry in entries]
                )
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 60)
            ws.freeze_panes = "A2"
            wb.save(path)
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self)
            return

        messagebox.showinfo(
            "Export",
            f"Exported {len(entries)} rows ({start_date} to {end_date}) to:\n{path}",
            parent=self,
        )

    # ---------- Users tab ----------
    def _build_users_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color=config.WHITE)
        container.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("First", "Last", "4x4", "Advisor", "Equip")
        self._user_tree = ttk.Treeview(container, columns=cols, show="headings", height=12)
        for c in cols:
            self._user_tree.heading(c, text=c)
            self._user_tree.column(c, width=140, anchor="w")
        self._user_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(container, orient="vertical", command=self._user_tree.yview)
        scroll.pack(side="right", fill="y")
        self._user_tree.configure(yscrollcommand=scroll.set)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        ctk.CTkButton(
            btn_row, text="Add New User",
            command=self._open_registration,
            font=theme.font_body_bold(),
            height=32, width=140,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Refresh",
            command=self._refresh_users,
            font=theme.font_caption(),
            height=32, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)

        self._refresh_users()

    def _refresh_users(self):
        for item in self._user_tree.get_children():
            self._user_tree.delete(item)
        _, detail_map = auth.load_users()
        for u in detail_map.values():
            self._user_tree.insert("", "end", values=(
                u.get("first_name", ""), u.get("last_name", ""),
                u.get("username", ""), u.get("advisor_last", ""),
                u.get("equipment_name", ""),
            ))

    def _open_registration(self):
        RegistrationDialog(self, on_saved=self._refresh_users)

    # ---------- Manage Apps tab ----------
    def _build_apps_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color=config.WHITE)
        container.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("Display Name", "Exe Path", "Window Hint")
        self._app_tree = ttk.Treeview(container, columns=cols, show="headings", height=12)
        widths = {"Display Name": 180, "Exe Path": 360, "Window Hint": 160}
        for c in cols:
            self._app_tree.heading(c, text=c)
            self._app_tree.column(c, width=widths.get(c, 140), anchor="w")
        self._app_tree.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(container, orient="vertical", command=self._app_tree.yview)
        scroll.pack(side="right", fill="y")
        self._app_tree.configure(yscrollcommand=scroll.set)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(pady=6)
        ctk.CTkButton(
            btn_row, text="Add App",
            command=self._open_app_add,
            font=theme.font_body_bold(),
            height=32, width=120,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Edit Selected",
            command=self._open_app_edit,
            font=theme.font_caption(),
            height=32, width=120,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Remove Selected",
            command=self._remove_app,
            font=theme.font_caption(),
            height=32, width=140,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="Refresh",
            command=self._refresh_apps,
            font=theme.font_caption(),
            height=32, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="left", padx=4)

        self._refresh_apps()

    def _refresh_apps(self):
        for item in self._app_tree.get_children():
            self._app_tree.delete(item)
        for a in app_registry.load_apps():
            self._app_tree.insert("", "end", values=(
                a.get("display_name", ""),
                a.get("exe_path", ""),
                a.get("window_hint", ""),
            ))

    def _selected_app_display_name(self) -> str | None:
        sel = self._app_tree.selection()
        if not sel:
            return None
        values = self._app_tree.item(sel[0], "values")
        return values[0] if values else None

    def _open_app_add(self):
        AppDialog(self, on_saved=self._refresh_apps, existing=None)

    def _open_app_edit(self):
        name = self._selected_app_display_name()
        if not name:
            messagebox.showinfo("Edit", "Select an app first.", parent=self)
            return
        existing = app_registry.find_app(name)
        if existing is None:
            messagebox.showerror("Edit", f"App '{name}' not found.", parent=self)
            self._refresh_apps()
            return
        AppDialog(self, on_saved=self._refresh_apps, existing=existing)

    def _remove_app(self):
        name = self._selected_app_display_name()
        if not name:
            messagebox.showinfo("Remove", "Select an app first.", parent=self)
            return
        if not messagebox.askyesno("Remove", f"Remove '{name}' from the registered list?", parent=self):
            return
        if not app_registry.remove_app(name):
            messagebox.showerror("Remove", f"App '{name}' not found.", parent=self)
        self._refresh_apps()

    # ---------- Integrity tab ----------
    def _build_integrity_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color=config.WHITE)
        container.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            container,
            text="Audit Log Integrity Check",
            font=theme.font_h2(),
            text_color=config.GRAY_900,
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            container,
            text=(
                "Each log row is HMAC-chained to the previous row using a secret key\n"
                "stored in .audit_key. Any edit to a stored row breaks the chain."
            ),
            font=theme.font_body(),
            text_color=config.GRAY_600,
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        ctk.CTkButton(
            container, text="Verify Log",
            command=self._verify,
            font=theme.font_body_bold(),
            height=38, width=160,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(anchor="w")

        self._verify_result = ctk.CTkLabel(
            container, text="",
            font=theme.font_body_bold(),
            text_color=config.GRAY_900,
            justify="left",
        )
        self._verify_result.pack(anchor="w", pady=16)

    def _verify(self):
        ok, bad_row, msg = audit_log.verify_chain()
        color = config.SUCCESS_GREEN if ok else config.URGENT_RED
        prefix = "✓ " if ok else "✗ "
        self._verify_result.configure(text=prefix + msg, text_color=color)


class RegistrationDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_saved):
        super().__init__(parent)
        self.title("Register User")
        self.geometry("380x560")
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()
        self._on_saved = on_saved

        HeaderBar(self, "New User", "Register lab access").pack(fill="x")

        body = ctk.CTkScrollableFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        self._fields: dict[str, FormField] = {}
        for fname in config.USER_FIELDS:
            label = fname.replace("_", " ").title()
            ff = FormField(body, label)
            ff.pack(fill="x", pady=2)
            self._fields[fname] = ff

        ctk.CTkButton(
            self, text="Save",
            command=self._save,
            font=theme.font_body_bold(),
            height=36,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", padx=16, pady=(4, 14))

    def _save(self):
        row = {f: self._fields[f].value().strip() for f in config.USER_FIELDS}
        missing = [f for f, v in row.items() if not v]
        for f in config.USER_FIELDS:
            self._fields[f].clear_error()
        if missing:
            for f in missing:
                self._fields[f].set_error("Required")
            return
        try:
            auth.append_user(row)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self._on_saved()
        self.destroy()


def prompt_admin_password(parent) -> bool:
    dlg = AdminPasswordDialog(parent)
    parent.wait_window(dlg)
    if dlg.result is None:
        return False
    if dlg.result == config.ADMIN_PASSWORD:
        return True
    messagebox.showerror("Denied", "Incorrect password", parent=parent)
    return False


class AdminPasswordDialog(ctk.CTkToplevel):
    """Themed admin-password prompt — matches OU crimson style."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Admin Portal")
        self.geometry("380x300")
        self.minsize(380, 300)
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()
        self.result: str | None = None

        HeaderBar(self, "Admin Portal", "Enter admin password").pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=20, pady=14)

        self._field = FormField(body, "Password", show="*")
        self._field.pack(fill="x")
        self._field.focus()

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkButton(
            btns, text="Cancel",
            command=self._cancel,
            font=theme.font_caption(),
            height=32, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns, text="Unlock",
            command=self._submit,
            font=theme.font_body_bold(),
            height=32, width=120,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="right", padx=4)

        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self._cancel())

    def _submit(self) -> None:
        self.result = self._field.value()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def _entry_in_range(date_str: str, start: str, end: str) -> bool:
    if not date_str:
        return False
    return start <= date_str <= end


def _preset_range(preset: str) -> tuple[str, str, str]:
    today = date.today()
    if preset == "Last 7 Days":
        return (today - timedelta(days=6)).isoformat(), today.isoformat(), "last_7_days"
    if preset == "Last 30 Days":
        return (today - timedelta(days=29)).isoformat(), today.isoformat(), "last_30_days"
    if preset == "This Month":
        first = today.replace(day=1)
        return first.isoformat(), today.isoformat(), today.strftime("%Y_%m")
    if preset == "Last Month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev.isoformat(), last_prev.isoformat(), last_prev.strftime("%Y_%m")
    if preset == "This Year":
        return today.replace(month=1, day=1).isoformat(), today.isoformat(), str(today.year)
    return "1900-01-01", today.isoformat(), "all_time"


class ExportRangeDialog(ctk.CTkToplevel):
    """Picks a date range for exporting usage logs. `result` is (start, end, label) or None."""

    PRESETS = ("All Time", "This Month", "Last Month", "Last 7 Days", "Last 30 Days", "This Year", "Custom")

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Export Date Range")
        self.geometry("420x460")
        self.minsize(420, 460)
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()
        self.result: tuple[str, str, str] | None = None

        HeaderBar(self, "Export Range", "Pick a preset or enter custom dates").pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=20, pady=12)

        ctk.CTkLabel(
            body, text="Preset",
            font=theme.font_caption(),
            text_color=config.GRAY_600,
        ).pack(anchor="w")
        self._preset_var = ctk.StringVar(value="This Month")
        ctk.CTkOptionMenu(
            body, values=list(self.PRESETS),
            variable=self._preset_var,
            command=self._on_preset_changed,
            fg_color=config.CRIMSON,
            button_color=config.CRIMSON_HOVER,
            button_hover_color=config.CRIMSON_HOVER,
            text_color=config.WHITE,
            font=theme.font_body_bold(),
            height=36,
            dropdown_fg_color=config.WHITE,
            dropdown_hover_color=config.CRIMSON,
            dropdown_text_color=config.GRAY_900,
            dropdown_font=theme.font_body(),
        ).pack(fill="x", pady=(2, 12))

        self._start = FormField(body, "Start Date (YYYY-MM-DD)")
        self._start.pack(fill="x", pady=4)
        self._end = FormField(body, "End Date (YYYY-MM-DD)")
        self._end.pack(fill="x", pady=4)

        self._on_preset_changed("This Month")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 14))
        ctk.CTkButton(
            btns, text="Cancel",
            command=self._cancel,
            font=theme.font_caption(),
            height=32, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns, text="Export",
            command=self._submit,
            font=theme.font_body_bold(),
            height=32, width=120,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(side="right", padx=4)

    def _on_preset_changed(self, value: str) -> None:
        if value == "Custom":
            return
        start, end, _ = _preset_range(value)
        self._start.set(start)
        self._end.set(end)

    def _submit(self) -> None:
        start = self._start.value().strip()
        end = self._end.value().strip()
        self._start.clear_error()
        self._end.clear_error()
        try:
            sd = datetime.strptime(start, "%Y-%m-%d").date()
        except ValueError:
            self._start.set_error("Use YYYY-MM-DD")
            return
        try:
            ed = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            self._end.set_error("Use YYYY-MM-DD")
            return
        if sd > ed:
            self._end.set_error("End must be on/after start")
            return
        preset = self._preset_var.get()
        if preset == "Custom":
            label = f"{start}_to_{end}"
        else:
            _, _, label = _preset_range(preset)
        self.result = (start, end, label)
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class AppDialog(ctk.CTkToplevel):
    """Add or edit a registered app. If `existing` is given, dialog is in edit mode."""

    def __init__(self, parent, on_saved, existing: dict | None):
        super().__init__(parent)
        self._existing = existing
        self._on_saved = on_saved
        self.title("Edit App" if existing else "Add App")
        self.geometry("460x520")
        self.minsize(420, 460)
        self.configure(fg_color=config.WHITE)
        self.transient(parent)
        self.grab_set()

        title = "Edit App" if existing else "Add App"
        subtitle = "Update an existing entry" if existing else "Register a new app"
        HeaderBar(self, title, subtitle).pack(fill="x")

        body = ctk.CTkScrollableFrame(self, fg_color=config.WHITE)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        self._fields: dict[str, FormField] = {}
        for fname in config.APP_FIELDS:
            label = fname.replace("_", " ").title()
            ff = FormField(body, label)
            ff.pack(fill="x", pady=6)
            if existing:
                ff.set(existing.get(fname, ""))
            self._fields[fname] = ff

        # Browse button next to exe_path
        browse_row = ctk.CTkFrame(body, fg_color="transparent")
        browse_row.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(
            browse_row, text="Browse…",
            command=self._browse_exe,
            font=theme.font_caption(),
            height=26, width=100,
            **theme.OUTLINE_BUTTON_KW,
        ).pack(anchor="e")

        ctk.CTkButton(
            self, text="Save",
            command=self._save,
            font=theme.font_body_bold(),
            height=36,
            **theme.CRIMSON_BUTTON_KW,
        ).pack(fill="x", padx=16, pady=(4, 14))

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select executable",
            filetypes=[("Executables", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self._fields["exe_path"].set(path)

    def _save(self):
        row = {f: self._fields[f].value().strip() for f in config.APP_FIELDS}
        for f in config.APP_FIELDS:
            self._fields[f].clear_error()

        if self._existing is None:
            err = app_registry.append_app(row)
        else:
            err = app_registry.update_app(self._existing["display_name"], row)

        if err is not None:
            # Heuristic: route message to the relevant field if obvious
            if "Display name" in err:
                self._fields["display_name"].set_error(err)
            elif "Exe path" in err:
                self._fields["exe_path"].set_error(err)
            else:
                messagebox.showerror("Save failed", err, parent=self)
            return
        self._on_saved()
        self.destroy()
