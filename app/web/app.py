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

    # ---------------- 相关性分析接口 ----------------
    @app.route("/api/salary_correlation")
    def api_salary_correlation():
        return jsonify(stats.salary_factor_correlation())

    # ---------------- 薪资分布接口 ----------------
    @app.route("/api/salary_histogram")
    def api_salary_histogram():
        return jsonify(stats.salary_histogram())

    # ---------------- 数据导出(CSV 下载) ----------------
    @app.route("/api/export.csv")
    def api_export_csv():
        """把 job 表导出成 CSV 供下载。用 utf-8-sig(带 BOM),
        Excel 打开中文不乱码。"""
        import csv
        import io

        from app.db.session import get_session
        from app.db.models import Job

        session = get_session()
        try:
            jobs = session.query(Job).all()
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                "来源", "职位关键词", "岗位名称", "公司", "城市",
                "学历", "经验", "薪资原文",
                "最低月薪(K)", "最高月薪(K)", "平均月薪(K)", "技能标签",
            ])
            for j in jobs:
                writer.writerow([
                    j.source, j.keyword, j.title, j.company, j.city,
                    j.education, j.experience, j.salary_text,
                    j.salary_min, j.salary_max, j.salary_avg, j.tags,
                ])
        finally:
            session.close()

        from flask import Response
        csv_bytes = buf.getvalue().encode("utf-8-sig")
        return Response(
            csv_bytes,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=jobs_export.csv"
            },
        )

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
        report = ml_predict.get_report()
        if not report:
            return jsonify({"ok": False, "msg": "模型未训练,请先运行 train_model.py"})

        data = request.get_json(silent=True) or {}
        fields = ("city", "education", "experience", "keyword")
        opts = report.get("feature_options", {})

        # 输入校验:四个字段必须都是非空字符串,且取值在训练时见过的可选集合内。
        # 不校验会有两个问题:①空 body 全 None 也能返回一个"看起来合理"的假预测;
        # ②传入 list/dict 等类型让 OneHotEncoder 抛异常变成 500。
        for f in fields:
            v = data.get(f)
            if not isinstance(v, str) or not v.strip():
                return jsonify({"ok": False, "msg": f"字段 {f} 缺失或格式非法(需非空字符串)"}), 400
            allowed = opts.get(f)
            if allowed and v not in allowed:
                return jsonify({"ok": False, "msg": f"字段 {f} 的值 '{v}' 不在可选范围内"}), 400

        try:
            pred = ml_predict.predict(
                city=data["city"], education=data["education"],
                experience=data["experience"], keyword=data["keyword"],
            )
        except Exception:
            # 兜底:任何预测期异常都返回干净的 400,而不是泄露堆栈的 500
            return jsonify({"ok": False, "msg": "预测失败,请检查输入"}), 400

        if pred is None:
            return jsonify({"ok": False, "msg": "模型未训练,请先运行 train_model.py"})
        return jsonify({"ok": True, "salary": pred})

    return app
