from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from history import Conversation, History
from gui.chat_view import ChatView
from gui.contacts_panel import ContactsPanel
from vlc_interface import VLCInterface


class ChatApp:
    """Tkinter-based GUI that connects the history with the VLC interface."""

    def __init__(self, *, history: History, vlc_interface: VLCInterface, local_mac: str) -> None:
        self.history = history
        self.vlc_interface = vlc_interface
        self.local_mac = local_mac
        self._logger = logging.getLogger(__name__)

        self.root = tk.Tk()
        self.root.title("VLC Chat")
        self.root.geometry("960x600")
        self.root.minsize(720, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=3)
        self.root.rowconfigure(0, weight=1)

        self.contacts_panel = ContactsPanel(self.root, on_select=self._handle_contact_selection)
        self.contacts_panel.grid(row=0, column=0, sticky="nsew")

        self.chat_view = ChatView(self.root, on_send=self._handle_send_message)
        self.chat_view.grid(row=0, column=1, sticky="nsew")

        self.current_mac: Optional[str] = None
        self.refresh_contacts(select_first=True)
        self.chat_view.focus_input()

        self.vlc_interface.register_message_callback(self._on_message_from_interface)
        self.vlc_interface.register_statistics_callback(self._on_stats_from_interface)

    def run(self) -> None:
        self.root.mainloop()

    def refresh_contacts(self, *, select_first: bool = False) -> None:
        contacts = self.history.list_contacts()
        self.contacts_panel.set_contacts(contacts)
        if select_first and contacts:
            self.contacts_panel.select_contact(contacts[0])

    def _handle_contact_selection(self, mac: str) -> None:
        self.current_mac = mac
        conversation = self._safe_get_conversation(mac)
        self.chat_view.show_conversation(mac, conversation)

    def _handle_send_message(self, message: str) -> None:
        mac = self.current_mac
        if not mac:
            messagebox.showinfo("Select Contact", "Please select a contact before sending messages.")
            return
        self.history.record_sent_message(mac, message)
        self.chat_view.append_message(mac, "sent", message)
        self.vlc_interface.send_message(dest_mac=mac, message=message)
        self._logger.info("TX -> %s: %s", mac, message)

    def _on_message_from_interface(self, mac: str, message: str, stats: Optional[dict] = None) -> None:
        def _process() -> None:
            self._logger.info("RX <- %s: %s", mac, message)
            if stats:
                self._logger.info("RX stats: %s", stats)
            self.history.record_received_message(mac, message)
            self.refresh_contacts()
            self.chat_view.append_message(mac, "received", message)

        # Ensure UI updates happen on the Tk event loop.
        self.root.after(0, _process)

    def _on_stats_from_interface(self, stats: dict) -> None:
        self._logger.info("STAT %s", stats)

    def _safe_get_conversation(self, mac: str) -> Optional[Conversation]:
        try:
            return self.history.get_conversation(mac)
        except KeyError:
            return None

    def _handle_close(self) -> None:
        self.root.quit()
