"""
爬虫用到的通用工具:薪资文本解析、字段清洗等。
这些函数是纯函数,单独拎出来方便写单元测试,论文里"数据清洗"环节也讲得清。
"""
import re
from typing import Optional, Tuple


# 法定月计薪天数(用于把"元/天"日薪折算成月薪)。
# 国家规定月计薪天数 = (365 - 104 双休) / 12 ≈ 21.75 天。
WORK_DAYS_PER_MONTH = 21.75


def _num_to_qian(num: float, unit: str) -> float:
    """把单个数字按它自己的单位换算成 千元。unit 是紧跟在数字后的字符。"""
    if "万" in unit or "w" in unit.lower():
        return num * 10.0   # 万 -> 千
    # K / 千 / 无单位,都按千计
    return num


def parse_salary(text: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    把薪资文本解析成 (最低, 最高, 平均),单位统一为 千元/月。

    三种计薪周期都要归一到"千元/月",否则统计和模型会被严重污染:
      - 月薪(默认):  "15-25K" / "8千-1.2万" / "1.5-3万"(万即万元/月)
      - 年薪(带/年): "30-60万/年" 要 ÷12 才是月薪,否则 30万被当成 30万/月
      - 日薪(带/天): "800元/天" 要 ×21.75 计薪日,否则 800 被当成 800千/月

    关键点:月/年薪里每个数字带自己的单位分别换算,才能正确处理"8千-1.2万"
    这类混合单位(低位是千、高位是万)的情况。

    支持常见格式:
        "15-25K"        -> (15, 25, 20)
        "15-25K·13薪"   -> 折算 13 薪 -> (16.25, 27.08, 21.66)
        "8千-1.2万"     -> (8, 12, 10)
        "1.5-3万"       -> (15, 30, 22.5)
        "30-60万/年"    -> 年薪÷12 -> (25, 50, 37.5)
        "800元/天"      -> 日薪×21.75 -> (17.4, 17.4, 17.4)
        "20K以上"       -> (20, None, 20)
        "面议"/None     -> (None, None, None)
    """
    if not text:
        return None, None, None

    t = text.strip().replace(" ", "")

    # 先定计薪周期(决定最后怎么折算到"千元/月")。
    # 日薪/年薪靠"/天""/年"这类后缀识别;都没有就按月薪处理。
    if "/天" in t or "/日" in t:
        period = "day"
    elif "/年" in t:
        period = "year"
    else:
        period = "month"

    # 提取 "·N薪" 里的薪资月数,默认 12。只有月薪才有"多发几个月"的说法。
    months = 12
    m_months = re.search(r"[·xX*,，/、](\d{1,2})薪", t)
    if m_months:
        months = int(m_months.group(1))

    # 抓出"数字 + 紧跟的单位字符"。单位可能是 K/k/千/万/w,也可能为空。
    # 例:"8千-1.2万" -> [("8","千"), ("1.2","万")]
    pairs = re.findall(r"(\d+\.?\d*)\s*([Kk千万wW]?)", t)
    # findall 会带出空匹配,过滤掉数字为空的项
    pairs = [(n, u) for n, u in pairs if n]
    if not pairs:
        return None, None, None

    if period == "day":
        # 日薪:数字是"元/天",按计薪天数折算成千元/月(元×天数÷1000)。
        nums = [float(n) for n, _ in pairs[:2]]
        vals = [round(x * WORK_DAYS_PER_MONTH / 1000.0, 2) for x in nums]
    else:
        # 月薪/年薪:数字带 K/千/万 单位,先统一换算成"千元"。
        # 若整串只出现"万"这一种单位、但某些数字后没写单位
        # (如 "1.5-3万" 里 1.5 后面没单位),用串里出现过的单位补齐。
        trailing_unit = ""
        if "万" in t:
            trailing_unit = "万"
        elif "K" in t or "k" in t or "千" in t:
            trailing_unit = "K"

        vals = []
        for n, u in pairs[:2]:
            unit = u if u else trailing_unit
            vals.append(_num_to_qian(float(n), unit))

        if period == "year":
            # 年薪总额(千元)平摊到 12 个月,才是可比的月薪。
            vals = [round(x / 12.0, 2) for x in vals]

    if len(vals) == 1:
        lo = hi = vals[0]
    else:
        lo, hi = vals[0], vals[1]

    # 按 N 薪折算回等效月薪(N薪意味着年终多发,平摊到12个月)。仅月薪适用。
    if period == "month":
        factor = months / 12.0
        lo = round(lo * factor, 2)
        hi = round(hi * factor, 2)

    avg = round((lo + hi) / 2, 2)

    # "20K以上"这种只有一个数,hi 置空但 avg 用该值
    if len(vals) == 1 and ("以上" in t or "+" in t):
        return lo, None, lo

    return round(lo, 2), round(hi, 2), avg


def clean_education(text: Optional[str]) -> Optional[str]:
    """把学历归一化成固定几档,便于统计。"""
    if not text:
        return None
    t = text.strip()
    mapping = [
        ("博士", "博士"),
        ("EMBA", "硕士"),
        ("MBA", "硕士"),
        ("硕士", "硕士"),
        ("研究生", "硕士"),
        ("本科", "本科"),
        ("大专", "大专"),
        ("专科", "大专"),
        ("高中", "高中及以下"),
        ("中专", "高中及以下"),
        ("初中", "高中及以下"),
    ]
    for kw, norm in mapping:
        if kw in t:
            return norm
    return "不限"


def clean_experience(text: Optional[str]) -> Optional[str]:
    """
    把经验要求归一化成固定几档:应届/不限 · 1年以下 · 1-3年 · 3-5年 · 5-10年 · 10年以上。

    ⚠️ 关键:原始文本大量是区间("1-3年")或下界("3年及以上")或上界("5年以下"),
    绝不能只取"第一个数字"当年限——那会把"1-3年"错判成"1年以下"(取到 1),
    把"3年及以上"错判成"1-3年"。此前的实现正是这个 off-by-one,导致约 1.5 万条
    真实的"1-3年"被误标进"1年以下",严重污染经验维度。

    归档口径:
      - 区间 "a-b年"       -> 取下界 a(该岗最低要求 a 年),按"含 a 的桶"入档
      - "N年以上/及以上"    -> 取 N,按"含 N 的桶"入档
      - 单值 "N年"         -> 取 N,按"含 N 的桶"入档
      - "N年以下"          -> 上限语义(招 N 年以内的人,偏初级),按"上界为 N 的桶"入档,
                             即 3年以下→1-3年、5年以下→3-5年、10年以下→5-10年
    "含 y 的桶":y<1→1年以下,1<=y<3→1-3年,3<=y<5→3-5年,5<=y<10→5-10年,y>=10→10年以上。
    """
    if not text:
        return None
    t = text.strip()
    # 明确表述应届/无经验要求的,直接归"应届/不限"
    if any(k in t for k in ("应届", "在校", "经验不限", "无需经验", "不限")):
        return "应届/不限"
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if not nums:
        return "应届/不限"

    if "以下" in t:
        # 上限语义:N 是天花板,归到"上界为 N 的那个桶"(N<=1 即 1年以下)
        cap = nums[0]
        if cap <= 1:
            return "1年以下"
        if cap <= 3:
            return "1-3年"
        if cap <= 5:
            return "3-5年"
        if cap <= 10:
            return "5-10年"
        return "10年以上"

    # 区间取下界(最低要求年限);单值/以上取给定数值。按"含 y 的桶"入档。
    years = min(nums) if len(nums) > 1 else nums[0]
    if years < 1:
        return "1年以下"
    if years < 3:
        return "1-3年"
    if years < 5:
        return "3-5年"
    if years < 10:
        return "5-10年"
    return "10年以上"


def split_tags(text: Optional[str]) -> str:
    """把技能标签文本规整成逗号分隔的字符串。"""
    if not text:
        return ""
    parts = re.split(r"[,，、\s;；/|]+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    return ",".join(parts)


# 技能词库:规范名 -> 该技能的所有别名/写法(小写)。
# 从岗位标题里按别名匹配,命中后统一记为规范名,避免 "js"/"JS"/"JavaScript" 被算成三个。
# 论文里这属于"基于词典的关键词抽取",简单可靠、结果可解释。
SKILL_DICT = {
    "Python": ["python"],
    "Java": ["java"],
    "C++": ["c++"],
    "C#": ["c#", ".net", "asp.net"],
    "Go": ["golang", "go语言"],
    "PHP": ["php"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Vue": ["vue"],
    "React": ["react"],
    "Angular": ["angular"],
    "HTML/CSS": ["html", "css", "h5"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Spring": ["spring", "springboot", "spring boot", "springcloud"],
    "MySQL": ["mysql"],
    "Redis": ["redis"],
    "MongoDB": ["mongodb", "mongo"],
    "Oracle": ["oracle"],
    "SQL": ["sql"],
    "Linux": ["linux"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "分布式": ["分布式"],
    "微服务": ["微服务"],
    "大数据": ["大数据", "hadoop", "spark", "hive", "flink"],
    "机器学习": ["机器学习", "machine learning", "ml"],
    "深度学习": ["深度学习", "deep learning", "dl", "pytorch", "tensorflow"],
    "算法": ["算法"],
    "爬虫": ["爬虫", "spider", "scrapy"],
    "数据分析": ["数据分析", "数据挖掘"],
    "测试": ["测试", "自动化测试", "qa"],
    "运维": ["运维", "devops"],
    "前端": ["前端"],
    "后端": ["后端", "服务端"],
    "全栈": ["全栈"],
    "Android": ["android", "安卓"],
    "iOS": ["ios"],
}


def _alias_hit(alias: str, blob: str) -> bool:
    """
    判断别名是否命中文本 blob(已小写)。

    ⚠️ 纯英文短别名(ml/dl/ts/js/go/ios 等)必须用"词边界"匹配,否则会子串误伤:
    "ml" 是 "html" 的子串 → 任何含 HTML 的标题会被误标"机器学习";
    "dl" 命中 "middle","ts" 命中 "charts","js" 命中 "jsp" 等同理。
    对全 ASCII 字母的别名用前后非字母断言;含中文/符号(c++/.net/中文词)的别名保留子串匹配。
    """
    if alias.isascii() and alias.isalpha():
        # (?<![a-z])alias(?![a-z]):前后都不是英文字母才算独立词
        return re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", blob) is not None
    return alias in blob


def extract_skills(*texts: Optional[str]) -> str:
    """
    从一段或多段文本(通常是岗位标题)里抽取技能关键词,
    返回逗号分隔的规范技能名字符串(去重、保持词库顺序)。

    例:extract_skills("Python后端开发工程师") -> "Python,后端"
        extract_skills("高级Java(Spring) 工程师") -> "Java,Spring"
    """
    blob = " ".join(t for t in texts if t).lower()
    if not blob:
        return ""
    found = []
    for norm, aliases in SKILL_DICT.items():
        if any(_alias_hit(alias, blob) for alias in aliases):
            found.append(norm)
    return ",".join(found)


if __name__ == "__main__":
    # 快速自测薪资解析:覆盖月薪/年薪/日薪三种周期
    cases = [
        "15-25K", "15-25K·13薪", "8千-1.2万", "1.5-3万", "20K以上", "面议",
        "30-60万/年", "18-30万/年", "40-80万/年",   # 年薪:应 ÷12
        "800元/天", "200元/天", "500元/天",          # 日薪:应 ×21.75/1000
    ]
    for s in cases:
        print(f"{s:14s} -> {parse_salary(s)}")
