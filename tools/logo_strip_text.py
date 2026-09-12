#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.20 双端需求#3：电视台台标「只要图形不要文字」。v2：空白带切割法。

原理：图形与频道名文字之间的透明间隙在行/列 alpha 剖面上表现为全空带。
top=在高度中部找全空行带，保留上方（CCTV 族：CCTV-N 台标 + 下方频道名）；
left=在宽度中部找全空列带，保留左方（省级卫视：图形 + 右侧台名）；
largest=连通域取最大簇（CETV 三段并排）。找不到清晰空带 → 该文件原样跳过。

用法：
  python tools/logo_strip_text.py preview   # 生成 tools/out/logo_strip_preview.png（不落盘改动）
  python tools/logo_strip_text.py apply     # 裁剪写入 assets/logos（原文件备份到 tools/out/logo_backup/）
"""
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

LOGO_DIR = pathlib.Path(r"D:\MyProjects\My TV\android\app\src\main\assets\logos")
OUT_DIR = pathlib.Path(r"D:\MyProjects\My TV\tools\out")
BACKUP_DIR = OUT_DIR / "logo_backup"

# 仅收录「独立图形 + 冗余台名文字」且空带可分离的频道（预览视觉复核通过，2026-09-03）。
# CCTV 主频道族：CCTV-N 台标 + 下方中文频道名 → 保留上方；省级卫视：图形 + 右侧台名 → 保留左方。
# 不收录：CCTV付费频道/CETV/CGTN（文字即徽标，裁剪会误删）、大湾区/广东系（图形与文字
# 无空带交叠不可分）、西藏（裁后残缺）。
RULES = {
    **{f"l{i:02d}.png": "top" for i in list(range(0, 12)) + list(range(20, 26))},
    **{f"l{i:02d}.png": "left" for i in [26, 29, 30, 31]},
}

BAND_MIN_FRAC = 0.012   # 空带最小厚度（按短边比例）
SEARCH_LO, SEARCH_HI = 0.30, 0.80  # 空带搜索窗口（避开边缘留白）


def mask_of(im: Image.Image) -> np.ndarray:
    a = np.asarray(im.convert("RGBA"))
    alpha = a[..., 3] > 40
    if alpha.mean() > 0.97:  # 无透明通道：近白视为底
        rgb = a[..., :3].astype(int)
        return (rgb @ [299, 587, 114] // 1000) < 235
    return alpha


def find_band(profile: np.ndarray, lo: int, hi: int, min_w: int):
    """在 profile[lo:hi] 找最长连续 0 段，返回 (start, end)（含端点），无则 None"""
    best = None
    i = lo
    while i < hi:
        if profile[i] == 0:
            j = i
            while j < hi and profile[j] == 0:
                j += 1
            if j - i >= min_w and (best is None or j - i > best[1] - best[0]):
                best = (i, j)
            i = j
        else:
            i += 1
    return best


def strip_one(fname: str, rule: str):
    """返回 (新图 or None原因, 说明)"""
    im = Image.open(LOGO_DIR / fname).convert("RGBA")
    W, H = im.size
    mask = mask_of(im)
    min_w = max(2, int(min(W, H) * BAND_MIN_FRAC))
    box = None
    if rule in ("top", "left"):
        prof = mask.sum(axis=1) if rule == "top" else mask.sum(axis=0)
        span = H if rule == "top" else W
        band = find_band(prof, int(span * SEARCH_LO), int(span * SEARCH_HI), min_w)
        if not band:
            return None, "中部无空带"
        cut = band[0]
        box = (0, 0, W, cut) if rule == "top" else (0, 0, cut, H)
    else:  # largest
        total = int(mask.sum())
        r = max(2, int(min(W, H) * 0.018))
        lab, n = ndimage.label(ndimage.binary_dilation(mask, np.ones((r, r))))
        best = None
        for i, sl in enumerate(ndimage.find_objects(lab), 1):
            m = mask & (lab == i)
            mass = int(m.sum())
            if mass < total * 0.05:
                continue
            if best is None or mass > best[0]:
                ys, xs = np.nonzero(m)
                best = (mass, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        if not best:
            return None, "无有效连通域"
        box = best[1]
    out = im.crop(box)
    # 精修：按原始掩码再 trim 四周一圈
    m2 = mask_of(out)
    if m2.any():
        ys, xs = np.nonzero(m2)
        out = out.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    if out.size[0] < 16 or out.size[1] < 16:
        return None, "裁后过小(%dx%d)" % out.size
    return out, "%s %dx%d→%dx%d" % (rule, W, H, out.size[0], out.size[1])


def main(mode: str):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    results = []  # (fname, ok, desc, out)
    for fname, rule in sorted(RULES.items()):
        out, desc = strip_one(fname, rule)
        results.append((fname, out is not None, desc, out))
    for fname, ok, desc, _ in results:
        print(("OK  " if ok else "--  ") + fname, desc)

    # 预览拼图：每行 = 原图(左) + 裁剪结果(右)，深底格子，下方文件名标签
    CELL, PAD, LABEL = 200, 8, 22
    rows = [r for r in results if r[1]] + [r for r in results if not r[1]]
    sheet = Image.new("RGB", (CELL * 2 + PAD * 3, (CELL + LABEL + PAD) * len(rows) + PAD), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 13)
    except Exception:
        font = None
    y = PAD
    for fname, ok, desc, out in rows:
        orig = Image.open(LOGO_DIR / fname).convert("RGBA")
        for slot, img in ((0, orig), (1, out if out is not None else orig)):
            x = PAD + slot * (CELL + PAD)
            tile = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
            iw, ih = img.size
            s = min(CELL * 0.86 / iw, CELL * 0.86 / ih)
            img2 = img.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)
            tile.paste(img2, ((CELL - img2.size[0]) // 2, (CELL - img2.size[1]) // 2), img2)
            sheet.paste(tile, (x, y), tile)
            d.rectangle([x - 2, y - 2, x + CELL + 1, y + CELL + 1], outline=(70, 70, 78), width=1)
        d.text((PAD, y + CELL + 3), "%s  %s%s" % (fname, "" if ok else "[跳过] ", desc), fill=(190, 190, 198), font=font)
        y += CELL + LABEL + PAD
    sheet.save(OUT_DIR / "logo_strip_preview.png")
    print("预览 →", OUT_DIR / "logo_strip_preview.png")

    if mode == "apply":
        for fname, ok, _, out in results:
            if not ok:
                continue
            p = LOGO_DIR / fname
            if not (BACKUP_DIR / fname).is_file():
                (BACKUP_DIR / fname).write_bytes(p.read_bytes())
            out.save(p, "PNG", optimize=True)
        print("已写入 %d 个（原图备份在 %s）" % (sum(1 for r in results if r[1]), BACKUP_DIR))
    return 0


if __name__ == "__main__":
    from PIL import ImageFont
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "preview"))
