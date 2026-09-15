import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]


class WebRecoveryContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tools/backend-src/www/app.js").read_text(encoding="utf-8")

    def test_live_recovery_resolves_a_fresh_url(self):
        self.assertIn("async function recoverPlayback", self.source)
        self.assertIn("fresh=1", self.source)
        self.assertIn("recoveryGen", self.source)
        self.assertIn("MAX_RECOVERY_ATTEMPTS", self.source)

    def test_hls_fatal_error_uses_recovery_not_same_stale_load(self):
        start = self.source.index("function attachPlayer")
        block = self.source[start:self.source.index("function nextSource", start)]
        self.assertIn("recoverPlayback", block)
        self.assertNotIn("pv.hls.startLoad(); return", block)

    def test_foreground_and_network_hooks_refresh_visible_content(self):
        self.assertIn('addEventListener("online", refreshVisibleContent)', self.source)
        self.assertIn('addEventListener("focus", refreshVisibleContent)', self.source)
        self.assertIn('addEventListener("pageshow", refreshVisibleContent)', self.source)
        self.assertIn("backgroundedAt", self.source)


if __name__ == "__main__":
    unittest.main()

