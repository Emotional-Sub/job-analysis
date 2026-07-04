"""
数据统计查询层:从 job 表聚合出可视化需要的各类统计数据。

每个函数返回的都是可以直接喂给前端 ECharts 的 Python 结构
(list / dict),路由层再转成 JSON。把统计逻辑集中在这里,
路由只负责"取数据 -> 返回 JSON",职责清晰,论文里也好讲。
"""
from collections import Counter
from typing import List, Dict

from sqlalchemy import func

from app.db.session import get_session
from app.db.models import Job


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


def salary_by_city(top_n: int = 10) -> Dict:
    """各城市平均薪资 Top N,用于柱状图。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.city,
                func.avg(Job.salary_avg).label("avg_sal"),
            )
            .filter(Job.salary_avg.isnot(None), Job.city.isnot(None))
            .group_by(Job.city)
            .order_by(func.avg(Job.salary_avg).desc())
            .limit(top_n)
            .all()
        )
        return {
            "cities": [r.city for r in rows],
            "salaries": [round(float(r.avg_sal), 1) for r in rows],
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
