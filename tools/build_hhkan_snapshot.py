#!/usr/bin/env python3
"""从好好看实时页面生成零数据库依赖的云端容灾快照。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "tools" / "backend-src"
OUT = BACKEND / "hhkan_snapshot.json"
sys.path.insert(0, str(BACKEND))

import hhkan  # noqa: E402


CHANNELS = {1: "电影", 2: "电视剧", 3: "动漫", 4: "综艺", 6: "短剧"}


def retry(label, fn, attempts=4):
    last = None
    for attempt in range(1, attempts + 1):
        try:
            value = fn()
            print("OK", label)
            return value
        except Exception as exc:  # 网络/挑战短时失败重试
            last = exc
            print("RETRY", label, attempt, type(exc).__name__)
            time.sleep(min(6, attempt * 1.5))
    raise RuntimeError("%s: %s" % (label, last))


def main():
    parser = argparse.ArgumentParser()
    # 详情上限（2026-09-10 从 260 提至 700）：详情平均 ~20KB，700 条 ≈ 14MB，
    # 云函数包/热更包可承受；优先级顺序（首页→轮播→频道→by3 热门页）保证
    # 热门层先拿到详情——快照搜索搜得到且点得开（有播放线路）。
    parser.add_argument("--details-limit", type=int, default=700)
    args = parser.parse_args()

    homepage = retry("home", lambda: hhkan.get_page("/"))
    home = {"sections": hhkan.parse_home(homepage), "carousel": hhkan.parse_carousel(homepage)}
    channels, channel_sections, filters, shows, latest = {}, {}, {}, {}, {}
    ordered_items = []

    def add_items(items):
        ordered_items.extend(item for item in (items or []) if item.get("id"))

    for section in home["sections"]:
        add_items(section.get("items"))
    for item in home["carousel"]:
        add_items([{"id": item.get("id"), "title": item.get("title", ""),
                    "cover": item.get("backdrop", ""), "score": 0, "remark": ""}])

    for cid, name in CHANNELS.items():
        page = retry("channel-%s" % cid, lambda cid=cid: hhkan.get_page("/channel/%d.html" % cid))
        items = hhkan._parse_vod_list(page)
        sections = hhkan.complete_channel_sections(hhkan.parse_channel_sections(page))
        channels[str(cid)] = {"name": name, "items": items}
        channel_sections[str(cid)] = {
            "cid": cid, "source": "hhkan", "supplemented": False, "sections": sections,
        }
        add_items(items)
        for section in sections:
            add_items(section.get("items"))
        filters[str(cid)] = retry("filters-%s" % cid, lambda cid=cid: hhkan.get_filters(cid))
        # 页深（2026-09-10 云端搜索容灾）：by=3（最热）抓 1..6 页——热门剧集/电影
        # 大多落在 by3 的 3~6 页（实测「庆余年」一二季在 cid2 by3 p3/p4），快照搜索
        # （子串匹配 items 索引）靠这层覆盖热门片名；by=2（最新）保持 2 页，
        # 只服务「最新上线」浏览。中间页不额外探测 has_more（下一页本就在抓取
        # 范围内），仅末页多抓一页判断，把请求量控制在详情抓取之下。
        sort_pages = {"3": 6, "2": 2}
        for by, max_page in sort_pages.items():
            for page_no in range(1, max_page + 1):
                page_items = retry(
                    "show-%s-%s-%s" % (cid, by, page_no),
                    lambda cid=cid, by=by, page_no=page_no: hhkan.get_show_page(cid, by=by, page=page_no),
                )
                if page_no < max_page:
                    has_more = True  # 下一页在抓取范围内，无需探测
                else:
                    next_items = retry(
                        "show-next-%s-%s-%s" % (cid, by, page_no),
                        lambda cid=cid, by=by, page_no=page_no: hhkan.get_show_page(cid, by=by, page=page_no + 1),
                    )
                    has_more = bool(next_items)
                shows["%s|%s|%s" % (cid, by, page_no)] = {
                    "cid": cid, "page": page_no, "items": page_items, "has_more": has_more,
                }
                add_items(page_items)

    for page_no in (1, 2):
        path = "/label/new.html" if page_no == 1 else "/new/%d.html" % page_no
        items = hhkan._parse_vod_list(retry("latest-%s" % page_no, lambda path=path: hhkan.get_page(path)))
        latest[str(page_no)] = {"page": page_no, "items": items}
        add_items(items)

    item_index = {}
    for item in ordered_items:
        item_index.setdefault(str(item["id"]), item)

    priority = []
    for item in home["carousel"]:
        if item.get("id"):
            priority.append(str(item["id"]))
    priority.extend(key for key in item_index if key not in priority)
    details = {}
    for index, key in enumerate(priority[:max(0, args.details_limit)], 1):
        vid = int(key)
        try:
            detail = retry("detail-%s" % vid,
                           lambda vid=vid: hhkan.parse_detail(hhkan.get_page("/detail/%d.html" % vid), vid),
                           attempts=2)
            if detail.get("title"):
                details[key] = detail
        except Exception as exc:
            print("SKIP detail-%s %s" % (vid, type(exc).__name__))
        if index % 25 == 0:
            print("DETAIL_PROGRESS", index, "/", min(len(priority), args.details_limit))

    payload = {
        "schema": 1,
        "source": "hhkan",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "home": home,
        "channels": channels,
        "channelSections": channel_sections,
        "filters": filters,
        "shows": shows,
        "latest": latest,
        "items": item_index,
        "details": details,
        "stats": {"items": len(item_index), "details": len(details)},
    }
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(OUT)
    print("WROTE", OUT, OUT.stat().st_size, payload["stats"])


if __name__ == "__main__":
    main()
