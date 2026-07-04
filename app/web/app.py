"""
Flask 应用:招聘数据可视化网站。

架构(前后端通过 JSON 接口交互,论文里对应"接口设计"):
  - 页面路由 /            返回 HTML 页面(前端框架)
  - 数据接口 /api/xxx     返回 JSON,前端 fetch 后喂给 ECharts

启动:
  venv/Scripts/python.exe run_web.py
然后浏览器打开 http://localhost:5000
"""
from flask import Flask, render_template, jsonify

from app.web import stats


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

    return app
