"""
薪资预测模型训练入口。

用法:
    venv/Scripts/python.exe train_model.py

从 job 表读数据,对比三个回归模型(线性回归/随机森林/梯度提升),
选交叉验证 R² 最优者持久化到 app/ml/model.pkl,供 Web 端实时预测。

数据变了(比如又抓了一批)就重跑一次,模型会用最新数据重训。
"""
from app.ml.predict import train


def main():
    print("[train] 开始训练薪资预测模型...")
    rep = train()
    print(f"[train] 样本 {rep['n_samples']} 条,最优模型:{rep['best_model']}")
    print("[train] 模型对比:")
    print(f"    {'模型':8s}  {'CV-R2':>7s}  {'测试R2':>7s}  {'MAE(K)':>7s}")
    for s in rep["scores"]:
        print(f"    {s['model']:8s}  {s['cv_r2']:>7.3f}  "
              f"{s['test_r2']:>7.3f}  {s['test_mae']:>7.2f}")
    print(f"[train] 模型已保存,Web 端 /api/predict 即可调用。")


if __name__ == "__main__":
    main()
