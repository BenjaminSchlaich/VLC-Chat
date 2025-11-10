from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from history import Conversation, MessageRecord


MAX_MESSAGE_LENGTH = 200


class ChatView(ttk.Frame):
    """Displays the messages of the currently selected conversation."""

    def __init__(self, master: tk.Widget, *, on_send: Callable[[str], None], recv_color: str = "#ffffff") -> None:
        """recv_color: Tk color string used for incoming message text (e.g. "black" or "#ffffff")."""
        super().__init__(master, padding=12)
        self._on_send = on_send
        self._active_mac: Optional[str] = None

        self._contact_label = ttk.Label(self, text="No contact selected", font=("TkDefaultFont", 12, "bold"))
        self._contact_label.pack(anchor="w")

        self._text = tk.Text(self, wrap="word", state="disabled", height=25)
        self._text.pack(fill="both", expand=True, pady=(8, 8))
        self._text.tag_configure("sent_true", justify="right", foreground="#2ecc71")
        self._text.tag_configure("sent_outstanding", justify="right", foreground="#0a84ff")
        self._text.tag_configure("sent_false", justify="right", foreground="#ff3b30")
        # Configure the received tag using the supplied color.
        self._text.tag_configure("received", justify="left", foreground=recv_color)

        input_frame = ttk.Frame(self)
        input_frame.pack(fill="x")

        self._message_var = tk.StringVar()
        self._entry = ttk.Entry(input_frame, textvariable=self._message_var)
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.bind("<Return>", self._handle_send_event)

        self._send_button = ttk.Button(input_frame, text="Send", command=self._handle_send)
        self._send_button.pack(side="left", padx=(8, 0))

    def show_conversation(self, mac: Optional[str], conversation: Optional["Conversation"]) -> None:
        self._active_mac = mac
        title = f"Conversation with {mac}" if mac else "No contact selected"
        self._contact_label.configure(text=title)

        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)

        if conversation:
            for direction, record in conversation.iter_events():
                self._insert_record(direction, record)

        self._text.configure(state="disabled")
        self._text.see(tk.END)

    def append_message(self, mac: str, direction: str, record: "MessageRecord") -> None:
        if mac != self._active_mac:
            return
        self._text.configure(state="normal")
        self._insert_record(direction, record)
        self._text.configure(state="disabled")
        self._text.see(tk.END)

    def clear_input(self) -> None:
        self._message_var.set("")

    def focus_input(self) -> None:
        self._entry.focus_set()

    def _insert_record(self, direction: str, record: "MessageRecord") -> None:
        if not record.message:
            return
        if direction == "received":
            tag = "received"
        else:
            status = (record.ack_status or "outstanding").lower()
            tag = f"sent_{status}" if status in {"true", "outstanding", "false"} else "sent_outstanding"
        stamp = record.timestamp.astimezone().strftime("%H:%M:%S")
        self._text.insert(tk.END, f"[{stamp}] {record.message}\n", (tag,))

    def _handle_send_event(self, event: tk.Event) -> None:  # type: ignore[override]
        self._handle_send()

    def _handle_send(self) -> None:
        text = self._message_var.get()
        stripped = text.strip()
        if not stripped:
            return

        try:
            stripped.encode("ascii")
        except UnicodeEncodeError:
            messagebox.showerror("Invalid Message", "Messages may only contain ASCII characters.")
            return

        if len(stripped) > MAX_MESSAGE_LENGTH:
            messagebox.showerror("Invalid Message", f"Messages cannot exceed {MAX_MESSAGE_LENGTH} ASCII characters.")
            return

        if self._on_send:
            self._on_send(stripped)
        self._message_var.set("")
