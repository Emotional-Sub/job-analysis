"""
爬虫用到的通用工具:薪资文本解析、字段清洗等。
这些函数是纯函数,单独拎出来方便写单元测试,论文里"数据清洗"环节也讲得清。
"""
import re
from typing import Optional, Tuple


def _num_to_qian(num: float, unit: str) -> float:
    """把单个数字按它自己的单位换算成 千元/月。unit 是紧跟在数字后的字符。"""
    if "万" in unit or "w" in unit.lower():
        return num * 10.0   # 万 -> 千
    # K / 千 / 无单位,都按千计
    return num


def parse_salary(text: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    把薪资文本解析成 (最低, 最高, 平均),单位统一为 千元/月。

    关键点:每个数字带自己的单位分别换算,才能正确处理"8千-1.2万"这类
    混合单位(低位是千、高位是万)的情况。

    支持常见格式:
        "15-25K"        -> (15, 25, 20)
        "15-25K·13薪"   -> 折算 13 薪 -> (16.25, 27.08, 21.66)
        "8千-1.2万"     -> (8, 12, 10)
        "1.5-3万"       -> (15, 30, 22.5)
        "20K以上"       -> (20, None, 20)
        "面议"/None     -> (None, None, None)
    """
    if not text:
        return None, None, None

    t = text.strip().replace(" ", "")

    # 提取 "·N薪" 里的薪资月数,默认 12
    months = 12
    m_months = re.search(r"[·xX*](\d{1,2})薪", t)
    if m_months:
        months = int(m_months.group(1))

    # 抓出"数字 + 紧跟的单位字符"。单位可能是 K/k/千/万/w,也可能为空。
    # 例:"8千-1.2万" -> [("8","千"), ("1.2","万")]
    pairs = re.findall(r"(\d+\.?\d*)\s*([Kk千万wW]?)", t)
    # findall 会带出空匹配,过滤掉数字为空的项
    pairs = [(n, u) for n, u in pairs if n]
    if not pairs:
        return None, None, None

    # 若整串里只出现了"万"这一种单位、但某些数字后没写单位
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

    if len(vals) == 1:
        lo = hi = vals[0]
    else:
        lo, hi = vals[0], vals[1]

    # 按 N 薪折算回等效月薪(N薪意味着年终多发,平摊到12个月)
    factor = months / 12.0
    lo = round(lo * factor, 2)
    hi = round(hi * factor, 2)
    avg = round((lo + hi) / 2, 2)

    # "20K以上"这种只有一个数,hi 置空但 avg 用该值
    if len(vals) == 1 and ("以上" in t or "+" in t):
        return lo, None, lo

    return lo, hi, avg


def clean_education(text: Optional[str]) -> Optional[str]:
    """把学历归一化成固定几档,便于统计。"""
    if not text:
        return None
    t = text.strip()
    mapping = [
        ("博士", "博士"),
        ("硕士", "硕士"),
        ("研究生", "硕士"),
        ("本科", "本科"),
        ("大专", "大专"),
        ("专科", "大专"),
        ("高中", "高中及以下"),
        ("中专", "高中及以下"),
    ]
    for kw, norm in mapping:
        if kw in t:
            return norm
    return "不限"


def clean_experience(text: Optional[str]) -> Optional[str]:
    """把经验要求归一化成固定几档。"""
    if not text:
        return None
    t = text.strip()
    if "应届" in t or "在校" in t or "经验不限" in t or "不限" in t:
        return "应届/不限"
    m = re.search(r"(\d+)", t)
    if not m:
        return "应届/不限"
    years = int(m.group(1))
    if years <= 1:
        return "1年以下"
    if years <= 3:
        return "1-3年"
    if years <= 5:
        return "3-5年"
    if years <= 10:
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
        if any(alias in blob for alias in aliases):
            found.append(norm)
    return ",".join(found)


if __name__ == "__main__":
    # 快速自测薪资解析
    for s in ["15-25K", "15-25K·13薪", "8千-1.2万", "1.5-3万", "20K以上", "面议"]:
        print(f"{s:14s} -> {parse_salary(s)}")
