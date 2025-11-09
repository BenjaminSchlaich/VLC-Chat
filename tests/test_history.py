import json
import tempfile
import unittest
from pathlib import Path

from history import History


class HistoryTests(unittest.TestCase):
    def test_history_loads_existing_file(self) -> None:
        sample = [
            {"MAC": "ab", "SentMessages": ["hello"], "ReceivedMessages": ["hi"]},
            {"MAC": "ff", "SentMessages": [], "ReceivedMessages": ["broadcast"]},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.json"
            history_path.write_text(json.dumps(sample), encoding="utf-8")

            history = History(storage_path=history_path)

            self.assertEqual(["AB", "FF"], history.list_contacts())
            convo = history.get_conversation("ab")
            self.assertEqual("AB", convo.mac)
            self.assertEqual(["hello"], convo.sent_messages)
            self.assertEqual(["hi"], convo.received_messages)

    def test_history_records_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            history_path = Path(tmpdir) / "history.json"
            history = History(storage_path=history_path)

            history.record_sent_message("aa", "Hello there")
            history.record_received_message("aa", "General Kenobi")

            data = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual("AA", data[0]["MAC"])
            self.assertEqual(["Hello there"], data[0]["SentMessages"])
            self.assertEqual(["General Kenobi"], data[0]["ReceivedMessages"])

            convo = history.get_conversation("AA")
            convo.sent_messages.append("mutation")
            convo2 = history.get_conversation("AA")
            self.assertNotIn("mutation", convo2.sent_messages)


if __name__ == "__main__":
    unittest.main()
