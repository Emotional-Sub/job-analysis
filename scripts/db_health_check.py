"""
数据库体检脚本(只读,纯 SELECT,不写库)。
用途:整理数据库前先看清现状——两表条数/口径一致性/重复/脏数据/空值/分布。
从项目根运行:venv/Scripts/python.exe scripts/db_health_check.py
"""
import os
import sys

# 终端 GBK,而本脚本会打印 ⚠️ 等字符——且恰好在"检测到问题"时才打
# (口径不一致/有空值),不重配 stdout 的话体检会在发现问题的瞬间 UnicodeEncodeError 崩掉。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import get_session

CITIES_20 = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆", "西安",
    "苏州", "天津", "长沙", "郑州", "青岛", "宁波", "济南", "合肥", "福州", "无锡",
]


def q(s, sql):
    return s.execute(text(sql)).fetchall()


def main():
    s = get_session()
    try:
        print("=" * 60)
        print("【1】两表总条数与口径")
        job_n = q(s, "SELECT COUNT(*) FROM job")[0][0]
        raw_n = q(s, "SELECT COUNT(*) FROM raw_job")[0][0]
        print(f"  job     : {job_n}")
        print(f"  raw_job : {raw_n}")
        print(f"  口径一致 : {'是' if job_n == raw_n else '否 ⚠️'}")

        print("\n【2】重复检查 (source, job_key)")
        for tbl in ("job", "raw_job"):
            dup = q(s, f"""
                SELECT COUNT(*) FROM (
                    SELECT source, job_key FROM {tbl}
                    GROUP BY source, job_key HAVING COUNT(*) > 1
                ) t
            """)[0][0]
            print(f"  {tbl:8}: 重复组 {dup}")

        print("\n【3】来源分布")
        for tbl in ("job", "raw_job"):
            rows = q(s, f"SELECT source, COUNT(*) FROM {tbl} GROUP BY source ORDER BY 2 DESC")
            print(f"  {tbl}: " + ", ".join(f"{r[0]}={r[1]}" for r in rows))

        print("\n【4】名单外城市 (脏数据)")
        inlist = "','".join(CITIES_20)
        for tbl in ("job", "raw_job"):
            rows = q(s, f"""
                SELECT city, COUNT(*) FROM {tbl}
                WHERE city IS NULL OR city NOT IN ('{inlist}')
                GROUP BY city ORDER BY 2 DESC
            """)
            total = sum(r[1] for r in rows)
            print(f"  {tbl:8}: 名单外 {total} 条" + (f"  → {[(r[0], r[1]) for r in rows[:10]]}" if rows else ""))

        print("\n【5】关键空值 (job 表,影响建模/展示)")
        checks = {
            "salary_avg 为空": "salary_avg IS NULL",
            "salary_avg<=0": "salary_avg <= 0",
            "city 为空": "city IS NULL OR city = ''",
            "experience 为空": "experience IS NULL OR experience = ''",
            "education 为空": "education IS NULL OR education = ''",
            "title 为空": "title IS NULL OR title = ''",
            "keyword 为空": "keyword IS NULL OR keyword = ''",
        }
        for label, cond in checks.items():
            n = q(s, f"SELECT COUNT(*) FROM job WHERE {cond}")[0][0]
            flag = "  ⚠️" if n > 0 else ""
            print(f"  {label:18}: {n}{flag}")

        print("\n【6】薪资异常值 (job 表)")
        rows = q(s, """
            SELECT
                SUM(CASE WHEN salary_avg > 200 THEN 1 ELSE 0 END) AS gt200,
                SUM(CASE WHEN salary_avg < 1 AND salary_avg > 0 THEN 1 ELSE 0 END) AS lt1,
                SUM(CASE WHEN salary_min > salary_max THEN 1 ELSE 0 END) AS minmax,
                MIN(salary_avg), MAX(salary_avg), ROUND(AVG(salary_avg),2)
            FROM job WHERE salary_avg IS NOT NULL
        """)[0]
        print(f"  >200K(疑年薪误算): {rows[0]}   <1K: {rows[1]}   min>max: {rows[2]}")
        print(f"  salary_avg 范围: {rows[3]} ~ {rows[4]}   均值: {rows[5]}")

        print("\n【7】城市分布 (job 表, 20 城)")
        rows = q(s, "SELECT city, COUNT(*) FROM job GROUP BY city ORDER BY 2 DESC")
        for r in rows:
            print(f"    {r[0] or '(空)':6}: {r[1]}")

        print("\n【8】关键词分布 (job 表)")
        rows = q(s, "SELECT keyword, COUNT(*) FROM job GROUP BY keyword ORDER BY 2 DESC")
        for r in rows:
            print(f"    {r[0] or '(空)':12}: {r[1]}")

        print("\n【9】经验分档分布 (job 表)")
        rows = q(s, """
            SELECT experience, COUNT(*), ROUND(AVG(salary_avg),1)
            FROM job GROUP BY experience ORDER BY 2 DESC
        """)
        for r in rows:
            print(f"    {r[0] or '(空)':10}: {r[1]:6}  均薪 {r[2]}K")

        print("\n" + "=" * 60)
        print("体检完成(只读,未修改任何数据)")
    finally:
        s.close()


if __name__ == "__main__":
    main()
