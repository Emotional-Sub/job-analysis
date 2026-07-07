"""
一次性清理脚本:删除「数据分析」关键词带出来的跨行业非 IT 岗。

背景
----
采集关键词里的「数据分析」是跨行业通用词,在 51job 搜索会返回医药、
财务、服装、金融、市场、人力各行各业的「X分析」岗位(如药物分析、
财务分析师、女装商品经理、招聘专员)。这些岗薪资分布与 IT 岗完全不同,
污染薪资统计、城市对比和预测模型。Java/Python/前端 是专有技术词,基本
不跑偏,故本脚本只针对非技术岗特征清理。

判定口径(务必只删明确非 IT 岗,宁可漏删不可误删真 IT 岗)
--------
两级过滤:
  1. 白保护:title 含 _TECH_KWS(开发/工程师/算法/后端/前端/测试…)的一律
     保留 —— 哪怕它也含某个黑名单词(如「测试开发工程师」含「测试」但是 IT 岗)。
  2. 黑名单:在白保护之外,title 含 _NONTECH_KWS(财务/会计/医药/临床/HR…)
     的判为非 IT 岗,删除。

两者都不命中的「存疑岗」不删,由 export_suspect.py / 人工另行判断。

用法(默认只预览,加 --apply 才真正删除):
    venv/Scripts/python.exe scripts/clean_nontech.py            # 预览会删哪些
    venv/Scripts/python.exe scripts/clean_nontech.py --apply    # 确认后执行删除
"""
import os
import sys
from statistics import mean

# 脚本挪进 scripts/ 后,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job

# 白保护词:title 含这些技术词就是 IT 岗,无条件保留(优先级高于黑名单)。
# 覆盖「测试开发工程师」「数据研发」这类同时含黑名单词的真 IT 岗。
_TECH_KWS = (
    "开发", "工程师", "程序员", "算法", "架构", "后端", "前端", "全栈",
    "运维", "测试开发", "数据研发", "数据开发", "大数据", "机器学习",
    "深度学习", "人工智能", "爬虫", "软件", "研发工程", "SRE", "DevOps",
    "Java", "Python", "Golang", "C++", "前端开发", "web开发", "嵌入式",
)

# 黑名单词:明确的跨行业非 IT 岗特征。白保护之外命中即删。
# 分类只为可读,判断时合并成一个集合。
_NONTECH_KWS = (
    # 财务/会计
    "财务", "会计", "出纳", "审计", "税务", "成本核算", "核价", "成本会计",
    # 医药/生物/临床/化学
    "药物", "药品", "临床", "生信", "单细胞", "医药", "制药", "药学",
    "化验", "检测员", "化学检测", "无机化学", "药物分析", "化验员",
    # 人力/行政/招聘
    "人力", "人事", "招聘", "薪酬", "绩效", "行政", "HRBP", "HR",
    "培训生", "储备干部",
    # 市场/销售/运营/客服
    "市场分析", "商业分析", "销售", "客服", "运营专员", "商品主管",
    "商品经理", "品类", "选品", "外贸", "跟单",
    # 金融/投资
    "投资", "证券", "基金", "风控专员", "信贷",
    # 服装/纺织/制造蓝领
    "服装", "纺织", "女装", "男装", "面料", "IE分析", "车间", "生产计划",
    "计划员", "物料", "仓储", "质检",
    # 统计/调研/文职
    "统计员", "调研", "录入", "数据录入", "文员", "助理",
)

_TECH_SET = tuple(_TECH_KWS)
_NONTECH_SET = tuple(_NONTECH_KWS)


def _is_tech(title: str) -> bool:
    """白保护:含技术词即 IT 岗。"""
    return bool(title) and any(k in title for k in _TECH_SET)


def _is_nontech(title: str) -> bool:
    """黑名单:白保护之外含非 IT 特征词即判为非 IT 岗。"""
    if not title:
        return False
    if _is_tech(title):
        return False
    return any(k in title for k in _NONTECH_SET)


def _avg(jobs) -> float:
    sals = [j.salary_avg for j in jobs if j.salary_avg is not None]
    return round(mean(sals), 1) if sals else 0.0


def main(apply: bool) -> None:
    session = get_session()
    try:
        # 只清 51job 的「数据分析」关键词岗 —— 污染集中在这里。
        # 其它关键词(Java/Python/前端)是专有技术词,基本不跑偏,不动。
        jobs = (
            session.query(Job)
            .filter(Job.keyword == "数据分析")
            .all()
        )
        to_delete = [j for j in jobs if _is_nontech(j.title)]
        keep = [j for j in jobs if not _is_nontech(j.title)]

        print(f"「数据分析」关键词岗总数: {len(jobs)}")
        print(f"判定为非 IT 岗(将删除):  {len(to_delete)}  平均薪资 {_avg(to_delete)}K")
        print(f"保留(IT岗+存疑岗):        {len(keep)}  平均薪资 {_avg(keep)}K")

        if not apply:
            print("\n[预览模式] 未做任何改动。确认无误后加 --apply 真正删除:")
            print("    venv/Scripts/python.exe scripts/clean_nontech.py --apply")
            print("\n将删除的非 IT 岗抽样(前 40 条):")
            for j in to_delete[:40]:
                print(f"  [{j.city}] {j.title}  ({j.salary_avg}K)")
            return

        for j in to_delete:
            session.delete(j)
        session.commit()
        print(f"\n[已执行] 删除 {len(to_delete)} 条非 IT 岗,保留 {len(keep)} 条。")
        print("提示:薪资预测模型请重跑 train_model.py,用干净数据重训。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
