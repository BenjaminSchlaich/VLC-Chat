from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from history import Conversation, History
from gui.chat_view import ChatView
from gui.contacts_panel import ContactsPanel
from vlc_interface import VLCInterface


class ChatApp:
    """Tkinter-based GUI that connects the history with the VLC interface."""

    def __init__(self, *, history: History, vlc_interface: VLCInterface, local_mac: str, recv_color: str = "black") -> None:
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

        self.chat_view = ChatView(self.root, on_send=self._handle_send_message, recv_color=recv_color)
        self.chat_view.grid(row=0, column=1, sticky="nsew")

        self.current_mac: Optional[str] = None
        self.refresh_contacts(select_first=True)
        self.chat_view.focus_input()

        self.vlc_interface.register_message_callback(self._on_message_from_interface)
        self.vlc_interface.register_statistics_callback(self._on_stats_from_interface)
        self.vlc_interface.register_ack_callback(self._on_ack_from_interface)
        self.vlc_interface.register_sequence_callback(self._on_sequence_assigned)

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
        record = self.history.record_sent_message(mac, message)
        self.chat_view.append_message(mac, "sent", record)
        self._schedule_ack_timeout(mac, record.timestamp)
        self.vlc_interface.send_message(dest_mac=mac, message=message, timestamp=record.timestamp)
        self._logger.info("TX -> %s: %s", mac, message)

    def _on_message_from_interface(self, mac: str, message: str, stats: Optional[dict] = None) -> None:
        def _process() -> None:
            self._logger.info("RX <- %s: %s", mac, message)
            if stats:
                self._logger.info("RX stats: %s", stats)
            seq = stats.get("seq") if stats else None
            dest = stats.get("dest") if stats else None
            target_mac = "FF" if dest == "FF" else mac
            self.history.record_received_message(target_mac, message, seq=seq)
            self.refresh_contacts()
            if target_mac == self.current_mac:
                conversation = self._safe_get_conversation(target_mac)
                self.chat_view.show_conversation(target_mac, conversation)

        # Ensure UI updates happen on the Tk event loop.
        self.root.after(0, _process)

    def _on_stats_from_interface(self, stats: dict) -> None:
        self._logger.info("STAT %s", stats)

    def _on_ack_from_interface(self, mac: str, seq: int) -> None:
        def _process() -> None:
            updated = self.history.set_ack_status_by_seq(mac, seq, "true")
            if updated:
                self._logger.info("ACK confirmed for %s seq=%s", mac, seq)
                self._refresh_chat_if_current(mac)

        self.root.after(0, _process)

    def _on_sequence_assigned(self, mac: str, seq: int, timestamp) -> None:
        def _process() -> None:
            changed = self.history.set_sequence_for_message(mac, timestamp, seq)
            if changed:
                self._logger.info("Sequence %s assigned to %s", seq, mac)

        self.root.after(0, _process)

    def _schedule_ack_timeout(self, mac: str, timestamp) -> None:
        def _timeout() -> None:
            if self.history.fail_pending_ack(mac, timestamp):
                self._logger.warning("ACK timeout for %s @ %s", mac, timestamp)
                self._refresh_chat_if_current(mac)

        self.root.after(5000, _timeout)

    def _refresh_chat_if_current(self, mac: str) -> None:
        if self.current_mac == mac:
            conversation = self._safe_get_conversation(mac)
            self.chat_view.show_conversation(mac, conversation)

    def _safe_get_conversation(self, mac: str) -> Optional[Conversation]:
        try:
            return self.history.get_conversation(mac)
        except KeyError:
            return None

    def _handle_close(self) -> None:
        self.root.quit()
