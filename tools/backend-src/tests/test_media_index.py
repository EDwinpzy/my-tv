import pathlib
import sys
import tempfile
import unittest


BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import media_index  # noqa: E402


PINYIN = {
    "庆": "qing", "余": "yu", "年": "nian", "第": "di", "二": "er", "季": "ji",
    "斗": "dou", "罗": "luo", "大": "da", "陆": "lu",
    "张": "zhang", "若": "ruo", "昀": "yun", "李": "li", "沁": "qin",
    "科": "ke", "幻": "huan", "剧": "ju", "情": "qing",
}


def subject(douban_id, title, **extra):
    value = {
        "id": "douban:" + douban_id,
        "douban_id": douban_id,
        "title": title,
        "original_title": "",
        "aliases": [],
        "year": "2024",
        "category": "tv",
        "genres": ["剧情"],
        "regions": ["中国大陆"],
        "season": 0,
        "rating": 8.0,
        "rating_count": 1,
        "summary": "",
        "directors": [],
        "actors": [],
        "poster_url": "",
        "backdrop_url": "",
        "release_date": "",
    }
    value.update(extra)
    return value


class MediaIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "media" / "mytv.db"
        self.index = media_index.MediaIndex(self.db, pinyin_map=PINYIN)
        self.index.upsert_many([
            subject("1", "庆余年 第二季", aliases=["庆余年2", "庆余年 第二部"], season=2,
                    actors=["张若昀", "李沁"]),
            subject("2", "斗罗大陆", genres=["动画", "奇幻"]),
        ])

    def tearDown(self):
        self.index.close()
        self.tmp.cleanup()

    def assert_first(self, query, douban_id="1"):
        rows = self.index.search(query, limit=10)
        self.assertTrue(rows, query)
        self.assertEqual(rows[0]["douban_id"], douban_id, query)

    def test_searches_title_alias_full_pinyin_initials_and_season(self):
        for query in ("庆余年", "庆余", "余年", "qingyunian", "qingyu", "qyn", "qyn2", "庆余年2"):
            with self.subTest(query=query):
                self.assert_first(query)

    def test_searches_people_and_genres(self):
        for query in ("张若昀", "zhangruoyun", "zry", "李沁", "动画", "奇幻"):
            with self.subTest(query=query):
                self.assert_first(query, "1" if query not in ("动画", "奇幻") else "2")

    def test_fuzzy_fallback_only_repairs_close_queries(self):
        self.assert_first("qinyunian")
        self.assert_first("斗罗大路", "2")
        self.assertEqual(self.index.search("完全不存在的长标题", limit=10), [])

    def test_reopen_preserves_rows_and_schema_version(self):
        self.index.close()
        reopened = media_index.MediaIndex(self.db, pinyin_map=PINYIN)
        try:
            self.assertEqual(reopened.schema_version, media_index.SCHEMA_VERSION)
            self.assertEqual(reopened.search("qyn2")[0]["title"], "庆余年 第二季")
        finally:
            reopened.close()

    def test_upsert_updates_metadata_without_duplicate_rows(self):
        updated = subject("1", "庆余年 第二季", aliases=["庆余年2"], season=2, rating=9.1,
                          actors=["张若昀"])
        self.index.upsert_many([updated])
        rows = self.index.search("庆余年")
        self.assertEqual([row["douban_id"] for row in rows].count("1"), 1)
        self.assertEqual(rows[0]["rating"], 9.1)


if __name__ == "__main__":
    unittest.main()
