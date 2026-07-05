"""
数据统计查询层:从 job 表聚合出可视化需要的各类统计数据。

每个函数返回的都是可以直接喂给前端 ECharts 的 Python 结构
(list / dict),路由层再转成 JSON。把统计逻辑集中在这里,
路由只负责"取数据 -> 返回 JSON",职责清晰,论文里也好讲。
"""
from collections import Counter, defaultdict
from statistics import median
from typing import List, Dict

from sqlalchemy import func

from app import config
from app.db.session import get_session
from app.db.models import Job

# 只统计这些目标城市。51job 搜"苏州"会带出昆山/常熟/太仓等周边县市,
# 样本少、噪声大,排除掉,避免它们混进城市排名。
TARGET_CITIES = set(c.strip() for c in config.CITIES)


def get_overview() -> Dict:
    """顶部概览卡片:总岗位数、城市数、平均薪资、最高薪资。"""
    session = get_session()
    try:
        total = session.query(func.count(Job.id)).scalar() or 0
        city_count = (
            session.query(func.count(func.distinct(Job.city)))
            .filter(Job.city.isnot(None))
            .scalar()
            or 0
        )
        avg_salary = (
            session.query(func.avg(Job.salary_avg))
            .filter(Job.salary_avg.isnot(None))
            .scalar()
        )
        max_salary = (
            session.query(func.max(Job.salary_max))
            .filter(Job.salary_max.isnot(None))
            .scalar()
        )
        return {
            "total": int(total),
            "city_count": int(city_count),
            "avg_salary": round(float(avg_salary), 1) if avg_salary else 0,
            "max_salary": round(float(max_salary), 1) if max_salary else 0,
        }
    finally:
        session.close()


def salary_by_keyword() -> Dict:
    """各职位(关键词)的平均薪资,用于柱状图。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.keyword,
                func.avg(Job.salary_avg).label("avg_sal"),
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.salary_avg.isnot(None), Job.keyword.isnot(None))
            .group_by(Job.keyword)
            .order_by(func.avg(Job.salary_avg).desc())
            .all()
        )
        return {
            "keywords": [r.keyword for r in rows],
            "salaries": [round(float(r.avg_sal), 1) for r in rows],
            "counts": [int(r.cnt) for r in rows],
        }
    finally:
        session.close()


def jobs_by_city(top_n: int = 10) -> Dict:
    """各城市岗位数量 Top N,用于柱状图/地图。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.city,
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.city.isnot(None))
            .group_by(Job.city)
            .order_by(func.count(Job.id).desc())
            .limit(top_n)
            .all()
        )
        return {
            "cities": [r.city for r in rows],
            "counts": [int(r.cnt) for r in rows],
        }
    finally:
        session.close()


def salary_by_city(top_n: int = 10, min_samples: int = 20) -> Dict:
    """
    各城市薪资 Top N,用于柱状图。返回的是**中位数薪资**。

    两点数据可靠性处理:
    1. 只统计 config.CITIES 里的目标城市 —— 51job 搜"苏州"会带出昆山、常熟等
       周边县市,样本少、噪声大,不属于我们的分析对象,过滤掉。
    2. 用中位数而非平均数 —— 薪资分布右偏(少数高薪岗会把均值拉高),
       中位数更能代表"该城市的普遍薪资水平",是薪资统计的通行做法。

    只保留样本数 >= min_samples 的城市,样本太少不足以代表城市整体。
    """
    target_cities = set(c.strip() for c in config.CITIES)
    session = get_session()
    try:
        rows = (
            session.query(Job.city, Job.salary_avg)
            .filter(Job.salary_avg.isnot(None), Job.city.isnot(None))
            .all()
        )
        # 城市 -> [薪资, ...],只收目标城市
        bucket: Dict[str, List[float]] = defaultdict(list)
        for city, sal in rows:
            if city in target_cities:
                bucket[city].append(float(sal))

        # 算每个城市的薪资中位数,过滤样本不足的
        city_median = [
            (city, round(median(sals), 1))
            for city, sals in bucket.items()
            if len(sals) >= min_samples
        ]
        city_median.sort(key=lambda x: x[1], reverse=True)
        city_median = city_median[:top_n]

        return {
            "cities": [c for c, _ in city_median],
            "salaries": [s for _, s in city_median],
            "counts": [len(bucket[c]) for c, _ in city_median],
        }
    finally:
        session.close()


def education_distribution() -> List[Dict]:
    """学历要求分布,用于饼图。返回 [{name, value}, ...]。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.education,
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.education.isnot(None))
            .group_by(Job.education)
            .order_by(func.count(Job.id).desc())
            .all()
        )
        return [{"name": r.education, "value": int(r.cnt)} for r in rows]
    finally:
        session.close()


def experience_distribution() -> List[Dict]:
    """经验要求分布,用于饼图。返回 [{name, value}, ...]。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.experience,
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.experience.isnot(None))
            .group_by(Job.experience)
            .order_by(func.count(Job.id).desc())
            .all()
        )
        return [{"name": r.experience, "value": int(r.cnt)} for r in rows]
    finally:
        session.close()


def top_skills(top_n: int = 20) -> List[Dict]:
    """
    技能标签词频 Top N,用于词云/柱状图。
    tags 字段是逗号分隔的字符串,这里在 Python 里拆开统计。
    返回 [{name, value}, ...]。
    """
    session = get_session()
    try:
        rows = session.query(Job.tags).filter(Job.tags.isnot(None)).all()
        counter: Counter = Counter()
        for (tags,) in rows:
            if not tags:
                continue
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    counter[tag] += 1
        return [
            {"name": name, "value": cnt}
            for name, cnt in counter.most_common(top_n)
        ]
    finally:
        session.close()


def salary_by_skill(top_n: int = 15, min_samples: int = 5) -> Dict:
    """
    各技能对应岗位的薪资中位数 Top N,用于横向柱状图。

    tags 是逗号分隔的技能串,一个岗位可能含多个技能。这里把每个岗位的
    salary_avg 归到它包含的每个技能上,再取中位数(与城市图口径一致)。
    只保留样本数 >= min_samples 的技能,避免个别岗位把冷门技能顶上来。
    返回 {skills: [...], salaries: [...]},按薪资中位数降序。
    """
    session = get_session()
    try:
        rows = (
            session.query(Job.tags, Job.salary_avg)
            .filter(Job.tags.isnot(None), Job.salary_avg.isnot(None))
            .all()
        )
        # 技能 -> [薪资, 薪资, ...]
        bucket: Dict[str, List[float]] = {}
        for tags, sal in rows:
            if not tags:
                continue
            for tag in tags.split(","):
                tag = tag.strip()
                if tag:
                    bucket.setdefault(tag, []).append(float(sal))

        # 求每个技能的薪资中位数(与城市图口径一致,抗极值),过滤样本太少的
        stats_list = [
            (skill, round(median(sals), 1))
            for skill, sals in bucket.items()
            if len(sals) >= min_samples
        ]
        # 按薪资中位数降序,取前 top_n
        stats_list.sort(key=lambda x: x[1], reverse=True)
        stats_list = stats_list[:top_n]

        return {
            "skills": [s for s, _ in stats_list],
            "salaries": [sal for _, sal in stats_list],
        }
    finally:
        session.close()


def jobs_by_source() -> List[Dict]:
    """
    各数据源(站点)的岗位数量,用于饼图,直观体现"多源采集"。
    返回 [{name, value}, ...],按数量降序。
    """
    session = get_session()
    try:
        rows = (
            session.query(
                Job.source,
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.source.isnot(None))
            .group_by(Job.source)
            .order_by(func.count(Job.id).desc())
            .all()
        )
        return [{"name": r.source, "value": int(r.cnt)} for r in rows]
    finally:
        session.close()


# ==================== 多源对比分析 ====================
# 下面三个函数把「数据源」作为分组维度,横向对比不同招聘平台的差异。
# 这是接入猎聘后真正体现「多源采集」价值的地方 —— 不只是把两家数据堆一起,
# 而是能看出同一职位在不同平台的薪资/学历口径差异。


def salary_by_source() -> Dict:
    """
    各数据源的薪资中位数对比,用于柱状图。

    用中位数而非均值(与城市图口径一致,抗高薪离群值)。同时返回每个源的
    样本数,前端标注出来 —— 样本量差得多时,对比要谨慎解读。
    """
    session = get_session()
    try:
        rows = (
            session.query(Job.source, Job.salary_avg)
            .filter(Job.salary_avg.isnot(None), Job.source.isnot(None))
            .all()
        )
        bucket: Dict[str, List[float]] = defaultdict(list)
        for source, sal in rows:
            bucket[source].append(float(sal))

        items = [
            (src, round(median(sals), 1), len(sals))
            for src, sals in bucket.items()
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return {
            "sources": [s for s, _, _ in items],
            "salaries": [sal for _, sal, _ in items],
            "counts": [c for _, _, c in items],
        }
    finally:
        session.close()


def education_by_source() -> Dict:
    """
    各数据源的学历要求分布对比(占比%),用于分组柱状图。

    做成占比而非绝对数,消除两个源样本量悬殊的影响,更能看出学历要求结构差异。
    返回 {sources, educations, matrix},matrix[i][j] = 源 i 在学历 j 的占比%。
    """
    session = get_session()
    try:
        rows = (
            session.query(
                Job.source,
                Job.education,
                func.count(Job.id).label("cnt"),
            )
            .filter(Job.source.isnot(None), Job.education.isnot(None))
            .group_by(Job.source, Job.education)
            .all()
        )
        by_source: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        edu_set = set()
        for source, edu, cnt in rows:
            by_source[source][edu] = int(cnt)
            edu_set.add(edu)

        edu_order = ["博士", "硕士", "本科", "大专", "高中及以下", "不限"]
        educations = [e for e in edu_order if e in edu_set]
        educations += [e for e in edu_set if e not in edu_order]

        sources = list(by_source.keys())
        matrix = []
        for src in sources:
            total = sum(by_source[src].values()) or 1
            row = [round(by_source[src].get(e, 0) / total * 100, 1) for e in educations]
            matrix.append(row)

        return {"sources": sources, "educations": educations, "matrix": matrix}
    finally:
        session.close()


def salary_by_source_keyword() -> Dict:
    """
    各数据源 × 各职位 的平均薪资对比,用于分组柱状图。

    同一个职位在 51job 和猎聘的平均薪资并排对比,一眼看出平台差异。
    返回 {keywords, sources, matrix},matrix[i][j] = 源 i 在职位 j 的平均薪资。
    """
    session = get_session()
    try:
        rows = (
            session.query(
                Job.source,
                Job.keyword,
                func.avg(Job.salary_avg).label("avg_sal"),
            )
            .filter(
                Job.salary_avg.isnot(None),
                Job.source.isnot(None),
                Job.keyword.isnot(None),
            )
            .group_by(Job.source, Job.keyword)
            .all()
        )
        by_source: Dict[str, Dict[str, float]] = defaultdict(dict)
        kw_set = set()
        for source, kw, avg_sal in rows:
            by_source[source][kw] = round(float(avg_sal), 1)
            kw_set.add(kw)

        kw_order = [k.strip() for k in config.KEYWORDS]
        keywords = [k for k in kw_order if k in kw_set]
        keywords += [k for k in kw_set if k not in kw_order]

        sources = list(by_source.keys())
        matrix = []
        for src in sources:
            row = [by_source[src].get(k) for k in keywords]
            matrix.append(row)

        return {"keywords": keywords, "sources": sources, "matrix": matrix}
    finally:
        session.close()


# ==================== 地图可视化 ====================
# 城市经纬度表:ECharts 地图散点靠 [经度, 纬度] 定位。
# 省级地图 GeoJSON 里没有地级市(如苏州/无锡),所以不靠地名匹配,
# 直接用经纬度打点,最稳、不受 GeoJSON 城市名有无影响。
CITY_COORDS = {
    "北京": [116.41, 39.90], "上海": [121.47, 31.23], "广州": [113.26, 23.13],
    "深圳": [114.06, 22.55], "重庆": [106.55, 29.56], "天津": [117.20, 39.13],
    "杭州": [120.15, 30.28], "宁波": [121.55, 29.88], "成都": [104.07, 30.57],
    "南京": [118.80, 32.06], "苏州": [120.62, 31.32], "无锡": [120.30, 31.57],
    "武汉": [114.31, 30.52], "长沙": [112.94, 28.23], "郑州": [113.63, 34.75],
    "西安": [108.95, 34.27], "青岛": [120.38, 36.07], "济南": [117.00, 36.65],
    "福州": [119.30, 26.08], "合肥": [117.28, 31.86],
}


def city_geo_stats(min_samples: int = 5) -> List[Dict]:
    """
    地图散点数据:每个目标城市的岗位数 + 薪资中位数 + 经纬度。
    返回 [{name, value: [经度, 纬度, 岗位数], salary}, ...]。
    只保留有经纬度且样本数 >= min_samples 的城市。
    """
    session = get_session()
    try:
        rows = (
            session.query(Job.city, Job.salary_avg)
            .filter(Job.city.isnot(None))
            .all()
        )
        counts: Dict[str, int] = defaultdict(int)
        salaries: Dict[str, List[float]] = defaultdict(list)
        for city, sal in rows:
            if city not in CITY_COORDS:
                continue
            counts[city] += 1
            if sal is not None:
                salaries[city].append(float(sal))

        result = []
        for city, cnt in counts.items():
            if cnt < min_samples:
                continue
            lon, lat = CITY_COORDS[city]
            sal_list = salaries[city]
            med = round(median(sal_list), 1) if sal_list else None
            result.append({
                "name": city,
                "value": [lon, lat, cnt],
                "salary": med,
            })
        result.sort(key=lambda x: x["value"][2], reverse=True)
        return result
    finally:
        session.close()
