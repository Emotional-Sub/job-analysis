"""
公共清洗入库管道(与具体站点无关)。

设计说明
--------
原来 clean_and_save / _make_job_key 写在 spider_51job.py 里,但它们其实
只吃「一个 dict 列表」,跟是哪个站点无关。要接入第二个数据源(猎聘)时,
把这段公共逻辑抽出来共用,各站点爬虫只负责「把页面解析成统一结构的 dict」,
清洗和入库都走这里。这样加新站点不用复制一遍入库代码,也保证各源清洗口径一致。

各站点爬虫产出的 raw dict 约定字段(缺的给 None 即可):
    source          数据来源站点,如 "51job" / "liepin"
    job_key         站点内岗位唯一标识(官方 id 最佳,没有就用 url)
    title           岗位名称
    company         公司名称
    city            城市
    industry        行业(可选)
    salary_text     薪资原始文本,如 "15-25K·13薪"
    education_text  学历要求原文
    experience_text 经验要求原文
    tags_text       技能标签文本(逗号分隔)
    keyword         搜索关键词
    url             详情页链接
"""
import hashlib
from typing import List, Dict

from app.db.session import get_session
from app.db.models import Job
from app.spider.utils import (
    parse_salary,
    clean_education,
    clean_experience,
    split_tags,
)


# job_key 字段在库里是 String(128),超过就会 "Data too long" 报错。
# 任何来源的 key 超过这个长度都退化成定长哈希,既不撑爆字段、又保持唯一。
JOB_KEY_MAX = 128


def make_job_key(raw: Dict) -> str:
    """
    生成站点内岗位唯一标识,用于去重。
    优先用站点官方岗位 id(最稳定);没有就退而用详情页 url;
    再没有就用 标题+公司+城市 拼哈希。

    最后统一做一道长度兜底:任何超过 JOB_KEY_MAX 的 key(比如带一长串
    查询参数的详情页 url)都换成它自身的 md5 哈希,避免超出字段长度。
    """
    if raw.get("job_key"):
        key = str(raw["job_key"])
    elif raw.get("url"):
        key = str(raw["url"])
    else:
        base = f"{raw.get('title')}|{raw.get('company')}|{raw.get('city')}"
        key = "h" + hashlib.md5(base.encode("utf-8")).hexdigest()

    if len(key) > JOB_KEY_MAX:
        key = "h" + hashlib.md5(key.encode("utf-8")).hexdigest()
    return key


def clean_and_save(raw_list: List[Dict]) -> int:
    """把原始卡片列表清洗后写入数据库,返回新增条数。

    用 (source, job_key) 去重:同一个岗位只存一次,重爬不会重复入库。
    """
    session = get_session()
    inserted = 0
    try:
        for raw in raw_list:
            source = raw.get("source", "unknown")
            job_key = make_job_key(raw)

            exists = (
                session.query(Job)
                .filter_by(source=source, job_key=job_key)
                .first()
            )
            if exists:
                continue

            lo, hi, avg = parse_salary(raw.get("salary_text"))
            job = Job(
                source=source,
                job_key=job_key,
                title=raw.get("title"),
                company=raw.get("company"),
                city=raw.get("city"),
                industry=raw.get("industry"),
                salary_text=raw.get("salary_text"),
                salary_min=lo,
                salary_max=hi,
                salary_avg=avg,
                education=clean_education(raw.get("education_text")),
                experience=clean_experience(raw.get("experience_text")),
                tags=split_tags(raw.get("tags_text")),
                keyword=raw.get("keyword"),
            )
            session.add(job)
            inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return inserted
