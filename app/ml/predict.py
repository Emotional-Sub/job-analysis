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
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app import config
from app.db.session import get_session
from app.db.models import Job

# 模型文件路径(与本模块同目录)
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")

# 参与训练的类别特征列
CAT_FEATURES = ["city", "education", "experience", "keyword"]


def _load_dataframe() -> pd.DataFrame:
    """从 job 表读出训练数据,返回 DataFrame(只保留有薪资和关键特征的行)。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.city,
                Job.education,
                Job.experience,
                Job.keyword,
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
        rows, columns=["city", "education", "experience", "keyword", "salary_avg"]
    )
    return df


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
    """把 One-Hot 编码器和回归模型串成一条 sklearn Pipeline。"""
    encoder = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
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

    X = df[CAT_FEATURES]
    y = df["salary_avg"]

    # 留出测试集用于报告最终误差(交叉验证用于选型)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    scores: List[Dict] = []
    best_name = None
    best_r2 = float("-inf")
    best_pipeline = None

    for name, model in _build_models().items():
        pipe = _make_pipeline(model)
        # 5 折交叉验证的 R²(在训练集上,用于公平选型)
        cv_r2 = cross_val_score(pipe, X_train, y_train, cv=5, scoring="r2")
        # 在测试集上训练后评估 MAE / R²(用于报告)
        pipe.fit(X_train, y_train)
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

    # 用全量数据重训最优模型(交叉验证只为选型,最终模型吃满所有数据)
    best_pipeline.fit(X, y)

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

    report = {
        "n_samples": n,
        "scores": scores,
        "best_model": best_name,
        "feature_options": feature_options,
    }

    # 持久化:最优模型 + 报告一起存
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"pipeline": best_pipeline, "report": report}, f)

    return report


# ---------------- 预测(Web 端调用) ----------------
_CACHE: Optional[Dict] = None


def _load() -> Optional[Dict]:
    """加载并缓存 model.pkl。没训练过则返回 None。"""
    global _CACHE
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
    X = pd.DataFrame(
        [{"city": city, "education": education,
          "experience": experience, "keyword": keyword}]
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
