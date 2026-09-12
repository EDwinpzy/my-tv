"""好好看目录快照容灾。

快照只包含由好好看页面解析得到的目录、卡片和详情。它不读取 macCMS，
因此云函数被源站风控时也不会让补充播放源反向成为卡片数据源。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path


SNAPSHOT_PATH = Path(__file__).with_name("hhkan_snapshot.json")


class SnapshotCatalog:
    def __init__(self, data=None):
        data = data if isinstance(data, dict) else {}
        self.data = data if data.get("source") == "hhkan" else {}

    @classmethod
    def load_default(cls):
        try:
            return cls(json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return cls()

    @property
    def available(self):
        return bool(self.data.get("home") or self.data.get("channels"))

    @property
    def generated_at(self):
        return self.data.get("generatedAt", "")

    def _tag(self, payload):
        if not isinstance(payload, dict):
            return None
        result = copy.deepcopy(payload)
        result["source"] = "hhkan-snapshot"
        result["stale"] = True
        if self.generated_at:
            result["snapshotAt"] = self.generated_at
        return result

    def home(self):
        return self._tag(self.data.get("home"))

    def channel(self, cid):
        return self._tag((self.data.get("channels") or {}).get(str(cid)))

    def channel_sections(self, cid):
        return self._tag((self.data.get("channelSections") or {}).get(str(cid)))

    def filters(self, cid):
        return self._tag((self.data.get("filters") or {}).get(str(cid)))

    def show(self, cid, by="3", page=1, type_="", area="", lang="", year=""):
        # 部署快照保存未筛选的常用排序页。带筛选请求通过详情元数据在本地过滤，
        # 无法精确判断语言时宁可少返回，也不混入其他来源卡片。
        shows = self.data.get("shows") or {}
        if int(cid) == 0:
            merged, seen, more = [], set(), False
            for channel_id in (1, 2, 3, 4, 6):
                part = self.show(channel_id, by, page, type_, area, lang, year)
                if not part:
                    continue
                more = more or bool(part.get("has_more"))
                for item in part.get("items", []):
                    if item.get("id") not in seen:
                        seen.add(item.get("id"))
                        merged.append(item)
            return self._tag({"cid": 0, "page": int(page), "items": merged,
                              "has_more": more}) if merged else None
        key = "%s|%s|%s" % (cid, by or "3", page)
        payload = copy.deepcopy(shows.get(key))
        if not payload:
            return None
        if any((type_, area, lang, year)):
            details = self.data.get("details") or {}

            def matches(item):
                detail = details.get(str(item.get("id"))) or {}
                haystack = " / ".join(str(detail.get(k) or "") for k in
                                      ("meta", "year", "desc"))
                return all(not value or value in haystack
                           for value in (type_, area, lang, year))

            payload["items"] = [item for item in payload.get("items", []) if matches(item)]
            payload["has_more"] = False
        return self._tag(payload)

    def latest(self, page=1):
        return self._tag((self.data.get("latest") or {}).get(str(page)))

    def detail(self, vid):
        details = self.data.get("details") or {}
        payload = details.get(str(vid))
        if payload:
            return self._tag(payload)
        card = (self.data.get("items") or {}).get(str(vid))
        if not card:
            return None
        return self._tag({
            "id": int(vid),
            "title": card.get("title", ""),
            "cover": card.get("cover", ""),
            "score": card.get("score", 0),
            "year": "",
            "meta": card.get("remark", ""),
            "director": "",
            "actors": "",
            "desc": "",
            "sources": [],
        })

    def search(self, keyword, page=1, page_size=30):
        needle = "".join(str(keyword or "").lower().split())
        if not needle:
            return []
        found = []
        for item in (self.data.get("items") or {}).values():
            title = "".join(str(item.get("title") or "").lower().split())
            if needle in title:
                found.append(copy.deepcopy(item))
        start = max(0, int(page) - 1) * page_size
        return found[start:start + page_size]
