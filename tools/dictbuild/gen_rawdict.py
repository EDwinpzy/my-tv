# -*- coding: utf-8 -*-
"""扩充 AOSP 谷歌拼音 rawdict 词表（2026-08-29）。

背景：随包 dict_pinyin.dat 是 2009 年词典，缺影视新词（santi 首选是「三提」而非「三体」）。
本脚本把手工标注拼音的影视/热词条目追加到 rawdict（词长≤4、多字词 freq≥60 为
dictbuilder 硬约束），再由 tools/dictbuild 在设备上重建 dict_pinyin.dat。

用法：python tools/dictbuild/gen_rawdict.py
输入：cpp/pinyinime/data/rawdict_utf16_65105_freq.txt + valid_utf16.txt
输出：tools/dictbuild/rawdict_ext.txt（UTF-16LE，带 BOM，与原文件同构）
"""
import pathlib
import sys

ROOT = pathlib.Path(r"D:/MyProjects/Apple TV")
DATA = ROOT / "android/app/src/main/cpp/pinyinime/data"
OUT = ROOT / "tools/dictbuild/rawdict_ext.txt"

# 新词条目：(词, 拼音音节...)。freq 统一 50000：高于爱情(14477)低于中国(106588)，
# 保证新词排在候选前列但不压过超高频日常词。
FREQ = "50000.0"

WORDS = [
    # 影视剧名/系列（≤4 字）
    ("三体", "san", "ti"), ("流浪地球", "liu", "lang", "di", "qiu"),
    ("庆余年", "qing", "yu", "nian"), ("狂飙", "kuang", "biao"),
    ("繁花", "fan", "hua"), ("长相思", "chang", "xiang", "si"),
    ("莲花楼", "lian", "hua", "lou"), ("与凤行", "yu", "feng", "xing"),
    ("一念关山", "yi", "nian", "guan", "shan"),
    ("墨雨云间", "mo", "yu", "yun", "jian"),
    ("追风者", "zhui", "feng", "zhe"), ("承欢记", "cheng", "huan", "ji"),
    ("九重紫", "jiu", "chong", "zi"), ("国色芳华", "guo", "se", "fang", "hua"),
    ("难哄", "nan", "hong"), ("诡事录", "gui", "shi", "lu"),
    ("宁安如梦", "ning", "an", "ru", "meng"), ("花间令", "hua", "jian", "ling"),
    ("白月梵星", "bai", "yue", "fan", "xing"), ("六姊妹", "liu", "zi", "mei"),
    ("漠风吟", "mo", "feng", "yin"), ("凡人修仙", "fan", "ren", "xiu", "xian"),
    ("斗破苍穹", "dou", "po", "cang", "qiong"),
    ("斗罗大陆", "dou", "luo", "da", "lu"),
    ("完美世界", "wan", "mei", "shi", "jie"), ("沧元图", "cang", "yuan", "tu"),
    ("披荆斩棘", "pi", "jing", "zhan", "ji"), ("过家家", "guo", "jia", "jia"),
    ("排球少年", "pai", "qiu", "shao", "nian"),
    ("鬼灭之刃", "gui", "mie", "zhi", "ren"),
    ("咒术回战", "zhou", "shu", "hui", "zhan"),
    ("海贼王", "hai", "zei", "wang"), ("火影忍者", "huo", "ying", "ren", "zhe"),
    ("名侦探", "ming", "zhen", "tan"), ("柯南", "ke", "nan"),
    ("奥特曼", "ao", "te", "man"), ("家有儿女", "jia", "you", "er", "nv"),
    ("武林外传", "wu", "lin", "wai", "zhuan"), ("甄嬛传", "zhen", "huan", "zhuan"),
    ("琅琊榜", "lang", "ya", "bang"), ("伪装者", "wei", "zhuang", "zhe"),
    ("白夜追凶", "bai", "ye", "zhui", "xiong"),
    ("无证之罪", "wu", "zheng", "zhi", "zui"),
    ("隐秘角落", "yin", "mi", "jiao", "luo"),
    ("少年歌行", "shao", "nian", "ge", "xing"),
    ("悍刀行", "han", "dao", "xing"), ("择天记", "ze", "tian", "ji"),
    ("全职高手", "quan", "zhi", "gao", "shou"),
    ("诡秘之主", "gui", "mi", "zhi", "zhu"), ("打更人", "da", "geng", "ren"),
    ("苦尽柑来", "ku", "jin", "gan", "lai"),
    ("爱情公寓", "ai", "qing", "gong", "yu"),
    ("脱口秀", "tou", "kou", "xiu"), ("大侦探", "da", "zhen", "tan"),
    ("极限挑战", "ji", "xian", "tiao", "zhan"),
    ("拍案惊奇", "pai", "an", "jing", "qi"),
    ("说唱", "shuo", "chang"), ("短剧", "duan", "ju"),
    # 高频影视词（源站频道/分类用语）
    ("美剧", "mei", "ju"), ("英剧", "ying", "ju"), ("韩剧", "han", "ju"),
    ("日剧", "ri", "ju"), ("泰剧", "tai", "ju"), ("综艺", "zong", "yi"),
    ("动漫", "dong", "man"), ("国产剧", "guo", "chan", "ju"),
    ("欧美剧", "ou", "mei", "ju"), ("网剧", "wang", "ju"),
    ("纪录片", "ji", "lu", "pian"), ("喜剧片", "xi", "ju", "pian"),
    ("动作片", "dong", "zuo", "pian"), ("恐怖片", "kong", "bu", "pian"),
    # 通用新词（老词典 2009 年缺）
    ("短视频", "duan", "shi", "pin"), ("直播", "zhi", "bo"),
    ("带货", "dai", "huo"), ("内卷", "nei", "juan"),
    ("躺平", "tang", "ping"), ("打卡", "da", "ka"),
    ("元宇宙", "yuan", "yu", "zhou"),
    ("人工智能", "ren", "gong", "zhi", "neng"),
    ("新冠", "xin", "guan"), ("疫情", "yi", "qing"),
    ("核酸", "he", "suan"), ("疫苗", "yi", "miao"),
    ("智能手机", "zhi", "neng", "shou", "ji"),
    ("机器人", "ji", "qi", "ren"), ("大数据", "da", "shu", "ju"),
    ("云电脑", "yun", "dian", "nao"), ("投影仪", "tou", "ying", "yi"),
    ("遥控器", "yao", "kong", "qi"),
]


def read_utf16(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-16")


def main() -> int:
    raw = read_utf16(DATA / "rawdict_utf16_65105_freq.txt")
    valid = read_utf16(DATA / "valid_utf16.txt")
    valid_set = set(ch for ch in valid if ch.strip())
    existing = set()
    for line in raw.splitlines():
        parts = line.split()
        if parts:
            existing.add(parts[0])

    out_lines = []
    skipped = []
    for entry in WORDS:
        w, *syls = entry
        if len(w) > 4:
            skipped.append((w, "too long"))
            continue
        if w in existing:
            skipped.append((w, "exists"))
            continue
        if len(syls) != len(w):
            skipped.append((w, "syl count mismatch"))
            continue
        bad = [ch for ch in w if ch not in valid_set]
        if bad:
            skipped.append((w, "invalid chars " + "".join(bad)))
            continue
        out_lines.append("%s %s 0 %s" % (w, FREQ, " ".join(syls)))
        existing.add(w)

    OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-16")
    print("appended %d entries -> %s" % (len(out_lines), OUT))
    for w, why in skipped:
        print("  skipped: %s (%s)" % (w, why))
    return 0


if __name__ == "__main__":
    sys.exit(main())
