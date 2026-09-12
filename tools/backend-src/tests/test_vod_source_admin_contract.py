import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
ADMIN_SERVER = ROOT / "tools" / "admin_server.py"
ADMIN_HTML = ROOT / "tools" / "admin.html"

spec = importlib.util.spec_from_file_location("admin_server", ADMIN_SERVER)
admin_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin_server)


class VodSourceAdminContractTest(unittest.TestCase):
    def test_source_mutations_are_registered_behind_session_gate(self):
        source = ADMIN_SERVER.read_text(encoding="utf-8")
        for route in ("vod_source_list", "vod_source_save", "vod_source_delete",
                      "vod_source_discover", "vod_source_test", "vod_source_publish"):
            self.assertIn('"/api/' + route + '"', source)

    def test_test_grade_boundaries(self):
        self.assertEqual(admin_server.vod_test_grade(80), "优秀")
        self.assertEqual(admin_server.vod_test_grade(60), "良好")
        self.assertEqual(admin_server.vod_test_grade(40), "一般")
        self.assertEqual(admin_server.vod_test_grade(39), "不可用")

    def test_admin_has_draft_publish_and_per_source_test_controls(self):
        html = ADMIN_HTML.read_text(encoding="utf-8")
        self.assertIn('data-tab="vod-sources"', html)
        self.assertIn('id="btn-vod-source-publish"', html)
        self.assertIn('id="vod-source-test-veil"', html)
        self.assertIn('id="vod-source-preview"', html)
        self.assertIn("未发布变更", html)
        self.assertIn("立即推送", html)


if __name__ == "__main__":
    unittest.main()
