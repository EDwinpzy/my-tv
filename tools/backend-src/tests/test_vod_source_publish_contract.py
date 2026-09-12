import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "tools" / "vod_sources_migration.sql"
HOTUPDATE = ROOT / "cloudfunctions" / "hotupdate" / "index.js"


class VodSourcePublishContractTest(unittest.TestCase):
    def test_migration_exposes_required_rpc_without_table_grants(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        for name in ("vod_source_admin_list", "vod_source_admin_save", "vod_source_admin_delete",
                     "vod_source_admin_publish", "vod_source_public_check"):
            self.assertIn("function " + name, sql)
        self.assertNotIn("grant select on vod_source_drafts to anon", sql)

    def test_publish_is_versioned_and_atomic(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("for update", sql)
        self.assertIn("vod_source_versions", sql)
        self.assertIn("sha256", sql)
        self.assertIn("at least one enabled source", sql)

    def test_hotupdate_exposes_vod_source_check(self):
        js = HOTUPDATE.read_text(encoding="utf-8")
        self.assertIn('url.pathname === "/vod-sources/check"', js)
        self.assertIn('rpc("vod_source_public_check"', js)
        self.assertIn("VOD_SOURCE_CACHE_MS = 2 * 60 * 1000", js)


if __name__ == "__main__":
    unittest.main()
