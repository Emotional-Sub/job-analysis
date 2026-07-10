"""
Web 网站启动入口。

用法:
    venv/Scripts/python.exe run_web.py
然后浏览器打开 http://localhost:5000

说明:
- 依赖数据库里已有数据。若还没跑过采集,先执行:
      venv/Scripts/python.exe run_spider.py --demo
  往库里灌入样例数据,页面才有图可看。
- 本服务无鉴权,所有接口(含 /api/export.csv 全库导出)对能访问端口的人开放。
  故默认只绑 127.0.0.1 仅本机可访问。⚠️ 若改 0.0.0.0 供局域网访问,整个数据库
  会对同网段暴露,务必先加访问控制(如反向代理加 Basic Auth / 令牌)。
"""
from app.web.app import create_app

app = create_app()

if __name__ == "__main__":
    # host=127.0.0.1 仅本机访问;改成 0.0.0.0 前请先看上面 docstring 的安全提示。
    # debug=False:关闭自动重载,避免改项目文件时 reloader 反复分裂出多进程占端口
    app.run(host="127.0.0.1", port=5000, debug=False)
