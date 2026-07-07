"""
一次性回填脚本:用 job 表的现有数据补齐 raw_job 原始表。

背景
----
raw_job(原始表)与 job(分析表)是"采集/分析解耦"的双表设计,但早期爬虫
只写了 job 表,raw_job 一直是空的。pipeline 现已改为双表落地,新抓的数据
会同时进两张表;本脚本把「存量」job 记录回填进 raw_job,让双表设计名副其实、
可供演示与回溯。

说明
----
job 表保留了 salary_text(原始薪资文本)、title、company、city、keyword 等
字段,足以重建 raw_job 的主要内容。清洗才产生的字段(如归一化学历)在 raw_job
里按其语义留原文/留空。已存在的 (source, job_key) 跳过,可重复运行。

用法:venv/Scripts/python.exe backfill_raw_job.py
"""
from app.db.session import get_session
from app.db.models import Job, RawJob


def main() -> None:
    session = get_session()
    try:
        jobs = session.query(Job).all()
        existing = {
            (s, k)
            for s, k in session.query(RawJob.source, RawJob.job_key).all()
        }
        added = 0
        for j in jobs:
            if (j.source, j.job_key) in existing:
                continue
            session.add(RawJob(
                source=j.source,
                job_key=j.job_key,
                title=j.title,
                salary_text=j.salary_text,
                city=j.city,
                experience=j.experience,   # job 里是归一化后的,作原文占位
                education=j.education,
                company=j.company,
                industry=j.industry,
                tags=j.tags,
                keyword=j.keyword,
                crawled_at=j.crawled_at,
            ))
            added += 1
        session.commit()
        total = session.query(RawJob).count()
        print(f"回填完成:新增 {added} 条,raw_job 现有 {total} 条(job 表 {len(jobs)} 条)")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
