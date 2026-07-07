"""
一次性清理脚本:删除已入库的猎聘实习/兼职岗。

背景
----
早期版本的猎聘爬虫没有过滤实习岗,导致 814 条猎聘数据里混进了 354 条
实习/兼职岗(占 43%)。这些岗位薪资多为日薪(如 200元/天)或极低月薪,
把猎聘薪资中位数从正常水平(约 15K)砸到了 5.5K,严重污染:
  - 各数据源薪资对比图
  - 地图上的城市薪资
  - 薪资预测模型的训练数据

爬虫端已加 _is_intern 过滤,新抓的数据不会再有。本脚本清理存量脏数据,
让现有看板/模型立刻用上干净数据,不必等重新抓。

判定口径
--------
库里 job 表没存详情页 URL,无法用 /lptjob/ 频道判断,只能靠标题匹配
(_INTERN_KWS: 实习/见习/兼职/日结/临时工)。抽样验证过,标题匹配准确 ——
命中的确实都是实习岗,不会误删正式岗。

用法(默认只预览,加 --apply 才真正删除):
    venv/Scripts/python.exe scripts/clean_liepin_intern.py            # 预览会删哪些
    venv/Scripts/python.exe scripts/clean_liepin_intern.py --apply    # 确认后执行删除
"""
import os
import sys
from statistics import median

# 脚本挪进 scripts/ 后,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job
from app.spider.spider_liepin import _INTERN_KWS


def _is_intern_title(title: str) -> bool:
    """库里没存 URL,只能靠标题判断是否实习/兼职岗。"""
    return bool(title) and any(k in title for k in _INTERN_KWS)


def _median_salary(jobs) -> float:
    """算一组岗位的薪资中位数(忽略无薪资的),用于对比清理前后效果。"""
    sals = [j.salary_avg for j in jobs if j.salary_avg is not None]
    return round(median(sals), 1) if sals else 0.0


def main(apply: bool) -> None:
    session = get_session()
    try:
        liepin = session.query(Job).filter(Job.source == "liepin").all()
        interns = [j for j in liepin if _is_intern_title(j.title)]
        keep = [j for j in liepin if not _is_intern_title(j.title)]

        print(f"猎聘总数:        {len(liepin)}")
        print(f"判定为实习岗:    {len(interns)}  (将删除)")
        print(f"保留正式岗:      {len(keep)}")
        print(f"清理前薪资中位数: {_median_salary(liepin)}K")
        print(f"清理后薪资中位数: {_median_salary(keep)}K  (仅正式岗)")

        if not apply:
            print("\n[预览模式] 未做任何改动。确认无误后加 --apply 真正删除:")
            print("    venv/Scripts/python.exe scripts/clean_liepin_intern.py --apply")
            print("\n将删除的实习岗抽样(前 15 条):")
            for j in interns[:15]:
                print(f"  [{j.title}]  {j.salary_text}")
            return

        # 真正删除
        for j in interns:
            session.delete(j)
        session.commit()
        print(f"\n[已执行] 删除 {len(interns)} 条猎聘实习岗,保留 {len(keep)} 条正式岗。")
        print("提示:薪资预测模型请重跑 train_model.py,用干净数据重训。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
