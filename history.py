
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Union, Optional, Tuple


@dataclass
class Conversation:
    """Container that holds all message history for a single MAC address."""

    mac: str
    sent_messages: List["MessageRecord"] = field(default_factory=list)
    received_messages: List["MessageRecord"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Union[str, Sequence[Dict[str, str]]]]:
        return {
            "MAC": self.mac,
            "SentMessages": [record.to_dict(include_ack=True) for record in self.sent_messages],
            "ReceivedMessages": [record.to_dict(include_ack=False) for record in self.received_messages],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Sequence[str]]) -> "Conversation":
        mac = payload.get("MAC")
        if not isinstance(mac, str) or not mac.strip():
            raise ValueError("Conversation entry is missing a valid MAC address.")

        def _messages(key: str, *, is_sent: bool) -> List["MessageRecord"]:
            value = payload.get(key, [])
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a list.")
            return [MessageRecord.from_payload(entry, origin=key, is_sent=is_sent) for entry in value]

        return cls(
            mac=_normalize_mac(mac),
            sent_messages=_messages("SentMessages", is_sent=True),
            received_messages=_messages("ReceivedMessages", is_sent=False),
        )

    def iter_events(self) -> Iterable[tuple[str, "MessageRecord"]]:
        """Return a chronological list of message events based on timestamps."""
        events = [("received", rec) for rec in self.received_messages] + [("sent", rec) for rec in self.sent_messages]
        events.sort(key=lambda item: (item[1].timestamp, 0 if item[0] == "received" else 1))
        for direction, record in events:
            yield direction, record

    def copy(self) -> "Conversation":
        return Conversation(
            mac=self.mac,
            sent_messages=[record.copy() for record in self.sent_messages],
            received_messages=[record.copy() for record in self.received_messages],
        )


@dataclass
class MessageRecord:
    timestamp: datetime
    message: str
    ack_status: Optional[str] = None
    seq: Optional[int] = None

    def to_dict(self, *, include_ack: bool) -> Dict[str, str]:
        payload = {"timestamp": _format_timestamp(self.timestamp), "message": self.message}
        if include_ack and self.ack_status is not None:
            payload["ack"] = self.ack_status
        if self.seq is not None:
            payload["seq"] = self.seq
        return payload

    def copy(self) -> "MessageRecord":
        return MessageRecord(timestamp=self.timestamp, message=self.message, ack_status=self.ack_status, seq=self.seq)

    @classmethod
    def from_payload(cls, payload, *, origin: str, is_sent: bool) -> "MessageRecord":
        if isinstance(payload, str):
            # Legacy format without timestamps.
            fallback_ts = _legacy_timestamp(origin)
            ack_status = ACK_TRUE if is_sent else None
            return cls(timestamp=fallback_ts, message=payload, ack_status=ack_status)
        if not isinstance(payload, dict):
            raise ValueError(f"Message entries in {origin} must be objects.")
        if "message" not in payload:
            raise ValueError(f"Message entry in {origin} missing 'message'.")
        message = payload["message"]
        if not isinstance(message, str):
            raise ValueError("Message text must be a string.")

        timestamp_raw = payload.get("timestamp")
        if not isinstance(timestamp_raw, str):
            raise ValueError("Message timestamp must be a string.")
        timestamp = _parse_timestamp(timestamp_raw)
        ack_field = payload.get("ack")
        ack_status = _normalize_ack_status(ack_field) if ack_field is not None else (ACK_TRUE if is_sent else None)
        seq_value = payload.get("seq")
        seq = _safe_int(seq_value) if seq_value is not None else None
        return cls(timestamp=timestamp, message=message, ack_status=ack_status, seq=seq)


ACK_TRUE = "true"
ACK_FALSE = "false"
ACK_OUTSTANDING = "outstanding"
ACK_STATUSES = {ACK_TRUE, ACK_FALSE, ACK_OUTSTANDING}


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
        self._seq_index: Dict[int, Tuple[str, MessageRecord]] = {}
        self._seq_offset: int = 0
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.reload()

    def reload(self) -> None:
        _reset_legacy_counters()
        self._seq_offset = 0
        if not self._storage_path.exists():
            self._conversations.clear()
            self._order.clear()
            self._seq_index.clear()
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
        self._seq_index.clear()
        for entry in data:
            if not isinstance(entry, dict):
                raise ValueError("Every conversation entry must be an object.")
            conversation = Conversation.from_dict(entry)
            self._conversations[conversation.mac] = conversation
            self._order.append(conversation.mac)
            self._register_conversation_sequences(conversation)
        self._seq_offset = max(self._seq_index.keys(), default=0)

    def save(self) -> None:
        conversations = [self._conversations[mac].to_dict() for mac in self._order]
        self._storage_path.write_text(json.dumps(conversations, indent=4), encoding="utf-8")

    def iter_conversations(self) -> Iterable[Conversation]:
        for mac in self._order:
            yield self._conversations[mac]

    def list_contacts(self) -> List[str]:
        return list(self._order)

    @property
    def seq_offset(self) -> int:
        return self._seq_offset

    def normalize_seq(self, raw_seq: Optional[int]) -> Optional[int]:
        if raw_seq is None:
            return None
        return raw_seq + self._seq_offset + 1

    def get_conversation(self, mac: str) -> Conversation:
        mac = _normalize_mac(mac)
        conversation = self._conversations.get(mac)
        if conversation is None:
            raise KeyError(f"No conversation found for MAC {mac}.")
        return conversation.copy()

    def ensure_contact(self, mac: str) -> Conversation:
        mac = _normalize_mac(mac)
        if mac not in self._conversations:
            self._conversations[mac] = Conversation(mac=mac)
            self._order.append(mac)
        return self._conversations[mac]

    def _register_conversation_sequences(self, conversation: Conversation) -> None:
        for record in conversation.sent_messages:
            self._index_sequence(conversation.mac, record)
        for record in conversation.received_messages:
            self._index_sequence(conversation.mac, record)

    def delete_contact(self, mac: str, persist: bool = True) -> None:
        mac = _normalize_mac(mac)
        if mac in self._conversations:
            del self._conversations[mac]
            self._order = [m for m in self._order if m != mac]
            self._rebuild_seq_index()
            if persist:
                self.save()

    def record_sent_message(
        self,
        mac: str,
        message: str,
        *,
        timestamp: datetime | None = None,
        ack_status: Optional[str] = None,
        seq: Optional[int] = None,
        persist: bool = True,
    ) -> "MessageRecord":
        record = self._append_message(
            mac,
            message,
            direction="sent",
            timestamp=timestamp,
            ack_status=ack_status or ACK_OUTSTANDING,
            seq=seq,
        )
        if persist:
            self.save()
        return record

    def record_received_message(
        self,
        mac: str,
        message: str,
        *,
        timestamp: datetime | None = None,
        seq: Optional[int] = None,
        persist: bool = True,
    ) -> "MessageRecord":
        record = self._append_message(mac, message, direction="received", timestamp=timestamp, seq=seq)
        if persist:
            self.save()
        return record

    def set_ack_status(self, mac: str, timestamp: Union[datetime, str], status: Union[str, bool], *, persist: bool = True) -> bool:
        mac = _normalize_mac(mac)
        normalized_status = _normalize_ack_status(status)
        record = self._find_sent_record(mac, timestamp)
        if record is None or record.ack_status == normalized_status:
            return False
        record.ack_status = normalized_status
        if persist:
            self.save()
        return True

    def set_ack_status_by_seq(self, seq: int, status: Union[str, bool], *, persist: bool = True) -> bool:
        entry = self._seq_index.get(seq)
        if not entry:
            return False
        normalized = _normalize_ack_status(status)
        record = entry[1]
        if record.ack_status == normalized:
            return False
        record.ack_status = normalized
        if persist:
            self.save()
        return True

    def fail_pending_ack(self, mac: str, timestamp: Union[datetime, str], *, persist: bool = True) -> bool:
        mac = _normalize_mac(mac)
        record = self._find_sent_record(mac, timestamp)
        if record is None or record.ack_status == ACK_TRUE or record.ack_status == ACK_FALSE:
            return False
        record.ack_status = ACK_FALSE
        if persist:
            self.save()
        return True

    def set_sequence_for_message(
        self, mac: str, timestamp: Union[datetime, str], seq: int, *, persist: bool = True
    ) -> bool:
        mac = _normalize_mac(mac)
        record = self._find_sent_record(mac, timestamp)
        if record is None:
            return False
        if record.seq == seq:
            return False
        if record.seq is not None and record.seq != seq:
            self._remove_sequence(record)
        record.seq = seq
        self._index_sequence(mac, record)
        if persist:
            self.save()
        return True

    def clear(self, persist: bool = True) -> None:
        self._conversations.clear()
        self._order.clear()
        self._seq_index.clear()
        if persist:
            self.save()

    def _append_message(
        self,
        mac: str,
        message: str,
        direction: str,
        timestamp: datetime | None = None,
        ack_status: Optional[str] = None,
        seq: Optional[int] = None,
    ) -> MessageRecord:
        if not isinstance(message, str):
            raise TypeError("Messages must be strings.")
        mac = _normalize_mac(mac)
        conversation = self.ensure_contact(mac)
        ts = timestamp or _now_utc()
        ack = _normalize_ack_status(ack_status) if ack_status is not None else (ACK_OUTSTANDING if direction == "sent" else None)
        record = MessageRecord(timestamp=ts, message=message, ack_status=ack, seq=seq)
        if direction == "sent":
            conversation.sent_messages.append(record)
        elif direction == "received":
            conversation.received_messages.append(record)
        else:
            raise ValueError("Unsupported direction provided to _append_message.")
        self._index_sequence(mac, record)
        return record

    def _find_sent_record(self, mac: str, timestamp: Union[datetime, str]) -> Optional[MessageRecord]:
        conversation = self._conversations.get(mac)
        if not conversation:
            return None
        target_ts = _coerce_timestamp(timestamp)
        for record in conversation.sent_messages:
            if record.timestamp == target_ts:
                return record
        return None

    def _index_sequence(self, mac: str, record: MessageRecord) -> None:
        if record.seq is None:
            return
        existing = self._seq_index.get(record.seq)
        if existing and existing[1] is not record:
            raise ValueError(f"Duplicate sequence number {record.seq} detected for {mac}.")
        self._seq_index[record.seq] = (mac, record)

    def _remove_sequence(self, record: MessageRecord) -> None:
        if record.seq is not None:
            self._seq_index.pop(record.seq, None)

    def _rebuild_seq_index(self) -> None:
        self._seq_index.clear()
        for conversation in self._conversations.values():
            self._register_conversation_sequences(conversation)


_LEGACY_COUNTERS: Dict[str, int] = {"SentMessages": 0, "ReceivedMessages": 0}


def _legacy_timestamp(origin: str) -> datetime:
    # Provides deterministic ordering for legacy entries without timestamps.
    count = _LEGACY_COUNTERS.setdefault(origin, 0)
    _LEGACY_COUNTERS[origin] = count + 1
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=count)


def _reset_legacy_counters() -> None:
    for key in _LEGACY_COUNTERS:
        _LEGACY_COUNTERS[key] = 0


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO 8601 timestamp: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_ack_status(value: Union[str, bool, None]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        normalized = ACK_TRUE if value else ACK_FALSE
    else:
        normalized = str(value).strip().lower()
        if normalized == "pending":
            normalized = ACK_OUTSTANDING
    if normalized not in ACK_STATUSES:
        raise ValueError(f"Invalid acknowledgement status: {value}")
    return normalized


def _coerce_timestamp(value: Union[datetime, str]) -> datetime:
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        ts = _parse_timestamp(value)
    else:
        raise TypeError("Timestamp must be datetime or ISO string.")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _safe_int(value: Union[str, int, None]) -> Optional[int]:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
