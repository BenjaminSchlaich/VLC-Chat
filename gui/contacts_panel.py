from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Optional


class ContactsPanel(ttk.Frame):
    """Left-hand panel that lists known contacts by MAC address."""

    def __init__(self, master: tk.Widget, *, on_select: Callable[[str], None]) -> None:
        super().__init__(master, padding=12)
        self._on_select = on_select
        self._contacts: list[str] = []

        header = ttk.Label(self, text="Contacts", font=("TkDefaultFont", 12, "bold"))
        header.pack(anchor="w")

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, pady=(8, 0))

        self._listbox = tk.Listbox(container, height=20, exportselection=False)
        self._listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self._listbox.configure(yscrollcommand=scrollbar.set)

        self._listbox.bind("<<ListboxSelect>>", self._handle_select)

    def set_contacts(self, mac_addresses: Iterable[str]) -> None:
        selected_mac = self.get_selected_mac()
        self._contacts = list(mac_addresses)

        self._listbox.delete(0, tk.END)
        for mac in self._contacts:
            self._listbox.insert(tk.END, mac)

        if selected_mac:
            self.select_contact(selected_mac)

    def select_contact(self, mac: str) -> None:
        if mac not in self._contacts:
            return
        idx = self._contacts.index(mac)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._notify_selection(mac)

    def get_selected_mac(self) -> Optional[str]:
        selection = self._listbox.curselection()
        if not selection:
            return None
        idx = selection[0]
        if 0 <= idx < len(self._contacts):
            return self._contacts[idx]
        return None

    def _handle_select(self, event: tk.Event) -> None:  # type: ignore[override]
        mac = self.get_selected_mac()
        if mac:
            self._notify_selection(mac)

    def _notify_selection(self, mac: str) -> None:
        if self._on_select:
            self._on_select(mac)
