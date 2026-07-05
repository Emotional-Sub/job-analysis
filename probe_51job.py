"""
51job 页面结构探测脚本(一次性调试工具,不属于正式代码)。

用途
----
真实爬虫要能抓到数据,前提是知道页面里"岗位卡片/标题/薪资"这些元素
的真实 CSS 选择器。但页面结构会变,只能对着真实页面看。这个脚本就是
帮我们把真实结构"抓下来看"的工具:

1. 用你系统的 Chrome 打开 51job 搜索页(可见窗口)。
2. 暂停,等你在浏览器里手动登录 / 过掉验证码(如果有),
   然后回到终端按回车继续。
3. 脚本把渲染后的整页 HTML 存成文件,并尝试自动猜测岗位卡片选择器,
   把候选打印出来。

运行:
    venv/Scripts/python.exe probe_51job.py

产出:
    debug_page.html   —— 渲染后的完整 HTML(用浏览器或编辑器打开看结构)
    debug_shot.png    —— 页面截图(确认到底停在哪个页面)
"""
from playwright.sync_api import sync_playwright

# 探测用的搜索词和页面(先固定一个词,跑通再说)
KEYWORD = "Python"
SEARCH_URL = f"https://we.51job.com/pc/search?keyword={KEYWORD}&searchType=2"

# 一些"常见岗位卡片"的候选选择器,脚本会逐个数一下命中多少,帮我们缩小范围
CANDIDATE_SELECTORS = [
    ".joblist-item",
    ".j_joblist .e",
    ".joblist .joblist-item",
    "div[class*='joblist']",
    "div[class*='job-item']",
    "div[class*='jobitem']",
    "a[class*='job']",
    ".sensors_exposure",
    "[sensorsdata]",
]


def main():
    with sync_playwright() as p:
        # channel="chrome" 用你系统装的 Chrome;headless=False 显示窗口
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"[probe] 打开搜索页: {SEARCH_URL}")
        page.goto(SEARCH_URL, timeout=60000)

        print("\n" + "=" * 60)
        print("浏览器已打开。请在浏览器里:")
        print("  1) 如果要求登录,就登录;如果有滑块/验证码,手动过掉")
        print("  2) 确认页面上能看到岗位列表")
        print("  3) 然后回到这个终端,按回车继续")
        print("=" * 60)
        input(">>> 准备好后按回车...")

        # 给页面一点时间把动态内容渲染完
        page.wait_for_timeout(2000)

        # 存整页 HTML
        html = page.content()
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[probe] 已保存 debug_page.html ({len(html)} 字符)")

        # 截图
        page.screenshot(path="debug_shot.png", full_page=False)
        print("[probe] 已保存 debug_shot.png")

        # 打印当前 URL 和标题(确认没被跳去登录页)
        print(f"[probe] 当前 URL: {page.url}")
        print(f"[probe] 页面标题: {page.title()}")

        # 逐个数候选选择器命中多少个元素
        print("\n--- 候选选择器命中数(数量多的更可能是岗位卡片) ---")
        for sel in CANDIDATE_SELECTORS:
            try:
                n = len(page.query_selector_all(sel))
            except Exception as e:
                n = f"错误:{e}"
            print(f"  {n:>4}  {sel}")

        print("\n[probe] 完成。把 debug_page.html 发我,或告诉我上面哪个选择器命中数正常(比如 20~50)。")
        input(">>> 看完后按回车关闭浏览器...")
        browser.close()


if __name__ == "__main__":
    main()
