# -*- coding: utf-8 -*-
"""
生成「片名拼音首字母 → 片名」联想词表（tools/gen_pinyin_titles.py）

用户需求（2026-09-05）：TV 搜索输入法首字母联想（aqgy→爱情公寓 / heysn→花儿与少年）。
数据源 = hhkan 全站可播内容（6 分类 show 分页全量，每分类 360 条/20 页，共 ~2160 条）——
联想源与可播内容精确对齐（联想出的都能播）。运行期 dictz 反查方案已否决（词典非影视词库）。

输出：android/app/src/main/assets/pinyin_titles.txt
  格式：每行「首字母串<TAB>片名」（UTF-8，~2160 行）。运行期懒加载为列表做前缀匹配。

自验：aqgy → 命中爱情公寓系列；heysn → 命中花儿与少年。
用法：python tools/gen_pinyin_titles.py   （需可访问 hhkan 源站，~2 分钟）
"""
import os
import sys
import time

sys.path.insert(0, "tools/backend-src")
import hhkan  # noqa: E402
from pypinyin import pinyin, Style  # noqa: E402

OUT = os.path.normpath("android/app/src/main/assets/pinyin_titles.txt")
# 输出路径为脚本内硬编码常量（无用户输入）；显式断言无穿越段且落在项目 assets 内
assert not OUT.split(os.sep).__contains__(".."), "path traversal in OUT"
assert OUT.replace(os.sep, "/").endswith("android/app/src/main/assets/pinyin_titles.txt")
CATS = {1: "电影", 2: "电视剧", 3: "动漫", 4: "综艺", 6: "短剧"}
MAX_PAGE = 25   # 源站每分类 20 页封顶；留余量


def initials_of(title: str) -> str:
    """片名 → 拼音首字母串：汉字取 pypinyin 首字母；英文字母保留；其余跳过"""
    sb = []
    for ch in title:
        if ch.isascii() and ch.isalpha():
            sb.append(ch.lower())
        elif "\u4e00" <= ch <= "\u9fff":
            py = pinyin(ch, style=Style.NORMAL, errors=lambda x: [""])[0]
            if py and py[0][:1].isalpha():
                sb.append(py[0][:1].lower())
    return "".join(sb)


def main():
    seen = {}
    for cid, name in CATS.items():
        got = 0
        for page in range(1, MAX_PAGE + 1):
            try:
                items = hhkan.get_show_page(cid, page=page)
            except Exception as e:
                print(f"  {name} p{page} ERR {e}")
                break
            if not items:
                break
            for it in items:
                title = (it.get("title") or "").strip()
                if title and it["id"] not in seen:
                    seen[it["id"]] = title
            got += len(items)
            time.sleep(0.2)
        print(f"{name}(cid={cid}): {got} 条")
    print(f"全库去重 {len(seen)} 条")

    rows = []
    for vid, title in seen.items():
        ini = initials_of(title)
        if len(ini) >= 2:
            rows.append((ini, title))
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(OUT, "w", encoding="utf-8") as f:
        for ini, title in rows:
            f.write(f"{ini}\t{title}\n")
    print(f"written {len(rows)} rows -> {OUT}")

    table = {}
    for ini, title in rows:
        table.setdefault(ini, []).append(title)
    for q, expect in (("aqgy", "爱情公寓"), ("heysn", "花儿与少年")):
        hits = [t for t in table.get(q, [])]
        print(f"  {q} -> {hits[:4]} {'OK' if any(expect in h for h in hits) else 'MISS ' + expect}")


if __name__ == "__main__":
    sys.exit(main())
