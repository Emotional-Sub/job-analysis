"""
招聘数据爬虫(Playwright 实现,目标站:51job 前程无忧)。

设计说明
--------
1. 用 Playwright 驱动真实 Chromium,能处理 JS 动态渲染。
2. 首次运行会打开浏览器让你手动登录(如需要),登录状态存到 storage_state.json,
   之后自动复用,不用每次登录。
3. 抓到的原始卡片先经过 utils 里的清洗函数,再统一入库。
4. 带 --demo 模式:不连网,用内置样例数据跑通"清洗->入库"全流程,
   方便第一次验证环境和数据库是否 OK。

注意:招聘站反爬较强、页面结构会变。real 模式的选择器(selector)可能需要
你打开页面用开发者工具核对后微调。这是爬虫项目的常态,不是 bug。
"""
import hashlib
import time
from typing import List, Dict

from app import config
from app.db.session import init_db, get_session
from app.db.models import Job
from app.spider.utils import (
    parse_salary,
    clean_education,
    clean_experience,
    split_tags,
)


# ---------------- 样例数据(demo 模式用) ----------------
SAMPLE_RAW: List[Dict] = [
    {
        "title": "Python开发工程师",
        "company": "字节跳动",
        "salary_text": "25-45K·15薪",
        "city": "北京",
        "education_text": "本科",
        "experience_text": "3-5年",
        "tags_text": "Python,后端,MySQL,Redis",
        "keyword": "Python",
        "source": "51job",
        "url": "https://example.com/job/1",
    },
    {
        "title": "Java高级工程师",
        "company": "阿里巴巴",
        "salary_text": "30-50K·16薪",
        "city": "杭州",
        "education_text": "本科",
        "experience_text": "5-10年",
        "tags_text": "Java,Spring,分布式,微服务",
        "keyword": "Java",
        "source": "51job",
        "url": "https://example.com/job/2",
    },
    {
        "title": "前端开发实习生",
        "company": "某创业公司",
        "salary_text": "8千-1.2万",
        "city": "深圳",
        "education_text": "大专",
        "experience_text": "应届",
        "tags_text": "Vue,JavaScript,CSS",
        "keyword": "前端",
        "source": "51job",
        "url": "https://example.com/job/3",
    },
    {
        "title": "数据分析师",
        "company": "美团",
        "salary_text": "20-35K·14薪",
        "city": "北京",
        "education_text": "硕士",
        "experience_text": "3-5年",
        "tags_text": "SQL,Python,数据分析,Tableau",
        "keyword": "数据分析",
        "source": "51job",
        "url": "https://example.com/job/4",
    },
    {
        "title": "算法工程师",
        "company": "腾讯",
        "salary_text": "1.5-3万",
        "city": "上海",
        "education_text": "硕士",
        "experience_text": "1-3年",
        "tags_text": "机器学习,Python,深度学习",
        "keyword": "Python",
        "source": "51job",
        "url": "https://example.com/job/5",
    },
]


def _make_job_key(raw: Dict) -> str:
    """
    生成站点内岗位唯一标识,用于去重。
    优先用详情页 url;没有 url 时用 标题+公司+城市 拼一个哈希。
    """
    url = raw.get("url")
    if url:
        return url
    base = f"{raw.get('title')}|{raw.get('company')}|{raw.get('city')}"
    return "h" + hashlib.md5(base.encode("utf-8")).hexdigest()


def clean_and_save(raw_list: List[Dict]) -> int:
    """把原始卡片列表清洗后写入数据库,返回新增条数。"""
    session = get_session()
    inserted = 0
    try:
        for raw in raw_list:
            source = raw.get("source", "51job")
            job_key = _make_job_key(raw)

            # 用 (source, job_key) 去重:同一个岗位只存一次
            exists = (
                session.query(Job)
                .filter_by(source=source, job_key=job_key)
                .first()
            )
            if exists:
                continue

            lo, hi, avg = parse_salary(raw.get("salary_text"))
            job = Job(
                source=source,
                job_key=job_key,
                title=raw.get("title"),
                company=raw.get("company"),
                city=raw.get("city"),
                salary_text=raw.get("salary_text"),
                salary_min=lo,
                salary_max=hi,
                salary_avg=avg,
                education=clean_education(raw.get("education_text")),
                experience=clean_experience(raw.get("experience_text")),
                tags=split_tags(raw.get("tags_text")),
                keyword=raw.get("keyword"),
            )
            session.add(job)
            inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return inserted


def run_demo() -> None:
    """demo 模式:用样例数据跑通整条管道,验证环境和数据库。"""
    print("[demo] 初始化数据库表...")
    init_db()
    print(f"[demo] 清洗并写入 {len(SAMPLE_RAW)} 条样例数据...")
    n = clean_and_save(SAMPLE_RAW)
    print(f"[demo] 完成,新增 {n} 条(重复的已跳过)。")


# ---------------- 真实抓取(Playwright) ----------------
def _extract_cards(page) -> List[Dict]:
    """
    从当前搜索结果页提取岗位卡片。
    ⚠️ 选择器需要你对照 51job 实际页面核对/微调。
    这里给出的是常见结构示意。
    """
    cards = []
    items = page.query_selector_all(".joblist .joblist-item, .j_joblist .e")
    for it in items:
        def _txt(sel):
            el = it.query_selector(sel)
            return el.inner_text().strip() if el else None

        def _attr(sel, attr):
            el = it.query_selector(sel)
            return el.get_attribute(attr) if el else None

        cards.append({
            "title": _txt(".jname, .job-title"),
            "company": _txt(".cname, .company-name"),
            "salary_text": _txt(".sal, .salary"),
            "city": _txt(".d.at, .job-area"),
            "education_text": None,   # 51job 学历常在详情/属性行,按需补充
            "experience_text": None,
            "tags_text": _txt(".tags, .job-tags"),
            "url": _attr("a", "href"),
        })
    return cards


def run_real() -> None:
    """
    真实抓取模式。需要先 pip install playwright 且 playwright install chromium。
    """
    from playwright.sync_api import sync_playwright
    import os

    init_db()
    total = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        # 复用已保存的登录状态(如果有)
        ctx_kwargs = {}
        if os.path.exists(config.STORAGE_STATE):
            ctx_kwargs["storage_state"] = config.STORAGE_STATE
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        for kw in config.KEYWORDS:
            kw = kw.strip()
            print(f"[real] 搜索关键词: {kw}")
            for pg in range(1, config.MAX_PAGES + 1):
                # 51job 搜索 URL 结构(示意,可能需按实际调整)
                url = (
                    f"https://we.51job.com/pc/search?keyword={kw}"
                    f"&searchType=2&pageNum={pg}"
                )
                page.goto(url, timeout=60000)
                page.wait_for_timeout(int(config.REQUEST_DELAY * 1000))

                cards = _extract_cards(page)
                for c in cards:
                    c["keyword"] = kw
                    c["source"] = "51job"
                if cards:
                    total += clean_and_save(cards)
                print(f"  第 {pg} 页,抓到 {len(cards)} 条")
                time.sleep(config.REQUEST_DELAY)

        # 保存登录状态,方便下次复用
        context.storage_state(path=config.STORAGE_STATE)
        browser.close()

    print(f"[real] 完成,累计新增 {total} 条。")
