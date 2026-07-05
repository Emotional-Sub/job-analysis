"""
Flask 应用:招聘数据可视化网站。

架构(前后端通过 JSON 接口交互,论文里对应"接口设计"):
  - 页面路由 /            返回 HTML 页面(前端框架)
  - 数据接口 /api/xxx     返回 JSON,前端 fetch 后喂给 ECharts

启动:
  venv/Scripts/python.exe run_web.py
然后浏览器打开 http://localhost:5000
"""
from flask import Flask, render_template, jsonify, request

from app.web import stats
from app.ml import predict as ml_predict


def create_app() -> Flask:
    app = Flask(__name__)

    # ---------------- 页面 ----------------
    @app.route("/")
    def index():
        # 概览数据直接在服务端渲染进页面,图表数据由前端异步拉取
        overview = stats.get_overview()
        return render_template("index.html", overview=overview)

    # ---------------- 数据接口(返回 JSON) ----------------
    @app.route("/api/overview")
    def api_overview():
        return jsonify(stats.get_overview())

    @app.route("/api/salary_by_keyword")
    def api_salary_by_keyword():
        return jsonify(stats.salary_by_keyword())

    @app.route("/api/jobs_by_city")
    def api_jobs_by_city():
        return jsonify(stats.jobs_by_city())

    @app.route("/api/salary_by_city")
    def api_salary_by_city():
        return jsonify(stats.salary_by_city())

    @app.route("/api/education")
    def api_education():
        return jsonify(stats.education_distribution())

    @app.route("/api/experience")
    def api_experience():
        return jsonify(stats.experience_distribution())

    @app.route("/api/skills")
    def api_skills():
        return jsonify(stats.top_skills())

    @app.route("/api/salary_by_skill")
    def api_salary_by_skill():
        return jsonify(stats.salary_by_skill())

    @app.route("/api/jobs_by_source")
    def api_jobs_by_source():
        return jsonify(stats.jobs_by_source())

    # ---------------- 多源对比接口 ----------------
    @app.route("/api/salary_by_source")
    def api_salary_by_source():
        return jsonify(stats.salary_by_source())

    @app.route("/api/education_by_source")
    def api_education_by_source():
        return jsonify(stats.education_by_source())

    @app.route("/api/salary_by_source_keyword")
    def api_salary_by_source_keyword():
        return jsonify(stats.salary_by_source_keyword())

    # ---------------- 地图接口 ----------------
    @app.route("/api/city_geo")
    def api_city_geo():
        return jsonify(stats.city_geo_stats())

    # ---------------- 薪资预测接口 ----------------
    @app.route("/api/model_scores")
    def api_model_scores():
        """返回训练报告:三模型评分对比 + 各特征可选值(填充前端下拉框)。
        未训练时返回 trained=False,前端据此提示先跑 train_model.py。"""
        report = ml_predict.get_report()
        if not report:
            return jsonify({"trained": False})
        return jsonify({"trained": True, **report})

    @app.route("/api/predict", methods=["POST"])
    def api_predict():
        """接收 {city, education, experience, keyword},返回预测月薪(千元)。"""
        data = request.get_json(silent=True) or {}
        pred = ml_predict.predict(
            city=data.get("city"),
            education=data.get("education"),
            experience=data.get("experience"),
            keyword=data.get("keyword"),
        )
        if pred is None:
            return jsonify({"ok": False, "msg": "模型未训练,请先运行 train_model.py"})
        return jsonify({"ok": True, "salary": pred})

    return app
