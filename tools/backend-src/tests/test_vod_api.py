import json
import pathlib
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer


BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import proxy  # noqa: E402


class _FakeVodService:
    def home(self, category):
        item = {"id": "douban:1292052", "title": "肖申克的救赎"}
        return {"category": category, "sections": [
            {"title": "最近热门", "items": [item]},
            {"title": "最新上映", "items": [item]},
            {"title": "豆瓣高分", "items": [item]},
        ]}

    def filters(self, category):
        return {"category": category, "filters": ["类别", "类型", "地区", "年份", "评分", "排序"]}

    def show(self, category, query):
        return {"category": category, "items": [], "page": int(query.get("page", ["1"])[0])}

    def search(self, query, page=1, limit=30):
        return {"query": query, "page": page, "limit": limit, "items": [], "total": 0, "local": True}

    def detail(self, douban_id, defer_sources=False):
        return {"id": "douban:" + douban_id, "title": "肖申克的救赎",
                "source_state": "matching" if defer_sources else "unavailable", "sources": []}

    def play(self, douban_id, line_id, episode):
        return {"id": "douban:" + douban_id, "line_id": line_id, "episode": episode, "url": "https://video.example/a.m3u8"}

    def source_status(self):
        return {"version": 1, "sources": []}


class VodApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_service = getattr(proxy, "VOD_SERVICE", None)
        proxy.VOD_SERVICE = _FakeVodService()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), proxy.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        proxy.VOD_SERVICE = cls.old_service

    def fetch(self, path):
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.server.server_port, path), timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_vod_home_uses_douban_cards(self):
        payload = self.fetch("/vod/home?category=movie")
        self.assertEqual([s["title"] for s in payload["sections"]], ["最近热门", "最新上映", "豆瓣高分"])
        self.assertTrue(all(i["id"].startswith("douban:") for s in payload["sections"] for i in s["items"]))

    def test_detail_keeps_subject_when_no_source_matches(self):
        payload = self.fetch("/vod/detail/1292052")
        self.assertEqual(payload["id"], "douban:1292052")
        self.assertEqual(payload["source_state"], "unavailable")
        self.assertEqual(payload["sources"], [])

    def test_detail_distinguishes_matching_from_unavailable(self):
        self.assertEqual(self.fetch("/vod/detail/1292052?defer_sources=1")["source_state"], "matching")

    def test_search_has_one_local_api_for_all_clients(self):
        payload = self.fetch("/api/search?q=%E8%82%96%E7%94%B3%E5%85%8B&limit=7")
        self.assertTrue(payload["local"])
        self.assertEqual(payload["limit"], 7)

    def test_filter_contract_has_no_language_row(self):
        payload = self.fetch("/vod/filters/movie")
        self.assertEqual(payload["filters"], ["类别", "类型", "地区", "年份", "评分", "排序"])

    def test_backend_packaging_requires_new_vod_modules(self):
        root = BACKEND.parents[1]
        admin = (root / "tools" / "admin_server.py").read_text(encoding="utf-8")
        build = (root / "tools" / "build_backend_zip.py").read_text(encoding="utf-8")
        web_build = (root / "tools" / "build_web_function.py").read_text(encoding="utf-8")
        for name in ("douban_catalog.py", "douban_snapshot.json", "vod_api.py", "vod_sources.py", "vod_sources.default.json"):
            self.assertIn(name, admin)
            self.assertIn(name, build)
            self.assertIn(name, web_build)


if __name__ == "__main__":
    unittest.main()
