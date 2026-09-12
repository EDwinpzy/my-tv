import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "tools" / "backend-src" / "www" / "app.js"


class WebDoubanContractTest(unittest.TestCase):
    def test_web_uses_vod_api_and_douban_filters(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn('"/vod/home?category="', app)
        self.assertIn('"评分"', app)
        self.assertIn('[["hot", "热门"], ["new", "最新上映"], ["rating", "豆瓣高分"]]', app)
        self.assertNotIn('["lang", "语言"', app)

    def test_web_renders_matching_and_unavailable_separately(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("正在查找片源", app)
        self.assertIn("暂无片源", app)


if __name__ == "__main__":
    unittest.main()
