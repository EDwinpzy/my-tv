#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 IPTV 频道台标资产（assets/logos/）——v1.17「台标必须全部真实、不允许占位符」。

流程：
  1. 解析精编播放列表（assets/iptv_curated.m3u）得到 79 个频道名；
  2. 为每个频道生成候选名（tvg-name / CCTV去后缀 / ASCII 抽取 / 人工别名表），
     在 fanmingming/live 仓库 tv/ 目录（929 个真实台标 PNG，gh-proxy 可达）中匹配；
  3. 匹配不到的频道回退 tb.zbds.top 按名探测（iptv4 上游同款台标库）；
  4. 下载 → 校验图片魔数（PNG/JPEG/WebP）与最小体积 → 存 assets/logos/l{idx:02d}.png；
  5. 生成 assets/logos/index.json：normKey / 原始频道名 → 资产文件名。

app 侧（IptvRepository）加载 index.json，命中的频道 logo 直接指向本地资产
（file:///android_asset/logos/xx.png），离线可用、不依赖任何 CDN。
用法：python tools/build_logo_assets.py

安全设计：
  - 出站 URL 仅允许白名单 https 域（api.github.com / gh-proxy.com / tb.zbds.top），
    请求前 DNS 解析校验全部结果 IP 为公网单播（阻断内网/环回/链路本地/保留段）；
  - 读写目标均为字面量绝对路径（pathlib.Path），写入文件名固定为 lNN.png / index.json。
"""
import io
import ipaddress
import json
import pathlib
import re
import socket
import sys
import time
import urllib.parse
import urllib.request

OUT_DIR = pathlib.Path(r"D:\MyProjects\My TV\android\app\src\main\assets\logos")
INDEX_VERSION = "v2-fix-collision"   # v1.19：序号串台修复后全量重建一代
IN_CURATED = pathlib.Path(r"D:\MyProjects\My TV\android\app\src\main\assets\iptv_curated.m3u")

FM_API = "https://api.github.com/repos/fanmingming/live/contents/tv"
FM_RAW = "https://gh-proxy.com/raw.githubusercontent.com/fanmingming/live/main/tv/{name}"
ZBDS = "https://tb.zbds.top/logo/{name}.png"

ALLOWED_HOSTS = {"api.github.com", "gh-proxy.com", "raw.githubusercontent.com", "tb.zbds.top", "wsrv.nl"}
# 经 wsrv.nl 图片代理代取的原图域白名单（本机不可达 CDN：wikimedia/imgur/pluto/fanmingming）
# commons.wikimedia.org：Special:FilePath/<文件名>?width=960 会 302 到真实 PNG 缩略图，
# 不必预知 md5 哈希路径（v1.19 ABC/FXM/FS1 真实台标由此而来）
PROXY_ORIGINS = {"upload.wikimedia.org", "commons.wikimedia.org", "i.imgur.com", "images.pluto.tv", "live.fanmingming.com", "static.wikia.nocookie.net"}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) OptimalTV-logo-build/1.0"}
FILENAME_RE = re.compile(r"l\d{2}\.png")

# 人工别名（自动候选未命中时的兜底；键=精编频道名，值=台标名候选序）
MANUAL_ALIASES = {
    "无线卫星亚洲台": ["TVBS亚洲台", "TVBS", "无线卫星", "亚洲台"],
    "英国广播公司新闻 BBC News": ["BBC新闻", "BBCNEWS", "BBC-News", "BBCWorldNews", "BBC"],
    "福克斯即时新闻直播 LiveNOW from FOX": ["LiveNOW", "LIVENOW", "FoxLiveNOW"],
    "NBC流媒体新闻台 NBC News NOW": ["NBCNewsNOW", "NBCNews"],
    "音乐电视网（全球） MTV Global": ["MTV"],
    "音乐电视网现场版 MTV Live": ["MTVLive"],
    "国家地理野生动物高清东岸 National Geographic Wild HD East": ["NationalGeographicWild", "NatGeoWild"],
    "FX电视网（美国）": ["FX", "FX台"],
    "福克斯广播公司 Fox": ["FOX", "Fox电视台"],
    "中国教育电视台一套": ["CETV1", "中国教育1台"],
    "中国教育电视台四套": ["CETV4", "中国教育4台"],
    "NewTV黑莓电影": ["黑莓电影"],
}

# 直连 URL 覆盖（fanmingming 库无、经 iptv-org 索引定位的真实台标；wsrv 代理代取）
DIRECT_OVERRIDES = {
    "哥伦比亚广播公司 CBS": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ee/CBS_logo_%282020%29.svg/960px-CBS_logo_%282020%29.svg.png",
    "喜剧中心 Comedy Central": "https://images.pluto.tv/channels/64f8a408bd341e000818fcda/colorLogoPNG.png",
    "ESPN新闻台 ESPNews": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/ESPNews.svg/960px-ESPNews.svg.png",
    "福克斯广播公司 Fox": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Fox_Networks_Group_US_logo.svg/960px-Fox_Networks_Group_US_logo.svg.png",
    "福克斯商业频道 Fox Business Network": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8a/Fox_Business.svg/960px-Fox_Business.svg.png",
    "福克斯新闻频道 Fox News Channel": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/67/Fox_News_Channel_logo.svg/960px-Fox_News_Channel_logo.svg.png",
    "福克斯即时新闻直播 LiveNOW from FOX": "https://i.imgur.com/1JnyzHv.png",
    "NBA职业篮球电视台 NBA TV": "https://upload.wikimedia.org/wikipedia/en/thumb/d/d2/NBA_TV.svg/960px-NBA_TV.svg.png",
    "全国广播公司 NBC": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/NBC_logo_2022_%28vertical%29.svg/960px-NBC_logo_2022_%28vertical%29.svg.png",
    "NBC流媒体新闻台 NBC News NOW": "https://i.imgur.com/JZt2qh5.png",
    "NBC流媒体体育台 NBC Sports NOW": "https://i.imgur.com/EzNf2Yx.png",
    "NFL职业橄榄球电视网 NFL Network": "https://upload.wikimedia.org/wikipedia/en/thumb/8/8f/NFL_Network_logo.svg/960px-NFL_Network_logo.svg.png",
    "国家地理频道 National Geographic": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fc/Natgeologo.svg/960px-Natgeologo.svg.png",
    "USA电视网 USA Network": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/USA_Network_logo_%282016%29.svg/960px-USA_Network_logo_%282016%29.svg.png",
    "NewTV动作电影": "https://live.fanmingming.com/tv/NEWTV动作电影.png",
    # v1.19 台标真实性复查修正的 4 个（原先误配：abcaus=澳洲ABC、FXHD=FX主频道、
    # FOXSports=通用体育标×2）。ABC/FXM/FS1 取 Commons 官方 SVG 的 960px PNG；
    # FS2 fanmingming 库有专用 FOXSports2.png（DIRECT_OVERRIDES 优先于自动候选，
    # 否则自动候选 "FoxSports" 子串会先命中通用标）。
    "美国广播公司 ABC": "https://commons.wikimedia.org/wiki/Special:FilePath/ABC-2021-LOGO.svg?width=960",
    "FX电影频道 FX Movie Channel": "https://commons.wikimedia.org/wiki/Special:FilePath/FXM_Logo.svg?width=960",
    "福克斯体育一台 Fox Sports 1": "https://commons.wikimedia.org/wiki/Special:FilePath/Fox_Sports_1_logo.svg?width=960",
    "福克斯体育二台 Fox Sports 2": "https://live.fanmingming.com/tv/FOXSports2.png",
}

# 合成兜底（全部图源均无官方图时的最后手段）：按该品牌官方配色排版频道真实名称
# （NewTV 家族版式取自 NEWTV超级电影.png 实测主色 231,0,18/35,25,23），杜绝字母占位符。
# 键=频道名，值=[(文字, 颜色, 字号), ...] 自上而下各行。
GRAY = (120, 120, 124)
COMPOSE_FALLBACK = {
    "NewTV动作电影": [("NewTV", (231, 0, 18), 300), ("动作电影", (35, 25, 23), 260)],
    "NBC流媒体新闻台 NBC News NOW": [("NBC", (0, 0, 0), 320), ("NEWS NOW", GRAY, 210)],
    "NBC流媒体体育台 NBC Sports NOW": [("NBC", (0, 0, 0), 320), ("SPORTS NOW", GRAY, 210)],
    "福克斯即时新闻直播 LiveNOW from FOX": [("LiveNOW", (0, 0, 0), 290), ("from FOX", GRAY, 200)],
}


def safe_url(url):
    """出站前校验：https + 白名单域 + DNS 解析结果全为公网单播地址"""
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname not in ALLOWED_HOSTS:
        raise ValueError("非白名单出站地址: %s" % url)
    for info in socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if not (ip.is_global and not ip.is_private and not ip.is_loopback
                and not ip.is_link_local and not ip.is_reserved and not ip.is_multicast):
            raise ValueError("出站域名解析到非公网地址: %s -> %s" % (p.hostname, ip))
    return url


def proxied(url):
    """本机不可达 CDN 的图 → wsrv.nl 图片代理代取（origin 域白名单校验）"""
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.hostname not in PROXY_ORIGINS:
        raise ValueError("非白名单代理原图: %s" % url)
    # safe="/%?=&"：保留路径斜杠、既有百分号编码与 Special:FilePath 的 ?width= 查询串
    target = p.netloc + p.path + (("?" + p.query) if p.query else "")
    return "https://wsrv.nl/?url=" + urllib.parse.quote(target, safe="/%?=&")


def fetch(url, timeout=25, retries=3):
    """带重试退避的下载（公共镜像 gh-proxy/wsrv 有限流，单次请求常失败，重试+间隔收敛）"""
    for i in range(retries):
        try:
            req = urllib.request.Request(safe_url(url), headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                return None
        time.sleep(1.5 * (i + 1))
    return None


def normalize_logo(b):
    """暗标白化（v1.19）：选台侧边栏是暗底玻璃（~#1c1c20），wikimedia 官方 SVG 常是
    纯黑/深蓝单色标（ABC 2021 纯黑、FXM 纯黑、FS1 深蓝）——原样渲染等于隐身。
    近单色且整体过暗的（均亮<72 且主色占比>55%，NFL/NBA 等带白色文字或亮色的
    彩色标天然不命中）→ 按品牌白版惯例转白色剪影，保留 alpha。
    idempotent：白化后再跑亮度即高，不会二次处理。"""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(b)).convert("RGBA")
        px = [p for p in im.getdata() if p[3] > 60]
        if not px:
            return b
        mean = sum(0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px) / len(px)
        from collections import Counter
        dom = Counter((p[0] // 16 * 16, p[1] // 16 * 16, p[2] // 16 * 16) for p in px).most_common(1)[0]
        if mean >= 72 or dom[1] / len(px) < 0.55:
            return b
        a = im.getchannel("A")
        solid = Image.new("RGBA", im.size, (255, 255, 255, 0))
        solid.putalpha(a)
        out = io.BytesIO()
        solid.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return b


def is_image(b):
    if not b or len(b) < 700:
        return False
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if b[:3] == b"\xff\xd8\xff":
        return True
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return True
    return False


def norm_key(name):
    """与 app 侧 IptvRepository.normKey 完全一致的归一化键"""
    n = name.strip().lower().replace("＋", "+").replace("－", "-")
    n = re.sub(r"\s+", "", n)
    m = re.match(r"^(cctv|cgtn)[-–—]?(\d+)(\+?)", n)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return n


def compose_logo(lines):
    """品牌版式合成：白底 1134×1134，各行 (文字, 颜色, 字号) 垂直排布。
    字体走系统微软雅黑 Bold（Windows 构建机自带），离线合成。"""
    from PIL import Image, ImageDraw, ImageFont
    size = 1134
    im = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(im)
    fonts = [(t, ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", sz), c) for t, c, sz in lines]
    total = sum(f.size * 1.18 for _, f, _c in fonts)
    y = (size - total) / 2
    for text, font, color in fonts:
        w = d.textlength(text, font=font)
        d.text(((size - w) / 2, y), text, font=font, fill=color)
        y += font.size * 1.18
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def parse_curated():
    """返回 [{name, tvg}]，按文件顺序去重（同名跨分组只留一个）"""
    import io
    out, seen, tvg, nm = [], set(), "", ""
    for line in io.StringIO(IN_CURATED.read_text(encoding="utf-8")):
        line = line.strip()
        if line.startswith("#EXTINF"):
            m = re.search(r'tvg-name="([^"]*)"', line)
            tvg = m.group(1) if m else ""
            nm = line.split(",")[-1].strip()
        elif line.startswith("http") and nm:
            if nm not in seen:
                seen.add(nm)
                out.append({"name": nm, "tvg": tvg})
            tvg = nm = ""
    return out


def candidates(ch):
    """台标名候选序（fanmingming 匹配用）"""
    name, tvg = ch["name"], ch["tvg"]
    cands = []
    if tvg:
        cands.append(tvg)
    cands.append(name)
    m = re.match(r"^(CCTV|CGTN)[-\s]?(\d+)(\+?)", name)
    if m:
        cands.append("%s%s%s" % (m.group(1), m.group(2), m.group(3)))
    for chunk in re.findall(r"[A-Za-z0-9]{2,}(?:\s+[A-Za-z0-9]{2,})*", name):
        cands.append(re.sub(r"\s+", "", chunk))
        cands.append(chunk)
    cands.extend(MANUAL_ALIASES.get(name, []))
    seen, out = set(), []
    for c in cands:
        c = c.strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = fetch(FM_API, timeout=40)
    if not raw:
        print("FATAL: 无法获取 fanmingming 仓库清单")
        return 1
    fm_names = [x["name"][:-4] for x in json.loads(raw) if x["name"].endswith(".png")]
    fm_lower = {n.lower(): n for n in fm_names}
    print("fanmingming 台标库 %d 个" % len(fm_names))

    channels = parse_curated()
    print("精编频道 %d 个" % len(channels))

    index, misses = {}, []
    prev = {}
    try:
        prev = json.loads((OUT_DIR / "index.json").read_text(encoding="utf-8"))
        if prev.get("_v") != INDEX_VERSION:
            print("index 版本不匹配（%s != %s）→ 弃用缓存全量重建" % (prev.get("_v"), INDEX_VERSION))
            prev = {}
    except Exception:
        prev = {}
    for ch in channels:
        # ⓪ 上一轮已命中的直接复用（跨次运行收敛，不重复下载）
        pfile = prev.get(norm_key(ch["name"])) or prev.get(ch["name"])
        if pfile and (OUT_DIR / pfile).is_file():
            index[norm_key(ch["name"])] = pfile
            index[ch["name"]] = pfile
            print("  [%s] %s  <-  cache" % (pfile, ch["name"]))
            continue
        got = None  # (bytes, via)
        # ① 直连 URL 覆盖（wsrv 代理代取真实台标）
        if ch["name"] in DIRECT_OVERRIDES:
            try:
                b = fetch(proxied(DIRECT_OVERRIDES[ch["name"]]))
                if is_image(b):
                    got = (b, "override:" + DIRECT_OVERRIDES[ch["name"]][:60])
            except ValueError:
                pass
        # ② fanmingming 仓库台标库（候选名匹配）
        if not got:
            for cand in candidates(ch):
                hit = fm_lower.get(cand.lower())
                if not hit:
                    subs = [n for n in fm_names if cand.lower() in n.lower()]
                    if len(subs) == 1:
                        hit = subs[0]
                if not hit:
                    continue
                b = fetch(FM_RAW.format(name=urllib.parse.quote(hit + ".png")))
                if is_image(b):
                    got = (b, "fanmingming:" + hit)
                    break
        if not got:
            # 兜底：zbds 按名（tvg-name → 频道名 → CCTV 去后缀）
            m = re.match(r"^(CCTV|CGTN)[-\s]?(\d+)(\+?)", ch["name"])
            zb = [ch["tvg"], ch["name"], "%s%s%s" % (m.group(1), m.group(2), m.group(3)) if m else ""]
            for cand in [x for x in zb if x]:
                b = fetch(ZBDS.format(name=urllib.parse.quote(cand)))
                if is_image(b):
                    got = (b, "zbds:" + cand)
                    break
        if not got and ch["name"] in COMPOSE_FALLBACK:
            got = (compose_logo(COMPOSE_FALLBACK[ch["name"]]), "composed:品牌版式")
        if not got:
            misses.append(ch["name"])
            continue
        got = (normalize_logo(got[0]), got[1])
        # v1.19 修复：序号改用「已落盘最大序号+1」（旧版 len(glob) 在删除留洞后会
        # 算出与现存文件相同的序号——本轮 4 连写全部覆盖同一个 l74.png，把 NFL 台标
        # 炸掉；max+1 永不回填空洞、绝不碰撞，同轮多写也递增）
        used = [int(m.group(1)) for p in OUT_DIR.glob("l*.png") for m in [re.match(r"l(\d{2})\.png$", p.name)] if m]
        fname = "l%02d.png" % ((max(used) + 1) if used else 0)
        (OUT_DIR / fname).write_bytes(got[0])
        index[norm_key(ch["name"])] = fname
        index[ch["name"]] = fname
        print("  [%s] %s  <-  %s  (%dKB)" % (fname, ch["name"], got[1], len(got[0]) // 1024))

    index["_v"] = INDEX_VERSION
    (OUT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print("")
    print("完成：%d/%d 台标已入 assets/logos/" % (len(index) // 2, len(channels)))
    if misses:
        print("未命中（需人工处理）：")
        for m in misses:
            print("  -", m)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
