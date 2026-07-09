"""
一次性清理脚本:删除「年薪被误当月薪」导致 salary_avg 异常高的脏数据。

背景
----
猎聘部分高端岗位 salary_text 用的是年薪单位(如 "490-500k"、"270-350k·13薪"),
parse_salary 按月薪折算后得到 salary_avg 高达数百 K/月(如 495K/月),
在物理上不可能,是明确的脏数据。这类岗位无法可靠还原真实月薪
(不知道年包该除以几个月),留着会拉高薪资均值/方差、干扰建模,故直接删除。

判定口径
--------
salary_avg > THRESHOLD_K(千元/月)即判为年薪误算。
正常月薪不可能超过 200K/月,阈值取 200 安全。

两表同删
--------
job 与 raw_job 按 (source, job_key) 对齐删除,保持两表口径一致
(memory 记录的坑:clean_offlist_cities.py 只删 job 不动 raw_job)。

用法(默认只预览,加 --apply 才真正删除):
    venv/Scripts/python.exe scripts/clean_annual_as_monthly.py            # 预览会删哪些
    venv/Scripts/python.exe scripts/clean_annual_as_monthly.py --apply    # 确认后执行删除
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.session import get_session

# 月薪阈值(千元/月)。salary_avg 超过此值即判为年薪误算。
THRESHOLD_K = 200.0


def main(apply: bool) -> None:
    session = get_session()
    try:
        # 先锁定 job 表里的异常行,取其 (source, job_key) 作为两表对齐的删除键
        rows = session.execute(
            text(
                "SELECT source, job_key, city, title, salary_text, salary_avg "
                "FROM job WHERE salary_avg > :thr ORDER BY salary_avg DESC"
            ),
            {"thr": THRESHOLD_K},
        ).fetchall()

        print(f"阈值:salary_avg > {THRESHOLD_K}K/月")
        print(f"job 表命中:{len(rows)} 条\n")
        print("待删明细(城市 / 原文 / 折算月薪 / 岗位):")
        for r in rows:
            print(f"  {r.city:6s} {r.salary_text:16s} avg={r.salary_avg:>7.1f}K  {r.title}")

        if not rows:
            print("\n无命中,无需清理。")
            return

        keys = [(r.source, r.job_key) for r in rows]

        # 顺带看这些键在 raw_job 里能对上几条(核对口径)
        raw_hit = 0
        for src, jk in keys:
            raw_hit += session.execute(
                text("SELECT COUNT(*) FROM raw_job WHERE source=:s AND job_key=:k"),
                {"s": src, "k": jk},
            ).scalar()
        print(f"\nraw_job 表对齐命中:{raw_hit} 条")

        if not apply:
            print("\n[预览模式] 未做任何改动。确认无误后加 --apply 真正删除:")
            print("    venv/Scripts/python.exe scripts/clean_annual_as_monthly.py --apply")
            return

        job_del = raw_del = 0
        for src, jk in keys:
            job_del += session.execute(
                text("DELETE FROM job WHERE source=:s AND job_key=:k"),
                {"s": src, "k": jk},
            ).rowcount
            raw_del += session.execute(
                text("DELETE FROM raw_job WHERE source=:s AND job_key=:k"),
                {"s": src, "k": jk},
            ).rowcount
        session.commit()
        print(f"\n[已执行] job 删除 {job_del} 条,raw_job 删除 {raw_del} 条,两表口径保持一致。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
