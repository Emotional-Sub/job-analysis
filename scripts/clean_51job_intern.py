"""
一次性清理脚本:删除已入库的 51job 实习/兼职岗。

背景
----
猎聘爬虫加了 _is_intern 过滤,但 51job 爬虫一直没有对应过滤,导致
3211 条 51job 数据里混进了约 25 条实习/兼职岗(占 0.8%)。这些岗位薪资
多为日薪(如 600元/天)或极低月薪(3~7K),会往下拽全库薪资统计,
偏离"正式技术岗薪资"的分析口径,污染:
  - 各数据源薪资对比图
  - 地图上的城市薪资
  - 薪资预测模型的训练数据

占比虽小,但清掉能让统计更贴合正式岗口径,论文"数据清洗"环节也好交代。
清理 job 与 raw_job **两表同删**(按 source+job_key 对齐),保持两表口径一致
——否则 db_health_check 的口径检查会报两表条数不等。

判定口径
--------
沿用猎聘那套关键词 _INTERN_KWS(实习/见习/兼职/日结/临时工)做标题匹配。
库里 job 表没存详情页 URL,只能靠标题判断。抽样验证过,命中的确实都是
实习/兼职岗,不会误删正式岗。

用法(默认只预览,加 --apply 才真正删除):
    venv/Scripts/python.exe scripts/clean_51job_intern.py            # 预览会删哪些
    venv/Scripts/python.exe scripts/clean_51job_intern.py --apply    # 确认后执行删除
"""
import os
import sys
from statistics import median

# 脚本挪进 scripts/ 后,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job, RawJob
from app.spider.spider_liepin import _INTERN_KWS


# 否定表述:标题虽含"实习"等词,但明确声明"不招实习/非实习",实为正式岗,别误删
_NEGATION_KWS = ("不招实习", "非实习", "不含实习", "拒绝实习")


def _is_intern_title(title: str) -> bool:
    """库里没存 URL,只能靠标题判断是否实习/兼职岗。

    先排除否定表述(如"全职 不招实习生"),再按关键词匹配 ——
    否则"不招实习生"会被"实习"命中,误删掉正式岗。
    """
    if not title:
        return False
    if any(neg in title for neg in _NEGATION_KWS):
        return False
    return any(k in title for k in _INTERN_KWS)


def _median_salary(jobs) -> float:
    """算一组岗位的薪资中位数(忽略无薪资的),用于对比清理前后效果。"""
    sals = [j.salary_avg for j in jobs if j.salary_avg is not None]
    return round(median(sals), 1) if sals else 0.0


def main(apply: bool) -> None:
    session = get_session()
    try:
        qcjob = session.query(Job).filter(Job.source == "51job").all()
        interns = [j for j in qcjob if _is_intern_title(j.title)]
        keep = [j for j in qcjob if not _is_intern_title(j.title)]

        print(f"51job 总数:      {len(qcjob)}")
        print(f"判定为实习岗:    {len(interns)}  (将删除)")
        print(f"保留正式岗:      {len(keep)}")
        print(f"清理前薪资中位数: {_median_salary(qcjob)}K")
        print(f"清理后薪资中位数: {_median_salary(keep)}K  (仅正式岗)")

        if not apply:
            print("\n[预览模式] 未做任何改动。确认无误后加 --apply 真正删除:")
            print("    venv/Scripts/python.exe scripts/clean_51job_intern.py --apply")
            print("\n将删除的实习岗抽样(前 30 条):")
            for j in interns[:30]:
                print(f"  [{j.city}] [{j.title}]  {j.salary_text}")
            return

        # 真正删除:job 与 raw_job 两表同删(按 source+job_key 对齐),保持口径一致
        raw_del = 0
        for j in interns:
            raw_del += (
                session.query(RawJob)
                .filter_by(source=j.source, job_key=j.job_key)
                .delete()
            )
            session.delete(j)
        session.commit()
        print(f"\n[已执行] job 删除 {len(interns)} 条 51job 实习岗(raw_job 同步删 {raw_del} 条),保留 {len(keep)} 条正式岗。")
        print("提示:薪资预测模型请重跑 train_model.py,用干净数据重训。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
