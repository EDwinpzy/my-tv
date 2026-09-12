"""球队 16:9 海报（TheSportsDB fanart 1280×720 实测；免费无 key）。

用法:
    from team_backdrop import team_backdrop_url
    url = team_backdrop_url("皇家马德里")   # 未命中返回 ""
"""
import json
import threading
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 中文队名 → TheSportsDB 英文名（搜索用下划线）。主流队覆盖直播数据常见球队。
TEAM_EN = {
    # 英超
    "曼城": "Manchester_City", "曼彻斯特城": "Manchester_City", "利物浦": "Liverpool",
    "阿森纳": "Arsenal", "曼联": "Manchester_United", "曼彻斯特联": "Manchester_United",
    "切尔西": "Chelsea", "热刺": "Tottenham", "托特纳姆热刺": "Tottenham",
    "纽卡斯尔联": "Newcastle", "阿斯顿维拉": "Aston_Villa", "布莱顿": "Brighton",
    "西汉姆联": "West_Ham", "埃弗顿": "Everton", "莱斯特城": "Leicester",
    "狼队": "Wolves", "水晶宫": "Crystal_Palace", "富勒姆": "Fulham",
    "布伦特福德": "Brentford", "伯恩茅斯": "Bournemouth", "诺丁汉森林": "Nottingham_Forest",
    # 西甲
    "皇家马德里": "Real_Madrid", "巴塞罗那": "Barcelona", "马德里竞技": "Atletico_Madrid",
    "塞维利亚": "Sevilla", "皇家社会": "Real_Sociedad", "毕尔巴鄂竞技": "Athletic_Bilbao",
    "比利亚雷亚尔": "Villarreal", "瓦伦西亚": "Valencia", "皇家贝蒂斯": "Real_Betis",
    "赫塔菲": "Getafe", "奥萨苏纳": "Osasuna", "塞尔塔": "Celta_Vigo", "马洛卡": "Mallorca",
    "阿拉维斯": "Alaves", "赫罗纳": "Girona", "拉斯帕尔马斯": "Las_Palmas",
    "巴列卡诺": "Rayo_Vallecano",
    # 意甲
    "国际米兰": "Inter_Milan", "AC米兰": "Milan", "尤文图斯": "Juventus",
    "那不勒斯": "Napoli", "罗马": "Roma", "拉齐奥": "Lazio", "亚特兰大": "Atalanta",
    "佛罗伦萨": "Fiorentina", "都灵": "Torino", "博洛尼亚": "Bologna",
    "乌迪内斯": "Udinese", "维罗纳": "Verona", "卡利亚里": "Cagliari",
    "热那亚": "Genoa", "恩波利": "Empoli", "莱切": "Lecce", "萨索洛": "Sassuolo",
    "帕尔马": "Parma", "蒙扎": "Monza", "科莫": "Como",
    # 德甲
    "拜仁慕尼黑": "Bayern_Munich", "多特蒙德": "Borussia_Dortmund",
    "勒沃库森": "Bayer_Leverkusen", "莱比锡红牛": "RB_Leipzig", "法兰克福": "Eintracht_Frankfurt",
    "沃尔夫斯堡": "Wolfsburg", "门兴格拉德巴赫": "Borussia_Monchengladbach",
    "斯图加特": "Stuttgart", "弗赖堡": "Freiburg", "霍芬海姆": "Hoffenheim",
    "美因茨": "Mainz", "奥格斯堡": "Augsburg", "云达不莱梅": "Werder_Bremen",
    "柏林联合": "Union_Berlin", "波鸿": "Bochum", "海登海姆": "Heidenheim",
    "圣保利": "St_Pauli", "基尔": "Holstein_Kiel",
    # 法甲
    "巴黎圣日耳曼": "PSG", "马赛": "Marseille", "里昂": "Lyon", "摩纳哥": "Monaco",
    "里尔": "Lille", "尼斯": "Nice", "朗斯": "Lens", "雷恩": "Rennes",
    "斯特拉斯堡": "Strasbourg", "南特": "Nantes", "图卢兹": "Toulouse", "欧塞尔": "Auxerre",
    # 葡超/荷甲/比甲/土超
    "本菲卡": "Benfica", "波尔图": "Porto", "里斯本竞技": "Sporting_Lisbon",
    "阿贾克斯": "Ajax", "埃因霍温": "PSV", "费耶诺德": "Feyenoord",
    "布鲁日": "Club_Brugge", "安德莱赫特": "Anderlecht", "根特": "Gent",
    "加拉塔萨雷": "Galatasaray", "费内巴切": "Fenerbahce", "贝西克塔斯": "Besiktas",
    "特拉布宗体育": "Trabzonspor",
    # 苏超/英冠/德乙/其他欧洲
    "凯尔特人": "Celtic", "流浪者": "Rangers",
    "利兹联": "Leeds", "南安普顿": "Southampton", "谢菲尔德联": "Sheffield_United",
    "桑德兰": "Sunderland", "米德尔斯堡": "Middlesbrough", "考文垂": "Coventry",
    "沃特福德": "Watford", "西布罗姆维奇": "West_Brom", "斯托克城": "Stoke_City",
    "伯明翰": "Birmingham", "布里斯托尔城": "Bristol_City", "诺维奇": "Norwich",
    "赫尔城": "Hull_City", "女王公园巡游者": "QPR", "普雷斯顿": "Preston",
    "卡迪夫城": "Cardiff", "斯旺西": "Swansea", "米尔沃尔": "Millwall",
    "布莱克本": "Blackburn", "德比郡": "Derby_County", "卢顿": "Luton",
    "凯泽斯劳滕": "Kaiserslautern", "汉诺威96": "Hannover", "柏林赫塔": "Hertha_Berlin",
    "汉堡": "Hamburg", "纽伦堡": "Nuremberg", "菲尔特": "Greuther_Furth",
    "马格德堡": "Magdeburg", "科隆": "Cologne", "沙尔克04": "Schalke",
    # 中超/中甲/中乙
    "上海海港": "Shanghai_Port", "上海申花": "Shanghai_Shenhua", "北京国安": "Beijing_Guoan",
    "山东泰山": "Shandong_Taishan", "成都蓉城": "Chengdu_Rongcheng", "浙江队": "Zhejiang",
    "天津津门虎": "Tianjin_Jinmen_Tiger", "武汉三镇": "Wuhan_Three_Towns",
    "河南队": "Henan", "长春亚泰": "Changchun_Yatai", "青岛海牛": "Qingdao_Hainiu",
    "深圳新鹏城": "Shenzhen_New_Pengcheng", "云南玉昆": "Yunnan_Yukun",
    "大连英博": "Dalian_Yingbo", "梅州客家": "Meizhou_Hakka", "辽宁铁人": "Liaoning_Tieren",
    # 日本/韩国
    "鹿岛鹿角": "Kashima_Antlers", "浦和红钻": "Urawa_Red_Diamonds", "川崎前锋": "Kawasaki_Frontale",
    "横滨水手": "Yokohama_F_Marinos", "神户胜利船": "Vissel_Kobe", "大阪钢巴": "Gamba_Osaka",
    "大阪樱花": "Cerezo_Osaka", "名古屋鲸八": "Nagoya_Grampus", "广岛三箭": "Sanfrecce_Hiroshima",
    "福冈黄蜂": "Avispa_Fukuoka", "东京FC": "FC_Tokyo", "京都不死鸟": "Kyoto_Sanga",
    "町田泽维亚": "Machida_Zelvia", "清水鼓动": "Shimizu_S-Pulse",
    "蔚山HD": "Ulsan_HD", "全北现代": "Jeonbuk_Hyundai_Motors", "浦项制铁": "Pohang_Steelers",
    "首尔FC": "FC_Seoul", "FC首尔": "FC_Seoul", "水原三星": "Suwon_Samsung_Bluewings",
    "济州SK": "Jeju_United", "光州FC": "Gwangju_FC", "江原FC": "Gangwon_FC",
    "大田市民": "Daejeon_Hana_Citizen", "仁川联队": "Incheon_United", "金泉尚武": "Gimcheon_Sangmu",
    "大邱FC": "Daegu_FC", "全南天龙": "Jeonnam_Dragons", "安养FC": "FC_Anyang",
    # 南美/北美
    "博卡青年": "Boca_Juniors", "河床": "River_Plate", "帕尔梅拉斯": "Palmeiras",
    "弗拉门戈": "Flamengo", "弗鲁米嫩塞": "Fluminense", "科林蒂安": "Corinthians",
    "圣保罗": "Sao_Paulo", "桑托斯": "Santos", "格雷米奥": "Gremio",
    "迈阿密国际": "Inter_Miami", "洛杉矶FC": "Los_Angeles_FC", "洛杉矶银河": "LA_Galaxy",
    "纽约红牛": "New_York_Red_Bulls", "亚特兰大联": "Atlanta_United", "西雅图海湾人": "Seattle_Sounders",
    "蒙特利尔": "CF_Montreal", "多伦多FC": "Toronto_FC", "华盛顿联队": "DC_United",
    "堪萨斯城竞技": "Sporting_Kansas_City", "纳什威尔": "Nashville", "夏洛特FC": "Charlotte",
    "辛辛那提": "Cincinnati", "哥伦布机员": "Columbus_Crew", "奥兰多城": "Orlando_City",
    "新英格兰革命": "New_England_Revolution", "休斯敦迪纳摩": "Houston_Dynamo",
    "皇家盐湖城": "Real_Salt_Lake", "明尼苏达联": "Minnesota_United", "科罗拉多急流": "Colorado_Rapids",
    "圣何塞地震": "San_Jose_Earthquakes", "圣路易斯城": "St_Louis_City", "圣地亚哥": "San_Diego_FC",
    "波特兰伐木者": "Portland_Timbers", "芝加哥火焰": "Chicago_Fire", "费城联合": "Philadelphia_Union",
    # 国家队
    "中国": "China", "中国男足": "China", "日本": "Japan", "韩国": "South_Korea",
    "巴西": "Brazil", "阿根廷": "Argentina", "法国": "France", "德国": "Germany",
    "西班牙": "Spain", "意大利": "Italy", "英格兰": "England", "葡萄牙": "Portugal",
    "荷兰": "Netherlands", "比利时": "Belgium", "克罗地亚": "Croatia",
    "乌拉圭": "Uruguay", "哥伦比亚": "Colombia", "摩洛哥": "Morocco",
    "墨西哥": "Mexico", "美国": "USA", "泰国": "Thailand", "越南": "Vietnam",
    "马来西亚": "Malaysia", "新加坡": "Singapore", "印度尼西亚": "Indonesia",
    "澳大利亚": "Australia", "沙特阿拉伯": "Saudi_Arabia", "卡塔尔": "Qatar",
    # —— 主流俱乐部英文映射（队标/海报查询用）——
    "兹沃勒": "PEC_Zwolle", "前进之鹰": "Go_Ahead_Eagles", "沙佩科恩斯": "Chapecoense",
    "巴伊亚": "Bahia", "葡萄牙国民": "Nacional", "埃斯托里尔": "Estoril",
    "海伦芬": "Heerenveen", "桑坦德竞技": "Racing_Santander", "伊斯坦布巴萨克塞尔": "Basaksehir",
    "高卡尔利": "Kocaelispor", "阿罗卡": "Arouca", "摩里伦斯": "Moreirense",
    "西班牙人": "Espanyol", "萨尔米安杜": "Sarmiento", "埃于普体育": "Eyupspor",
    "阿美德": "Amedspor", "埃祖姆BB": "Erzurumspor", "瓦斯科达伽马": "Vasco_da_Gama",
    "布拉加": "Braga", "奥勒松": "Aalesund", "根特": "Gent", "格雷米奥": "Gremio",
    "汉诺威96": "Hannover_96", "沃尔夫斯堡": "Wolfsburg", "霍芬海姆": "Hoffenheim",
    "诺丁汉森林": "Nottingham_Forest", "沃特福德": "Watford", "南安普顿": "Southampton",
    "朗斯": "Lens", "科莫": "Como", "热那亚": "Genoa", "赫罗纳": "Girona",
    "沙尔克04": "Schalke_04", "阿贾克斯": "Ajax", "海伦芬": "Heerenveen",
    "特温特": "Twente", "费耶诺德": "Feyenoord", "埃因霍温": "PSV",
    "波尔图": "Porto", "本菲卡": "Benfica", "里斯本竞技": "Sporting_CP",
    "贝西克塔斯": "Besiktas", "加拉塔萨雷": "Galatasaray", "费内巴切": "Fenerbahce",
    "桑托斯": "Santos", "米内罗竞技": "Atletico_Mineiro", "弗拉门戈": "Flamengo",
    "博卡青年": "Boca_Juniors", "河床": "River_Plate", "帕尔梅拉斯": "Palmeiras",
    "利雅得胜利": "Al_Nassr", "利雅得新月": "Al_Hilal", "吉达联合": "Al_Ittihad",
    "迈阿密国际": "Inter_Miami", "洛杉矶FC": "LAFC", "纽约城": "New_York_City",
    "芝华士": "Chivas", "墨西哥美洲队": "Club_America", "蓝十字": "Cruz_Azul",
    "巴塞罗那": "Barcelona", "皇家马德里": "Real_Madrid", "马德里竞技": "Atletico_Madrid",
    "曼城": "Manchester_City", "阿森纳": "Arsenal", "利物浦": "Liverpool",
    "国际米兰": "Inter_Milan", "AC米兰": "AC_Milan", "尤文图斯": "Juventus",
    "巴黎圣日耳曼": "Paris_Saint-Germain", "拜仁慕尼黑": "Bayern_Munich", "多特蒙德": "Borussia_Dortmund",
    # —— 南美 / 美职 / 其他主流球队（TDB 已验证有真实队标）——
    "河床": "River_Plate", "弗拉门戈": "Flamengo", "科林蒂安": "Corinthians",
    "博塔弗戈": "Botafogo", "维多利亚": "Vitoria", "米拉索": "Mirassol",
    "阿根廷青年人": "Argentinos_Juniores", "罗萨里奥中央": "Rosario_Central",
    "西雅图海湾人": "Seattle_Sounders", "温哥华白浪": "Vancouver_Whitecaps",
    "巴拉卡斯中央队": "Barracas_Central", "科尔多瓦中央SDE": "Central_Cordoba",
    "科尔多瓦学院": "Instituto_Cordoba", "萨尔米安杜": "Sarmiento",
    "瓦斯科达伽马": "Vasco_da_Gama", "桑托斯": "Santos", "帕尔梅拉斯": "Palmeiras",
    "克鲁塞罗": "Cruzeiro", "格雷米奥": "Gremio", "巴西国际": "Internacional",
    "飓风队": "Huracan", "拉普拉塔大学生": "Estudiantes", "圣洛伦索": "San_Lorenzo",
    "利马切颜色": "Colo_Colo", "天主大学": "Universidad_Catolica",
    "瓜达拉哈拉": "Chivas", "美洲狮": "Pumas", "老虎大学": "Tigres",
    "蒙特雷": "Monterrey", "提华纳": "Tijuana", "蓝十字": "Cruz_Azul",
    "亚特兰大联": "Atlanta_United", "迈阿密国际": "Inter_Miami", "洛杉矶FC": "Los_Angeles_FC",
    "纽约城": "New_York_City", "芝加哥火焰": "Chicago_Fire", "波特兰伐木工": "Portland_Timbers",
    "费城联合": "Philadelphia_Union", "堪萨斯城竞技": "Sporting_Kansas_City",
    # —— 葡超 / 阿甲 / 土超 / 西乙 等主流联赛球队（TDB 已验证有真实队标）——
    "法马利康": "Famalicao", "马里迪莫": "Maritimo", "吉维森特": "Gil_Vicente",
    "阿根廷青年人": "Argentinos_Juniors", "萨姆松体育": "Samsunspor", "哥兹塔比": "Goztepe",
    "埃尔切": "Elche", "卡萨比亚": "Casa_Pia", "拉努斯": "Lanus",
    "防卫者": "Defensa_y_Justicia", "甘拿斯亚门多萨": "Gimnasia_Mendoza",
    "里奥夸尔托学生队": "Estudiantes_Rio_Cuarto", "博塔弗戈": "Botafogo",
    "葡萄牙国民": "Nacional", "埃斯托里尔": "Estoril", "摩里伦斯": "Moreirense",
    "阿罗卡": "Arouca", "海伦芬": "Heerenveen", "兹沃勒": "PEC_Zwolle",
    "前进之鹰": "Go_Ahead_Eagles", "兰德斯": "Randers", "锡尔克堡": "Silkeborg",
    "中日德兰": "Midtjylland", "哥本哈根": "Copenhagen", "布隆德比": "Brondby",
    "哥德堡": "IFK_Goteborg", "马尔默": "Malmo", "哈马比": "Hammarby",
    "索尔纳": "AIK", "尤尔加登": "Djurgarden", "卡尔马": "Kalmar",
    "博多格林特": "Bodo_Glimt", "莫尔德": "Molde", "布兰": "Brann",
    "奥勒松": "Aalesund", "瓦勒伦加": "Valerenga", "斯特罗姆加斯特": "Stromsgodset",
    "赫尔辛基": "HJK", "图尔库国际": "Inter_Turku", "埃尔维斯": "Ilves",
    "瓦斯特拉斯": "Vasteras", "韦纳穆": "Varnamo", "布洛马波卡纳": "Brommapojkarna",
    "天狼星": "Sirius", "哈尔姆斯塔德": "Halmstad", "北雪平": "Norrkoping",
    "米亚尔比": "Mjallby", "佐加顿斯": "Djurgarden", "赫根": "Hacken",
    # —— 2026-08-19 补：当前直播数据出现、此前缺映射的队（TDB 中文查询失败，需英文名）——
    "马拉加": "Malaga", "LASK林茨": "LASK", "开罗国民": "Al_Ahly",
    "墨尔本胜利": "Melbourne_Victory", "奥斯汀FC": "Austin_FC",
    "城南FC": "Seongnam_FC", "富川FC": "Bucheon_FC_1995", "釜山偶像": "Busan_IPark",
    "金浦市民": "Gimpo_FC", "蔚山市民": "Ulsan_Citizen", "忠南牙山": "Chungnam_Asan",
    "晋州市民": "Jinju_Citizen", "唐津市民": "Tangjin_Citizen",
    "圣塔菲联": "Union_Santa_Fe", "波特诺山丘": "Cerro_Porteno", "竞技俱乐部": "Racing_Club",
    "布拉干蒂诺RB": "Red_Bull_Bragantino", "普拉腾斯": "Platense",
    # TDB 搜索词实测：Al-Fateh 带连字符查不到、下划线才行；Taawoun 才能命中 Al-Taawoun
    "哈萨征服": "Al_Fateh", "布赖代合作": "Taawoun", "达马克": "Damac_FC",
    "阿尔乌拉": "Al-Ula", "坎斯大班": "Cairns_Taipans", "莱卡特老虎": "Leichhardt",
    "约旦": "Jordan", "中国台湾白队": "Chinese_Taipei", "中国台湾蓝队": "Chinese_Taipei",
}

_cache = {}
_lock = threading.Lock()


def team_backdrop_url(name):
    """球队 16:9 海报：TheSportsDB searchteams → strFanart1（1280×720 实测）。
    未命中返回空串（前端用队徽+渐变合成兜底）。结果按队名缓存。"""
    key = name.strip()
    if not key:
        return ""
    with _lock:
        if key in _cache:
            return _cache[key]
    en = TEAM_EN.get(key, key)
    url = ""
    try:
        q = urllib.parse.quote(en.replace(" ", "_"))
        req = urllib.request.Request(
            "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t=%s" % q,
            headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        t = (data.get("teams") or [{}])[0]
        url = t.get("strFanart1") or t.get("strFanart2") or t.get("strBanner") or ""
    except Exception:
        url = ""
    with _lock:
        _cache[key] = url
    return url
