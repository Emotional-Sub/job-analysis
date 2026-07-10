# -*- coding: utf-8 -*-
"""
一次性重清洗脚本:用修正后的清洗函数,从 raw_job 的原始字段重建 job 表的
experience / education / tags 三个派生字段(不重抓,原始文本都在 raw_job)。

为什么需要
----------
代码审查发现两个清洗 bug,已在 app/spider/utils.py 修正,但**存量 job 表数据
是用旧逻辑清洗的**,必须重跑一遍才生效:
  1. clean_experience 旧实现只取第一个数字,把区间"1-3年"错判成"1年以下"、
     "3年及以上"错判成"1-3年" —— 约 1.5 万条经验档系统性下移一级。
  2. extract_skills 旧实现用子串匹配,"ml"命中"html" → 含 HTML 的岗位被误标
     "机器学习"(全库约 10 条误标)。
  3. clean_education 旧实现漏了 MBA/EMBA/初中(影响极小,一并修)。

数据来源
--------
  - job.experience = clean_experience(raw_job.experience)   # raw_job 存原始经验文本
  - job.education  = clean_education(raw_job.education)      # raw_job 存原始学历文本
  - job.tags       = extract_skills(raw_job.title)          # tags 本就是从标题抽取
    (核实过:两源 raw_job.tags 都等于 extract_skills(title),非站点原始标签,
     故可安全用新代码从标题重抽;同时同步更新 raw_job.tags 保持两表一致。)

用法(默认只预览,加 --apply 才真正写库):
    venv/Scripts/python.exe scripts/reclean_from_raw.py            # 预览各字段会改多少
    venv/Scripts/python.exe scripts/reclean_from_raw.py --apply    # 确认后执行
"""
import os
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job, RawJob
from app.spider.utils import clean_experience, clean_education, extract_skills


def main(apply: bool) -> None:
    session = get_session()
    try:
        # 建 (source, job_key) -> raw 原始字段 的映射
        raw_map = {}
        for r in session.query(RawJob).all():
            raw_map[(r.source, r.job_key)] = r

        jobs = session.query(Job).all()
        exp_changed = edu_changed = tags_changed = 0
        exp_before, exp_after = Counter(), Counter()

        for j in jobs:
            raw = raw_map.get((j.source, j.job_key))
            if raw is None:
                continue  # 理论上不会发生(两表已对齐)

            new_exp = clean_experience(raw.experience)
            new_edu = clean_education(raw.education)
            new_tags = extract_skills(raw.title)

            exp_before[j.experience] += 1
            exp_after[new_exp] += 1
            if j.experience != new_exp:
                exp_changed += 1
            if j.education != new_edu:
                edu_changed += 1
            if (j.tags or "") != new_tags:
                tags_changed += 1

            if apply:
                j.experience = new_exp
                j.education = new_edu
                j.tags = new_tags
                raw.tags = new_tags  # 同步 raw_job.tags,保持两表 tags 一致

        print(f"job 总数: {len(jobs)}")
        print(f"experience 将变更: {exp_changed} 条")
        print(f"education  将变更: {edu_changed} 条")
        print(f"tags       将变更: {tags_changed} 条")

        order = ["应届/不限", "1年以下", "1-3年", "3-5年", "5-10年", "10年以上", None]
        print("\n经验分布 变更前 -> 变更后:")
        print(f"  {'档位':10}{'变更前':>10}{'变更后':>10}")
        for k in order:
            print(f"  {str(k):10}{exp_before.get(k, 0):>10}{exp_after.get(k, 0):>10}")

        if not apply:
            print("\n[预览模式] 未写库。确认无误后加 --apply 真正重清洗:")
            print("    venv/Scripts/python.exe scripts/reclean_from_raw.py --apply")
            return

        session.commit()
        print("\n[已执行] job 的 experience/education/tags 已按修正逻辑重建,raw_job.tags 已同步。")
        print("提示:数据已变,请重跑 train_model.py、salary_inference.py、skill_analysis.py。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
