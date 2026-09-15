"""豆瓣快照契约：云端与离线环境只有这份随包快照可用。

线上 v1.26 事故就是随包快照为空导致影视首页、详情与本地搜索一起变空，
所以这里既校验内容非空，也校验「无网络时仍可用」。
"""
import json
import pathlib
import sys
import tempfile
import unittest


BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import douban_catalog  # noqa: E402
import media_index  # noqa: E402


SNAPSHOT = BACKEND / "douban_snapshot.json"
CATEGORIES = ("movie", "tv", "anime", "variety", "short")
PINYIN = {"肖": "xiao", "申": "shen", "克": "ke", "的": "de", "救": "jiu", "赎": "shu"}


def offline_fetch(*_args, **_kwargs):
    raise OSError("offline")


class DoubanSnapshotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.catalog = douban_catalog.DoubanCatalog(fetch=offline_fetch, snapshot=cls.snapshot)

    def section_items(self, category):
        return [item for section in self.snapshot["home"][category]["sections"]
                for item in section["items"]]

    def test_home_sections_keep_the_product_contract(self):
        self.assertEqual(self.snapshot["source"], "douban")
        for category in CATEGORIES:
            value = self.snapshot["home"][category]
            self.assertEqual(value["category"], category)
            self.assertEqual([section["title"] for section in value["sections"]],
                             list(douban_catalog.HOME_SECTION_NAMES))

    def test_snapshot_is_not_an_empty_stub(self):
        for category in CATEGORIES:
            self.assertTrue(self.section_items(category), "%s 首页三段是空的" % category)
        for item in self.section_items("movie"):
            self.assertTrue(str(item.get("douban_id") or "").isdigit())
            self.assertTrue(str(item.get("title") or "").strip())

    def test_home_serves_snapshot_without_network(self):
        result = self.catalog.home("movie")
        self.assertTrue(result["stale"])
        self.assertEqual(result["source"], "douban-snapshot")
        self.assertTrue(result["sections"][0]["items"])

    def test_show_falls_back_to_snapshot_page(self):
        result = self.catalog.show("movie", sort="hot", page=1)
        self.assertEqual(result["source"], "douban-snapshot")
        self.assertTrue(result["items"])
        self.assertLessEqual(len(result["items"]), douban_catalog.EXPLORE_PAGE_SIZE)
        self.assertTrue(all(item["title"] and item["douban_id"] for item in result["items"]))
        self.assertTrue(result["has_more"])  # 快照三段共 60 条，首页只给一页

    def test_warm_index_makes_local_search_work_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = media_index.MediaIndex(pathlib.Path(tmp) / "mytv.db", pinyin_map=PINYIN)
            try:
                self.assertEqual(index.count(), 0)
                catalog = douban_catalog.DoubanCatalog(fetch=offline_fetch, snapshot=self.snapshot,
                                                       media_index=index)
                catalog.warm_index()
                self.assertEqual(index.count(), len(self.snapshot["index"]))
                self.assertEqual(catalog.warm_index(), 0)  # 已有索引就不再重复写入
                sample = self.snapshot["index"][0]
                hits = {item["douban_id"] for item in catalog.search(sample["title"])["items"]}
                self.assertIn(sample["douban_id"], hits)
            finally:
                index.close()

    def test_detail_falls_back_to_snapshot(self):
        sample = next(iter(self.snapshot["details"].values()))
        result = self.catalog.detail(sample["douban_id"])
        self.assertEqual(result["title"], sample["title"])
        self.assertEqual(result["source"], "douban-snapshot")

    def test_detail_without_baked_details_uses_snapshot_list_row(self):
        """快照详情有配额，没补到详情的条目也得能打开详情页。"""
        detail_ids = set(self.snapshot["details"])
        sample = next(item for item in self.snapshot["index"]
                      if item["douban_id"] not in detail_ids)
        result = self.catalog.detail(sample["douban_id"])
        self.assertEqual(result["title"], sample["title"])
        self.assertEqual(result["source"], "douban-snapshot")

    def test_catalog_avoids_the_parameter_ignoring_endpoint(self):
        """`recent_hot` 会忽略排序/类型参数（三种排序返回同一份列表），别再退回去。"""
        source = (BACKEND / "douban_catalog.py").read_text(encoding="utf-8")
        self.assertNotIn("rexxar/api/v2/subject/recent_hot", source)


if __name__ == "__main__":
    unittest.main()
