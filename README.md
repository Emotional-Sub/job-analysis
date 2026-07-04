# 招聘数据爬取与可视化分析系统

基于 Python 的招聘岗位数据采集、清洗、存储与可视化分析系统。面向计算机相关岗位（Python / Java / 前端 / 数据分析等），采集招聘数据后清洗入库，通过 Web 端交互式图表展示薪资、城市、学历、技能等多维度分析结果。

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| 采集层 | Playwright | 驱动真实浏览器，处理动态渲染 / 登录页 |
| 存储层 | MySQL 8 + SQLAlchemy | 关系型存储，ORM 操作 |
| 展示层 | Flask + ECharts | 后端提供 JSON 接口，前端渲染交互图表 |
| 数据处理 | pandas | 数据清洗与分析 |
| 加分项 | APScheduler / scikit-learn | 定时爬取 / 薪资预测（规划中） |

## 目录结构

```
job-analysis/
├── app/
│   ├── config.py            # 配置：从 .env 读取数据库密码、爬取参数
│   ├── db/
│   │   ├── models.py        # 数据表模型：raw_job（原始）+ job（清洗后）
│   │   └── session.py       # 数据库连接、建库建表
│   ├── spider/
│   │   ├── utils.py         # 薪资解析、学历/经验归一化等清洗工具
│   │   └── spider_51job.py  # 爬虫主体（demo / real 两种模式）
│   └── web/
│       ├── app.py           # Flask 应用：页面路由 + JSON 接口
│       ├── stats.py         # 统计查询层：聚合出图表所需数据
│       └── templates/
│           └── index.html   # 前端页面 + ECharts 图表
├── run_spider.py            # 爬虫入口
├── run_web.py               # Web 服务入口
├── requirements.txt         # 依赖清单
├── .env.example             # 配置模板（复制为 .env 后填写）
└── .gitignore
```

## 数据库设计

采用**双表分离**设计，将「采集」与「分析」解耦：

- **raw_job（原始岗位表）**：爬虫直接写入，尽量保留站点原始字段，仅做去重。重爬不影响已清洗数据。
- **job（分析岗位表）**：清洗后的结构化数据，可视化与预测均基于此表。薪资统一折算为「千元/月」，存 `salary_min` / `salary_max` / `salary_avg`。

清洗逻辑改动后，可从 `raw_job` 重新生成 `job`，对应论文中的「数据清洗」环节。

## 快速开始

### 1. 环境准备

- Python 3.11
- MySQL 8

### 2. 安装依赖

```bash
# 创建并激活虚拟环境（Windows）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器（真实抓取时需要）
playwright install chromium
```

### 3. 配置数据库

复制 `.env.example` 为 `.env`，填入自己的 MySQL 连接信息：

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=job_analysis
```

### 4. 采集数据

```bash
# demo 模式：用样例数据跑通「清洗 -> 入库」全流程，验证环境（不联网）
python run_spider.py --demo

# real 模式：真实抓取 51job（页面选择器需按实际页面核对微调）
python run_spider.py --real
```

### 5. 启动可视化网站

```bash
python run_web.py
```

浏览器打开 http://localhost:5000 查看分析看板。

## 可视化维度

首页看板包含以下图表：

- **概览卡片**：总岗位数、覆盖城市数、平均薪资、最高薪资
- **各职位平均薪资**：柱状图，对比不同技术方向薪资水平
- **城市岗位数量 Top 10**：反映各城市招聘热度
- **城市平均薪资 Top 10**：反映各城市薪资水平
- **学历要求分布**：饼图
- **经验要求分布**：饼图
- **技能标签词频 Top 20**：反映市场对各项技能的需求热度

## 命令速查

```bash
python run_spider.py --demo     # 样例数据跑通管道
python run_spider.py --real     # 真实抓取 51job
python run_web.py               # 启动可视化网站
python -m app.spider.utils      # 单测薪资解析函数
```

## 说明

- `--real` 模式的页面选择器为示意性写法，招聘站反爬较强且页面结构常变，需对照 51job 真实页面用浏览器开发者工具核对后微调。
- `.env` 文件包含数据库密码，已在 `.gitignore` 中排除，不会提交到版本库。
