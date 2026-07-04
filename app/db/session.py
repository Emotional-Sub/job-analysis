"""
数据库连接与会话管理。

- engine:全局唯一的数据库引擎。
- SessionLocal:会话工厂,每次操作数据库时 SessionLocal() 拿一个 session。
- init_db():建库(如果不存在) + 建表。第一次运行项目时调用。
"""
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config
from app.db.models import Base


# echo=False:不打印每条 SQL(调试时可改 True);pool_pre_ping:自动检测断连
engine = create_engine(config.DB_URL, echo=False, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _ensure_database():
    """如果目标数据库不存在,先用 pymysql 连到 MySQL 服务器把库建出来。"""
    conn = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
        conn.commit()
    finally:
        conn.close()


def init_db():
    """初始化数据库:建库 + 建表。幂等,重复调用安全。"""
    _ensure_database()
    Base.metadata.create_all(engine)
    print(f"[db] 数据库 `{config.DB_NAME}` 与数据表已就绪")


def get_session():
    """拿一个新的数据库会话。调用方用完记得 session.close()。"""
    return SessionLocal()


if __name__ == "__main__":
    # 直接运行本文件即可初始化数据库:python -m app.db.session
    init_db()
