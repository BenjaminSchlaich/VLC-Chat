import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from history import History, ACK_OUTSTANDING, ACK_TRUE, ACK_FALSE


class HistoryTests(unittest.TestCase):
    def test_history_loads_existing_file(self) -> None:
        sample = [
            {
                "MAC": "ab",
                "SentMessages": [{"timestamp": "2025-11-08T14:36:20Z", "message": "hello", "ack": "true"}],
                "ReceivedMessages": [{"timestamp": "2025-11-08T14:37:20Z", "message": "hi"}],
            },
            {
                "MAC": "ff",
                "SentMessages": [{"timestamp": "2025-11-08T14:32:05Z", "message": "Hello, world!", "ack": "false"}],
                "ReceivedMessages": [{"timestamp": "2025-11-08T14:38:20Z", "message": "broadcast"}],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.json"
            history_path.write_text(json.dumps(sample), encoding="utf-8")

            history = History(storage_path=history_path)

            self.assertEqual(["AB", "FF"], history.list_contacts())
            convo = history.get_conversation("ab")
            self.assertEqual("AB", convo.mac)
            self.assertEqual("hello", convo.sent_messages[0].message)
            self.assertEqual(ACK_TRUE, convo.sent_messages[0].ack_status)
            self.assertEqual("hi", convo.received_messages[0].message)
            self.assertIsNone(convo.received_messages[0].ack_status)

    def test_history_records_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.json"
            history = History(storage_path=history_path)

            timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc)
            record = history.record_sent_message("aa", "Hello there", timestamp=timestamp)
            self.assertEqual(ACK_OUTSTANDING, record.ack_status)
            history.record_received_message("aa", "General Kenobi", timestamp=timestamp)

            history.set_ack_status("aa", timestamp, "true")

            data = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual("AA", data[0]["MAC"])
            self.assertEqual("Hello there", data[0]["SentMessages"][0]["message"])
            self.assertEqual("true", data[0]["SentMessages"][0]["ack"])
            self.assertEqual("General Kenobi", data[0]["ReceivedMessages"][0]["message"])
            self.assertEqual("2025-01-01T00:00:00Z", data[0]["SentMessages"][0]["timestamp"])

            convo = history.get_conversation("AA")
            convo.sent_messages.append(convo.sent_messages[0])
            convo2 = history.get_conversation("AA")
            self.assertEqual(1, len(convo2.sent_messages))

    def test_fail_pending_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.json"
            history = History(storage_path=history_path)
            ts = datetime(2025, 2, 1, tzinfo=timezone.utc)
            history.record_sent_message("aa", "Ping", timestamp=ts)

            changed = history.fail_pending_ack("aa", ts)
            self.assertTrue(changed)
            convo = history.get_conversation("aa")
            self.assertEqual(ACK_FALSE, convo.sent_messages[0].ack_status)


if __name__ == "__main__":
    unittest.main()
