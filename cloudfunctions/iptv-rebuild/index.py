#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OptimalTV v1.19 电视源每日校验推送（电视#9）——CloudBase Event 云函数（Python）+ 定时触发器

每日 06:30（7 段 cron "0 30 6 * * * *"）或手动 invoke 执行一轮：
拉取上游聚合源 → normKey 归并线路 → 逐线测活（HTTP 可达 + m3u8 清单可拉 +
首分片 range 探测）→ 剔除死线/全死频道 → 按测速升序排序 → 上限 8 线/频道 →
序列化 m3u 写入 pgstore 公开桶 hotupdate 的 iptv/iptv-latest.m3u（匿名 GET、
支持 Range）——客户端 IptvRepository.SOURCES 首位【直接拉桶对象】，
不经本函数（零网关依赖）。

安全（SSRF 防护——云函数会请求来自公网 m3u 的任意线路 URL）：
- 全部出站请求走 http_open() 单一检查点：仅 http/https；域名解析出的【全部】IP
  必须为公网地址（拒绝环回/私网/链路本地[169.254.169.254 元数据]/CGNAT/组播等）；
- 禁用 urllib 自动重定向，手动循环 ≤3 跳、每跳重新过检查点（防重定向绕过；
  DNS rebinding 残余风险由「读上限字节 + 不回显内容 + 只取状态码」缓解）。
与 hotupdate 云函数同体系（svc signin + pgstore HTTP API，svc_import 具桶写权）；仅标准库。
"""
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib import request as urlreq
from urllib.parse import urlparse, urljoin
from urllib.error import HTTPError, URLError

HOST = "https://appletv-d5ge1bth794873f76.api.tcloudbasegateway.com"
PG_M3U_PUT = HOST + "/v1/storages/object/hotupdate/iptv/iptv-latest.m3u?x-upsert=1"
PG_META_PUT = HOST + "/v1/storages/object/hotupdate/iptv/version.json?x-upsert=1"

UPSTREAMS = [
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "https://gh-proxy.com/raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "https://gh-proxy.com/raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
]

CONCURRENCY = 24
LINE_TIMEOUT = 8.0
MAX_LINES_PER_CHANNEL = 8
TOTAL_BUDGET_S = 8 * 60
PROBE_BUDGET_LINES = 1500
UA = "Mozilla/5.0 OptimalTV/iptv-check"
MAX_REDIRECTS = 3

# 测活对公网直播源放宽证书校验（大量自签/过期证书源；只读探测，不涉敏感数据）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# 禁自动重定向的 opener（重定向由 http_open 手动受控循环，逐跳校验）
class _NoRedirect(urlreq.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urlreq.build_opener(_NoRedirect, urlreq.HTTPSHandler(context=SSL_CTX))


def assert_public_url(u):
    """出站边界校验：仅 http/https；域名解析的全部 IP 必须为公网地址（SSRF 防护）。"""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("bad scheme/host: %s" % u[:80])
    port = p.port or (443 if p.scheme == "https" else 80)
    infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("non-global target %s -> %s" % (p.hostname, ip))


def http_open(u, timeout, headers=None):
    """校验 → 打开 → 返回响应；3xx 由调用方逐跳处理（重定向每跳重新校验）。"""
    assert_public_url(u)
    req = urlreq.Request(u, headers=headers or {})
    return OPENER.open(req, timeout=timeout)


def http_get_text(u, timeout, max_bytes, range_header=None):
    """GET 并限长读文本；跟随 ≤3 跳重定向（逐跳校验）；返回 (status, text) 或 None。"""
    headers = {"User-Agent": UA}
    if range_header:
        headers["Range"] = range_header
    cur, hops = u, 0
    while True:
        try:
            resp = http_open(cur, timeout, headers)
        except HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location")
                if not loc or hops >= MAX_REDIRECTS:
                    return e.code, ""
                hops += 1
                cur = urljoin(cur, loc)
                continue
            return e.code, ""
        except (ValueError, URLError, OSError, ssl.SSLError, socket.gaierror):
            return None
        with resp:
            data = resp.read(max_bytes + 1)
            return resp.status, data[:max_bytes].decode("utf-8", "replace")


_token_lock = threading.Lock()
_token_cache = {"token": None, "exp": 0.0}


def _pg_token():
    with _token_lock:
        if _token_cache["token"] and time.time() < _token_cache["exp"] - 120:
            return _token_cache["token"]
        body = json.dumps({
            "username": os.environ.get("OTV_AUTH_USER", ""),
            "password": os.environ.get("OTV_AUTH_PASS", ""),
        }).encode("utf-8")
        assert_public_url(HOST + "/auth/v1/signin")
        req = urlreq.Request(HOST + "/auth/v1/signin", data=body, method="POST",
                             headers={"Content-Type": "application/json", "User-Agent": UA})
        with OPENER.open(req, timeout=15) as r:
            out = json.loads(r.read().decode("utf-8"))
        tok = out.get("access_token")
        if not tok:
            raise RuntimeError("no access_token")
        _token_cache["token"] = tok
        _token_cache["exp"] = time.time() + int(out.get("expires_in", 7200))
        return tok


def _pg_put(u, data, content_type):
    assert_public_url(u)
    for _ in range(2):  # token 过期重试一次
        req = urlreq.Request(u, data=data.encode("utf-8"), method="POST", headers={
            "Authorization": "Bearer " + _pg_token(),
            "Content-Type": content_type,
            "User-Agent": UA,
        })
        try:
            with OPENER.open(req, timeout=30) as r:
                r.read()
            return
        except HTTPError as e:
            if e.code == 401:
                _token_cache["token"] = None
                continue
            raise
    raise RuntimeError("pg put failed")


def norm_key(name):
    n = re.sub(r"\s+", "", name.strip().lower().replace("＋", "+").replace("－", "-"))
    m = re.match(r"^(cctv|cgtn)[-–—]?(\d+)(\+?)", n)
    return (m.group(1) + m.group(2) + m.group(3)) if m else n


def parse_m3u(raw):
    by_key, order = {}, []
    p_name, p_logo = "", ""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            p_name = line[line.rfind(",") + 1:].strip()
            m = re.search(r'tvg-logo="([^"]*)"', line)
            p_logo = m.group(1) if m else ""
        elif line.startswith("http://") or line.startswith("https://"):
            if not p_name or not line:
                continue
            key = norm_key(p_name)
            ch = by_key.get(key)
            if ch is None:
                ch = {"name": p_name, "logo": p_logo, "urls": []}
                by_key[key] = ch
                order.append(ch)
            if not ch["logo"] and p_logo:
                ch["logo"] = p_logo
            if len(ch["urls"]) < 24 and line not in ch["urls"]:
                ch["urls"].append(line)
            p_name, p_logo = "", ""
    return order


def probe_line(url):
    """单线测活：第一跳清单/直连 + m3u8 首分片 range 探测；内网目标直接判死（安全边界）。"""
    t0 = time.time()
    try:
        first = http_get_text(url, LINE_TIMEOUT, 256 * 1024)
    except ValueError:
        return {"dead": True}   # 内网/非法目标：拒绝探测并剔除（SSRF 防护落地）
    if not first or first[0] >= 400 or first[0] == 0:
        return {"dead": True}
    is_playlist = ".m3u8" in urlparse(url).path or "/m3u8" in url
    if not is_playlist:
        return {"dead": False, "ms": int((time.time() - t0) * 1000)}   # 直连线：有响应即活
    if "#EXTM3U" not in first[1]:
        return {"dead": False, "ms": int((time.time() - t0) * 1000)}   # 伪装直连流，视为活
    seg = next((l for l in first[1].splitlines() if l and not l.startswith("#")), None)
    if not seg:
        return {"dead": False, "ms": int((time.time() - t0) * 1000)}
    try:
        second = http_get_text(urljoin(url, seg), LINE_TIMEOUT, 64 * 1024, "bytes=0-65535")
    except ValueError:
        return {"dead": True}
    if not second or second[0] >= 400 or second[0] == 0:
        return {"dead": True}
    if second[0] != 206 and not second[1]:
        return {"dead": True}
    return {"dead": False, "ms": int((time.time() - t0) * 1000)}


def rebuild():
    t0 = time.time()
    # v1.20 电视源管理：后台切到 manual（托管发布）模式时跳过自动推流——
    # 每日构建产物会覆盖 iptv-latest.m3u，若不跳过将冲掉后台手动发布的托管列表。
    # 模式写在公开桶 version.json（后台发布时写入 mode=manual；切回 auto 写 auto）。
    cur_meta = http_get_text(
        HOST + "/v1/storages/object/hotupdate/iptv/version.json", 10.0, 64 * 1024)
    if cur_meta and cur_meta[0] == 200 and cur_meta[1]:
        try:
            if json.loads(cur_meta[1]).get("mode") == "manual":
                return {"ret": 0, "skipped": True, "reason": "manual mode（后台托管发布，自动推流暂停）"}
        except ValueError:
            pass  # 损坏的 meta 视为 auto 继续

    # 1) 拉上游（任一成功即用；全失败抛错保留桶内旧版）
    channels, src_used = None, ""
    for src in UPSTREAMS:
        r = http_get_text(src, 20.0, 16 * 1024 * 1024)
        if r and r[0] == 200 and "#EXTM3U" in r[1]:
            channels = parse_m3u(r[1])
            src_used = src
            break
    if not channels:
        raise RuntimeError("all upstreams failed")

    # 2) 全量线路测活（预算内，线程池并发）
    all_urls = [u for ch in channels for u in ch["urls"]][:PROBE_BUDGET_LINES]
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        verdicts = dict(zip(all_urls, pool.map(probe_line, all_urls)))

    # 3) 剔死 + 按测速排序 + 截断；全死频道整个剔除（电视#9：删除不可用数据源）
    dead_removed, out, lines_count = 0, [], 0
    for ch in channels:
        alive = []
        for u in ch["urls"]:
            v = verdicts.get(u)
            if v and not v["dead"]:
                alive.append((v["ms"], u))
            else:
                dead_removed += 1
        if not alive:
            continue
        alive.sort()
        out.append((ch["name"], ch["logo"], [u for _, u in alive[:MAX_LINES_PER_CHANNEL]]))
        if time.time() - t0 > TOTAL_BUDGET_S:
            break

    # 4) 序列化 m3u（group-title 留空——客户端按内置精编表归组，云端只管线路池）
    parts = ["#EXTM3U"]
    for name, logo, urls in out:
        for u in urls:
            parts.append('#EXTINF:-1 tvg-logo="%s" group-title="",%s' % (logo or "", name))
            parts.append(u)
            lines_count += 1
    m3u = "\n".join(parts) + "\n"

    meta = {
        "ret": 0,
        "mode": "auto",   # 自动推流产物（后台切 manual 时本轮已被上方守卫跳过）
        "version": int(time.time() * 1000),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "srcUsed": src_used,
        "channels": len(out),
        "lines": lines_count,
        "deadRemoved": dead_removed,
        "tookMs": int((time.time() - t0) * 1000),
    }
    _pg_put(PG_M3U_PUT, m3u, "audio/x-mpegurl")
    _pg_put(PG_META_PUT, json.dumps(meta, ensure_ascii=False), "application/json")
    return meta


def main_handler(event, context):
    """Event 入口：Timer 定时（每日 06:30）或手动 invoke 都执行一轮
    「拉上游→测活剔死→按测速排序→写公开桶 iptv/iptv-latest.m3u」。
    客户端不经过本函数——直接匿名 GET 公开桶对象（SOURCES 首位）。"""
    try:
        return rebuild()
    except Exception as e:  # noqa: BLE001
        print("rebuild failed:", e)
        return {"ret": 1, "msg": str(e)}


if __name__ == "__main__":
    print(json.dumps(main_handler({}, None), ensure_ascii=False))

# MCP updateFunctionCode 会把 Handler 重置为 index.main——别名适配两种入口名
main = main_handler
