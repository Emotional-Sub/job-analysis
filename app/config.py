"""
项目配置:从 .env 读取数据库连接、爬虫参数等。
用法:先把 .env.example 复制成 .env 并填好自己的 MySQL 密码。
"""
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件
load_dotenv(BASE_DIR / ".env")

# ---------- MySQL 配置 ----------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "job_analysis")

# SQLAlchemy 连接串(pymysql 驱动)
DB_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# ---------- 爬虫配置 ----------
# 搜索关键词(默认爬这些岗位)
KEYWORDS = os.getenv("KEYWORDS", "Python,Java,前端,数据分析").split(",")

# 目标城市列表。循环这些城市抓取,才能让"各城市"相关图表有横向对比价值。
# 只想抓单个城市时,把 .env 里的 CITIES 设成一个即可。
CITIES = os.getenv(
    "CITIES",
    "上海,北京,深圳,重庆,广州,苏州,成都,杭州,武汉,南京,"
    "宁波,天津,青岛,无锡,长沙,郑州,福州,济南,合肥,西安",
).split(",")

# 51job 城市编码映射:搜索 URL 用 jobArea=编码 来按城市过滤。
# 这些是 51job 常用的城市区域码。若某城市抓不到结果(跑完看城市分布是 0),
# 多半是码变了:到 51job 网页手动筛该城市,看地址栏 jobArea= 后面的数字更正。
CITY_CODES = {
    "北京": "010000",
    "上海": "020000",
    "广州": "030200",
    "深圳": "040000",
    "重庆": "060000",
    "天津": "050000",
    "杭州": "080200",
    "宁波": "080300",
    "成都": "090200",
    "南京": "070200",
    "苏州": "070300",
    "无锡": "070400",
    "武汉": "180200",
    "长沙": "190200",
    "郑州": "170200",
    "西安": "200200",
    "青岛": "120300",
    "济南": "120200",
    "福州": "110200",
    "合肥": "150200",
    "全国": "000000",
}

# 猎聘城市编码映射:搜索 URL 用 dq=编码 按城市过滤(猎聘用行政区划码,与 51job 不同)。
# 若某城市抓不到结果,到猎聘网页手动筛该城市,看地址栏 dq= 后面的数字更正。
# 猎聘城市编码(dq= 行政区划码)。顺序与 CITIES 一致(1~20)。
# 2026-07 全表核对更正:旧配置里长沙/青岛/福州/济南/合肥/宁波/无锡等码错误,
# 导致按"某城"搜索实际抓到贵阳/金华/长春/安顺等外地岗位。以下为核对后的正确码。
LIEPIN_CITY_CODES = {
    "上海": "020",      # 1
    "北京": "010",      # 2
    "深圳": "050090",   # 3
    "重庆": "040",      # 4
    "广州": "050020",   # 5
    "苏州": "060080",   # 6
    "成都": "280020",   # 7
    "杭州": "070020",   # 8
    "武汉": "170020",   # 9
    "南京": "060020",   # 10
    "宁波": "070030",   # 11
    "天津": "030",      # 12
    "青岛": "250070",   # 13
    "无锡": "060100",   # 14
    "长沙": "180020",   # 15
    "郑州": "150020",   # 16
    "福州": "090020",   # 17
    "济南": "250020",   # 18
    "合肥": "080020",   # 19
    "西安": "270020",   # 20
    "全国": "000",
}

# 目标城市(城市编码见各站点,这里用名称,后面爬虫里映射)
CITY = os.getenv("CITY", "全国")

# 每个关键词最多爬多少页(先小一点跑通)
MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))

# 请求间隔(秒),防止爬太快被封。这是"基础"延迟,实际等待 = 基础 + 随机抖动。
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "10"))

# 随机抖动上限(秒)。固定间隔本身就是一种可被识别的访问模式(每次都精确 N 秒),
# 反爬会盯这个规律性。每次请求在 [REQUEST_DELAY, REQUEST_DELAY+REQUEST_JITTER]
# 之间随机取值,让节奏看起来更像人。设 0 则退回固定间隔。
REQUEST_JITTER = float(os.getenv("REQUEST_JITTER", "5"))


def request_delay_seconds() -> float:
    """返回本次请求应等待的秒数:基础延迟 + [0, REQUEST_JITTER] 的随机抖动。"""
    return REQUEST_DELAY + random.uniform(0, REQUEST_JITTER)


def sleep_between_requests() -> None:
    """按带抖动的间隔阻塞等待。爬虫主循环统一调这个,不要再直接 time.sleep 固定值。"""
    time.sleep(request_delay_seconds())

# 是否显示浏览器窗口(True=看得见,调试用;False=无头,正式跑用)
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"

# 浏览器登录状态保存路径(首次手动登录后复用,免得每次登录)
STORAGE_STATE = str(BASE_DIR / "storage_state.json")
