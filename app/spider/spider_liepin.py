"""
招聘数据爬虫(Playwright 实现,目标站:猎聘 liepin)。

设计说明
--------
和 spider_51job.py 结构完全对齐,只是换了目标站点和页面选择器:
1. 用 Playwright 驱动真实 Chromium 处理 JS 动态渲染。
2. 首次运行打开浏览器让你手动登录/过验证,登录状态存到 storage_state_liepin.json,
   之后自动复用(和 51job 分开存,互不影响)。
3. 抓到的原始卡片经 pipeline.clean_and_save 清洗入库,与 51job 共用同一条管道。
4. 带 --demo 模式:不连网,用内置样例跑通"清洗->入库"全流程。

去重:猎聘岗位卡片带一个 data-tgranslate-title / 详情链接里含 jobId,
优先用 jobId 作为 job_key(配合 source="liepin" 保证跨站不撞)。

注意:猎聘反爬强、页面结构会变。real 模式的选择器需你打开页面用开发者工具
核对后微调 —— 用 probe_liepin.py 探测。这是爬虫项目常态,不是 bug。
"""
import re
import time
from typing import List, Dict

from app import config
from app.db.session import init_db
from app.spider.pipeline import clean_and_save
from app.spider.utils import extract_skills


# 猎聘登录状态单独存一份,和 51job 互不干扰
LIEPIN_STORAGE_STATE = str(config.BASE_DIR / "storage_state_liepin.json")


# ---------------- 样例数据(demo 模式用) ----------------
SAMPLE_RAW: List[Dict] = [
    {
        "title": "Python高级开发工程师",
        "company": "网易",
        "salary_text": "25-40K·14薪",
        "city": "杭州",
        "education_text": "本科",
        "experience_text": "3-5年",
        "tags_text": "Python,后端,MySQL,Docker",
        "keyword": "Python",
        "source": "liepin",
        "url": "https://example.com/liepin/1",
    },
    {
        "title": "Java架构师",
        "company": "京东",
        "salary_text": "35-60K·15薪",
        "city": "北京",
        "education_text": "本科",
        "experience_text": "5-10年",
        "tags_text": "Java,Spring,分布式,微服务",
        "keyword": "Java",
        "source": "liepin",
        "url": "https://example.com/liepin/2",
    },
    {
        "title": "前端开发工程师",
        "company": "小红书",
        "salary_text": "20-35K·13薪",
        "city": "上海",
        "education_text": "本科",
        "experience_text": "1-3年",
        "tags_text": "Vue,React,TypeScript",
        "keyword": "前端",
        "source": "liepin",
        "url": "https://example.com/liepin/3",
    },
    {
        "title": "数据分析专家",
        "company": "滴滴",
        "salary_text": "30-50K·14薪",
        "city": "北京",
        "education_text": "硕士",
        "experience_text": "5-10年",
        "tags_text": "SQL,Python,数据分析,大数据",
        "keyword": "数据分析",
        "source": "liepin",
        "url": "https://example.com/liepin/4",
    },
]


def run_demo() -> None:
    """demo 模式:用样例数据跑通整条管道,验证环境和数据库。"""
    print("[liepin-demo] 初始化数据库表...")
    init_db()
    print(f"[liepin-demo] 清洗并写入 {len(SAMPLE_RAW)} 条样例数据...")
    n = clean_and_save(SAMPLE_RAW)
    print(f"[liepin-demo] 完成,新增 {n} 条(重复的已跳过)。")


# ---------------- 真实抓取(Playwright) ----------------
def _extract_job_id(url: str) -> str:
    """
    从猎聘详情链接里抽岗位 id 作为去重键。
    猎聘详情页有两种:普通岗位 /job/{id}.shtml,直招/实习岗 /lptjob/{id}。
    两种都取路径里的数字 id。抽不到就退回去掉查询串的短 url
    (整条带 ?pgRef=... 的 url 有一两百字符,会撑爆 job_key 字段)。
    """
    if not url:
        return ""
    m = re.search(r"/(?:lpt)?job/(\d+)", url)
    if m:
        return m.group(1)
    # 兜底:砍掉 ? 后面的查询参数,只留短路径
    return url.split("?")[0]


# 薪资文本特征:形如 "30-50k·15薪""15-30k""薪资面议""20-40万/年""800元/天"。
# 猎聘列表页薪资没有独立语义 class,只能靠文本模式从一堆 span 里认出来。
_SALARY_RE = re.compile(r"\d+\s*[-~]\s*\d+\s*[kK万]|面议|\d+\s*元|\d+\s*万")

# 学历关键词:命中即判为学历标签
_EDU_KWS = ("本科", "大专", "硕士", "博士", "学历", "高中", "中专", "初中", "MBA", "EMBA")

# 经验标签特征:猎聘的经验档形如 "1-3年""3-5年""5-10年""10年以上""1年以下"
# "经验不限""应届""在校/应届"。之前只认含"年/应届/经验"的,漏掉了"在校""不限经验"
# 等写法,导致近半数经验字段为 None。这里放宽匹配。
_EXP_KWS = ("年", "应届", "经验", "在校", "不限", "往届")


def _classify_labels(spans_text: List[str]) -> Dict[str, str]:
    """
    从卡片里所有 span 的文本中,按内容特征认出 薪资 / 经验 / 学历。

    猎聘现在用构建时随机生成的混淆 class(如 _40108E8PWS),发版就变,不能依赖。
    但字段的文本格式是稳定的,所以改用"文本特征"来识别 —— 这样即便 class 再变,
    只要展示格式不变就还能抓到。

    识别顺序有讲究:先认学历(词表最明确),再认薪资,最后经验用最宽的兜底。
    这样"统招本科"不会被经验的"不限"之类误伤,经验也不会因为写法特殊而漏掉。
    """
    result: Dict[str, str] = {}
    for t in spans_text:
        t = t.strip()
        if not t or t in ("·", "|", "-"):
            continue
        # 学历:词表最明确,优先判
        if "edu" not in result and any(k in t for k in _EDU_KWS):
            result["edu"] = t
            continue
        # 薪资
        if "salary" not in result and _SALARY_RE.search(t):
            result["salary"] = t
            continue
        # 经验:放宽后的关键词兜底(且已排除学历/薪资)
        if "exp" not in result and any(k in t for k in _EXP_KWS):
            result["exp"] = t
            continue
    return result


# 实习岗标题特征:命中即视为实习岗,过滤掉(薪资多为日薪/低月薪,会拉低统计)
_INTERN_KWS = ("实习", "见习", "兼职", "日结", "临时工")


def _is_intern(title: str, url: str) -> bool:
    """
    判断是否实习/兼职岗。两个信号:
      1. 标题含"实习/见习/兼职"等词
      2. 详情链接走的是猎聘直招频道 /lptjob/(实习/低端岗聚集在此)
    命中任一即过滤 —— 我们分析的是正式技术岗薪资,实习岗会严重拉低中位数。
    """
    if title and any(k in title for k in _INTERN_KWS):
        return True
    if url and "/lptjob/" in url:
        return True
    return False


def _extract_cards(page) -> List[Dict]:
    """
    从当前搜索结果页提取岗位卡片。

    定位策略(2026-07 核对真实页面后重写):
    猎聘列表页的样式 class 是构建时随机混淆的(如 _40108yn42Q),会随发版变化,
    绝不能硬编码。但有两类**稳定锚点**:
      - a[data-nick="job-detail-job-info"]      岗位信息块(href 含 /job/{id})
      - div[data-nick="job-detail-company-info"] 公司信息块
    块内字段:
      - 岗位名:岗位块里的 div.ellipsis-1(带 title 属性)—— 与城市 span 区分开
      - 城市:  岗位块里的 span.ellipsis-1(形如 "北京-朝阳区",取 - 前)
      - 薪资/经验/学历:块内所有 span 文本,按 _classify_labels 的文本特征归类
      - 公司名:公司块里的 span.ellipsis-1
      - 行业:  公司块里最后一个 div 下的第一个 span

    页面结构再变时用 probe_liepin.py 重新核对。
    """
    cards: List[Dict] = []
    items = page.query_selector_all(".job-card-pc-container")
    for it in items:
        job = it.query_selector('a[data-nick="job-detail-job-info"]')
        if not job:
            continue

        # 岗位名:带 title 属性的 div.ellipsis-1(title 属性文本最完整、无省略号)
        title_el = job.query_selector("div.ellipsis-1[title]") or job.query_selector(
            "div.ellipsis-1"
        )
        title = None
        if title_el:
            title = (title_el.get_attribute("title") or title_el.inner_text() or "").strip()
        if not title:
            continue

        # 详情链接:岗位块 a 的 href(提前取,用于实习岗判断和去重)
        detail_url = job.get_attribute("href")

        # 过滤实习/兼职岗:薪资多为日薪/低月薪,会严重拉低正式岗薪资统计
        if _is_intern(title, detail_url or ""):
            continue

        # 城市:岗位块内的 span.ellipsis-1(标题是 div,城市是 span,天然区分)
        city_el = job.query_selector("span.ellipsis-1")
        dq_full = city_el.inner_text().strip() if city_el else None
        city = dq_full.split("-")[0].strip() if dq_full else None

        # 薪资/经验/学历:收集岗位块内所有 span 文本,按特征归类
        span_texts = [
            (s.inner_text() or "").strip()
            for s in job.query_selector_all("span")
        ]
        labels = _classify_labels(span_texts)
        salary = labels.get("salary")
        edu_text = labels.get("edu")
        exp_text = labels.get("exp")

        # 公司名 / 行业:在公司信息块里取
        comp = it.query_selector('[data-nick="job-detail-company-info"]')
        company = None
        industry = None
        if comp:
            cname = comp.query_selector("span.ellipsis-1")
            company = cname.inner_text().strip() if cname else None
            # 行业在公司块内最后一个 div 的第一个 span(后面还有融资轮次、规模)
            comp_divs = comp.query_selector_all("div")
            if comp_divs:
                first_span = comp_divs[-1].query_selector("span")
                industry = first_span.inner_text().strip() if first_span else None

        # 技能从标题里按词库抽取(列表页无独立技能字段)
        skills = extract_skills(title)

        job_id = _extract_job_id(detail_url or "")

        cards.append({
            "job_key": job_id or None,
            "title": title,
            "salary_text": salary,
            "city": city,
            "area": dq_full,
            "education_text": edu_text,
            "experience_text": exp_text,
            "tags_text": skills if skills else None,
            "company": company,
            "industry": industry,
            "url": detail_url,
        })
    return cards


def run_real() -> None:
    """
    真实抓取模式。需要先 pip install playwright 且 playwright install chromium。
    结构与 51job 版一致:城市 × 关键词 双层循环,翻页抓取。
    """
    from playwright.sync_api import sync_playwright
    import os

    init_db()
    total = 0

    first_login = not os.path.exists(LIEPIN_STORAGE_STATE)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=config.HEADLESS)
        ctx_kwargs = {}
        if os.path.exists(LIEPIN_STORAGE_STATE):
            ctx_kwargs["storage_state"] = LIEPIN_STORAGE_STATE
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        # 首次运行:打开搜索页,给你时间手动登录/过验证,回车后继续并保存状态
        if first_login:
            page.goto(
                "https://www.liepin.com/zhaopin/?key=Python", timeout=60000
            )
            print("\n" + "=" * 50)
            print("首次运行:请在弹出的 Chrome 里完成登录/验证,")
            print("看到岗位列表后,回到本终端按【回车】继续抓取。")
            print("=" * 50)
            input()
            context.storage_state(path=LIEPIN_STORAGE_STATE)
            print(f"[liepin] 登录状态已保存到 {LIEPIN_STORAGE_STATE}")

        # 连续多少页抓到 0 条就判定当前城市被拦/无更多结果,提前跳到下一组
        EMPTY_PAGE_LIMIT = 2

        # 断点续抓:读回已抓完的「城市×关键词」组合,被封/重启后跳过已完成的。
        cp = Checkpoint("liepin")
        print(f"[liepin] 剩余待抓组合:{cp.remaining(config.CITIES, config.KEYWORDS)} 组")

        # 城市 × 关键词 双层循环
        for city_name in config.CITIES:
            city_name = city_name.strip()
            dq_code = config.LIEPIN_CITY_CODES.get(city_name, "")
            for kw in config.KEYWORDS:
                kw = kw.strip()
                # 已抓完的组合直接跳过(断点续抓核心)
                if cp.done(city_name, kw):
                    print(f"[liepin] 跳过已抓:{city_name} × {kw}")
                    continue
                print(f"[liepin] 城市:{city_name}  关键词:{kw}")
                empty_streak = 0
                for pg in range(0, config.MAX_PAGES):
                    # 猎聘搜索:key=关键词,dq=城市码,curPage 从 0 开始
                    url = f"https://www.liepin.com/zhaopin/?key={kw}&curPage={pg}"
                    if dq_code:
                        url += f"&dq={dq_code}"

                    # goto 容错:被反爬掐断连接(ERR_ABORTED)等会抛异常,
                    # 单页失败不该让整个任务崩溃 —— 记一次空页,继续下一页
                    try:
                        page.goto(url, timeout=60000)
                    except Exception as e:
                        print(f"    第 {pg + 1} 页:打开失败({type(e).__name__}),跳过")
                        empty_streak += 1
                        if empty_streak >= EMPTY_PAGE_LIMIT:
                            print(f"    连续 {empty_streak} 页异常,疑似被拦,跳过该组")
                            break
                        config.sleep_between_requests()
                        continue

                    # 等岗位卡片渲染(动态加载),最多等 15 秒。
                    # 等不到就 continue,绝不往下抓 —— 否则抓到的是上一页的残留数据。
                    try:
                        page.wait_for_selector(
                            ".job-card-pc-container", timeout=15000
                        )
                    except Exception:
                        print(f"    第 {pg + 1} 页:等不到岗位卡片,可能被反爬拦截或没有结果")
                        empty_streak += 1
                        if empty_streak >= EMPTY_PAGE_LIMIT:
                            print(f"    连续 {empty_streak} 页无结果,跳过该组")
                            break
                        config.sleep_between_requests()
                        continue

                    page.wait_for_timeout(int(config.request_delay_seconds() * 1000))

                    cards = _extract_cards(page)
                    for c in cards:
                        c["keyword"] = kw
                        c["source"] = "liepin"
                        if not c.get("city"):
                            c["city"] = city_name

                    if cards:
                        empty_streak = 0
                        total += clean_and_save(cards)
                    else:
                        # 页面出来了但一条没抓到(可能全被实习岗过滤,或结构变了)
                        empty_streak += 1
                    print(f"    第 {pg + 1} 页,抓到 {len(cards)} 条")

                    if empty_streak >= EMPTY_PAGE_LIMIT:
                        print(f"    连续 {empty_streak} 页 0 条,跳过该组")
                        break

                    time.sleep(config.REQUEST_DELAY)

                # 这一组正常抓完,标记进度并落盘。下次重启会跳过这一组。
                # (中途硬崩的组不会走到这里,故不会被误标记,下次会重抓)
                cp.mark(city_name, kw)

                # 每组抓完存一次登录态,中途崩了也不丢已保存的 cookie
                try:
                    context.storage_state(path=LIEPIN_STORAGE_STATE)
                except Exception:
                    pass

        context.storage_state(path=LIEPIN_STORAGE_STATE)
        browser.close()

    print(f"[liepin] 完成,累计新增 {total} 条。")
    if total == 0:
        print("[提示] 新增 0 条。若之前已抓过会因去重跳过;若首次就 0 条,")
        print("       多半是登录态/反爬问题或选择器过时,先跑 probe_liepin.py 核对。")
