"""
断点续抓:记录已抓完的「城市×关键词」组合,被封/重启后跳过已完成的,支持分批抓。

为什么需要
----------
慢速抓一轮(20 城 × 4 关键词 = 80 组)要几个小时,中途极易被反爬拦断。
没有断点的话,重启就得从头再来,已抓的白等。有了断点:
  - 每抓完一组就落盘记一笔
  - 重启时读回记录,已完成的组合直接跳过
  - 支持"每次只抓几组"的分批策略(比连抓 6 小时更不容易被封)

设计取舍
--------
- 每站点一个文件 .checkpoint_{site}.json,互不干扰(51job 和猎聘进度独立)。
- 只在**整组抓完**后才记录。若某组抓到一半硬崩,该组不会被标记,
  下次重跑会重抓这一组 —— 宁可重抓一组(去重会挡住重复入库),也不漏抓。
- 文件是纯进度缓存,不该进 git(.gitignore 已加 .checkpoint_*.json),
  删掉它等于"从头再抓"。

用法
----
    cp = Checkpoint("liepin")
    if cp.done(city, kw):      # 已抓过就跳过
        continue
    ... 抓这一组 ...
    cp.mark(city, kw)          # 抓完落盘

    cp.reset()                 # 想重新全量抓时清空进度
"""
import json
from pathlib import Path

# 项目根目录(app/spider/checkpoint.py 往上两级)
_BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _key(city: str, keyword: str) -> str:
    """把 (城市, 关键词) 拼成唯一字符串键,用 | 分隔(城市/关键词都不含 |)。"""
    return f"{city.strip()}|{keyword.strip()}"


class Checkpoint:
    """单个站点的抓取进度:哪些「城市×关键词」组合已经抓完。"""

    def __init__(self, site: str) -> None:
        self.site = site
        self.path = _BASE_DIR / f".checkpoint_{site}.json"
        self._done = self._load()

    def _load(self) -> set:
        """从磁盘读回已完成组合;文件不存在或损坏都当作空进度(从头抓)。"""
        if not self.path.exists():
            return set()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            # 文件坏了不该让整个抓取崩,当空进度处理即可
            return set()

    def _save(self) -> None:
        """把当前进度落盘。每抓完一组调一次,崩了也不丢已记录的进度。"""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(sorted(self._done), f, ensure_ascii=False, indent=2)
        except Exception:
            # 落盘失败不致命:大不了下次重抓这一组(去重会兜底)
            pass

    def done(self, city: str, keyword: str) -> bool:
        """该「城市×关键词」组合是否已抓完。"""
        return _key(city, keyword) in self._done

    def mark(self, city: str, keyword: str) -> None:
        """标记一组已抓完并立即落盘。"""
        self._done.add(_key(city, keyword))
        self._save()

    def reset(self) -> None:
        """清空进度(重新全量抓时用):删文件 + 清内存。"""
        self._done.clear()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def remaining(self, cities, keywords) -> int:
        """还剩多少组没抓(给日志用,让你知道进度)。"""
        total = 0
        for c in cities:
            for k in keywords:
                if not self.done(c, k):
                    total += 1
        return total
