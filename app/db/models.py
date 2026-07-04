"""
数据库表结构(SQLAlchemy ORM 模型)。

设计说明:
- raw_job    原始岗位表:爬虫直接写入,尽量保留原站点字段,不做清洗。
- job        分析岗位表:清洗后的结构化数据,可视化和预测都基于这张表。
  两张表分开,是为了"采集"和"分析"解耦 —— 重爬不影响已清洗数据,
  清洗逻辑改了也能从 raw_job 重新生成。论文里对应"数据清洗"环节。

薪资统一折算成"月薪(千元/月)"存 salary_min / salary_max / salary_avg,
方便做统计和预测(原始文本如 "15-25K·13薪" 存在 salary_text 里备查)。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RawJob(Base):
    """原始岗位表:爬到什么存什么,只做去重。"""

    __tablename__ = "raw_job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 站点内的岗位唯一标识(用于去重),配合 source 保证唯一
    source = Column(String(20), nullable=False, comment="数据来源站点,如 boss/lagou")
    job_key = Column(String(128), nullable=False, comment="站点内岗位唯一标识")

    title = Column(String(200), comment="岗位名称")
    salary_text = Column(String(100), comment="薪资原始文本,如 15-25K·13薪")
    city = Column(String(50), comment="城市")
    area = Column(String(100), comment="区域,如 朝阳区")
    experience = Column(String(50), comment="经验要求原文,如 3-5年")
    education = Column(String(50), comment="学历要求原文,如 本科")

    company = Column(String(200), comment="公司名称")
    company_size = Column(String(50), comment="公司规模原文,如 100-499人")
    industry = Column(String(100), comment="所属行业")

    tags = Column(Text, comment="技能标签,原始文本(逗号或空格分隔)")
    keyword = Column(String(50), comment="爬取时用的搜索关键词")
    detail_url = Column(String(500), comment="岗位详情页链接")

    crawled_at = Column(DateTime, default=datetime.now, comment="爬取时间")

    __table_args__ = (
        UniqueConstraint("source", "job_key", name="uq_source_jobkey"),
        Index("idx_raw_keyword", "keyword"),
        {"mysql_charset": "utf8mb4", "comment": "原始岗位表"},
    )

    def __repr__(self):
        return f"<RawJob {self.title} @ {self.company}>"


class Job(Base):
    """分析岗位表:清洗后的结构化数据,可视化/预测都用这张。"""

    __tablename__ = "job"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    source = Column(String(20), nullable=False, comment="数据来源站点")
    job_key = Column(String(128), nullable=False, comment="站点内岗位唯一标识")

    title = Column(String(200), comment="岗位名称")
    keyword = Column(String(50), comment="搜索关键词(职位大类)")

    # 薪资统一折算成 千元/月
    salary_min = Column(Float, comment="最低月薪(千元/月)")
    salary_max = Column(Float, comment="最高月薪(千元/月)")
    salary_avg = Column(Float, comment="平均月薪(千元/月),用于统计和预测")
    salary_text = Column(String(100), comment="薪资原始文本")

    city = Column(String(50), comment="城市")
    experience = Column(String(50), comment="经验要求(归一化后)")
    education = Column(String(50), comment="学历要求(归一化后)")

    company = Column(String(200), comment="公司名称")
    company_size = Column(String(50), comment="公司规模")
    industry = Column(String(100), comment="所属行业")

    tags = Column(Text, comment="技能标签,逗号分隔(清洗后)")

    crawled_at = Column(DateTime, comment="原始爬取时间")
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="清洗更新时间"
    )

    __table_args__ = (
        UniqueConstraint("source", "job_key", name="uq_job_source_jobkey"),
        Index("idx_job_keyword", "keyword"),
        Index("idx_job_city", "city"),
        Index("idx_job_salary", "salary_avg"),
        {"mysql_charset": "utf8mb4", "comment": "清洗后的分析岗位表"},
    )

    def __repr__(self):
        return f"<Job {self.title} {self.salary_avg}k @ {self.city}>"
