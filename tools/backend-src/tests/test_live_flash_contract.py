import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("proxy_live_flash", ROOT / "proxy.py")
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class LiveFlashContractTest(unittest.TestCase):
    def test_cached_upcoming_projects_to_live_at_kickoff(self):
        item = {"date": "09-13", "time": "20:00", "status": "upcoming", "minute": ""}
        got = proxy.project_match_state(item, datetime(2026, 9, 13, 20, 0))
        self.assertEqual("live", got["status"])
        self.assertEqual("0", got["minute"])

    def test_finished_state_is_never_reopened(self):
        item = {"date": "09-13", "time": "20:00", "status": "finished", "minute": "90"}
        self.assertEqual("finished", proxy.project_match_state(item, datetime(2026, 9, 13, 20, 10))["status"])


if __name__ == "__main__":
    unittest.main()
