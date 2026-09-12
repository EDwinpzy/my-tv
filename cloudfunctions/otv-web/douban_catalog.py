"""Device-local Douban catalogue parsing, caching and snapshot fallback."""

from __future__ import annotations

import copy
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


HOME_SECTION_NAMES = ("最近热门", "最新上映", "豆瓣高分")
CATEGORY_VALUES = {"movie", "tv", "anime", "variety", "short"}
SUBJECT_FIELDS = (
    "id", "douban_id", "title", "original_title", "aliases", "year",
    "category", "genres", "regions", "season", "rating", "rating_count",
    "summary", "directors", "actors", "poster_url", "backdrop_url", "release_date",
)
TTL = {"home": 21600, "filters": 86400, "detail": 604800, "search": 1800, "show": 21600}
CACHE_SCHEMA = 1
CACHE_ENVELOPE_KEYS = {"schema", "fetched_at", "value"}
SNAPSHOT_PATH = Path(__file__).with_name("douban_snapshot.json")


def _text(value):
    return html.unescape(str(value or "")).strip()


def _list(value):
    if isinstance(value, list):
        return [_text(x.get("name") if isinstance(x, dict) else x) for x in value if x]
    if value:
        return [_text(value)]
    return []


def _number(value, default=0):
    if isinstance(value, dict):
        value = value.get("value", value.get("ratingValue", default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default=0):
    if isinstance(value, dict):
        value = value.get("count", value.get("ratingCount", default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_short_drama(item):
    tags = " ".join(_list(item.get("tags"))).lower()
    positive = ("短剧", "微短剧", "网络短剧", "竖屏剧", "迷你剧")
    return any(token in tags for token in positive)


def _category(item, requested="movie"):
    genres = set(_list(item.get("genres")))
    tags = set(_list(item.get("tags")))
    if is_short_drama(item):
        return "short"
    if "综艺" in genres or "真人秀" in genres or "综艺" in tags or "真人秀" in tags:
        return "variety"
    if "动画" in genres or "动画" in tags or "动漫" in tags:
        return "anime"
    return requested if requested in ("movie", "tv") else "movie"


def normalize_subject(raw, requested_category="movie"):
    raw = raw if isinstance(raw, dict) else {}
    subject_id = _text(raw.get("douban_id") or raw.get("id")).removeprefix("douban:")
    rating = raw.get("rating") or raw.get("aggregateRating") or {}
    poster = raw.get("poster_url") or raw.get("cover_url") or raw.get("image")
    if isinstance(raw.get("pic"), dict):
        poster = poster or raw["pic"].get("large") or raw["pic"].get("normal")
    result = {
        "id": "douban:" + subject_id if subject_id else "",
        "douban_id": subject_id,
        "title": _text(raw.get("title") or raw.get("name")),
        "original_title": _text(raw.get("original_title") or raw.get("originalName") or raw.get("alternateName")),
        "aliases": _list(raw.get("aliases")),
        "year": _text(raw.get("year")),
        "category": _category(raw, requested_category),
        "genres": _list(raw.get("genres") or raw.get("genre")),
        "regions": _list(raw.get("regions")),
        "season": _integer(raw.get("season"), 0),
        "rating": _number(rating),
        "rating_count": _integer(rating),
        "summary": _text(raw.get("summary") or raw.get("description")),
        "directors": _list(raw.get("directors") or raw.get("director")),
        "actors": _list(raw.get("actors") or raw.get("actor")),
        "poster_url": _text(poster),
        "backdrop_url": _text(raw.get("backdrop_url")),
        "release_date": _text(raw.get("release_date") or raw.get("datePublished")),
    }
    if not result["year"] and result["release_date"]:
        result["year"] = result["release_date"][:4]
    return result


def parse_explore(payload, category="movie"):
    if not isinstance(payload, dict):
        return []
    rows = payload.get("items") or payload.get("subjects") or payload.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("subjects") or []
    return [normalize_subject(row, category) for row in rows if isinstance(row, dict)]


def _json_ld(source):
    match = re.search(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', source, re.I | re.S)
    if not match:
        return {}
    try:
        value = json.loads(html.unescape(match.group(1)).strip())
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def parse_subject_html(source, douban_id):
    data = _json_ld(source)
    info_match = re.search(r'<div[^>]+id=["\']info["\'][^>]*>(.*?)</div>', source, re.I | re.S)
    info = re.sub(r"<[^>]+>", "\n", info_match.group(1)) if info_match else ""
    info = html.unescape(info)
    alias_match = re.search(r"又名\s*:\s*([^\r\n<]+)", info)
    region_match = re.search(r"制片国家/地区\s*:\s*([^\r\n<]+)", info)
    data["id"] = str(douban_id)
    data["aliases"] = [x.strip() for x in re.split(r"\s*/\s*", alias_match.group(1)) if x.strip()] if alias_match else []
    data["regions"] = [x.strip() for x in re.split(r"\s*/\s*", region_match.group(1)) if x.strip()] if region_match else []
    item = normalize_subject(data)
    title = item["title"]
    year_match = re.search(r"\((\d{4})\)\s*$", title)
    if year_match:
        item["year"] = item["year"] or year_match.group(1)
        item["title"] = title[:year_match.start()].strip()
    return item


class JsonDiskCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", key)
        return self.directory / (safe + ".json")

    def put(self, key, value, fetched_at=None):
        envelope = {"schema": CACHE_SCHEMA, "fetched_at": fetched_at or time.time(), "value": value}
        path = self._path(key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh, ensure_ascii=False, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def envelope(self, key):
        try:
            value = json.loads(self._path(key).read_text(encoding="utf-8"))
            if isinstance(value, dict) and CACHE_ENVELOPE_KEYS <= set(value) and value["schema"] == CACHE_SCHEMA:
                return value
        except (OSError, ValueError, TypeError):
            pass
        return None

    def get(self, key, ttl, now=None):
        envelope = self.envelope(key)
        now = time.time() if now is None else now
        if envelope and now - float(envelope["fetched_at"]) <= ttl:
            return copy.deepcopy(envelope["value"])
        return None

    def get_stale(self, key, now=None):
        envelope = self.envelope(key)
        return copy.deepcopy(envelope["value"]) if envelope else None


class DoubanCatalog:
    def __init__(self, fetch=None, cache=None, snapshot=None):
        self.fetch = fetch or self._fetch
        self.cache = cache
        self.snapshot = snapshot if isinstance(snapshot, dict) else self._load_snapshot()
        self._conditions = {}
        self._condition_lock = threading.Lock()

    @staticmethod
    def _load_snapshot():
        try:
            value = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _fetch(url):
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html"})
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", "replace")
            content_type = response.headers.get("Content-Type", "").lower()
            return json.loads(body) if "json" in content_type or body.lstrip().startswith(("{", "[")) else body

    def _coalesced(self, key, kind, producer, snapshot_value=None):
        if self.cache:
            fresh = self.cache.get(key, TTL[kind])
            if fresh is not None:
                return fresh
        with self._condition_lock:
            condition = self._conditions.setdefault(key, threading.Condition())
        with condition:
            if getattr(condition, "_running", False):
                condition.wait_for(lambda: not getattr(condition, "_running", False), timeout=15)
                fresh = self.cache.get(key, TTL[kind]) if self.cache else None
                if fresh is not None:
                    return fresh
            condition._running = True
        try:
            value = producer()
            if not value:
                raise ValueError("empty Douban response")
            if self.cache:
                self.cache.put(key, value)
            return value
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            stale = self.cache.get_stale(key) if self.cache else None
            fallback = stale if stale is not None else copy.deepcopy(snapshot_value)
            if isinstance(fallback, dict):
                fallback["stale"] = True
                fallback["source"] = "douban-cache" if stale is not None else "douban-snapshot"
            return fallback or {"stale": True, "source": "douban-snapshot"}
        finally:
            with condition:
                condition._running = False
                condition.notify_all()

    def _explore(self, category, sort):
        base = "tv" if category in ("tv", "anime", "variety", "short") else "movie"
        query = urllib.parse.urlencode({"type": base, "sort": sort, "page_limit": 20, "page_start": 0})
        payload = self.fetch("https://m.douban.com/rexxar/api/v2/subject/recent_hot/%s?%s" % (base, query))
        items = parse_explore(payload, base)
        return [item for item in items if category in ("movie", "tv") or item["category"] == category]

    def home(self, category):
        if category not in CATEGORY_VALUES:
            raise ValueError("unsupported category")
        snapshot_value = ((self.snapshot.get("home") or {}).get(category))

        def produce():
            return {"category": category, "sections": [
                {"title": HOME_SECTION_NAMES[0], "items": self._explore(category, "U")},
                {"title": HOME_SECTION_NAMES[1], "items": self._explore(category, "T")},
                {"title": HOME_SECTION_NAMES[2], "items": self._explore(category, "S")},
            ], "stale": False, "source": "douban"}

        return self._coalesced("home:" + category, "home", produce, snapshot_value)

    def filters(self, category):
        if category not in CATEGORY_VALUES:
            raise ValueError("unsupported category")
        current_year = time.localtime().tm_year
        genres = {
            "movie": ["全部", "剧情", "喜剧", "动作", "爱情", "科幻", "动画", "悬疑", "犯罪", "纪录片"],
            "tv": ["全部", "剧情", "喜剧", "爱情", "悬疑", "犯罪", "科幻"],
            "anime": ["全部", "动画", "奇幻", "冒险", "科幻", "喜剧"],
            "variety": ["全部", "真人秀", "音乐", "脱口秀", "歌舞"],
            "short": ["全部", "剧情", "喜剧", "爱情", "悬疑", "古装"],
        }[category]
        regions = ["全部", "中国大陆", "中国香港", "中国台湾", "美国", "英国", "日本", "韩国", "法国", "德国"]
        years = ["全部"] + [str(year) for year in range(current_year, current_year - 12, -1)] + ["更早"]
        ratings = ["全部", "9分以上", "8分以上", "7分以上", "暂无评分"]
        return {"category": category, "types": genres, "areas": regions, "years": years, "ratings": ratings, "rows": [
            {"name": "类别", "key": "category", "options": ["电影", "电视剧", "动漫", "综艺", "短剧"]},
            {"name": "类型", "key": "genre", "options": genres},
            {"name": "地区", "key": "region", "options": regions},
            {"name": "年份", "key": "year", "options": years},
            {"name": "评分", "key": "rating", "options": ratings},
            {"name": "排序", "key": "sort", "options": ["热门", "最新上映", "豆瓣高分"]},
        ], "source": "douban"}

    @staticmethod
    def _matches(item, genre="", region="", year="", rating=""):
        if genre and genre != "全部" and genre not in item.get("genres", []):
            return False
        if region and region != "全部" and region not in item.get("regions", []):
            return False
        if year and year != "全部":
            if year == "更早":
                if not item.get("year") or int(item["year"][:4]) >= time.localtime().tm_year - 11:
                    return False
            elif item.get("year") != year:
                return False
        if rating and rating != "全部":
            score = float(item.get("rating") or 0)
            if rating == "暂无评分":
                return score <= 0
            threshold_match = re.search(r"\d+", rating)
            if threshold_match and score < int(threshold_match.group(0)):
                return False
        return True

    def show(self, category, genre="", region="", year="", rating="", sort="hot", page=1):
        if category not in CATEGORY_VALUES:
            raise ValueError("unsupported category")
        sort_code = {"hot": "U", "new": "T", "rating": "S"}.get(sort, "U")
        key = "show:%s:%s:%s:%s:%s:%s:%s" % (category, genre, region, year, rating, sort_code, page)

        def produce():
            base = "tv" if category in ("tv", "anime", "variety", "short") else "movie"
            query = urllib.parse.urlencode({"type": base, "sort": sort_code, "page_limit": 24,
                                            "page_start": max(0, int(page) - 1) * 24})
            items = parse_explore(self.fetch("https://m.douban.com/rexxar/api/v2/subject/recent_hot/%s?%s" % (base, query)), base)
            items = [item for item in items if (category in ("movie", "tv") or item["category"] == category)
                     and self._matches(item, genre, region, year, rating)]
            return {"category": category, "page": int(page), "items": items,
                    "has_more": len(items) == 24, "source": "douban", "stale": False}

        snapshot_items = []
        for section in (((self.snapshot.get("home") or {}).get(category) or {}).get("sections") or []):
            snapshot_items.extend(section.get("items") or [])
        fallback = {"category": category, "page": int(page), "items": snapshot_items,
                    "has_more": False, "source": "douban-snapshot", "stale": True}
        return self._coalesced(key, "show", produce, fallback)

    def search(self, query, page=1):
        query = str(query or "").strip()
        if not query:
            return {"query": "", "page": int(page), "items": [], "has_more": False, "source": "douban"}
        key = "search:%s:%s" % (query, int(page))

        def produce():
            params = urllib.parse.urlencode({"q": query, "start": max(0, int(page) - 1) * 20, "count": 20})
            items = parse_explore(self.fetch("https://m.douban.com/rexxar/api/v2/search/subjects?" + params))
            return {"query": query, "page": int(page), "items": items,
                    "has_more": len(items) == 20, "source": "douban", "stale": False}

        return self._coalesced(key, "search", produce, {"query": query, "page": int(page), "items": [], "has_more": False})

    def detail(self, douban_id):
        douban_id = str(douban_id or "").removeprefix("douban:")
        if not douban_id.isdigit():
            raise ValueError("invalid Douban id")
        key = "detail:" + douban_id

        def produce():
            source = self.fetch("https://movie.douban.com/subject/%s/" % douban_id)
            if not isinstance(source, str):
                raise ValueError("invalid detail response")
            item = parse_subject_html(source, douban_id)
            item["source"] = "douban"
            item["stale"] = False
            return item

        return self._coalesced(key, "detail", produce, {"id": "douban:" + douban_id,
                                "douban_id": douban_id, "title": "", "sources": []})
