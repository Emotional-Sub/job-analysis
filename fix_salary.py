"""
一次性修复脚本:用修正后的 parse_salary 重算数据库里已有岗位的薪资。

背景:早期版本的 parse_salary 没处理"X万/年"(年薪)、"X元/天"(日薪)等格式,
把年薪当月薪算,导致出现 300K~800K 的天价异常值,污染了"各城市平均薪资"统计。
现已修正 parse_salary,本脚本把库里所有记录按新逻辑重算一遍,免得重新爬取。

用法:venv/Scripts/python.exe fix_salary.py
"""
from app.db.session import get_session
from app.db.models import Job
from app.spider.utils import parse_salary


def main() -> None:
    session = get_session()
    try:
        jobs = session.query(Job).all()
        total = len(jobs)
        changed = 0
        cleared = 0  # 新逻辑判定为无效(如时薪)而清空的
        for job in jobs:
            lo, hi, avg = parse_salary(job.salary_text)
            # 记录是否有变化
            if (job.salary_min, job.salary_max, job.salary_avg) != (lo, hi, avg):
                changed += 1
            if avg is None and job.salary_avg is not None:
                cleared += 1
            job.salary_min = lo
            job.salary_max = hi
            job.salary_avg = avg
        session.commit()
        print(f"共 {total} 条,更新 {changed} 条(其中 {cleared} 条因无法解析被清空薪资)")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
