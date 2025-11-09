import json
import tempfile
import unittest
from pathlib import Path

from main import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_normalizes_mac(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "MAC": "ab",
                        "FEC_THRESHOLD": 30,
                        "CHANNEL_BUSY_THRESHOLD": 20,
                        "N_RETRANSMISSIONS": 5,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)
            self.assertEqual("AB", config["MAC"])

    def test_load_config_missing_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            config_path.write_text(json.dumps({"MAC": "AB"}), encoding="utf-8")

            with self.assertRaises(KeyError):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
