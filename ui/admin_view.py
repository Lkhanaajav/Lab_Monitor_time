"""Admin portal — logs, user management, integrity verification."""
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

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
        self._tabs.add("Integrity")

        self._build_logs_tab(self._tabs.tab("Usage Logs"))
        self._build_users_tab(self._tabs.tab("Manage Users"))
        self._build_integrity_tab(self._tabs.tab("Integrity"))

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

        entries = audit_log.read_entries()
        if not entries:
            messagebox.showinfo("Export", "No log entries to export.", parent=self)
            return

        default_name = f"lab_usage_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
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

        messagebox.showinfo("Export", f"Exported {len(entries)} rows to:\n{path}", parent=self)

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
    dlg = ctk.CTkInputDialog(
        title="Admin Portal",
        text="Enter admin password:",
    )
    entered = dlg.get_input()
    if entered is None:
        return False
    if entered == config.ADMIN_PASSWORD:
        return True
    messagebox.showerror("Denied", "Incorrect password", parent=parent)
    return False
