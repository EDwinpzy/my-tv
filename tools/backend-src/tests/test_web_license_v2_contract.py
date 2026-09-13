import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
APP_JS = ROOT / "tools" / "backend-src" / "www" / "app.js"


class WebLicenseV2ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_JS.read_text(encoding="utf-8")

    def test_hashes_persistent_seed_with_origin(self):
        self.assertIn('async function webDeviceId()', self.source)
        self.assertIn('crypto.subtle.digest("SHA-256"', self.source)
        self.assertIn('location.origin', self.source)
        self.assertIn('`${seed}|web|${location.origin}`', self.source)
        self.assertIn('otvw:deviceSeed', self.source)

    def test_uses_protocol_two_actions_and_server_expiry(self):
        self.assertIn('protocol: 2', self.source)
        self.assertIn('action: action', self.source)
        self.assertIn('currentCode', self.source)
        self.assertIn('jo.licenseCode', self.source)
        self.assertIn('jo.activatedAt', self.source)
        self.assertIn('jo.expireAt', self.source)
        self.assertIn('jo.serverNow', self.source)
        self.assertNotIn('t.days * 86400000', self.source)

    def test_enforces_twenty_four_hour_transport_grace(self):
        self.assertIn('LICENSE_OFFLINE_GRACE_MS = 24 * 60 * 60 * 1000', self.source)
        self.assertIn('withinLicenseGrace', self.source)
        self.assertIn('[403, 404, 406].includes(jo.ret)', self.source)
        self.assertIn('jo.ret === 405', self.source)


if __name__ == "__main__":
    unittest.main()
