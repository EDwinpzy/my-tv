import json
import pathlib
import sys
import tempfile
import unittest
import urllib.parse


BACKEND = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "douban"
sys.path.insert(0, str(BACKEND))

import douban_catalog  # noqa: E402


def fixture_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def search_payload(rows):
    """豆瓣 Explore 搜索接口的响应形状（与 `recent_hot` 的 items 不同）。"""
    return {"data": rows}


class DoubanCatalogTest(unittest.TestCase):
    def test_movie_explore_maps_to_stable_subject(self):
        item = douban_catalog.parse_explore(fixture_json("explore_movie.json"))[0]
        self.assertEqual(item["id"], "douban:1292052")
        self.assertEqual(item["title"], "肖申克的救赎")
        self.assertEqual(item["category"], "movie")

    def test_short_category_rejects_plain_animated_short(self):
        self.assertFalse(douban_catalog.is_short_drama({"genres": ["动画", "短片"], "tags": []}))
        self.assertTrue(douban_catalog.is_short_drama({"genres": ["剧情"], "tags": ["网络短剧"]}))

    def test_detail_uses_douban_metadata(self):
        item = douban_catalog.parse_subject_html(fixture_text("subject_1292052.html"), "1292052")
        self.assertEqual(item["year"], "1994")
        self.assertEqual(item["rating"], 9.7)
        self.assertIn("弗兰克·德拉邦特", item["directors"])
        self.assertIn("月黑高飞", item["aliases"])

    def test_failed_refresh_keeps_last_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = douban_catalog.JsonDiskCache(tmp)
            cache.put("home:movie", {"sections": [1]}, fetched_at=100)
            self.assertEqual(cache.get_stale("home:movie", now=999999)["sections"], [1])

    def test_first_run_uses_bundled_snapshot(self):
        snapshot = {"home": {"movie": {"sections": [{"title": "最近热门", "items": []}]}}}
        catalog = douban_catalog.DoubanCatalog(
            fetch=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
            snapshot=snapshot,
        )
        result = catalog.home("movie")
        self.assertTrue(result["stale"])
        self.assertEqual(result["source"], "douban-snapshot")

    def test_filters_match_product_rows_and_remove_language(self):
        catalog = douban_catalog.DoubanCatalog(fetch=lambda _url: {})
        result = catalog.filters("movie")
        self.assertEqual([row["name"] for row in result["rows"]],
                         ["类别", "类型", "地区", "年份", "评分", "排序"])
        self.assertEqual(result["rows"][4]["options"], ["全部", "9分以上", "8分以上", "7分以上", "暂无评分"])

    def test_show_passes_sort_and_filters_to_douban_search(self):
        """`recent_hot` 会忽略 category/type；只有 Explore 搜索接口真正支持排序与筛选。"""
        calls = []

        def fetch(url):
            calls.append(url)
            return search_payload([{"id": "1292052", "title": "肖申克的救赎", "rate": "9.7",
                                    "cover": "https://img.example/1292052.jpg",
                                    "casts": ["蒂姆·罗宾斯"], "directors": ["弗兰克·德拉邦特"]}])

        result = douban_catalog.DoubanCatalog(fetch=fetch).show(
            "movie", genre="剧情", region="美国", year="1994", rating="9分以上", sort="rating", page=2)
        self.assertEqual([item["title"] for item in result["items"]], ["肖申克的救赎"])
        self.assertEqual(result["items"][0]["id"], "douban:1292052")
        self.assertEqual(result["items"][0]["rating"], 9.7)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0]).query)
        self.assertEqual(query["sort"], ["S"])
        self.assertEqual(query["range"], ["9,10"])
        self.assertEqual(query["tags"], ["电影,美国,1994"])
        self.assertEqual(query["genres"], ["剧情"])
        self.assertEqual(query["start"], ["20"])

    def test_detail_returns_douban_subject(self):
        def fetch(url):
            if "/subject/1292052" in url:
                raw = fixture_json("explore_movie.json")["items"][0]
                raw.update({"intro": "简介", "countries": ["美国"], "aka": ["月黑高飞"]})
                return raw
            return fixture_json("explore_movie.json")

        catalog = douban_catalog.DoubanCatalog(fetch=fetch)
        self.assertEqual(catalog.detail("1292052")["title"], "肖申克的救赎")

    def test_search_reads_local_index_without_network(self):
        class Index:
            def search(self, query, limit=30):
                return [{"id": "douban:1292052", "douban_id": "1292052", "title": query}]

        catalog = douban_catalog.DoubanCatalog(
            fetch=lambda _url: self.fail("local search must not fetch the network"), media_index=Index())
        result = catalog.search("肖申克", limit=7)
        self.assertTrue(result["local"])
        self.assertEqual(result["items"][0]["id"], "douban:1292052")

    def test_successful_scrapes_are_ingested(self):
        class Index:
            def __init__(self):
                self.ids = []

            def upsert_many(self, items):
                self.ids.extend(item["douban_id"] for item in items)

        index = Index()
        catalog = douban_catalog.DoubanCatalog(
            fetch=lambda _url: search_payload([{"id": "1292052", "title": "肖申克的救赎", "rate": "9.7"}]),
            media_index=index)
        catalog.home("movie")
        catalog.show("movie")
        self.assertIn("1292052", index.ids)


if __name__ == "__main__":
    unittest.main()
