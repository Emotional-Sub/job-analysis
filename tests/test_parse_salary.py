"""
parse_salary 的单元测试。

薪资解析是"数据清洗"环节最核心、最易出错的一步(月/年/日三种计薪周期、
K/千/万混合单位、·N薪 折算),一旦解析错会直接污染统计与预测模型。
这些用例把 docstring 里承诺的行为固化下来,改动 parse_salary 后跑一遍即可回归。

运行:
    venv/Scripts/python.exe -m pytest tests/test_parse_salary.py -v
"""
import pytest

from app.spider.utils import parse_salary


class TestMonthly:
    """月薪:默认周期,单位 K/千/万,可混合。"""

    def test_k_range(self):
        assert parse_salary("15-25K") == (15.0, 25.0, 20.0)

    def test_qian_wan_mixed(self):
        # 混合单位:低位"千"、高位"万",各自按自己单位换算
        assert parse_salary("8千-1.2万") == (8.0, 12.0, 10.0)

    def test_wan_range_trailing_unit(self):
        # "1.5-3万":1.5 后无单位,靠串里出现的"万"补齐
        assert parse_salary("1.5-3万") == (15.0, 30.0, 22.5)

    def test_thirteen_months(self):
        # ·13薪:年终多发,平摊回等效月薪(×13/12)
        lo, hi, avg = parse_salary("15-25K·13薪")
        assert lo == pytest.approx(16.25)
        assert hi == pytest.approx(27.08)
        assert avg == pytest.approx(21.66)


class TestYearly:
    """年薪:带 /年 后缀,总额需 ÷12 折算成月薪。"""

    def test_wan_per_year(self):
        assert parse_salary("30-60万/年") == (25.0, 50.0, 37.5)


class TestDaily:
    """日薪:带 /天 后缀,元/天 ×21.75 计薪日 ÷1000 折算成千元/月。"""

    def test_yuan_per_day(self):
        # 800 × 21.75 / 1000 = 17.4,单值 lo==hi
        assert parse_salary("800元/天") == (17.4, 17.4, 17.4)


class TestSingleValueAndOpenEnded:
    """单值 / "以上" 开区间。"""

    def test_k_or_above(self):
        # "20K以上":hi 置空,avg 取该值
        assert parse_salary("20K以上") == (20.0, None, 20.0)


class TestEmptyAndNonNumeric:
    """无法解析的输入应安全返回三个 None,而非报错。"""

    @pytest.mark.parametrize("text", ["面议", None, "", "   ", "薪资电议"])
    def test_returns_all_none(self, text):
        assert parse_salary(text) == (None, None, None)
