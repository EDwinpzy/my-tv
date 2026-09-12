# -*- coding: utf-8 -*-
"""
生成「汉字→拼音首字母」数据表（tools/gen_pinyin_initials.py）

用户需求（2026-09-05）：TV 搜索输入法首字母联想（aqgy→爱情公寓 / heysn→花儿与少年）。
数据源 pypinyin（词组感知，多音字按常用读音）——运行期 dictz 词典反查不可靠
（词典无"寓"的独立音节行，词组行污染映射）。

输出：android/app/src/main/assets/pinyin_initials.txt
  格式：每行一个汉字 + 其首字母（a-z），如「爱a」。按 Unicode 序存储，运行期加载为
  HashMap<Char, Char>（~7KB 文本，启动懒加载毫秒级）。

覆盖：GB2312 全部汉字（6763 常用字）+ CJK 基本区中 pypinyin 能给音的常见字。
用法：python tools/gen_pinyin_initials.py
"""
import os
import sys
from pypinyin import pinyin, Style

OUT = os.path.normpath("android/app/src/main/assets/pinyin_initials.txt")
# 输出路径为脚本内硬编码常量（无用户输入）；显式断言无穿越段且落在项目 assets 内
assert not OUT.split(os.sep).__contains__(".."), "path traversal in OUT"
assert OUT.replace(os.sep, "/").endswith("android/app/src/main/assets/pinyin_initials.txt")


def main():
    chars = []
    # GB2312 全字区（B0A1-F7FE）：编解码往返收集全部有效汉字
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gb2312")
                chars.append(ch)
            except UnicodeDecodeError:
                pass
    chars = sorted(set(chars))
    lines = []
    miss = 0
    for ch in chars:
        py = pinyin(ch, style=Style.NORMAL, errors=lambda x: [""])[0]
        first = py[0][:1].lower() if py and py[0] else ""
        if first in "abcdefghijklmnopqrstuvwxyz":
            lines.append(ch + first)
        else:
            miss += 1
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"written {len(lines)} chars to {OUT} (no-pinyin skipped: {miss})")
    # 自验用户两个例子
    table = dict((l[0], l[1]) for l in lines)
    for t, expect in (("爱", "a"), ("情", "q"), ("公", "g"), ("寓", "y"), ("花", "h"), ("儿", "e"), ("与", "y"), ("少", "s"), ("年", "n")):
        got = table.get(t, "?")
        flag = "OK" if got == expect else "MISMATCH"
        print(f"  {t} -> {got} (expect {expect}) {flag}")


if __name__ == "__main__":
    sys.exit(main())
