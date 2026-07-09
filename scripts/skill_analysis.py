# -*- coding: utf-8 -*-
"""
只读技能分析脚本:基于 job.tags(平台标注的技能标签)做三件事——
  1) 技能词归一化(大小写/别名/语义重叠合并,避免 Spring 与 spring 被拆开统计)
  2) 技能共现网络(哪些技能常一起出现,供前端力导向关系图)
  3) 技能薪资溢价(掌握某技能的岗位薪资中位数 vs 全库中位数)
可选:对归一后的技能词出一张词云图(--wordcloud)。

为什么用 tags 而不是对 title 分词:tags 是招聘平台已标注的干净技能词,
噪音低;title 分词会混入"招聘/工程师/高级"等大量非技能词,清洗成本高、
收益低。故以 tags 为主数据源。

只做 SELECT 查询,不写库,不影响抓取/建模。

用法:
    venv/Scripts/python.exe scripts/skill_analysis.py                # 打印共现+溢价
    venv/Scripts/python.exe scripts/skill_analysis.py --json         # 额外导出前端用 JSON
    venv/Scripts/python.exe scripts/skill_analysis.py --wordcloud    # 额外出词云图
"""
import os
import sys
import io
import json
import argparse
from collections import Counter, defaultdict
from itertools import combinations
from statistics import median

# 终端/文件统一 UTF-8,避免 GBK 打不出特殊字符
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 脚本在 scripts/ 下,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_session
from app.db.models import Job

# ---------------- 技能词归一化 ----------------
# 把大小写变体、别名、语义重叠的写法合并到一个规范名。
# key 用小写匹配(见 _normalize),value 是规范展示名。
_ALIAS = {
    # 语言
    "python": "Python", "python开发": "Python",
    "java": "Java", "java开发": "Java", "javaee": "Java",
    "golang": "Go", "go": "Go",
    "c++": "C++", "c/c++": "C++",
    "javascript": "JavaScript", "js": "JavaScript",
    "typescript": "TypeScript", "ts": "TypeScript",
    # 框架
    "spring": "Spring",
    "spring boot": "Spring Boot", "springboot": "Spring Boot",
    "spring bot": "Spring Boot",  # 平台常见错拼
    "spring cloud": "Spring Cloud", "springcloud": "Spring Cloud",
    "vue": "Vue", "vue.js": "Vue", "vuejs": "Vue",
    "react": "React", "react.js": "React",
    "angular": "Angular",
    "node.js": "Node.js", "nodejs": "Node.js",
    # 数据库/中间件
    "mysql": "MySQL", "redis": "Redis", "mongodb": "MongoDB",
    "elasticsearch": "Elasticsearch", "es": "Elasticsearch",
    "kafka": "Kafka",
    # 大数据
    "hadoop": "Hadoop", "hive": "Hive", "spark": "Spark",
    # 运维/云
    "linux": "Linux", "docker": "Docker",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "git": "Git", "shell": "Shell",
    # 前端
    "html5": "HTML5", "html": "HTML5", "css3": "CSS3", "css": "CSS3",
    "web前端": "前端开发", "前端": "前端开发", "前端开发": "前端开发",
    # 方向/概念(保留但归一)
    "数据分析": "数据分析", "数据挖掘": "数据挖掘", "数据仓库": "数据仓库",
    "数据开发": "数据开发", "数据治理": "数据治理", "数据可视化": "数据可视化",
    "机器学习": "机器学习", "深度学习": "深度学习", "大数据": "大数据",
    "微服务": "微服务", "微服务架构": "微服务", "分布式": "分布式",
    "分布式架构": "分布式", "数据库": "数据库", "sql": "SQL",
    "软件开发": "软件开发",
}


def _normalize(tag: str) -> str:
    """把一个原始 tag 归一到规范技能名;不在别名表里的原样返回(去空白)。"""
    t = tag.strip()
    return _ALIAS.get(t.lower(), t)


def _load_jobs():
    """读出 (归一后技能集合, salary_avg) 列表;只保留 tags 非空的岗位。"""
    session = get_session()
    try:
        rows = (
            session.query(Job.tags, Job.salary_avg)
            .filter(Job.tags.isnot(None))
            .all()
        )
    finally:
        session.close()

    result = []
    for tags, sal in rows:
        skills = {
            _normalize(t) for t in (tags or "").split(",") if t.strip()
        }
        if skills:
            result.append((skills, sal))
    return result


# ---------------- 共现网络 ----------------
def build_cooccurrence(jobs, top_n=25, min_edge=8):
    """
    统计技能共现。返回 (nodes, edges):
      nodes: [{"name", "value"(出现频次)}], 取频次 top_n 个技能
      edges: [{"source", "target", "weight"(共现次数)}], 只保留权重 >= min_edge
    只在 top_n 技能之间连边,避免长尾噪音把图糊成一团。
    """
    freq = Counter()
    for skills, _ in jobs:
        for s in skills:
            freq[s] += 1

    top_skills = [s for s, _ in freq.most_common(top_n)]
    top_set = set(top_skills)

    co = Counter()
    for skills, _ in jobs:
        inter = sorted(skills & top_set)
        for a, b in combinations(inter, 2):
            co[(a, b)] += 1

    nodes = [{"name": s, "value": freq[s]} for s in top_skills]
    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in co.items()
        if w >= min_edge
    ]
    return nodes, edges


# ---------------- 薪资溢价 ----------------
def skill_salary_premium(jobs, min_samples=20, top_n=20):
    """
    每个技能:掌握它的岗位薪资中位数,与全库中位数比,算溢价百分比。
    只保留样本数 >= min_samples 的技能,按溢价降序返回 top_n。
    返回 (overall_median, [{"skill","n","median","premium_pct"}]).
    """
    all_sal = [s for _, s in jobs if s is not None]
    overall = median(all_sal) if all_sal else 0.0

    bucket = defaultdict(list)
    for skills, sal in jobs:
        if sal is None:
            continue
        for s in skills:
            bucket[s].append(sal)

    rows = []
    for skill, sals in bucket.items():
        if len(sals) < min_samples:
            continue
        med = median(sals)
        premium = (med - overall) / overall * 100 if overall else 0.0
        rows.append({
            "skill": skill, "n": len(sals),
            "median": round(med, 1), "premium_pct": round(premium, 1),
        })
    rows.sort(key=lambda r: r["premium_pct"], reverse=True)
    return overall, rows[:top_n]


# ---------------- 词云(可选) ----------------
def make_wordcloud(jobs, out_path):
    """对归一后的技能词按频次出词云。中文需指定字体,否则乱码/空白。"""
    from wordcloud import WordCloud

    freq = Counter()
    for skills, _ in jobs:
        for s in skills:
            freq[s] += 1

    # Windows 常见中文字体,挨个探测取第一个存在的
    font = None
    for cand in (
        r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
        r"C:\Windows\Fonts\simhei.ttf",   # 黑体
        r"C:\Windows\Fonts\simsun.ttc",   # 宋体
    ):
        if os.path.exists(cand):
            font = cand
            break
    if not font:
        print("  [警告] 未找到中文字体,词云可能乱码。")

    wc = WordCloud(
        font_path=font, width=1000, height=600,
        background_color="white", max_words=80, colormap="viridis",
    )
    wc.generate_from_frequencies(dict(freq))
    wc.to_file(out_path)
    print(f"  词云已保存:{out_path}")


def main():
    parser = argparse.ArgumentParser(description="技能共现网络 + 薪资溢价分析")
    parser.add_argument("--json", action="store_true",
                        help="导出前端用 JSON 到 scripts/out/skill_graph.json")
    parser.add_argument("--wordcloud", action="store_true",
                        help="生成技能词云图到 scripts/out/skill_wordcloud.png")
    args = parser.parse_args()

    jobs = _load_jobs()
    print("\n" + "#" * 60)
    print(f"# 技能分析(tags 非空岗位 {len(jobs)} 条,已归一化)")
    print("#" * 60)

    # --- 共现网络 ---
    nodes, edges = build_cooccurrence(jobs)
    print("\n" + "=" * 60)
    print("技能共现网络(top 技能之间,共现次数 >= 8)")
    print("=" * 60)
    print(f"  节点(技能)数:{len(nodes)}   连边(共现对)数:{len(edges)}")
    print("\n  共现最强的 15 对技能:")
    for e in sorted(edges, key=lambda x: x["weight"], reverse=True)[:15]:
        print(f"    {e['source']:12s} — {e['target']:12s}  共现 {e['weight']} 次")

    # --- 薪资溢价 ---
    overall, premium = skill_salary_premium(jobs)
    print("\n" + "=" * 60)
    print(f"技能薪资溢价(全库中位薪资基准 {overall:.1f}K,样本>=20)")
    print("=" * 60)
    print(f"\n  {'技能':<14}{'岗位数':>6}{'中位薪资':>10}{'相对溢价':>10}")
    print("  " + "-" * 42)
    for r in premium:
        sign = "+" if r["premium_pct"] >= 0 else ""
        print(f"  {r['skill']:<14}{r['n']:>6}{r['median']:>9.1f}K"
              f"{sign}{r['premium_pct']:>8.1f}%")

    # --- 可选导出 ---
    if args.json or args.wordcloud:
        out_dir = os.path.join(os.path.dirname(__file__), "out")
        os.makedirs(out_dir, exist_ok=True)

        if args.json:
            out = os.path.join(out_dir, "skill_graph.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump({
                    "nodes": nodes, "edges": edges,
                    "overall_median": overall, "premium": premium,
                }, f, ensure_ascii=False, indent=2)
            print(f"\n  前端 JSON 已导出:{out}")

        if args.wordcloud:
            out = os.path.join(out_dir, "skill_wordcloud.png")
            make_wordcloud(jobs, out)

    print("\n" + "#" * 60)
    print("# 小结(供论文技能章)")
    print("#" * 60)
    print("""
  - 共现网络印证岗位方向的技能边界:后端簇(Java-Spring-MySQL)、
    前端簇(Vue-React-JavaScript)、数据簇(Python-SQL-数据分析)
    自然聚合,与职位方向分类互相印证。
  - 薪资溢价量化了"哪些技能更值钱":大数据/云原生组件(Spark/
    Hadoop/Kubernetes 等)通常显著高于全库中位,可作为求职者
    技能投资的参考,也补充了"技能"这一维度对薪资的解释。
""")


if __name__ == "__main__":
    main()
