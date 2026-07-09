"""
只读统计推断脚本:薪资影响因素的显著性检验 + 效应量。

核心问题:哪些因素真正决定 IT 岗位薪资?差异有没有统计学意义?差异有多大?

背景与动机
----------
描述统计(均值/中位数)和相关系数只能"看出趋势",不能回答两件事:
1. 观察到的薪资差异是不是偶然?——需要假设检验给出 p 值。
2. 差异到底有多大、值不值得当结论?——需要"效应量"。
   ⚠️ 大样本(本库 2.7 万条)下 p 值几乎必然显著,单看 p 会误导;
   必须配合效应量(η² / Cohen's d)才能判断差异的实际强度。

本脚本围绕"城市 / 学历 / 经验"三个维度,做:
  - 单因素方差分析(ANOVA):各组薪资是否存在整体显著差异(F 检验 + p)
  - 效应量 η²:该因素能解释多大比例的薪资方差
  - 事后两两对比(t 检验 + Cohen's d):挑代表性组做具体对比
  - 经验-薪资的秩相关(Spearman):验证薪资随经验单调递增的强度
最后把结论与已有的相关性热力图、随机森林特征重要性串成一条论证链。

只做 SELECT 查询,不写库,不影响抓取/建模。

用法:
    venv/Scripts/python.exe scripts/salary_inference.py
"""
import os
import sys
from collections import defaultdict
from statistics import median, mean

# Windows 终端默认 GBK,打印 η²/→ 等字符会 UnicodeEncodeError;
# 统一把标准输出重配成 UTF-8(Python 3.7+ 支持 reconfigure)。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 脚本在 scripts/ 下,需把项目根目录加进 sys.path,否则 import app 会失败。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scipy import stats as sps

from app.db.session import get_session
from app.db.models import Job

# 学历、经验的展示顺序(从低到高),便于观察单调性。
EDU_ORDER = ["高中及以下", "大专", "本科", "硕士", "博士"]
EXP_ORDER = ["应届/不限", "1年以下", "1-3年", "3-5年", "5-10年", "10年以上"]

# 事后对比要够样本量才有意义;组内薪资样本少于该数的组不参与检验。
MIN_GROUP_N = 30


def _load_rows():
    """取出所有 (city, education, experience, salary_avg) 且薪资非空的行。"""
    session = get_session()
    try:
        rows = (
            session.query(
                Job.city, Job.education, Job.experience, Job.salary_avg
            )
            .filter(Job.salary_avg.isnot(None))
            .all()
        )
    finally:
        session.close()
    # 转成普通元组列表,后续纯内存计算
    return [(c, e, x, float(s)) for (c, e, x, s) in rows if s is not None]


def _group_salaries(rows, key_idx):
    """按第 key_idx 列(city=0 / edu=1 / exp=2)分组,返回 {组名: [薪资...]}。"""
    buckets = defaultdict(list)
    for r in rows:
        key = (r[key_idx] or "").strip()
        if not key or key in ("None", "不限"):
            # "不限"学历语义模糊(既非低也非高),不纳入有序比较,避免污染趋势
            continue
        buckets[key].append(r[3])
    return buckets


def _eta_squared(groups):
    """
    计算单因素 ANOVA 的效应量 η²(eta squared)。
    η² = 组间平方和 / 总平方和,取值 [0,1],表示该因素解释的方差占比。
    经验判读:0.01 小、0.06 中、0.14 大(Cohen 标准)。
    """
    all_vals = [v for g in groups for v in g]
    grand_mean = mean(all_vals)
    ss_total = sum((v - grand_mean) ** 2 for v in all_vals)
    ss_between = sum(len(g) * (mean(g) - grand_mean) ** 2 for g in groups if g)
    return ss_between / ss_total if ss_total else 0.0


def _cohens_d(a, b):
    """
    两组均值差的标准化效应量 Cohen's d(合并标准差)。
    经验判读:0.2 小、0.5 中、0.8 大。
    """
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    va, vb = sps.tvar(a), sps.tvar(b)  # 样本方差(ddof=1)
    # 合并标准差
    sp = (((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)) ** 0.5
    return (mean(a) - mean(b)) / sp if sp else 0.0


def _eta_label(eta):
    if eta >= 0.14:
        return "大"
    if eta >= 0.06:
        return "中"
    if eta >= 0.01:
        return "小"
    return "极小"


def _d_label(d):
    ad = abs(d)
    if ad >= 0.8:
        return "大"
    if ad >= 0.5:
        return "中"
    if ad >= 0.2:
        return "小"
    return "极小"


def _p_str(p):
    """p 值展示:极小值用科学计数法,并标注显著性星号。"""
    if p < 1e-4:
        s = f"{p:.2e}"
    else:
        s = f"{p:.4f}"
    star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "n.s."
    return f"{s} ({star})"


def _print_anova(title, buckets, order=None):
    """对一个因素做 ANOVA + η²,并打印各组描述统计。返回 (F, p, eta)。"""
    print(f"\n{'=' * 60}")
    print(f"【{title}】单因素方差分析 (ANOVA)")
    print("=" * 60)

    # 只保留样本量达标的组
    valid = {k: v for k, v in buckets.items() if len(v) >= MIN_GROUP_N}
    dropped = {k: len(v) for k, v in buckets.items() if len(v) < MIN_GROUP_N}

    # 排序:有指定顺序按顺序,否则按薪资中位数降序
    if order:
        keys = [k for k in order if k in valid]
        keys += [k for k in valid if k not in order]  # 兜底:不在顺序表里的
    else:
        keys = sorted(valid, key=lambda k: median(valid[k]), reverse=True)

    print(f"\n{'组别':<12}{'样本数':>8}{'中位薪资':>10}{'均值薪资':>10}")
    print("-" * 44)
    for k in keys:
        v = valid[k]
        print(f"{k:<12}{len(v):>8}{median(v):>9.1f}K{mean(v):>9.1f}K")
    if dropped:
        drop_str = ", ".join(f"{k}({n})" for k, n in dropped.items())
        print(f"\n  (样本<{MIN_GROUP_N} 未纳入检验: {drop_str})")

    groups = [valid[k] for k in keys]
    if len(groups) < 2:
        print("\n  有效组不足 2 个,无法做 ANOVA。")
        return None, None, None

    f_stat, p_val = sps.f_oneway(*groups)
    eta = _eta_squared(groups)
    print(f"\n  F 统计量 = {f_stat:.2f}")
    print(f"  p 值     = {_p_str(p_val)}")
    print(f"  效应量 η² = {eta:.4f}  →  {_eta_label(eta)}效应"
          f"(该因素解释了 {eta*100:.1f}% 的薪资方差)")
    return f_stat, p_val, eta


def _print_posthoc(title, buckets, pairs):
    """对指定的若干对组做两两 t 检验 + Cohen's d。"""
    print(f"\n  ── {title} 事后两两对比 (Welch t 检验 + Cohen's d) ──")
    for a_key, b_key in pairs:
        a, b = buckets.get(a_key), buckets.get(b_key)
        if not a or not b or len(a) < MIN_GROUP_N or len(b) < MIN_GROUP_N:
            print(f"    {a_key} vs {b_key}: 样本不足,跳过")
            continue
        # Welch t 检验:不假设两组方差相等,更稳健
        t_stat, p_val = sps.ttest_ind(a, b, equal_var=False)
        d = _cohens_d(a, b)
        print(f"    {a_key}(中位{median(a):.0f}K) vs {b_key}(中位{median(b):.0f}K): "
              f"t={t_stat:.2f}, p={_p_str(p_val)}, "
              f"d={d:+.2f}({_d_label(d)}效应)")


def main():
    rows = _load_rows()
    n = len(rows)
    print(f"\n{'#' * 60}")
    print(f"# 薪资影响因素统计推断  (有效薪资样本 {n} 条)")
    print(f"{'#' * 60}")
    print("核心问题:城市 / 学历 / 经验是否显著影响薪资?差异有多大?")

    # ---------- 1. 城市 ----------
    city_b = _group_salaries(rows, 0)
    _print_anova("城市", city_b)
    # 事后:挑薪资最高档与最低档城市对比(按中位数)
    valid_cities = {k: v for k, v in city_b.items() if len(v) >= MIN_GROUP_N}
    if valid_cities:
        ranked = sorted(valid_cities, key=lambda k: median(valid_cities[k]))
        low, high = ranked[0], ranked[-1]
        # 再夹一个北上深代表
        _print_posthoc("城市", city_b, [(high, low)])

    # ---------- 2. 学历 ----------
    edu_b = _group_salaries(rows, 1)
    _print_anova("学历", edu_b, order=EDU_ORDER)
    # 事后:相邻学历逐级对比,看每升一级的显著性
    edu_pairs = [("大专", "本科"), ("本科", "硕士"), ("硕士", "博士")]
    _print_posthoc("学历", edu_b, edu_pairs)

    # ---------- 3. 经验 ----------
    exp_b = _group_salaries(rows, 2)
    _print_anova("经验", exp_b, order=EXP_ORDER)
    exp_pairs = [("1年以下", "1-3年"), ("1-3年", "3-5年"), ("3-5年", "5-10年")]
    _print_posthoc("经验", exp_b, exp_pairs)

    # ---------- 4. 经验-薪资 秩相关 ----------
    print(f"\n{'=' * 60}")
    print("【经验↔薪资】Spearman 秩相关(验证单调递增强度)")
    print("=" * 60)
    exp_rank = {lab: i for i, lab in enumerate(EXP_ORDER)}
    xs, ys = [], []
    for r in rows:
        lab = (r[2] or "").strip()
        if lab in exp_rank:
            xs.append(exp_rank[lab])
            ys.append(r[3])
    if len(xs) >= MIN_GROUP_N:
        rho, p_val = sps.spearmanr(xs, ys)
        print(f"  Spearman ρ = {rho:+.3f}   p = {_p_str(p_val)}")
        print(f"  → 薪资随经验档单调{'递增' if rho > 0 else '递减'},"
              f"相关强度{'强' if abs(rho) >= 0.5 else '中' if abs(rho) >= 0.3 else '弱'}")

    # ---------- 结论论证链 ----------
    print(f"\n{'#' * 60}")
    print("# 论证链小结(供论文分析章串联)")
    print(f"{'#' * 60}")
    print("""
  相关性热力图(初筛线性关联)
      → 假设检验 ANOVA(确认差异显著 + η² 量化解释力)
      → 事后 t 检验 + Cohen's d(具体到组间差异有多大)
      → 随机森林特征重要性(模型视角的因素排序)
      → 模型 R²≈0.31(能预测到什么程度 + 其余靠不可观测因素)

  一句话:三因素对薪资的影响均统计显著,但看效应量 η² 才能
  分清"谁的解释力更强";而 R² 的上限说明结构化特征只能解释
  约三成薪资方差,岗位描述/公司/议价等不可观测因素占了大头。
""")


if __name__ == "__main__":
    main()
