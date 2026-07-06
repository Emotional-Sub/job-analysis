"""
项目配置:从 .env 读取数据库连接、爬虫参数等。
用法:先把 .env.example 复制成 .env 并填好自己的 MySQL 密码。
"""
import os
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
LIEPIN_CITY_CODES = {
    "北京": "010",
    "上海": "020",
    "广州": "050020",
    "深圳": "050090",
    "重庆": "040",
    "天津": "030",
    "杭州": "070020",
    "宁波": "070060",
    "成都": "280020",
    "南京": "060020",
    "苏州": "060080",
    "无锡": "060050",
    "武汉": "170020",
    "长沙": "190020",
    "郑州": "150020",
    "西安": "270020",
    "青岛": "120050",
    "济南": "120020",
    "福州": "091",
    "合肥": "140020",
    "全国": "000",
}

# 目标城市(城市编码见各站点,这里用名称,后面爬虫里映射)
CITY = os.getenv("CITY", "全国")

# 每个关键词最多爬多少页(先小一点跑通)
MAX_PAGES = int(os.getenv("MAX_PAGES", "3"))

# 请求间隔(秒),防止爬太快被封
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "3"))

# 是否显示浏览器窗口(True=看得见,调试用;False=无头,正式跑用)
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"

# 浏览器登录状态保存路径(首次手动登录后复用,免得每次登录)
STORAGE_STATE = str(BASE_DIR / "storage_state.json")
