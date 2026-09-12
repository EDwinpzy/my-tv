# -*- coding: utf-8 -*-
"""生成 TV 拼音输入法词典资产 pinyin_ime.dict.gz
数据源（GitHub 成熟开源数据）：
- mozillazg/phrase-pinyin-data  词→带调拼音
- fxsjy/jieba dict.txt          词频（Apache-2.0）
输出：每行 "拼音字母串:词1,词2,..."（同 key 内按词频降序，cap 20），整体按 key 排序，gzip。
运行时 Kotlin 侧二分前缀查找。
"""
import gzip
import unicodedata
from collections import defaultdict

PINYIN_FILE = r"C:\Users\63054\AppData\Local\Temp\pinyin\large_pinyin.txt"
JIEBA_FILE = r"C:\Users\63054\AppData\Local\Temp\pinyin\jieba_dict.txt"
CHAR_FILE = r"C:\Users\63054\AppData\Local\Temp\pinyin\char_pinyin.txt"
OUT_RAW = r"C:\Users\63054\AppData\Local\Temp\pinyin\pinyin_ime.dict"
OUT_GZ = r"D:/MyProjects/My TV/android/app/src/main/assets/pinyin_ime.dict.gz"

# 标准普通话音节表（约 410 个）；ü 统一写作 v
SYLLABLES = set(
    "a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu "
    "ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi chong "
    "chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui cun cuo "
    "da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan "
    "dui dun duo e ei en eng er fa fan fang fei fen feng fo fou fu ga gai gan gang gao "
    "ge gei gen geng gong gou gu gua guai guan guang gui gun guo ha hai han hang hao he "
    "hei hen heng hong hou hu hua huai huan huang hui hun huo ji jia jian jiang jiao jie "
    "jin jing jiong jiu ju juan jue jun ka kai kan kang kao ke kei ken keng kong kou ku "
    "kua kuai kuan kuang kui kun kuo la lai lan lang lao le lei leng li lia lian liang "
    "liao lie lin ling liu lo long lou lu luan lun luo lv lue ma mai man mang mao me mei "
    "men meng mi mian miao mie min ming miu mo mou mu na nai nanang nao ne nei nen neng "
    "ni nian niang niao nie nin ning niu nong nou nu nuan nuo nv nue o ou pa pai pan pang "
    "pao pei pen peng pi pian piao pie pin ping po pou pu qi qian qiang qiao qie qin qing "
    "qiong qiu qu quan que qun ran rang rao re ren reng ri rong rou ru rua ruan rui run "
    "ruo sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng shi "
    "shou shu shua shuai shuan shuang shui shun shuo si song sou su suan sui sun suo ta "
    "tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo wa wai "
    "wan wang wei wen weng wo wu xi xia xian xiang xiao xie xin xing xiong xiu xu xuan "
    "xue xun ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun za zai zan zang "
    "zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhen zheng zhi zhong zhou zhu zhua "
    "zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo".split()
)
# 修正上面笔误（nanang → nan/nang）
SYLLABLES.discard("nanang")
SYLLABLES.update(["nan", "nang"])

def strip_tone(s: str) -> str:
    # 预组合 ü 变体 → v
    s = s.replace("ǖ", "v").replace("ǘ", "v").replace("ǚ", "v").replace("ǜ", "v").replace("ü", "v")
    # NFD 去组合附加符（声调）
    s = unicodedata.normalize("NFD", s)
    out = []
    for ch in s:
        if unicodedata.combining(ch) == 0:
            out.append(ch)
    r = "".join(out).lower().replace("û", "v").replace("v", "v")
    return r.strip()

# 1) 解析词→拼音
phrase_py = {}   # 词 -> [音节串 list]（多读音保留首个）
char_py = {}     # 单字 -> 音节（多音字保留全部，用于合成兜底）
with open(PINYIN_FILE, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        w, py = line.split(":", 1)
        w = w.strip()
        pys = [strip_tone(x) for x in py.split()]
        if not w or any(not p for p in pys):
            continue
        if len(w) == 1:
            for p in pys:
                if p in SYLLABLES:
                    char_py.setdefault(w, []).append(p)
            continue
        if any(p not in SYLLABLES for p in pys):
            continue
        if w not in phrase_py:
            phrase_py[w] = pys

# 1b) 单字拼音（mozillazg/pinyin-data，多音字全保留）
with open(CHAR_FILE, encoding="utf-8") as f:
    for line in f:
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        cp, pys = line.split(":", 1)
        try:
            ch = chr(int(cp.strip().replace("U+", ""), 16))
        except ValueError:
            continue
        for p in (strip_tone(x) for x in pys.split(",")):
            if p in SYLLABLES:
                char_py.setdefault(ch, []).append(p)


# 2) 解析 jieba 词频（纯汉字、长度 1..6）
def is_hanzi(w):
    return all("\u4e00" <= c <= "\u9fff" for c in w)

freq = {}
with open(JIEBA_FILE, encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split(" ")
        if len(parts) < 2:
            continue
        w = parts[0]
        if not w or not is_hanzi(w) or len(w) > 6:
            continue
        try:
            fr = int(parts[1])
        except ValueError:
            continue
        freq[w] = max(freq.get(w, 0), fr)

# 3) 合成词典：jieba 词表（拼音优先取 phrase_py，缺则单字合成）
buckets = defaultdict(list)   # key -> [(word, freq)]
def add(word, fr, pys):
    if not pys or any(p not in SYLLABLES for p in pys):
        return
    key = "".join(pys)
    if not key:
        return
    buckets[key].append((word, fr))

missing = 0
for w, fr in freq.items():
    if w in phrase_py:
        add(w, fr, phrase_py[w])
    elif len(w) == 1 and w in char_py:
        # 单字取词频最高音节（首个）也全音节注册
        for p in set(char_py[w]):
            add(w, fr, [p])
    else:
        pys = []
        ok = True
        for c in w:
            ps = char_py.get(c)
            if not ps:
                ok = False
                break
            pys.append(ps[0])
        if ok:
            add(w, fr, pys)
        else:
            missing += 1

# 补 phrase-pinyin 独有常用词（jieba 没有但有拼音且长度≤4）：给默认低词频
DEFAULT_FR = 500
for w, pys in phrase_py.items():
    if len(w) <= 4 and w not in freq:
        add(w, DEFAULT_FR, pys)

# 3b) 影视/搜索领域补充词表（jieba 未收录或不常用，给高词频保证靠前）
DOMAIN_VOCAB = [
    "科幻片", "动作片", "爱情片", "喜剧片", "恐怖片", "动画片", "纪录片", "悬疑片", "犯罪片",
    "战争片", "灾难片", "奇幻片", "冒险片", "剧情片", "武侠片", "科幻电影", "动作电影",
    "爱情电影", "喜剧电影", "恐怖电影", "电视剧", "电视剧集", "国产剧", "港剧", "台剧",
    "美剧", "英剧", "日剧", "韩剧", "泰剧", "综艺", "动漫", "短剧", "微短剧", "网剧",
    "好莱坞", "漫威", "迪士尼", "宝莱坞", "贺岁片", "贺岁档", "春节档", "暑期档",
    "仙侠", "玄幻", "修仙", "宫斗", "宅斗", "甜宠", "虐恋", "霸总", "霸道总裁",
    "谍战", "抗战", "解放", "剿匪", "刑侦", "缉毒", "法医", "悬疑", "推理", "烧脑",
    "穿越", "重生", "逆袭", "复仇", "赘婿", "战神", "兵王", "神医", "农门", "种田",
    "奥特曼", "变形金刚", "蜘蛛侠", "蝙蝠侠", "钢铁侠", "美国队长", "复仇者联盟",
    "功夫", "武打", "枪战", "飙车", "科幻", "灾难", "冒险", "励志", "青春", "校园",
    "偶像", "家庭", "伦理", "古装", "民国", "武侠剧", "历史剧", "传记", "音乐剧",
    "动画片儿", "小人书", "连续剧", "电视连续剧", "午夜场", "票房", "影评", "片花",
    "预告片", "主题曲", "插曲", "配音", "字幕", "国语", "粤语", "中文字幕",
    "高清", "蓝光", "全集中文", "完整版", "未删减", "免费观看", "在线观看", "立即播放",
    "足球", "篮球", "世界杯", "欧洲杯", "亚洲杯", "英超", "西甲", "意甲", "德甲", "法甲",
    "欧冠", "欧联", "联赛", "总决赛", "半决赛", "决赛", "集锦", "进球", "红牌", "黄牌",
]
for w in DOMAIN_VOCAB:
    if w in phrase_py:
        add(w, 800000, phrase_py[w])
    else:
        pys = []
        ok = True
        for c in w:
            ps = char_py.get(c)
            if not ps:
                ok = False
                break
            pys.append(ps[0])
        if ok:
            add(w, 800000, pys)

# 4) 输出：key 排序；桶内按词频降序 + 词长升序（同频短词优先），cap 20
lines = []
for key in sorted(buckets):
    items = buckets[key]
    # 词长 1-2 的词在长 key 里意义不大（前缀继续型），但保留排序即可
    items.sort(key=lambda t: (-t[1], len(t[0]), t[0]))
    words = [w for w, _ in items[:20]]
    dedup = []
    seen = set()
    for w in words:
        if w not in seen:
            seen.add(w)
            dedup.append(w)
    lines.append(key + ":" + ",".join(dedup))

with open(OUT_RAW, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

with gzip.GzipFile(OUT_GZ, "wb", mtime=0) as f:
    f.write(("\n".join(lines)).encode("utf-8"))

print("keys:", len(lines))
print("jieba words:", len(freq), "pinyin phrases:", len(phrase_py), "missing pinyin:", missing)
print("sample:", lines[:3])
import os
print("gz size:", os.path.getsize(OUT_GZ))
