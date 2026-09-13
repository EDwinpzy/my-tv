import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
FUNCTION = ROOT.parent / "cloudfunctions" / "activate" / "index.js"


class ActivateV2FunctionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = FUNCTION.read_text(encoding="utf-8")

    def test_requires_protocol_two_and_known_action(self):
        self.assertIn("protocol !== 2", self.src)
        self.assertIn('["activate", "verify", "renew"]', self.src)
        self.assertIn('msg: "upgrade_required"', self.src)

    def test_accepts_only_full_sha256_device_identifier(self):
        self.assertIn("^[a-f0-9]{64}$", self.src)

    def test_renew_requires_a_current_card(self):
        self.assertIn('action === "renew"', self.src)
        self.assertIn("currentCode", self.src)
        self.assertIn('msg: "bad_current_code"', self.src)

    def test_forwards_full_v2_rpc_contract(self):
        for token in ("p_protocol", "p_action", "p_current_code"):
            self.assertIn(token, self.src)
        self.assertIn("p_code: code", self.src)
        self.assertIn("p_device: deviceId", self.src)
        self.assertIn("p_ip: ip", self.src)


if __name__ == "__main__":
    unittest.main()
