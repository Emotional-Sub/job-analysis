"""
只读统计脚本:按经验档分层,查看各档的岗位数量与薪资分布。

目的:抓取时猎聘按经验分档,导致"1年以下"被反复抓、样本严重偏多;
     本脚本把各经验档的数量和薪资摆出来,判断经验维度样本是否够、是否失衡,
     为后续建模时是否需要分层/重采样提供依据。

只做 SELECT 查询,不写库,不影响正在进行的抓取。

用法:venv/Scripts/python.exe scripts/stats_by_experience.py
     可选:加 --source liepin  或  --source 51job  只看单个源
"""
import os
import sys
import argparse
from collections import defaultdict
from statistics import median

# 脚本在 scripts/ 下,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job

# 经验档展示顺序(从低到高),没匹配上的归到"其他/未知"
EXP_ORDER = ["应届/不限", "1年以下", "1-3年", "3-5年", "5-10年", "10年以上"]


def _exp_sort_key(label: str) -> int:
    """让输出按经验从低到高排列;未知档排最后。"""
    return EXP_ORDER.index(label) if label in EXP_ORDER else len(EXP_ORDER)


def _fmt_salary(avgs: list) -> str:
    """把一档里的平均薪资列表汇总成 '中位数 / 均值 (n条有薪资)' 字符串。"""
    vals = [a for a in avgs if a is not None]
    if not vals:
        return "无有效薪资"
    med = median(vals)
    mean = sum(vals) / len(vals)
    return f"中位 {med:.0f}K  均值 {mean:.1f}K  (有薪资 {len(vals)} 条)"


def main() -> None:
    parser = argparse.ArgumentParser(description="按经验档分层统计岗位数量与薪资")
    parser.add_argument("--source", choices=["liepin", "51job"], default=None,
                        help="只统计指定来源;不加则统计全部")
    args = parser.parse_args()

    session = get_session()
    try:
        q = session.query(Job)
        if args.source:
            q = q.filter(Job.source == args.source)
        jobs = q.all()

        # exp_label -> {"count": n, "avgs": [...]}
        buckets = defaultdict(lambda: {"count": 0, "avgs": []})
        for job in jobs:
            label = (job.experience or "").strip() or "(空)"
            buckets[label]["count"] += 1
            buckets[label]["avgs"].append(job.salary_avg)

        total = len(jobs)
        scope = args.source or "全部来源"
        print(f"\n=== 经验分层统计:{scope}  共 {total} 条 ===\n")

        # 按经验从低到高排;同档内不再细分
        for label in sorted(buckets, key=_exp_sort_key):
            b = buckets[label]
            pct = b["count"] / total * 100 if total else 0
            print(f"[{label}]  {b['count']} 条  ({pct:.1f}%)")
            print(f"    {_fmt_salary(b['avgs'])}\n")

        # 失衡提示:最大档占比过高时给个警示,提醒建模阶段处理
        if buckets:
            biggest = max(buckets.values(), key=lambda b: b["count"])
            share = biggest["count"] / total * 100 if total else 0
            if share >= 50:
                print(f"[!] 最大经验档占比 {share:.0f}%,样本明显偏斜。"
                      f"建模时建议对该档降采样或分层,避免模型被其主导。")
    finally:
        session.close()


if __name__ == "__main__":
    main()
