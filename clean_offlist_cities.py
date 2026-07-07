"""
一次性清理脚本:删除数据库里「不在目标 20 城名单」的岗位(liepin + 51job 都算)。

背景
----
早期猎聘城市编码(dq 码)配错,导致大量岗位抓成了名单外城市
(如金华/贵阳/长春/安顺/石家庄),污染城市维度分析。本脚本按白名单清理:
凡 city 不在 CITY_WHITELIST 内的行一律删除,与来源无关。

判定口径
--------
严格按 city 字段精确匹配白名单。白名单用官方 20 城顺序。
city 为空/None 的行也视为名单外(无法归属),一并删除。

用法(默认只预览,加 --apply 才真正删除):
    venv/Scripts/python.exe clean_offlist_cities.py            # 预览会删哪些
    venv/Scripts/python.exe clean_offlist_cities.py --apply    # 确认后执行删除
"""
import sys

from app.db.session import get_session
from app.db.models import Job

# 目标 20 城(官方顺序)。只保留这些城市的数据,其余全删。
CITY_WHITELIST = [
    "上海", "北京", "深圳", "重庆", "广州",
    "苏州", "成都", "杭州", "武汉", "南京",
    "宁波", "天津", "青岛", "无锡", "长沙",
    "郑州", "福州", "济南", "合肥", "西安",
]
_WHITELIST_SET = set(CITY_WHITELIST)


def _in_whitelist(city) -> bool:
    """city 精确命中白名单才保留;空值/名单外都判为待删。"""
    return bool(city) and city.strip() in _WHITELIST_SET


def main(apply: bool) -> None:
    session = get_session()
    try:
        all_jobs = session.query(Job).all()
        to_delete = [j for j in all_jobs if not _in_whitelist(j.city)]
        keep = [j for j in all_jobs if _in_whitelist(j.city)]

        # 按 (来源, 城市) 汇总待删,方便核对
        by_group = {}
        for j in to_delete:
            key = (j.source, (j.city or "<空>").strip())
            by_group[key] = by_group.get(key, 0) + 1

        print(f"总岗位:        {len(all_jobs)}")
        print(f"保留(名单内):  {len(keep)}")
        print(f"待删(名单外):  {len(to_delete)}")
        print("\n待删明细(来源 / 城市 / 条数):")
        for (src, city), n in sorted(by_group.items(), key=lambda x: (-x[1])):
            print(f"  {src:8s} {city:6s} {n}")

        if not apply:
            print("\n[预览模式] 未做任何改动。确认无误后加 --apply 真正删除:")
            print("    venv/Scripts/python.exe clean_offlist_cities.py --apply")
            return

        for j in to_delete:
            session.delete(j)
        session.commit()
        print(f"\n[已执行] 删除 {len(to_delete)} 条名单外数据,保留 {len(keep)} 条。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
