"""
一次性修复脚本:用修正后的 parse_salary 重算数据库里已有岗位的薪资。

背景:早期版本的 parse_salary 没处理"X万/年"(年薪)、"X元/天"(日薪)等格式,
把年薪当月薪算,导致出现 300K~800K 的天价异常值,污染了"各城市平均薪资"统计。
现已修正 parse_salary,本脚本把库里所有记录按新逻辑重算一遍,免得重新爬取。

这是**破坏性批量改写**,和清理脚本一样默认只预览,加 --apply 才真正写库:
    venv/Scripts/python.exe scripts/fix_salary.py            # 预览会改多少、若干样例
    venv/Scripts/python.exe scripts/fix_salary.py --apply    # 确认后执行

(只改 job 表的 salary_*;raw_job 只存 salary_text 原文、不存解析结果,无需同步。)
"""
import os
import sys

# 终端 GBK,统一 stdout 为 UTF-8 避免特殊字符崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 脚本挪进 scripts/ 后,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job
from app.spider.utils import parse_salary


def main(apply: bool) -> None:
    session = get_session()
    try:
        jobs = session.query(Job).all()
        total = len(jobs)
        changed = 0
        cleared = 0  # 新逻辑判定为无效(如时薪)而清空的
        samples = []  # 收集若干 before->after 供预览核对
        for job in jobs:
            lo, hi, avg = parse_salary(job.salary_text)
            if (job.salary_min, job.salary_max, job.salary_avg) != (lo, hi, avg):
                changed += 1
                if len(samples) < 15:
                    samples.append(
                        (job.salary_text, job.salary_avg, avg)
                    )
            if avg is None and job.salary_avg is not None:
                cleared += 1
            if apply:
                job.salary_min = lo
                job.salary_max = hi
                job.salary_avg = avg

        print(f"共 {total} 条,将更新 {changed} 条(其中 {cleared} 条因无法解析被清空薪资)")
        if samples:
            print("\n变更样例(原文 | 旧avg -> 新avg):")
            for txt, old, new in samples:
                print(f"  {str(txt):18} {str(old):>8} -> {str(new)}")

        if not apply:
            print("\n[预览模式] 未写库。确认无误后加 --apply 真正重算:")
            print("    venv/Scripts/python.exe scripts/fix_salary.py --apply")
            return

        session.commit()
        print(f"\n[已执行] 已重算并写库。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
