import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
ADMIN = ROOT / "tools" / "admin.html"


class AdminLicenseV2ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ADMIN.read_text(encoding="utf-8")

    def test_exposes_v2_lifecycle_fields(self):
        for label in ("首次激活", "统一到期", "续费去向"):
            self.assertIn(label, self.source)
        for field in ("activated_at", "expire_at", "redeemed_at", "redeemed_to"):
            self.assertIn(field, self.source)

    def test_can_filter_redeemed_cards(self):
        self.assertIn('<option value="redeemed">已用于续费</option>', self.source)

    def test_redeemed_cards_hide_mutating_controls(self):
        self.assertIn('const redeemed = !!r.redeemed_at', self.source)
        self.assertIn('redeemed ? ""', self.source)


if __name__ == "__main__":
    unittest.main()
