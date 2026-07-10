"""
薪资预测模型:根据城市、学历、经验、职位、技能预测月薪(千元/月)。

设计说明
--------
1. 特征都是类别型(城市/学历/经验/职位)+ 多标签(技能),用 One-Hot 编码。
2. 训练三个模型对比:线性回归、随机森林、梯度提升,用交叉验证的
   MAE(平均绝对误差)和 R²(拟合优度)评分,选 R² 最高的持久化。
3. 训练结果(最优模型 + 编码器 + 三模型评分)一起 pickle 到 model.pkl,
   Web 端加载后即可对用户输入实时预测。

论文里对应"薪资预测模型设计与实现"一章:特征工程 -> 多模型对比 -> 选型 -> 应用。

诚实说明:招聘数据薪资本身噪声大(同岗位不同公司差异悬殊),列表页可用
特征有限(没有公司规模、具体 JD),所以 R² 不会很高——这是这类问题的
固有难度,如实报告并分析原因,比虚标精度更有价值。
"""
import os
import pickle
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app import config
from app.db.session import get_session
from app.db.models import Job

# 模型文件路径(与本模块同目录)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

# 参与训练的特征:类别特征走 One-Hot,数值特征直接透传。
# 相比最初只有 city/education/experience,这里补了两类信号:
#   - keyword / source:岗位方向、数据来源(不同站点薪资口径有差异)
#   - skill_count:岗位要求的技能数量(要求越多通常越高级、薪资越高),
#     这是唯一的数值特征,能给模型一点"岗位复杂度"的量化信号。
CAT_FEATURES = ["city", "education", "experience", "keyword", "source"]
NUM_FEATURES = ["skill_count"]
FEATURES = CAT_FEATURES + NUM_FEATURES
# 特征中文名(展示"特征重要性图"时用,比英文列名友好)
FEATURE_LABELS = {
    "city": "城市",
    "education": "学历",
    "experience": "经验",
    "keyword": "职位方向",
    "source": "数据来源",
    "skill_count": "技能数量",
}


def _load_dataframe() -> pd.DataFrame:
    """从 job 表读出训练数据,返回 DataFrame(只保留有薪资和关键特征的行)。

    skill_count 由 tags(逗号分隔的技能串)现算:有几个技能就是几。
    tags 为空则记 0。
    """
    session = get_session()
    try:
        rows = (
            session.query(
                Job.city,
                Job.education,
                Job.experience,
                Job.keyword,
                Job.source,
                Job.tags,
                Job.salary_avg,
            )
            .filter(
                Job.salary_avg.isnot(None),
                Job.city.isnot(None),
                Job.education.isnot(None),
                Job.experience.isnot(None),
                Job.keyword.isnot(None),
            )
            .all()
        )
    finally:
        session.close()

    df = pd.DataFrame(
        rows,
        columns=[
            "city", "education", "experience", "keyword",
            "source", "tags", "salary_avg",
        ],
    )
    # 由 tags 派生技能数量:非空逗号串的元素个数
    df["skill_count"] = (
        df["tags"].fillna("").apply(
            lambda s: len([t for t in str(s).split(",") if t.strip()])
        )
    )
    # source 偶有缺失,填一个占位类别,避免 One-Hot 报错
    df["source"] = df["source"].fillna("unknown")
    return df


def _experience_weights(experience: pd.Series) -> np.ndarray:
    """按经验档算样本权重,缓解"1年以下"占 74% 导致的类别不平衡。

    用逆频率权重(balanced):某档权重 = 总样本 /(档数 × 该档样本数)。
    效果:样本越多的档单条权重越低、越少的档越高,让模型训练时不被
    低经验样本淹没,各经验档"话语权"趋于均衡。权重均值归一化到 1,
    不改变整体量级,只重新分配关注度 —— 数据一条不丢(A 方案:类别加权)。

    为什么不直接降采样:降采样会扔掉上万条真实低经验样本,且高经验档
    (365/658 条)本就少,均衡度提升有限。加权不丢数据、答辩好讲。
    """
    counts = experience.value_counts()
    n_total = len(experience)
    n_classes = len(counts)
    # 每档的逆频率权重
    w_per_class = {
        cls: n_total / (n_classes * cnt) for cls, cnt in counts.items()
    }
    w = experience.map(w_per_class).to_numpy(dtype=float)
    # 归一化到均值 1,避免影响学习率/正则的量级尺度
    w = w / w.mean()
    return w


def _build_models() -> Dict[str, object]:
    """返回待对比的三个回归模型(名称 -> 未训练的模型实例)。"""
    return {
        "线性回归": LinearRegression(),
        "随机森林": RandomForestRegressor(
            n_estimators=200, max_depth=12, random_state=42, n_jobs=-1
        ),
        "梯度提升": GradientBoostingRegressor(
            n_estimators=200, max_depth=3, random_state=42
        ),
    }


def _make_pipeline(model) -> Pipeline:
    """把预处理(类别 One-Hot + 数值透传)和回归模型串成一条 sklearn Pipeline。"""
    encoder = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
            ("num", "passthrough", NUM_FEATURES),
        ]
    )
    return Pipeline([("encoder", encoder), ("model", model)])


def train() -> Dict:
    """
    训练入口:读数据 -> 三模型交叉验证对比 -> 选最优 -> 持久化。
    返回训练报告(样本数 + 三模型评分 + 最优模型名)。
    """
    df = _load_dataframe()
    n = len(df)
    if n < 50:
        raise RuntimeError(
            f"训练样本太少({n}条),先跑采集补充数据再训练。"
        )

    X = df[FEATURES]
    y = df["salary_avg"]
    # 样本权重(按经验档逆频率),用于训练时缓解类别不平衡(A 方案)
    w = _experience_weights(df["experience"])

    # 留出测试集用于报告最终误差(交叉验证用于选型)。
    # stratify=经验档(C 方案):保证训练/测试集的经验分布与全量一致,
    # 否则完全随机划分下高经验档(仅几百条)可能在测试集里只剩个位数,
    # 评估不可信。权重跟着一起划分,保持与 X/y 行对齐。
    X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
        X, y, w, test_size=0.2, random_state=42, stratify=df["experience"]
    )

    scores: List[Dict] = []
    best_name = None
    best_r2 = float("-inf")
    best_pipeline = None

    # 显式用「打乱」的 5 折 KFold。数据是按抓取批次(城市→关键词→来源)插入的,
    # 默认 cv=5 等价 shuffle=False,折叠会按批次切分导致某些城市/来源在折内被过度
    # 代表,CV-R² 高方差且选型结果run-to-run 不稳。shuffle=True + 固定种子保证可复现。
    cv = KFold(n_splits=5, shuffle=True, random_state=42)

    for name, model in _build_models().items():
        pipe = _make_pipeline(model)
        # Pipeline 里给最后一步(model)传样本权重的语法:"<步骤名>__sample_weight"。
        # 步骤名是 "model"(见 _make_pipeline)。三个模型都支持 sample_weight。
        fit_kw = {"model__sample_weight": w_train}
        # 5 折交叉验证的 R²(在训练集上,用于公平选型)。带权重训练(A 方案)。
        cv_r2 = cross_val_score(
            pipe, X_train, y_train, cv=cv, scoring="r2", params=fit_kw
        )
        # 在测试集上训练后评估 MAE / R²(用于报告),同样带权重训练
        pipe.fit(X_train, y_train, **fit_kw)
        pred = pipe.predict(X_test)
        mae = mean_absolute_error(y_test, pred)
        r2 = r2_score(y_test, pred)

        scores.append({
            "model": name,
            "cv_r2": round(float(cv_r2.mean()), 3),   # 交叉验证 R²(选型依据)
            "test_r2": round(float(r2), 3),           # 测试集 R²
            "test_mae": round(float(mae), 2),         # 测试集 MAE(千元)
        })

        if cv_r2.mean() > best_r2:
            best_r2 = cv_r2.mean()
            best_name = name
            best_pipeline = pipe

    # 特征重要性:用置换重要性(permutation importance)。
    # 原理:把某一列的值随机打乱,看模型 R² 掉多少 —— 掉得越多说明该特征越关键。
    # 它模型无关(线性/树都能用)、直接反映"对预测的贡献",比树自带的
    # feature_importances_ 更公平,论文里也好解释。
    # ⚠️ 必须在「只用训练集拟合」的模型 + 留出的测试集上算(此刻 best_pipeline 仍是
    # 循环里的 train-only 拟合结果)。若先做下面的全量 refit(X 含 X_test),再在
    # X_test 上算,测试集就成了样内数据,重要性会被高估。故顺序:先算重要性,再全量重训。
    perm = permutation_importance(
        best_pipeline, X_test, y_test,
        n_repeats=10, random_state=42, scoring="r2",
    )
    # 归一化成占比(相对重要性),前端画柱状图更直观。负值(打乱后反而更好,
    # 属噪声)裁剪为 0。按重要性降序。
    raw = {f: max(float(v), 0.0) for f, v in zip(FEATURES, perm.importances_mean)}
    total_imp = sum(raw.values()) or 1.0
    feature_importance = sorted(
        [
            {"feature": FEATURE_LABELS.get(f, f), "importance": round(v / total_imp, 4)}
            for f, v in raw.items()
        ],
        key=lambda d: d["importance"],
        reverse=True,
    )

    # 收集每个特征的可选值,供前端下拉框用。
    # 城市特别处理:只列 config 里的目标城市(且训练数据里确实出现过的),
    # 避免把 51job 带出的周边县市、猎聘杂散城市都塞进下拉框(那样有 50+ 项,乱)。
    target_cities = [c.strip() for c in config.CITIES]
    seen_cities = set(df["city"].dropna().unique().tolist())
    feature_options = {}
    for col in CAT_FEATURES:
        if col == "city":
            feature_options[col] = [c for c in target_cities if c in seen_cities]
        else:
            feature_options[col] = sorted(df[col].dropna().unique().tolist())

    # 重要性算完后,再用全量数据重训最优模型持久化(交叉验证/重要性只为选型与解释,
    # 最终上线模型吃满所有数据)。带全量样本权重(A 方案),与选型口径一致。
    best_pipeline.fit(X, y, model__sample_weight=w)

    report = {
        "n_samples": n,
        "scores": scores,
        "best_model": best_name,
        "feature_options": feature_options,
        "feature_importance": feature_importance,
    }

    # 持久化:最优模型 + 报告一起存
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"pipeline": best_pipeline, "report": report}, f)

    return report


# ---------------- 预测(Web 端调用) ----------------
_CACHE: Optional[Dict] = None
_CACHE_LOCK = threading.Lock()


def _load() -> Optional[Dict]:
    """加载并缓存 model.pkl。没训练过则返回 None。线程安全(Flask 多线程下首次并发不会重复加载)。"""
    global _CACHE
    if _CACHE is None:
        with _CACHE_LOCK:
            # 双重检查:拿到锁后再确认一次,避免多个线程都进来重复读盘
            if _CACHE is None:
                if not os.path.exists(MODEL_PATH):
                    return None
                with open(MODEL_PATH, "rb") as f:
                    _CACHE = pickle.load(f)
    return _CACHE


def get_report() -> Optional[Dict]:
    """返回训练报告(模型评分对比 + 特征可选值)。未训练则 None。"""
    data = _load()
    return data["report"] if data else None


def predict(
    city: str, education: str, experience: str, keyword: str
) -> Optional[float]:
    """
    对单条输入预测月薪(千元/月)。模型未训练时返回 None。
    """
    data = _load()
    if not data:
        return None
    pipe = data["pipeline"]
    # 前端只提供 4 个字段;模型还吃 source / skill_count,给合理默认值:
    #   source     -> "51job"(样本量最大的来源,最具代表性)
    #   skill_count-> 2(岗位技能数的典型值),让预测落在常规区间
    X = pd.DataFrame(
        [{"city": city, "education": education,
          "experience": experience, "keyword": keyword,
          "source": "51job", "skill_count": 2}]
    )
    pred = pipe.predict(X)[0]
    # 薪资不会为负,兜底裁剪
    return round(max(float(pred), 0.0), 1)


if __name__ == "__main__":
    # 直接运行本文件即训练:python -m app.ml.predict
    rep = train()
    print(f"训练完成,样本 {rep['n_samples']} 条,最优模型:{rep['best_model']}")
    print("模型对比:")
    for s in rep["scores"]:
        print(f"  {s['model']:8s}  CV-R²={s['cv_r2']:.3f}  "
              f"测试R²={s['test_r2']:.3f}  MAE={s['test_mae']:.2f}K")
