
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass
class Conversation:
    """Container that holds all message history for a single MAC address."""

    mac: str
    sent_messages: List[str] = field(default_factory=list)
    received_messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Sequence[str]]:
        return {
            "MAC": self.mac,
            "SentMessages": list(self.sent_messages),
            "ReceivedMessages": list(self.received_messages),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Sequence[str]]) -> "Conversation":
        mac = payload.get("MAC")
        if not isinstance(mac, str) or not mac.strip():
            raise ValueError("Conversation entry is missing a valid MAC address.")

        def _messages(key: str) -> List[str]:
            value = payload.get(key, [])
            if not isinstance(value, list) or not all(isinstance(msg, str) for msg in value):
                raise ValueError(f"{key} must be a list of strings.")
            return list(value)

        return cls(mac=_normalize_mac(mac), sent_messages=_messages("SentMessages"), received_messages=_messages("ReceivedMessages"))


def _normalize_mac(mac: str) -> str:
    if not isinstance(mac, str):
        raise TypeError("MAC address must be provided as a string.")
    cleaned = mac.strip()
    if not cleaned:
        raise ValueError("MAC address must not be empty.")
    return cleaned.upper()


class History:
    """Loads and persists chat history for all contacts."""

    def __init__(self, storage_path: str | Path = Path(".data") / "history.json") -> None:
        self._storage_path = Path(storage_path)
        self._conversations: Dict[str, Conversation] = {}
        self._order: List[str] = []
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.reload()

    def reload(self) -> None:
        if not self._storage_path.exists():
            self._conversations.clear()
            self._order.clear()
            return

        try:
            raw = self._storage_path.read_text(encoding="utf-8")
            data = json.loads(raw or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in history file: {self._storage_path}") from exc

        if not isinstance(data, list):
            raise ValueError("History JSON must contain a list of conversations.")

        self._conversations.clear()
        self._order.clear()
        for entry in data:
            if not isinstance(entry, dict):
                raise ValueError("Every conversation entry must be an object.")
            conversation = Conversation.from_dict(entry)
            self._conversations[conversation.mac] = conversation
            self._order.append(conversation.mac)

    def save(self) -> None:
        conversations = [self._conversations[mac].to_dict() for mac in self._order]
        self._storage_path.write_text(json.dumps(conversations, indent=4), encoding="utf-8")

    def iter_conversations(self) -> Iterable[Conversation]:
        for mac in self._order:
            yield self._conversations[mac]

    def list_contacts(self) -> List[str]:
        return list(self._order)

    def get_conversation(self, mac: str) -> Conversation:
        mac = _normalize_mac(mac)
        conversation = self._conversations.get(mac)
        if conversation is None:
            raise KeyError(f"No conversation found for MAC {mac}.")
        return Conversation(mac=conversation.mac, sent_messages=list(conversation.sent_messages), received_messages=list(conversation.received_messages))

    def ensure_contact(self, mac: str) -> Conversation:
        mac = _normalize_mac(mac)
        if mac not in self._conversations:
            self._conversations[mac] = Conversation(mac=mac)
            self._order.append(mac)
        return self._conversations[mac]

    def delete_contact(self, mac: str, persist: bool = True) -> None:
        mac = _normalize_mac(mac)
        if mac in self._conversations:
            del self._conversations[mac]
            self._order = [m for m in self._order if m != mac]
            if persist:
                self.save()

    def record_sent_message(self, mac: str, message: str, persist: bool = True) -> None:
        self._append_message(mac, message, direction="sent")
        if persist:
            self.save()

    def record_received_message(self, mac: str, message: str, persist: bool = True) -> None:
        self._append_message(mac, message, direction="received")
        if persist:
            self.save()

    def clear(self, persist: bool = True) -> None:
        self._conversations.clear()
        self._order.clear()
        if persist:
            self.save()

    def _append_message(self, mac: str, message: str, direction: str) -> None:
        if not isinstance(message, str):
            raise TypeError("Messages must be strings.")
        mac = _normalize_mac(mac)
        conversation = self.ensure_contact(mac)
        if direction == "sent":
            conversation.sent_messages.append(message)
        elif direction == "received":
            conversation.received_messages.append(message)
        else:
            raise ValueError("Unsupported direction provided to _append_message.")
