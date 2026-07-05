"""
项目统一入口。

用法:
    # 1) 先跑 demo,验证环境 + 数据库管道(不联网)
    python run_spider.py --demo                    # 默认 51job 样例
    python run_spider.py --demo --site liepin      # 猎聘样例
    python run_spider.py --demo --site all         # 两个站的样例都灌一遍

    # 2) 真实抓取(需先 playwright install chromium)
    python run_spider.py --real                    # 默认抓 51job
    python run_spider.py --real --site liepin      # 只抓猎聘
    python run_spider.py --real --site all         # 先抓 51job 再抓猎聘

    # 3) 只测试薪资解析等工具函数
    python -m app.spider.utils

说明:
    --site 决定用哪个站点的爬虫。51job 和猎聘共用同一条清洗+入库管道
    (app/spider/pipeline.py),靠 source 字段区分来源,数据都进同一张 job 表。
"""
import argparse

from app.spider import spider_51job, spider_liepin


# 站点名 -> 对应爬虫模块。加新站点只需在这里登记一行。
SITES = {
    "51job": spider_51job,
    "liepin": spider_liepin,
}


def _run(site: str, real: bool) -> None:
    """按站点名调用对应爬虫的 demo / real。"""
    mod = SITES[site]
    if real:
        mod.run_real()
    else:
        mod.run_demo()


def main():
    parser = argparse.ArgumentParser(description="招聘数据爬虫")
    parser.add_argument("--demo", action="store_true", help="用样例数据跑通管道")
    parser.add_argument("--real", action="store_true", help="真实抓取")
    parser.add_argument(
        "--site",
        default="51job",
        choices=["51job", "liepin", "all"],
        help="目标站点:51job(默认)/ liepin / all(全部)",
    )
    args = parser.parse_args()

    # 要跑的站点列表:all 展开成全部
    targets = list(SITES.keys()) if args.site == "all" else [args.site]

    # --real 才联网抓取;否则一律走 demo(最安全)
    real = bool(args.real)
    for site in targets:
        _run(site, real)


if __name__ == "__main__":
    main()
