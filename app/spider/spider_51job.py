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
import json
import time
from typing import List, Dict

from app import config
from app.db.session import init_db
from app.spider.checkpoint import Checkpoint
from app.spider.pipeline import clean_and_save
from app.spider.utils import extract_skills


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

    51job 每个岗位卡片上都挂了一个 sensorsdata 属性,里面是完整的岗位 JSON
    (jobId/jobTitle/jobSalary/jobArea/jobYear/jobDegree/companyId 等),
    这是埋点数据。我们优先解析它 —— 比逐个抠 DOM 文本可靠得多,
    不怕布局变动、不怕文本里混入空格换行。

    公司名、行业、详情链接埋点里没有,再从 DOM 补充。
    """
    cards = []
    items = page.query_selector_all(".joblist-item")
    for it in items:
        # 埋点属性可能在自身或子元素上
        raw = it.get_attribute("sensorsdata")
        if not raw:
            inner = it.query_selector("[sensorsdata]")
            raw = inner.get_attribute("sensorsdata") if inner else None
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue

        # jobArea 形如 "成都·青羊区",取 · 前面作为城市
        area_full = data.get("jobArea") or ""
        city = area_full.split("·")[0].strip() if area_full else None

        # DOM 补充:公司名 / 行业 / 详情链接
        def _txt(sel):
            el = it.query_selector(sel)
            return el.inner_text().strip() if el else None

        def _attr(sel, attr):
            el = it.query_selector(sel)
            return el.get_attribute(attr) if el else None

        company = _txt(".cname") or _attr(".cname", "title")
        # 行业在 .bc 下的第一个 .dc(后面还有企业性质、规模等 .dc)
        industry = _attr(".bc .dc", "title") or _txt(".bc .dc")
        detail_url = _attr("a.comp", "href")

        # 技能从岗位标题里提取(51job 列表页没有独立的技能标签字段)
        # extract_skills 已返回逗号分隔字符串,直接用,不要再 join(会把字符串拆成单字符)
        title = data.get("jobTitle")
        skills = extract_skills(title)

        cards.append({
            "job_key": data.get("jobId"),          # 用官方 jobId 去重,最稳
            "title": title,
            "salary_text": data.get("jobSalary"),
            "city": city,
            "area": area_full,
            "education_text": data.get("jobDegree"),
            "experience_text": data.get("jobYear"),
            "tags_text": skills if skills else None,
            "company": company,
            "industry": industry,
            "url": detail_url,
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

    first_login = not os.path.exists(config.STORAGE_STATE)

    with sync_playwright() as p:
        # channel="chrome" 直接驱动你系统安装的 Chrome,不用另下 chromium 内核
        # 调试期建议 HEADLESS=False(在 .env 里设),能看到浏览器、方便过验证
        browser = p.chromium.launch(channel="chrome", headless=config.HEADLESS)
        # 复用已保存的登录状态(如果有)
        ctx_kwargs = {}
        if os.path.exists(config.STORAGE_STATE):
            ctx_kwargs["storage_state"] = config.STORAGE_STATE
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        # 首次运行:先打开首页,给你时间手动登录/过滑块,回车后继续并保存状态
        if first_login:
            page.goto("https://we.51job.com/pc/search?keyword=Python", timeout=60000)
            print("\n" + "=" * 50)
            print("首次运行:请在弹出的 Chrome 里完成登录/滑块验证,")
            print("看到岗位列表后,回到本终端按【回车】继续抓取。")
            print("=" * 50)
            input()
            context.storage_state(path=config.STORAGE_STATE)
            print(f"[real] 登录状态已保存到 {config.STORAGE_STATE}")

        # 断点续抓:读回已抓完的「城市×关键词」组合,被封/重启后跳过已完成的。
        cp = Checkpoint("51job")
        print(f"[real] 剩余待抓组合:{cp.remaining(config.CITIES, config.KEYWORDS)} 组")

        # 双层循环:城市 × 关键词。这样每个城市都能抓到足够样本,
        # "各城市"相关图表才有横向对比价值(不再是成都一根独大)。
        total_cities = len(config.CITIES)
        for idx, city_name in enumerate(config.CITIES, start=1):
            city_name = city_name.strip()
            area_code = config.CITY_CODES.get(city_name, "")
            for kw in config.KEYWORDS:
                kw = kw.strip()
                # 已抓完的组合直接跳过(断点续抓核心)
                if cp.done(city_name, kw):
                    print(f"[real] 跳过已抓:[{idx}/{total_cities}] {city_name} × {kw}")
                    continue
                print(f"[real] [{idx}/{total_cities}] 城市:{city_name}  关键词:{kw}")
                for pg in range(1, config.MAX_PAGES + 1):
                    url = (
                        f"https://we.51job.com/pc/search?keyword={kw}"
                        f"&searchType=2&pageNum={pg}"
                    )
                    # jobArea 是 51job 的城市编码;拿不到编码就退回不带(全国)
                    if area_code:
                        url += f"&jobArea={area_code}"
                    page.goto(url, timeout=60000)
                    # 等岗位卡片真正渲染出来(动态加载),最多等 15 秒
                    try:
                        page.wait_for_selector(".joblist-item", timeout=15000)
                    except Exception:
                        print(f"    第 {pg} 页:等不到岗位卡片,可能被反爬拦截或没有结果")
                    page.wait_for_timeout(int(config.request_delay_seconds() * 1000))

                    cards = _extract_cards(page)
                    for c in cards:
                        c["keyword"] = kw
                        c["source"] = "51job"
                        # 以搜索时指定的城市为准(页面上个别岗位可能标注周边区县)
                        if not c.get("city"):
                            c["city"] = city_name
                    if cards:
                        total += clean_and_save(cards)
                    print(f"    第 {pg} 页,抓到 {len(cards)} 条")
                    config.sleep_between_requests()

                # 这一组正常抓完,标记进度并落盘。下次重启会跳过这一组。
                # (中途硬崩的组不会走到这里,故不会被误标记,下次会重抓)
                cp.mark(city_name, kw)

        # 更新登录状态,方便下次复用
        context.storage_state(path=config.STORAGE_STATE)
        browser.close()

    print(f"[real] 完成,累计新增 {total} 条。")
    if total == 0:
        print("[提示] 新增 0 条。若之前已抓过会因去重跳过;若首次就 0 条,")
        print("       多半是登录态/反爬问题,把 HEADLESS 设为 False 观察页面。")
