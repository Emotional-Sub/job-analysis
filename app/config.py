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
