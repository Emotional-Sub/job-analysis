"""
Web 网站启动入口。

用法:
    venv/Scripts/python.exe run_web.py
然后浏览器打开 http://localhost:5000

说明:
- 依赖数据库里已有数据。若还没跑过采集,先执行:
      venv/Scripts/python.exe run_spider.py --demo
  往库里灌入样例数据,页面才有图可看。
- debug=True 便于开发时自动重载;正式部署请关掉。
"""
from app.web.app import create_app

app = create_app()

if __name__ == "__main__":
    # host=127.0.0.1 仅本机访问;如需局域网访问改成 0.0.0.0
    # debug=False:关闭自动重载,避免改项目文件时 reloader 反复分裂出多进程占端口
    app.run(host="127.0.0.1", port=5000, debug=False)
