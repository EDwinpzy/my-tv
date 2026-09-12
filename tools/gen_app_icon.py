#!/usr/bin/env python3
# 生成 My TV 品牌资源（2026-09-02 品牌更名：Apple TV → My TV）
# 输出（android 工程；移动工程由移植会话按清单自行复制）：
#   res/drawable/my_tv_logo.png             启动屏字标（白字透明底 ~2:1）
#   res/mipmap-xxxhdpi/ic_launcher_fg.png   自适应图标前景（白 logo，安全区居中）
#   res/mipmap-xhdpi/ic_launcher_fg.png
#   res/drawable/ic_banner.png              TV 桌面 banner 640×360
# 自适应图标 XML（ic_launcher.xml / ic_launcher_bg 颜色）为仓库内静态文件，无需改动。
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"
FONT_DIR = Path(r"C:\Windows\Fonts")
FONT_MY = FONT_DIR / "segoeuisl.ttf"   # Segoe UI Semilight：My
FONT_TV = FONT_DIR / "segoeuib.ttf"    # Segoe UI Bold：TV
SIZE = 200
GAP = 36


def make_wordmark() -> Image.Image:
    """白字透明底「My TV」字标：My=Semilight，TV=Bold，共基线。"""
    f_my = ImageFont.truetype(str(FONT_MY), SIZE)
    f_tv = ImageFont.truetype(str(FONT_TV), SIZE)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    w_my = probe.textlength("My", font=f_my)
    w_tv = probe.textlength("TV", font=f_tv)
    canvas = Image.new("RGBA", (int(w_my + GAP + w_tv) + 40, SIZE * 2), (255, 255, 255, 0))
    dd = ImageDraw.Draw(canvas)
    baseline = int(SIZE * 1.45)
    dd.text((20, baseline), "My", font=f_my, fill=(255, 255, 255, 255), anchor="ls")
    dd.text((20 + w_my + GAP, baseline), "TV", font=f_tv, fill=(255, 255, 255, 255), anchor="ls")
    bbox = canvas.getbbox()
    pad = 8
    return canvas.crop((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad))


def whiten(img: Image.Image) -> Image.Image:
    """保留 alpha，把所有颜色改纯白（图标前景/深底场景统一白标）"""
    a = img.getchannel("A")
    white = Image.new("RGBA", img.size, (255, 255, 255, 0))
    white.putalpha(a)
    return white


def make_fg(logo: Image.Image, size: int = 432) -> Image.Image:
    """自适应图标前景：内容落在中心 ~60% 安全区"""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    wl = whiten(logo)
    target_w = int(size * 0.60)
    fg = wl.resize((target_w, int(target_w * wl.height / wl.width)), Image.LANCZOS)
    canvas.alpha_composite(fg, ((size - fg.width) // 2, (size - fg.height) // 2))
    return canvas


def make_banner(logo: Image.Image, w: int = 640, h: int = 360) -> Image.Image:
    """TV banner：深黑底 + 白 logo 居中（宽 56%）"""
    canvas = Image.new("RGBA", (w, h), (16, 16, 20, 255))
    wl = whiten(logo)
    target_w = int(w * 0.56)
    fg = wl.resize((target_w, int(target_w * wl.height / wl.width)), Image.LANCZOS)
    canvas.alpha_composite(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return canvas


logo = make_wordmark()
(RES / "drawable").mkdir(parents=True, exist_ok=True)
logo.save(RES / "drawable" / "my_tv_logo.png")
(RES / "mipmap-xxxhdpi").mkdir(parents=True, exist_ok=True)
make_fg(logo, 432).save(RES / "mipmap-xxxhdpi" / "ic_launcher_fg.png")
(RES / "mipmap-xhdpi").mkdir(parents=True, exist_ok=True)
make_fg(logo, 216).save(RES / "mipmap-xhdpi" / "ic_launcher_fg.png")
make_banner(logo).save(RES / "drawable" / "ic_banner.png")
print(f"my_tv_logo {logo.size[0]}x{logo.size[1]} + launcher fg + banner 已生成到 {RES}")
