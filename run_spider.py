"""
项目统一入口。

用法:
    # 1) 先跑 demo,验证环境 + 数据库管道(不联网)
    python run_spider.py --demo

    # 2) 真实抓取(需先 playwright install chromium)
    python run_spider.py --real

    # 3) 只测试薪资解析等工具函数
    python -m app.spider.utils
"""
import argparse

from app.spider.spider_51job import run_demo, run_real


def main():
    parser = argparse.ArgumentParser(description="招聘数据爬虫")
    parser.add_argument("--demo", action="store_true", help="用样例数据跑通管道")
    parser.add_argument("--real", action="store_true", help="真实抓取 51job")
    args = parser.parse_args()

    if args.real:
        run_real()
    else:
        # 默认走 demo,最安全
        run_demo()


if __name__ == "__main__":
    main()
