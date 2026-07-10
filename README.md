# 招聘数据爬取与可视化分析系统

基于 Python 的招聘岗位数据采集、清洗、存储、可视化与薪资预测系统。面向计算机相关岗位（Python / Java / 前端 / 数据分析等），从多个招聘站点采集数据后清洗入库，通过 Web 端交互式图表展示薪资、城市、学历、经验、技能等多维度分析结果，并提供基于机器学习的薪资预测。

## 技术栈

| 层次 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 语言 / 运行 | Python | 3.11 | — |
| 采集层 | Playwright | 1.49.0 | 驱动真实 Chromium，处理动态渲染 / 登录态复用（storage_state），支持断点续抓 |
| 存储层 | MySQL 8 + SQLAlchemy | 2.0.36 | 关系型存储，ORM 建模，双表（raw_job / job）分离；utf8mb4 |
| 数据库驱动 | PyMySQL + cryptography | 1.1.1 / 44.0.0 | MySQL 8 的 caching_sha2 认证需要 cryptography |
| 数据处理 | pandas | 2.2.3 | 清洗、聚合、喂给模型 |
| 展示层（后端） | Flask | 3.1.0 | 提供页面路由 + 15+ 个 JSON 接口 |
| 展示层（前端） | ECharts 5.5.0 + echarts-wordcloud 2.1.0 | CDN | 柱/饼/直方图/热力图/中国地图（china.js）/词云；原生 `fetch` 拉数据，无前端框架 |
| 预测 | scikit-learn | 1.6.0 | 三模型对比（线性回归 / 随机森林 / 梯度提升），Pipeline + One-Hot 编码，经验逆频率加权 |
| 配置 | python-dotenv | 1.0.1 | 从 `.env` 读取数据库密码、城市码、爬取参数 |
| 定时（可选） | APScheduler | 3.11.0 | 预留的定时爬取能力 |
| 测试 | pytest | 9.1.1 | 薪资解析等纯函数的单元测试 |

## 数据源

| 站点 | 采集方式 | 说明 |
|------|----------|------|
| 51job（前程无忧） | JSON 接口（Playwright 取页内数据） | 20 城 × 4 关键词；接口结构化返回，城市分布天然均衡，无需经验分档 |
| 猎聘 | HTML 列表页解析（Playwright + 正则） | 20 城 × 4 关键词；列表被实习岗稀释，按经验分档抓取，爬虫端过滤实习/兼职岗 |

两站共用同一条清洗 + 入库管道（`app/spider/pipeline.py`），靠 `source` 字段区分来源，数据都进同一张 `job` 表。Web 端支持「多源对比」维度（各源岗位量、薪资、学历分布对比）。

## 数据现状

> 以下是最近一次全量采集 + 清洗后的库存快照（截至 2026-07），论文中引用具体数字时以实际数据库为准（跑 `python scripts/db_health_check.py` 可随时复核）。

| 指标 | 数值 | 说明 |
|------|------|------|
| 总岗位数 | **27305** | `job` 与 `raw_job` 两表口径一致，各 27305 条，零重复 |
| 覆盖城市 | 20 | 一线 + 新一线 + 主要二线（见 `app/config.py` 的 20 城白名单） |
| 关键词 | 4 | 数据分析 8701 / Python 7835 / Java 5558 / 前端 5211 |
| 来源分布 | 猎聘 25057 + 51job 2248 | 猎聘按经验分档抓取，覆盖量更大 |
| 有效薪资样本 | 26870 | 其余约 435 条为「薪资面议」，统计/建模时过滤 |

数据分布的两个已知特征（论文「数据质量分析」环节可直接引用）：

- **经验以「1-3 年」为主**：约 84% 的岗位要求 1-3 年经验，其余为 1 年以下(8%)、3-5 年、5-10 年、应届。这符合技术岗招聘以初中级为主力的市场规律。（注:早期 `clean_experience` 有一处取值 bug 曾把大量「1-3 年」误归为「1 年以下」，已在 2026-07 修复并用 `scripts/reclean_from_raw.py` 从原始表重清洗，此为修正后分布。）建模时仍保留经验档**逆频率加权 + 分层划分**（见「薪资预测模型」）。
- **学历梯度清晰**：大专 → 本科 → 硕士 → 博士，中位薪资单调递增（9.5K → 13.5K → 22.5K → 35K），是薪资最强的解释因素（见「分析纵深」）。

## 目录结构

```
job-analysis/
├── app/
│   ├── config.py                # 配置：从 .env 读取数据库密码、城市码、爬取参数
│   ├── db/
│   │   ├── models.py            # 数据表模型：raw_job（原始）+ job（清洗后）
│   │   └── session.py           # 数据库连接、建库建表
│   ├── spider/
│   │   ├── utils.py             # 薪资解析、学历/经验归一化、技能抽取等清洗工具
│   │   ├── checkpoint.py        # 断点续抓：记录已完成的 城市×关键词
│   │   ├── pipeline.py          # 采集管道：清洗 + 双表落库
│   │   ├── spider_51job.py      # 51job 爬虫（demo / real 两种模式）
│   │   └── spider_liepin.py     # 猎聘爬虫（含实习岗过滤）
│   ├── ml/
│   │   ├── predict.py           # 模型训练与预测（多模型对比、持久化）
│   │   └── model.pkl            # 训练好的最优模型
│   └── web/
│       ├── app.py               # Flask 应用：页面路由 + JSON 接口
│       ├── stats.py             # 统计查询层：聚合出图表所需数据
│       └── templates/
│           └── index.html       # 前端页面 + ECharts 图表
├── tests/
│   └── test_parse_salary.py     # 薪资解析单元测试
├── scripts/                     # 维护脚本 + 分析脚本 + 页面探针（从项目根用 python scripts/xxx.py 运行）
│   ├── db_health_check.py       # 只读体检：两表条数/口径/重复/名单外城市/空值/薪资异常/各维度分布
│   ├── stats_by_experience.py   # 只读：按经验档分层看数量/占比/薪资中位数与均值
│   ├── salary_inference.py      # 只读：薪资影响因素统计推断（ANOVA + 效应量 + 事后 t 检验 + 相关）
│   ├── skill_analysis.py        # 只读：技能共现网络 + 技能薪资溢价 + 词云
│   ├── backfill_raw_job.py      # 从 job 表回填 raw_job（双表落库后基本用不上）
│   ├── clean_51job_intern.py    # 清理 51job 实习/兼职岗
│   ├── clean_liepin_intern.py   # 清理猎聘实习/兼职岗
│   ├── clean_nontech.py         # 清理「数据分析」带出的跨行业非 IT 岗（白保护+黑名单两级过滤）
│   ├── clean_offlist_cities.py  # 清理 20 城白名单外的数据
│   ├── clean_annual_as_monthly.py # 清理年薪被当月薪误算的异常（阈值判定、两表同删）
│   ├── fix_salary.py            # 用最新 parse_salary 重算全库薪资
│   ├── probe_51job.py           # 探测 51job 页面结构（反爬/结构变动时用）
│   ├── probe_liepin.py          # 探测猎聘页面结构
│   └── out/                     # 分析脚本产物输出（技能共现图 JSON、词云图片等）
├── run_spider.py                # 爬虫入口
├── run_web.py                   # Web 服务入口
├── train_model.py               # 薪资预测模型训练入口
├── requirements.txt             # 依赖清单
├── .env.example                 # 配置模板（复制为 .env 后填写）
└── .gitignore
```

## 数据库设计

采用**双表分离**设计，将「采集」与「分析」解耦：

- **raw_job（原始岗位表）**：爬虫直接写入，尽量保留站点原始字段，仅做去重。重爬不影响已清洗数据。
- **job（分析岗位表）**：清洗后的结构化数据，可视化与预测均基于此表。薪资统一折算为「千元/月」，存 `salary_min` / `salary_max` / `salary_avg`。

两表都以 `(source, job_key)` 唯一约束去重（`job_key` 取详情页岗位 id），并在 `keyword` / `city` / `salary_avg` 上建索引。采集管道 `pipeline.py` 一次落地双表，两表口径保持一致。清洗逻辑改动后，可从 `raw_job` 重新生成 `job`，对应论文中的「数据清洗」环节。

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
# demo 模式：用样例数据跑通「清洗 -> 双表入库」全流程，验证环境（不联网，仅灌少量样例）
python run_spider.py --site 51job

# real 模式：真实抓取（--real 才真正联网抓取）
python run_spider.py --real --site 51job     # 抓 51job
python run_spider.py --real --site liepin     # 抓猎聘
python run_spider.py --real --site all        # 两站都抓
```

真实抓取支持**断点续抓**：中断后重跑会跳过已完成的「城市×关键词」组合。

### 5. 训练薪资预测模型

```bash
python train_model.py
```

从 job 表读数据，对比线性回归 / 随机森林 / 梯度提升三个模型，选交叉验证 R² 最优者持久化到 `app/ml/model.pkl`，供 Web 端 `/api/predict` 调用。数据更新后重跑即可用最新数据重训。

**当前模型结果**（基于 26851 条有效薪资样本，梯度提升最优）：

| 模型 | 交叉验证 R² | 测试集 R² | MAE（K/月） |
|------|-----------|----------|------------|
| 线性回归 | 0.218 | 0.228 | 6.90 |
| 随机森林 | 0.283 | 0.282 | 6.37 |
| **梯度提升（最优）** | **0.287** | **0.293** | **6.41** |

R²≈0.31 看似不高，但这是招聘薪资数据的**固有上限**：薪资还受岗位描述、公司规模、面试议价等大量**不可观测因素**影响，仅凭城市/学历/经验/方向 4 个结构化特征只能解释约三成方差。论文中这一点应作为「预测能力边界」的讨论，而非缺陷。

建模要点（`app/ml/predict.py`）：

- **特征**：城市 / 学历 / 经验 / 职位方向（关键词）/ 来源做 One-Hot（`ColumnTransformer` + `OneHotEncoder`），技能数量做数值透传，全部串进 sklearn `Pipeline`。
- **样本偏斜处理**：经验分布集中于「1-3 年」（约 84%），训练时按经验档**逆频率加权**（`sample_weight`）缓解主导档影响，且不丢数据；`train_test_split` 按经验**分层划分**，保证评估集经验分布一致。
- **特征重要性**：用 `permutation_importance`（比树自带的 `feature_importances_` 更公平，论文里也好解释；在「仅用训练集拟合」的模型 + 留出测试集上计算，避免样内高估）。当前排序：**学历 0.384 > 职位方向 0.229 > 经验 0.160 > 城市 0.124 > 数据来源 0.072 > 技能数 0.031**。学历解释力居首，与下文统计推断的 ANOVA 效应量结论互相印证。
- **预测**：Web 端只需输入城市 / 学历 / 经验 / 职位方向，模型对 source / 技能数量取代表性默认值补齐。

> 注意：预测走的是训练时冻结的 `model.pkl` 文件，`run_web.py` 只加载、不训练。数据变动后要让预测跟上，必须重跑 `train_model.py`；而图表统计页是实时查库的，改数据刷新即生效。

### 6. 启动可视化网站

```bash
python run_web.py
```

浏览器打开 http://localhost:5000 查看分析看板。

## 可视化维度

首页看板包含以下图表：

- **概览卡片**：总岗位数、覆盖城市数、平均薪资、最高薪资
- **各职位平均薪资**：柱状图，对比不同技术方向薪资水平
- **城市岗位数量 / 平均薪资 Top 10**：反映各城市招聘热度与薪资水平
- **城市薪资地图**：全国地图按城市薪资上色
- **学历 / 经验要求分布**：饼图
- **技能标签词云**：反映市场对各项技能的需求热度
- **各技能平均薪资**：不同技能方向的薪资对比
- **薪资分布直方图**：反映整体薪资集中区间
- **薪资影响因素相关性热力图**：经验 / 学历 / 技能等与薪资的相关性
- **多源对比**：各数据源的岗位量、薪资、学历分布对比
- **薪资预测**：输入城市/职位/经验/学历，实时预测薪资区间
- **数据导出**：`/api/export.csv` 导出全量数据为 CSV

## 数据分析与统计推断

除了描述性的可视化图表，项目还提供两个**只读**分析脚本，把「画图展示」提升为「有假设检验与效应量的统计分析」，为论文分析章提供可复现的证据链。两个脚本都只做 `SELECT`，不写库、不影响采集/建模，从项目根运行即可。

### 核心研究问题

> **哪些因素真正决定 IT 岗位薪资？能预测到什么程度？**

围绕这个问题，全流程串成一条论证链：

```
相关性热力图（初筛线性关联）
   → 假设检验 ANOVA（确认差异是否显著 + η² 量化解释力）
   → 事后两两对比 t 检验 + Cohen's d（差异具体有多大）
   → 随机森林特征重要性（模型视角的因素排序，交叉验证结论）
   → 模型 R²≈0.31（能预测到什么程度 + 其余靠不可观测因素解释）
```

### 模块 A：薪资影响因素统计推断（`scripts/salary_inference.py`）

对**城市 / 学历 / 经验**三个因素分别做单因素方差分析（ANOVA），并计算效应量，回答「是否显著」与「差异有多大」两个不同问题：

- **ANOVA + η²（eta squared，效应量）**：F 检验判断组间差异是否显著；η² 表示该因素能解释多大比例的薪资方差。**关键**：样本量近 2.7 万时，p 值几乎必然显著，光看 p 值分不清谁更重要——只有效应量 η² 才能量化解释力（判读标准：0.01 小 / 0.06 中 / 0.14 大）。
- **事后两两对比**：对代表性组做 Welch t 检验 + Cohen's d，给出具体组间差异的标准化大小。
- **Spearman 秩相关**：验证薪资随经验档是否单调递增及其强度。

**主要结论（基于 26,870 条有效薪资样本）：**

| 因素 | ANOVA F | p 值 | 效应量 η² | 解读 |
|------|---------|------|-----------|------|
| 学历 | 1279.91 | <0.001 | **0.167（大效应）** | 解释 16.7% 薪资方差，三因素中最强 |
| 城市 | 88.42 | <0.001 | 0.059（小-中） | 解释 5.9% 方差 |
| 经验 | 213.48 | <0.001 | 0.031（小效应） | 解释 3.1% 方差，随经验单调递增 |

- 三因素对薪资的影响**均统计显著**，但 η² 揭示**学历的解释力远强于城市和经验**——这与模型 permutation 特征重要性（学历 0.384 居首）**两个独立方法互相印证**，是分析章的核心论点。
- 学历事后对比：本科→硕士 Cohen's d=-0.82、硕士→博士 d=-0.93，均为**大效应**，学历越高薪资跳跃越大。

### 模块 B：技能共现网络与薪资溢价（`scripts/skill_analysis.py`）

以 `tags`（平台标注的技能标签，干净无噪音）为主数据源，用 jieba 从岗位标题按**技能白名单**补捞技能词，先做**技能归一化**（`spring/Spring`、`golang→Go`、`K8s→Kubernetes` 等大小写与别名统一），再产出：

- **技能共现网络**：统计技能两两在同一岗位共现的次数，建共现矩阵，导出 `scripts/out/skill_graph.json` 供 ECharts 力导向图渲染。后端簇（Java-后端-测试）、数据簇（Python-算法-大数据）、前端簇（Vue-React-前端开发）自然聚合，与职位方向分类互相印证。
- **技能薪资溢价榜**：计算掌握某技能的岗位薪资中位数相对全库中位数（14.5K）的溢价百分比，量化「哪些技能更值钱」，补上「技能」这一薪资解释维度。
- **技能词云**：对归一化后的技能词生成词云图（`scripts/out/skill_wordcloud.png`），用于论文/答辩配图。

**主要结论：**

| 溢价方向 | 代表技能（相对全库中位薪资） |
|----------|------------------------------|
| 高溢价 | 算法 +83.9%、深度学习 +78.4%、C++ +55.2%、机器学习 +52.0% |
| 低于中位 | Java -6.9%、前端开发 -13.8%、数据分析 -13.8% |

- **AI / 算法方向技能溢价最高**，普及型技能（前端、Java、数据分析）供给多、薪资被压低于中位——为「技能选择影响薪资」提供了量化依据。

### 运行

```bash
python scripts/salary_inference.py              # 模块 A：统计推断（打印分析结果）
python scripts/skill_analysis.py                # 模块 B：技能共现 + 薪资溢价
python scripts/skill_analysis.py --json          # 额外导出 skill_graph.json（供前端力导向图）
python scripts/skill_analysis.py --wordcloud     # 额外生成技能词云 PNG
```

## API 接口

后端（`app/web/app.py`）提供页面路由 `/` 与一组返回 JSON 的统计接口，前端用原生 `fetch` 拉取渲染：

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/overview` | GET | 概览卡片（总岗位数、城市数、平均/最高薪资） |
| `/api/salary_by_keyword` | GET | 各职位方向平均薪资 |
| `/api/jobs_by_city` / `/api/salary_by_city` | GET | 城市岗位量 / 平均薪资 Top 10 |
| `/api/city_geo` | GET | 城市薪资地图数据 |
| `/api/education` / `/api/experience` | GET | 学历 / 经验分布 |
| `/api/skills` / `/api/salary_by_skill` | GET | 技能词云 / 各技能平均薪资 |
| `/api/salary_histogram` | GET | 薪资分布直方图 |
| `/api/salary_correlation` | GET | 薪资影响因素相关性热力图 |
| `/api/jobs_by_source` / `/api/salary_by_source` / `/api/education_by_source` / `/api/salary_by_source_keyword` | GET | 多源对比 |
| `/api/model_scores` | GET | 三模型评分对比 + 特征可选值 |
| `/api/predict` | POST | 输入城市/职位/经验/学历，返回预测薪资 |
| `/api/export.csv` | GET | 导出全量数据为 CSV |

## 测试

薪资解析（`app/spider/utils.py` 的 `parse_salary`）覆盖月薪 / 年薪 / 日薪、13 薪、混合单位（千+万）、开区间、面议等场景，用 pytest 验证：

```bash
venv\Scripts\python.exe -m pytest tests/ -v
```

## 命令速查

```bash
python run_spider.py --real --site all    # 真实抓取全部数据源
python train_model.py                     # 训练/重训薪资预测模型
python run_web.py                          # 启动可视化网站
python scripts/salary_inference.py        # 统计推断分析（ANOVA / t 检验 / 效应量）
python scripts/skill_analysis.py          # 技能共现 + 薪资溢价分析
python scripts/db_health_check.py         # 只读体检：两表口径 / 重复 / 异常一把过
python -m pytest tests/                    # 运行单元测试
python -m app.spider.utils                # 快速自测薪资解析函数
```

## 维护脚本

维护脚本都在 `scripts/` 目录下，从**项目根目录**运行（脚本内已自举 sys.path，`python scripts/xxx.py` 即可正确 import app）。清理类脚本默认**预览**，加 `--apply` 才真正改动数据。

| 脚本 | 用途 |
|------|------|
| `scripts/db_health_check.py` | **只读**体检：两表条数/口径/重复/名单外城市/关键空值/薪资异常/各维度分布一把过（不写库） |
| `scripts/stats_by_experience.py` | **只读**：按经验档分层看数量/占比/薪资中位数与均值，最大档过半自动警示 |
| `scripts/salary_inference.py` | **只读**：薪资影响因素统计推断（城市/学历/经验 ANOVA + η² + 事后 t 检验 + Cohen's d，见「数据分析与统计推断」章） |
| `scripts/skill_analysis.py` | **只读**：技能共现网络 + 薪资溢价榜 + 词云（`--json` 导出图数据、`--wordcloud` 生成词云 PNG） |
| `scripts/clean_51job_intern.py` | 清理 51job 实习/兼职岗（含否定词排除，避免误删正式岗） |
| `scripts/clean_liepin_intern.py` | 清理猎聘实习/兼职岗 |
| `scripts/clean_nontech.py` | 清理「数据分析」关键词带出的跨行业非 IT 岗（白保护技术词 + 黑名单非技术词两级过滤） |
| `scripts/clean_offlist_cities.py` | 清理 20 城白名单外的数据（两表需同口径清） |
| `scripts/clean_annual_as_monthly.py` | 清理「年薪被当月薪」的脏数据（阈值 `salary_avg>200K` 判定，两表同删） |
| `scripts/fix_salary.py` | 用最新 `parse_salary` 重算全库薪资（默认预览，`--apply` 才写库） |
| `scripts/reclean_from_raw.py` | 从 raw_job 原始字段用最新清洗函数重建 job 的 experience/education/tags（默认预览，`--apply` 才写库） |
| `scripts/backfill_raw_job.py` | 从 job 表回填 raw_job（双表同步落地后一般用不上） |

```bash
# 例：预览 51job 实习岗清理（从项目根运行）
python scripts/clean_51job_intern.py            # 预览
python scripts/clean_51job_intern.py --apply    # 确认后执行
```

## 说明

- 真实抓取的页面选择器需对照站点真实页面核对；招聘站反爬较强且页面结构常变，结构变动时可用 `scripts/probe_51job.py` / `scripts/probe_liepin.py` 重新探测。
- `.env` 文件包含数据库密码，已在 `.gitignore` 中排除，不会提交到版本库。
