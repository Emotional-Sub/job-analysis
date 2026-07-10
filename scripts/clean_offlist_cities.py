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
    venv/Scripts/python.exe scripts/clean_offlist_cities.py            # 预览会删哪些
    venv/Scripts/python.exe scripts/clean_offlist_cities.py --apply    # 确认后执行删除
"""
import os
import sys

# 脚本挪进 scripts/ 后,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.db.session import get_session
from app.db.models import Job, RawJob

# 目标 20 城(官方顺序)。只保留这些城市的数据,其余全删。
_WHITELIST_SET = set(c.strip() for c in config.CITIES)


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
            print("    venv/Scripts/python.exe scripts/clean_offlist_cities.py --apply")
            return

        # 两表同删:job 按对象删,raw_job 按同一"名单外 city"条件删。
        # job/raw_job 的 city 是一起写入的,两边都清名单外城市后口径保持一致。
        for j in to_delete:
            session.delete(j)
        # raw_job:city 为空/None 或不在白名单的都删
        raw_rows = session.query(RawJob).all()
        raw_del = 0
        for r in raw_rows:
            if not _in_whitelist(r.city):
                session.delete(r)
                raw_del += 1
        session.commit()
        print(f"\n[已执行] job 删除 {len(to_delete)} 条名单外数据(raw_job 同步删 {raw_del} 条),job 保留 {len(keep)} 条。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
