import importlib.util
import json
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("proxy_football_logos", ROOT / "proxy.py")
proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proxy)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FootballLogosCcTest(unittest.TestCase):
    def setUp(self):
        proxy.FOOTBALL_LOGOS_INDEX = None

    def test_searches_index_with_existing_chinese_to_english_name(self):
        payload = [
            {"name": "Liverpool FC", "categoryId": "england", "id": "liverpool", "h": "abc123"},
            {"name": "Liverpool Montevideo", "categoryId": "uruguay", "id": "liverpool-montevideo", "h": "other"},
        ]
        with mock.patch.object(proxy.urlreq, "urlopen", return_value=_Response(payload)) as urlopen:
            result = proxy._football_logos_search_team("利物浦")

        self.assertEqual(
            "https://assets.football-logos.cc/logos/england/64x64/liverpool.abc123.png",
            result,
        )
        self.assertEqual("https://football-logos.cc/ac-v2.json", urlopen.call_args.args[0].full_url)

    def test_returns_none_when_index_has_no_matching_team(self):
        payload = [{"name": "Arsenal", "categoryId": "england", "id": "arsenal", "h": "hash"}]
        with mock.patch.object(proxy.urlreq, "urlopen", return_value=_Response(payload)):
            self.assertIsNone(proxy._football_logos_search_team("不存在球队"))

    def test_resolver_uses_football_logos_before_thesportsdb_and_caches_it(self):
        proxy.TEAM_ICON_CACHE.clear()
        logo_url = "https://assets.football-logos.cc/logos/japan/64x64/test.hash.png"
        with mock.patch.object(proxy, "_football_logos_search_team", return_value=logo_url), \
                mock.patch.object(proxy, "_tdb_search_team") as tdb, \
                mock.patch.object(proxy, "save_team_icon_cache"):
            result = proxy.resolve_team_icon("测试球队")

        self.assertEqual("football_logos_cc", result["source"])
        self.assertEqual(logo_url, result["url"])
        self.assertEqual(logo_url, proxy.TEAM_ICON_CACHE["测试球队"]["url"])
        tdb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
