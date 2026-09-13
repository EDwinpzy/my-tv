"""Playback-source registry, discovery, matching and quality ranking."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
import concurrent.futures
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_PATH = Path(__file__).with_name("vod_sources.default.json")
RUNTIME_PATH = Path(__file__).with_name("vod_sources.runtime.json")
AUTO_MATCH_THRESHOLD = 80
TITLE_SEPARATORS = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
PRIVATE_HOSTS = {"localhost", "localhost.localdomain"}


class UnsafeSourceUrl(ValueError):
    pass


@dataclass(frozen=True)
class VodSource:
    id: str
    name: str
    site_url: str
    api_url: str
    adapter_type: str
    enabled: bool = True
    revision: int = 1


class SourceRegistry:
    def __init__(self, sources=(), version=1, history=None, probe=None):
        self.sources = tuple(sources)
        self.version = int(version)
        self.history = history
        self.probe = probe or probe_stream

    @classmethod
    def from_dict(cls, payload):
        payload = payload if isinstance(payload, dict) else {}
        sources = []
        for raw in payload.get("sources") or []:
            if not isinstance(raw, dict):
                continue
            sources.append(VodSource(
                id=str(raw.get("id") or "").strip(),
                name=str(raw.get("name") or "").strip(),
                site_url=str(raw.get("site_url") or "").strip(),
                api_url=str(raw.get("api_url") or "").strip(),
                adapter_type=str(raw.get("adapter_type") or "").strip(),
                enabled=bool(raw.get("enabled", True)),
                revision=int(raw.get("revision") or 1),
            ))
        return cls(sources, payload.get("version") or 1)

    @classmethod
    def load_default(cls):
        return cls.from_dict(json.loads(DEFAULT_PATH.read_text(encoding="utf-8")))

    @classmethod
    def load_current(cls):
        try:
            runtime = cls.from_dict(json.loads(RUNTIME_PATH.read_text(encoding="utf-8")))
            if runtime.sources:
                return runtime
        except (OSError, ValueError, TypeError):
            pass
        return cls.load_default()

    def to_dict(self):
        return {"schema": 1, "version": self.version, "sources": [asdict(source) for source in self.sources]}

    def resolve_subject(self, subject):
        """Search enabled adapters and return only confident, normalized lines."""
        enabled = [source for source in self.sources if source.enabled]

        def resolve_one(source):
            try:
                adapter = HhkanAdapter(source) if source.adapter_type == "hhkan" else MacCmsAdapter(source)
                candidates = adapter.search(subject)
                best = max(candidates, key=lambda item: match_score(subject, item), default=None)
                if not best or match_score(subject, best) < AUTO_MATCH_THRESHOLD:
                    return []
                return adapter.detail(best)
            except Exception:
                return []

        if not enabled:
            return []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(enabled))) as pool:
            groups = list(pool.map(resolve_one, enabled))
        lines = [line for group in groups for line in group]

        def inspect(line):
            try:
                source = next(item for item in enabled if item.id == line.get("source_id"))
                adapter = HhkanAdapter(source) if source.adapter_type == "hhkan" else MacCmsAdapter(source)
                resolved = adapter.resolve(line, 0)
                line.update(self.probe(resolved.get("url")))
            except Exception:
                line.update({"alive": False, "latency_ms": None, "height": 0})
            return line

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(lines)))) as pool:
            lines = list(pool.map(inspect, lines))
        history = ({line["id"]: self.history.success_rate(line["id"]) for line in lines}
                   if self.history else None)
        return rank_lines(lines, history)

    def resolve_line(self, line, episode_index):
        source = next((item for item in self.sources if item.id == line.get("source_id")), None)
        if not source:
            raise LookupError("影视源不存在")
        adapter = HhkanAdapter(source) if source.adapter_type == "hhkan" else MacCmsAdapter(source)
        return adapter.resolve(line, episode_index)


def normalize_title(value):
    return TITLE_SEPARATORS.sub("", str(value or "")).casefold()


def _titles(item):
    values = [item.get("title"), item.get("original_title")]
    values.extend(item.get("aliases") or [])
    return {normalize_title(value) for value in values if normalize_title(value)}


def _year(value):
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group(0)) if match else None


def match_score(subject, candidate):
    if not (_titles(subject) & _titles(candidate)):
        return 0
    score = 60
    subject_year, candidate_year = _year(subject.get("year")), _year(candidate.get("year"))
    hard_year_conflict = bool(subject_year and candidate_year and abs(subject_year - candidate_year) > 1)
    if subject_year and candidate_year:
        score += 20 if subject_year == candidate_year else 10 if abs(subject_year - candidate_year) == 1 else 0
    subject_category, candidate_category = subject.get("category"), candidate.get("category")
    if subject_category and subject_category == candidate_category:
        score += 10
    subject_season, candidate_season = int(subject.get("season") or 0), int(candidate.get("season") or 0)
    if subject_season == candidate_season:
        score += 10
    return min(score, 79) if hard_year_conflict else min(score, 100)


def quality_score(height):
    height = int(height or 0)
    return 100 if height >= 2160 else 85 if height >= 1080 else 65 if height >= 720 else 35 if height > 0 else 20


def latency_score(milliseconds):
    if milliseconds is None:
        return 0
    milliseconds = int(milliseconds)
    return 100 if milliseconds <= 1000 else 80 if milliseconds <= 3000 else 50 if milliseconds <= 6000 else 20


def rank_lines(lines, history=None):
    history = history or {}
    ranked = []
    for raw in lines:
        line = copy.deepcopy(raw)
        alive = line.get("alive") is not False
        reliability = history.get(str(line.get("id")), line.get("success_rate", 0.5))
        reliability = max(0.0, min(1.0, float(reliability)))
        line["available"] = alive
        line["score"] = round(
            0.50 * quality_score(line.get("height")) +
            0.30 * latency_score(line.get("latency_ms")) +
            0.20 * (reliability * 100), 2)
        ranked.append(line)
    ranked.sort(key=lambda item: (item["available"], item["score"]), reverse=True)
    return ranked


class LineHistory:
    def __init__(self, path):
        self.path = Path(path)
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            self.data = {}

    def attempts(self, line_id):
        return list(self.data.get(str(line_id)) or [])[-20:]

    def success_rate(self, line_id):
        values = self.attempts(line_id)
        return sum(bool(value) for value in values) / len(values) if values else 0.5

    def record(self, line_id, success):
        key = str(line_id)
        self.data[key] = (self.attempts(key) + [bool(success)])[-20:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


def _validate_public_url(url, resolve_dns=False):
    parsed = urllib.parse.urlsplit(str(url or ""))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeSourceUrl("影视源地址必须是 http/https 公网 URL")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in PRIVATE_HOSTS:
        raise UnsafeSourceUrl("影视源地址不能指向本机或内网")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        if resolve_dns:
            try:
                addresses = {row[4][0] for row in socket.getaddrinfo(hostname, parsed.port or 443)}
            except socket.gaierror as exc:
                raise UnsafeSourceUrl("影视源域名无法解析") from exc
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise UnsafeSourceUrl("影视源域名解析到非公网地址")
    else:
        if not ip.is_global:
            raise UnsafeSourceUrl("影视源地址不能指向本机或内网")
    return url


def _default_fetch(url):
    _validate_public_url(url, resolve_dns=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json, application/xml, text/html"})
    with urllib.request.urlopen(request, timeout=8) as response:
        final_url = response.geturl()
        _validate_public_url(final_url, resolve_dns=True)
        return {"final_url": final_url, "content_type": response.headers.get_content_type(), "body": response.read(512 * 1024).decode("utf-8", "replace")}


def _probe_fetch(url):
    _validate_public_url(url, resolve_dns=True)
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.apple.mpegurl,*/*"})
    with urllib.request.urlopen(request, timeout=8) as response:
        _validate_public_url(response.geturl(), resolve_dns=True)
        body = response.read(256 * 1024).decode("utf-8", "replace")
    return {"elapsed_ms": int((time.monotonic() - started) * 1000), "body": body}


def probe_stream(url, fetch=None):
    """Probe the first playlist response and derive the best advertised resolution."""
    if not str(url or "").startswith(("http://", "https://")):
        return {"alive": False, "latency_ms": None, "height": 0}
    try:
        result = (fetch or _probe_fetch)(url)
        heights = [int(value) for value in re.findall(r"RESOLUTION=\d+x(\d+)", str(result.get("body") or ""), re.I)]
        return {"alive": True, "latency_ms": int(result.get("elapsed_ms") or 0),
                "height": max(heights, default=0)}
    except Exception:
        return {"alive": False, "latency_ms": None, "height": 0}


def discover_source(site_url, fetch=None):
    site_url = str(site_url or "").strip().rstrip("/")
    _validate_public_url(site_url)
    fetch = fetch or _default_fetch
    source_id = normalize_title(urllib.parse.urlsplit(site_url).hostname).replace("_", "-")[:40] or "source"
    candidates = [site_url + "/api.php/provide/vod/", site_url + "/provide/vod/"]
    for api_url in candidates:
        result = fetch(api_url + "?ac=list")
        final_url = result.get("final_url") or api_url
        _validate_public_url(final_url)
        body = str(result.get("body") or "").lstrip()
        content_type = str(result.get("content_type") or "").lower()
        if "json" in content_type or body.startswith("{"):
            try:
                payload = json.loads(body)
                if isinstance(payload, dict) and ("code" in payload or "list" in payload or "class" in payload):
                    return VodSource(source_id, urllib.parse.urlsplit(site_url).hostname, site_url, api_url, "macms_json")
            except ValueError:
                pass
        if "xml" in content_type or body.startswith("<?xml") or body.startswith("<rss"):
            return VodSource(source_id, urllib.parse.urlsplit(site_url).hostname, site_url, api_url, "macms_xml")
    raise ValueError("未识别到兼容的 MacCMS 影视接口")


class MacCmsAdapter:
    def __init__(self, source, fetch=None):
        self.source = source
        self.fetch = fetch or _default_fetch

    def search(self, subject):
        # ac=detail 才稳定返回 vod_play_from/vod_play_url；videolist 在不少站点只给摘要。
        query = urllib.parse.urlencode({"ac": "detail", "wd": subject.get("title") or ""})
        result = self.fetch(self.source.api_url + "?" + query)
        payload = json.loads(result.get("body") or "{}")
        candidates = []
        for item in payload.get("list") or []:
            type_name = str(item.get("type_name") or "")
            category = ("anime" if any(x in type_name for x in ("动漫", "动画")) else
                        "variety" if any(x in type_name for x in ("综艺", "真人秀")) else
                        "tv" if any(x in type_name for x in ("剧", "连续")) else "movie")
            candidates.append({"id": str(item.get("vod_id") or ""), "title": item.get("vod_name") or "", "year": item.get("vod_year") or "", "category": category, "season": 0, "raw": item})
        return candidates

    def detail(self, candidate):
        raw = candidate.get("raw") or {}
        play_urls = str(raw.get("vod_play_url") or "").split("$$$")
        play_names = str(raw.get("vod_play_from") or "").split("$$$")
        lines = []
        for index, group in enumerate(play_urls):
            episodes = []
            for episode_index, value in enumerate(group.split("#")):
                value = value.strip()
                if not value:
                    continue
                if "$" in value:
                    name, url = value.rsplit("$", 1)
                else:
                    name, url = "第%d集" % (episode_index + 1), value
                url = url.strip()
                if not url.startswith(("http://", "https://")):
                    continue
                episodes.append({"index": len(episodes), "name": name.strip() or "第%d集" % (episode_index + 1), "url": url})
            if episodes:
                label = play_names[index].strip() if index < len(play_names) else "线路%d" % (index + 1)
                lines.append({
                    "id": "%s:%s:%d" % (self.source.id, candidate.get("id"), index),
                    "source_id": self.source.id, "source_name": self.source.name,
                    "name": "%s·%s" % (self.source.name, label), "episodes": episodes,
                    "height": 0, "latency_ms": None, "alive": True,
                })
        return lines

    def resolve(self, line, episode_index):
        episodes = line.get("episodes") or []
        if not episodes:
            raise LookupError("线路没有可播放集")
        index = max(0, min(int(episode_index), len(episodes) - 1))
        episode = episodes[index]
        return {"line_id": line.get("id"), "name": episode.get("name"),
                "url": episode.get("url"), "headers": {}}


class HhkanAdapter:
    def __init__(self, source, module=None):
        self.source = source
        if module is None:
            import hhkan as module
        self.module = module

    def search(self, subject):
        title = str(subject.get("title") or "").strip()
        token = self.module.get_search_token()
        path = "/search?t=%s&k=%s&p=1" % (
            urllib.parse.quote(token), urllib.parse.quote(title))
        html = self.module.get_page(path)
        candidates = []
        for match in re.finditer(r'href=["\']/detail/(\d+)\.html["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            block = match.group(2)
            title_match = re.search(r'class=["\']title["\'][^>]*>([^<]+)', block, re.I)
            candidates.append({"id": match.group(1), "title": (title_match.group(1).strip() if title_match else title),
                               "year": subject.get("year") or "", "category": subject.get("category"),
                               "season": subject.get("season") or 0})
        return candidates

    def detail(self, candidate):
        vid = int(candidate.get("id") or 0)
        detail = self.module.parse_detail(self.module.get_page("/detail/%d.html" % vid), vid=vid)
        lines = []
        for index, raw in enumerate(detail.get("sources") or []):
            episodes = []
            for episode_index, episode in enumerate(raw.get("episodes") or []):
                episodes.append({"index": episode_index, "name": episode.get("ep") or "第%d集" % (episode_index + 1),
                                 "pid": int(episode.get("pid") or 0), "vid": int(episode.get("vid") or vid)})
            if episodes:
                pid = episodes[0]["pid"]
                lines.append({"id": "%s:%d:%d" % (self.source.id, vid, pid), "source_id": self.source.id,
                              "source_name": self.source.name, "name": "%s·%s" % (self.source.name, raw.get("name") or "线路%d" % (index + 1)),
                              "vod_id": vid, "episodes": episodes, "height": 0, "latency_ms": None, "alive": True})
        return lines

    def resolve(self, line, episode_index):
        episodes = line.get("episodes") or []
        if not episodes:
            raise LookupError("线路没有可播放集")
        episode = episodes[max(0, min(int(episode_index), len(episodes) - 1))]
        path = "/play/%d-%d-%d.html" % (int(line.get("vod_id") or 0), episode["pid"], episode["vid"])
        parsed = self.module.parse_play_page(self.module.get_page(path))
        streams = parsed.get("sources") or []
        if not streams:
            raise LookupError("播放线路不可用")
        selected = streams[-1]
        return {"line_id": line.get("id"), "name": episode.get("name"), "url": selected.get("url"), "headers": {}}
